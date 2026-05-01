"""
Academic Analyst Agent — Full Intelligence System v2.0
Analyzes:
  - RSI, MACD, EMA (primary TF daily)
  - Supertrend, ADX, EMA-200, StochRSI, OBV, VWAP
  - 1H + 4H higher-timeframe trend confirmation
  - Price action patterns (engulfing, hammer, doji, etc.)
  - RSI divergence + chart patterns (from indicators_service)
  - Multi-timeframe conflict detection (blocks false signals)
  - Scoring system: 15-point across 5 groups
"""
import asyncio
import json
import sys
import os

import yfinance as yf

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.yfinance_service import YF_SYMBOLS
from services.indicators_service import detect_rsi_divergence, detect_chart_patterns

from .base_agent import BaseAgent
from .memory_manager import MemoryManager


# ── Pure-Python helpers ──────────────────────────────────────────────────────

def _ema(data: list, period: int) -> float:
    if len(data) < period:
        return data[-1] if data else 0.0
    k = 2 / (period + 1)
    val = sum(data[:period]) / period
    for p in data[period:]:
        val = p * k + val * (1 - k)
    return round(val, 6)


def _compute_htf_indicators(candles: list) -> dict:
    """Compute trend direction from higher-TF candles."""
    if not candles or len(candles) < 20:
        return {"trend": "UNKNOWN", "ema_20": None, "ema_50": None}
    closes  = [c["close"] for c in candles]
    ema20   = _ema(closes, 20)
    ema50   = _ema(closes, min(50, len(closes)))
    trend   = "UPTREND" if ema20 > ema50 else "DOWNTREND"
    price   = closes[-1]
    above20 = price > ema20
    above50 = price > ema50
    if above20 and above50 and trend == "UPTREND":
        strength = "STRONG_UP"
    elif not above20 and not above50 and trend == "DOWNTREND":
        strength = "STRONG_DOWN"
    else:
        strength = trend
    return {
        "trend":       strength,
        "ema_20":      round(ema20, 6),
        "ema_50":      round(ema50, 6),
        "price":       round(price, 6),
        "above_ema20": above20,
        "above_ema50": above50,
    }


def _detect_candle_patterns(candles: list) -> list:
    """Detect key price action patterns from the last 3 candles."""
    patterns = []
    if len(candles) < 2:
        return ["Insufficient data for pattern detection"]

    c  = candles[-1]
    p  = candles[-2]

    body_c       = abs(c["close"] - c["open"])
    wick_upper_c = c["high"] - max(c["close"], c["open"])
    wick_lower_c = min(c["close"], c["open"]) - c["low"]
    range_c      = c["high"] - c["low"]
    body_p       = abs(p["close"] - p["open"])
    is_bull_c    = c["close"] >= c["open"]
    is_bull_p    = p["close"] >= p["open"]

    if range_c > 0 and body_c / range_c < 0.10:
        patterns.append("DOJI — Market indecision, wait for confirmation")

    if body_c > 0 and wick_lower_c > 2 * body_c and wick_upper_c < body_c and is_bull_c:
        patterns.append("HAMMER — Bullish reversal signal (buyers rejected lower prices)")

    if body_c > 0 and wick_upper_c > 2 * body_c and wick_lower_c < body_c and not is_bull_c:
        patterns.append("SHOOTING STAR — Bearish reversal signal (sellers rejected higher prices)")

    if (not is_bull_p and is_bull_c and body_p > 0
            and c["open"] <= p["close"] and c["close"] >= p["open"]
            and body_c > body_p):
        patterns.append("BULLISH ENGULFING — Strong buy signal (bulls overwhelmed bears)")

    if (is_bull_p and not is_bull_c and body_p > 0
            and c["open"] >= p["close"] and c["close"] <= p["open"]
            and body_c > body_p):
        patterns.append("BEARISH ENGULFING — Strong sell signal (bears overwhelmed bulls)")

    if len(candles) >= 3:
        c2 = candles[-3]
        hh = candles[-1]["high"] > candles[-2]["high"] > c2["high"]
        hl = candles[-1]["low"]  > candles[-2]["low"]  > c2["low"]
        lh = candles[-1]["high"] < candles[-2]["high"] < c2["high"]
        ll = candles[-1]["low"]  < candles[-2]["low"]  < c2["low"]
        if hh: patterns.append("HIGHER HIGHS — Bullish structure intact")
        if hl: patterns.append("HIGHER LOWS — Buyers defending each dip")
        if lh: patterns.append("LOWER HIGHS — Sellers capping each rally (bearish)")
        if ll: patterns.append("LOWER LOWS — Sellers in control (bearish)")

    return patterns if patterns else ["No dominant pattern — consolidation / balanced market"]


def _compute_swing_levels(candles: list, lookback: int = 30) -> dict:
    """Find recent swing highs and lows using 2-bar pivot detection."""
    recent = candles[-lookback:] if len(candles) >= lookback else candles
    highs, lows = [], []
    for i in range(1, len(recent) - 1):
        if recent[i]["high"] > recent[i-1]["high"] and recent[i]["high"] > recent[i+1]["high"]:
            highs.append(round(recent[i]["high"], 6))
        if recent[i]["low"] < recent[i-1]["low"] and recent[i]["low"] < recent[i+1]["low"]:
            lows.append(round(recent[i]["low"], 6))
    return {
        "swing_highs": sorted(set(highs), reverse=True)[:3],
        "swing_lows":  sorted(set(lows))[:3],
    }


def _mtf_verdict(ltf_indicators: dict, htf: dict) -> str:
    ltf_trend  = ltf_indicators.get("trend", "")
    htf_trend  = htf.get("trend", "UNKNOWN")
    ltf_macd   = ltf_indicators.get("macd_signal", "")

    ltf_bull = "UP" in ltf_trend.upper() or ltf_macd == "BULLISH"
    ltf_bear = "DOWN" in ltf_trend.upper() or ltf_macd == "BEARISH"
    htf_bull = "UP" in htf_trend.upper()
    htf_bear = "DOWN" in htf_trend.upper()

    if htf_trend == "UNKNOWN":
        return "MTF STATUS: HTF data unavailable — use primary TF signals only."
    if ltf_bull and htf_bear:
        return (
            "*** TREND CONFLICT *** Primary TF signal is BULLISH but HTF trend is BEARISH. "
            "DO NOT issue BUY — high probability of false breakout. "
            "Prefer HOLD or SELL with the higher timeframe."
        )
    if ltf_bear and htf_bull:
        return (
            "*** TREND CONFLICT *** Primary TF signal is BEARISH but HTF trend is BULLISH. "
            "DO NOT issue SELL — high probability of false breakdown. "
            "Prefer HOLD or BUY with the higher timeframe."
        )
    if ltf_bull and htf_bull:
        return (
            "MULTI-TIMEFRAME ALIGNED — BULLISH: Both primary TF and HTF confirm upward bias. "
            "BUY signals carry higher conviction. Increase confidence by 10-15%."
        )
    if ltf_bear and htf_bear:
        return (
            "MULTI-TIMEFRAME ALIGNED — BEARISH: Both primary TF and HTF confirm downward bias. "
            "SELL signals carry higher conviction. Increase confidence by 10-15%."
        )
    return "MTF STATUS: Mixed signals — no dominant alignment. Apply extra caution."


# ── Agent class ──────────────────────────────────────────────────────────────

class AcademicAgent(BaseAgent):
    def __init__(self):
        instruction = (
            "You are the Academic Analyst — a seasoned expert in technical and fundamental analysis. "
            "You have studied the top 50 trading books and apply their principles with discipline.\n\n"

            "TRADING RULES FROM TOP TRADERS:\n"
            "1. NEVER trade against the Daily trend — higher timeframe always wins\n"
            "2. Breakout without 1.5x volume = likely fake — do NOT chase\n"
            "3. Three timeframe confluence = highest probability trades only\n"
            "4. RSI divergence on 1H/4H = strong reversal signal — never ignore it\n"
            "5. Key zone touched 3+ times = support/resistance is weakening\n"
            "6. Wait for candle CLOSE above/below level — not just a wick touch\n"
            "7. Retest of broken level = lower-risk, higher-reward entry point\n\n"

            "SCORING GUIDE — Always include in your analysis:\n"
            "=== SCORE BREAKDOWN ===\n"
            "Trend Group    : X/4  [price>EMA200, Supertrend UP, ADX>25, 1H bullish]\n"
            "Momentum Group : X/3  [RSI>50, StochRSI>50, MACD>0]\n"
            "Volume Group   : X/2  [Volume>1.5x avg, OBV rising]\n"
            "Price Action   : X/3  [Patterns, divergence, structure]\n"
            "Multi-TF       : X/3  [1H, 4H, Daily aligned]\n"
            "Total          : X/15 -> SIGNAL\n\n"
            "Thresholds: >=10=STRONG BUY | >=7=BUY | <=4=SELL | <=2=STRONG SELL | else=HOLD\n\n"

            "CRITICAL RULES:\n"
            "- If a TREND CONFLICT is flagged, you MUST NOT issue a signal against the higher timeframe trend.\n"
            "- For BUY/SELL decisions always suggest Entry, Stop Loss (SL), and Take Profit (TP) levels.\n"
            "- ALWAYS end with: DECISION: BUY / SELL / HOLD\n  CONFIDENCE: X%"
        )
        super().__init__("Academic Analyst", "gemini-2.5-flash", instruction)
        self.principles = self._load_principles()
        self.memory     = MemoryManager("academic_analyst")

    # ── Knowledge base ───────────────────────────────────────────────────────

    def _load_principles(self) -> list:
        try:
            with open("knowledge/master_principles.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _select_relevant_principles(self, indicators: dict) -> str:
        if not self.principles:
            return "Apply all general trading principles."
        rsi_signal  = indicators.get("rsi_signal", "")
        trend       = indicators.get("trend", "")
        macd_signal = indicators.get("macd_signal", "")
        selected = []
        for book in self.principles:
            for principle in book.get("principles", []):
                pl = principle.lower()
                if rsi_signal == "OVERSOLD"   and any(w in pl for w in ["oversold", "support", "buy", "opportunity"]):
                    selected.append(f"[{book['author']}]: {principle}")
                elif rsi_signal == "OVERBOUGHT" and any(w in pl for w in ["overbought", "resistance", "caution", "sell"]):
                    selected.append(f"[{book['author']}]: {principle}")
                elif "UPTREND" in trend        and any(w in pl for w in ["trend", "momentum", "follow"]):
                    selected.append(f"[{book['author']}]: {principle}")
                elif "DOWNTREND" in trend      and any(w in pl for w in ["risk", "loss", "stop", "caution"]):
                    selected.append(f"[{book['author']}]: {principle}")
                elif macd_signal == "BULLISH"  and "momentum" in pl:
                    selected.append(f"[{book['author']}]: {principle}")
        for book in self.principles:
            if any(k in book.get("book", "").lower() for k in ["market wizard", "risk", "new trading"]):
                for p in book.get("principles", [])[:2]:
                    selected.append(f"[{book['author']}]: {p}")
        seen, unique = set(), []
        for p in selected:
            if p not in seen:
                seen.add(p)
                unique.append(p)
        return "\n".join(unique[:8]) if unique else "Apply standard risk management and trend-following principles."

    # ── Candle data fetchers ─────────────────────────────────────────────────

    async def _fetch_tf_candles(self, pair: str, interval: str, period: str = "5d") -> list:
        """Generic yf.download fetcher for any intraday interval."""
        sym = YF_SYMBOLS.get(pair)
        if not sym:
            return []

        def _sync() -> list:
            hist = yf.download(sym, period=period, interval=interval,
                               progress=False, auto_adjust=False)
            if hist is None or hist.empty:
                return []
            hist.columns = [col[0] if isinstance(col, tuple) else col
                            for col in hist.columns]
            candles = []
            for ts, row in hist.iterrows():
                try:
                    o = float(row["Open"])
                    h = float(row["High"])
                    l = float(row["Low"])
                    c = float(row["Close"])
                    if o > 0 and c > 0:
                        candles.append({
                            "time":   int(ts.timestamp()),
                            "open":   o, "high": h, "low": l, "close": c,
                            "volume": int(row.get("Volume", 0) or 0),
                        })
                except Exception:
                    pass
            return candles

        return await asyncio.to_thread(_sync)

    async def _fetch_1h_candles(self, pair: str) -> list:
        return await self._fetch_tf_candles(pair, "1h", "5d")

    async def _fetch_4h_candles(self, pair: str) -> list:
        return await self._fetch_tf_candles(pair, "4h", "60d")

    # ── Scoring system ───────────────────────────────────────────────────────

    def _compute_score(self, indicators: dict, htf_1h: dict,
                       htf_4h: dict, patterns: list) -> dict:
        """
        15-point scoring across 5 groups.
        Returns total, signal, and per-group breakdown.
        """
        pat_text = " ".join(patterns).upper()
        vol_ratio = indicators.get("volume_analysis", {}).get("ratio", 0) or 0

        # ── TREND GROUP (4 pts) ─────────────────────────────────────────────
        t = 0
        if indicators.get("ema_200", {}).get("price_above"):
            t += 1
        if indicators.get("supertrend", {}).get("direction") == "UP":
            t += 1
        if indicators.get("adx", {}).get("trending"):          # ADX > 25
            t += 1
        if "UP" in htf_1h.get("trend", "").upper():
            t += 1

        # ── MOMENTUM GROUP (3 pts) ──────────────────────────────────────────
        m = 0
        if (indicators.get("rsi") or 0) > 50:
            m += 1
        if indicators.get("stoch_rsi", {}).get("bullish"):
            m += 1
        if (indicators.get("macd") or 0) > 0:
            m += 1

        # ── VOLUME GROUP (2 pts) ────────────────────────────────────────────
        v = 0
        if vol_ratio >= 1.5:
            v += 1
        if indicators.get("obv", {}).get("rising"):
            v += 1

        # ── PRICE ACTION GROUP (3 pts) ──────────────────────────────────────
        pa = 0
        bullish_breakout = (
            any(p in pat_text for p in ["ASCENDING TRIANGLE", "FLAG AND POLE", "DOUBLE BOTTOM"])
            and vol_ratio >= 1.5
        )
        if bullish_breakout:
            pa = 2
        elif any(p in pat_text for p in [
            "HAMMER", "BULLISH ENGULFING", "HIGHER HIGH", "HIGHER LOW",
            "BULLISH_DIVERGENCE", "DOUBLE BOTTOM"
        ]):
            pa = 1
        elif any(p in pat_text for p in [
            "SHOOTING STAR", "BEARISH ENGULFING", "LOWER HIGH", "LOWER LOW",
            "BEARISH_DIVERGENCE", "DOUBLE TOP", "DESCENDING CHANNEL"
        ]):
            pa = -1
        pa = max(-1, min(pa, 3))

        # ── MULTI-TF GROUP (3 pts) ──────────────────────────────────────────
        tf = 0
        if "UP" in htf_1h.get("trend", "").upper():
            tf += 1
        if "UP" in htf_4h.get("trend", "").upper():
            tf += 1
        if "UPTREND" in indicators.get("trend", "").upper():
            tf += 1

        total = t + m + v + pa + tf
        if total >= 10:
            signal = "STRONG BUY"
        elif total >= 7:
            signal = "BUY"
        elif total <= 2:
            signal = "STRONG SELL"
        elif total <= 4:
            signal = "SELL"
        else:
            signal = "HOLD"

        return {
            "total": total,
            "max":   15,
            "signal": signal,
            "breakdown": {
                "trend":        {"pts": t,  "max": 4},
                "momentum":     {"pts": m,  "max": 3},
                "volume":       {"pts": v,  "max": 2},
                "price_action": {"pts": pa, "max": 3},
                "multi_tf":     {"pts": tf, "max": 3},
            },
        }

    # ── Main analysis ────────────────────────────────────────────────────────

    async def analyze(self, market_data: dict, indicators: dict = None,
                      pair: str = "EUR/USD") -> str:
        indicators = indicators or {}

        # ── 1. Fetch 1H and 4H candles for HTF confirmation ──────────────────
        htf_1h = {"trend": "UNKNOWN"}
        htf_4h = {"trend": "UNKNOWN"}
        h1_candles: list = []
        h4_candles: list = []

        try:
            h1_candles = await self._fetch_1h_candles(pair)
            if h1_candles and len(h1_candles) >= 20:
                htf_1h = _compute_htf_indicators(h1_candles)
        except Exception as e:
            print(f"[AcademicAgent] 1H fetch failed for {pair}: {e}")

        try:
            h4_candles = await self._fetch_4h_candles(pair)
            if h4_candles and len(h4_candles) >= 20:
                htf_4h = _compute_htf_indicators(h4_candles)
        except Exception as e:
            print(f"[AcademicAgent] 4H fetch failed for {pair}: {e}")

        # ── 2. Candle patterns (basic) ────────────────────────────────────────
        basic_patterns = _detect_candle_patterns(h1_candles) if h1_candles else [
            "No 1H candles available"
        ]

        # ── 3. Advanced patterns from indicators_service ──────────────────────
        rsi_div      = None
        chart_pats   = []
        try:
            if h1_candles and len(h1_candles) >= 30:
                rsi_div    = detect_rsi_divergence(h1_candles)
                chart_pats = detect_chart_patterns(h1_candles)
        except Exception as e:
            print(f"[AcademicAgent] Advanced patterns failed: {e}")

        all_patterns = list(basic_patterns)
        if rsi_div:
            all_patterns.append(f"RSI DIVERGENCE: {rsi_div} — Strong reversal signal")
        all_patterns.extend(chart_pats)

        # ── 4. Swing levels ───────────────────────────────────────────────────
        swing = (_compute_swing_levels(h1_candles)
                 if h1_candles else {"swing_highs": [], "swing_lows": []})

        # ── 5. MTF verdict (uses primary TF indicators vs 1H) ─────────────────
        mtf_verdict = _mtf_verdict(indicators, htf_1h)

        # ── 6. Scoring ────────────────────────────────────────────────────────
        score = self._compute_score(indicators, htf_1h, htf_4h, all_patterns)
        bd    = score["breakdown"]
        score_block = (
            f"=== SCORE BREAKDOWN ===\n"
            f"Trend Group    : {bd['trend']['pts']}/{bd['trend']['max']}"
            f"  [price>EMA200, Supertrend UP, ADX>25, 1H bullish]\n"
            f"Momentum Group : {bd['momentum']['pts']}/{bd['momentum']['max']}"
            f"  [RSI>50, StochRSI>50, MACD>0]\n"
            f"Volume Group   : {bd['volume']['pts']}/{bd['volume']['max']}"
            f"  [Volume>1.5x avg, OBV rising]\n"
            f"Price Action   : {bd['price_action']['pts']}/{bd['price_action']['max']}"
            f"  [Patterns, divergence, structure]\n"
            f"Multi-TF       : {bd['multi_tf']['pts']}/{bd['multi_tf']['max']}"
            f"  [1H, 4H, Daily aligned]\n"
            f"Total          : {score['total']}/15 -> {score['signal']}"
        )

        # ── 7. Build prompt ───────────────────────────────────────────────────
        principles_text = self._select_relevant_principles(indicators)
        past_summary    = self.memory.get_summary(pair=pair, n=5)
        bias            = self.memory.get_bias(pair=pair)
        streak          = self.memory.get_streak(pair=pair)
        total_decisions = self.memory.count()

        sh_str = ", ".join(str(v) for v in swing["swing_highs"]) or "None detected"
        sl_str = ", ".join(str(v) for v in swing["swing_lows"])  or "None detected"

        # Advanced indicator snapshot
        st   = indicators.get("supertrend", {})
        adx  = indicators.get("adx", {})
        e200 = indicators.get("ema_200", {})
        srsi = indicators.get("stoch_rsi", {})
        obv  = indicators.get("obv", {})
        vwap = indicators.get("vwap", {})
        vol  = indicators.get("volume_analysis", {})

        prompt = f"""
ACADEMIC ANALYST — FULL INTELLIGENCE ANALYSIS v2.0
Pair: {pair} | Past Decisions: {total_decisions}
========================================

{score_block}

========================================
PRIMARY TF INDICATORS (Daily):
  Price         : {indicators.get('current_price', market_data.get('price', 'N/A'))}
  EMA 20/50     : {indicators.get('ema_20','N/A')} / {indicators.get('ema_50','N/A')} ({indicators.get('trend','N/A')})
  EMA 200       : {e200.get('value','N/A')} — price {e200.get('signal','N/A')}
  RSI (14)      : {indicators.get('rsi','N/A')} → {indicators.get('rsi_signal','N/A')}
  MACD          : {indicators.get('macd','N/A')} → {indicators.get('macd_signal','N/A')}
  BB %B / ATR   : {indicators.get('bb_pct_b','N/A')} / {indicators.get('atr','N/A')}
  Supertrend    : {st.get('direction','N/A')} @ {st.get('value','N/A')} ({st.get('signal','N/A')})
  ADX           : {adx.get('adx','N/A')} ({adx.get('strength','N/A')}) | DI+={adx.get('di_plus','N/A')} DI-={adx.get('di_minus','N/A')}
  StochRSI K/D  : {srsi.get('k','N/A')} / {srsi.get('d','N/A')} → {srsi.get('signal','N/A')}
  OBV Direction : {obv.get('direction','N/A')}
  VWAP          : {vwap.get('value','N/A')} — price {vwap.get('signal','N/A')}
  Volume Ratio  : {vol.get('ratio','N/A')}x avg → {vol.get('signal','N/A')}

HIGHER TIMEFRAMES:
  1H Trend      : {htf_1h.get('trend','UNKNOWN')} | EMA20={htf_1h.get('ema_20','N/A')} EMA50={htf_1h.get('ema_50','N/A')}
  4H Trend      : {htf_4h.get('trend','UNKNOWN')} | EMA20={htf_4h.get('ema_20','N/A')} EMA50={htf_4h.get('ema_50','N/A')}

MULTI-TIMEFRAME VERDICT:
  {mtf_verdict}

PATTERNS DETECTED (1H candles):
{chr(10).join('  - ' + p for p in all_patterns)}
  Swing Highs (resistance): {sh_str}
  Swing Lows  (support)   : {sl_str}

MEMORY — Past Decisions for {pair}:
{past_summary}
  Recent bias    : {bias}
  Decision streak: {streak}

TRADING BOOK PRINCIPLES:
{principles_text}

========================================
YOUR TASK:

1. CONFIRM OR CHALLENGE the pre-computed score above.
   - Are the points assigned correctly given the full picture?
   - Any indicators overriding the score (e.g., extreme divergence, major news)?

2. MULTI-TIMEFRAME CHECK:
   - 1H and 4H both confirm / conflict with Daily?
   - If TREND CONFLICT is present, you MUST default to HOLD or align with HTF.

3. PRICE ACTION:
   - What do the detected patterns say?
   - Are we near a key swing high (resistance) or swing low (support)?

4. RISK MANAGEMENT:
   - Suggest Entry, SL (use swing levels), TP, and R:R ratio.
   - Volume confirmation present? Breakout genuine?

5. LEARNING FROM MEMORY:
   - What have past decisions taught you about {pair}?

=== SCORE BREAKDOWN ===
[Restate the breakdown from above — confirm or adjust points]

=== PATTERNS DETECTED ===
[List top 3 most relevant patterns]

=== AGENT DECISION ===
DECISION: BUY / SELL / HOLD
CONFIDENCE: X%
Entry: X.XXXX | SL: X.XXXX | TP: X.XXXX
========================================
"""
        response = await self.get_response(prompt)

        # ── Parse + store decision ─────────────────────────────────────────────
        decision   = "HOLD"
        confidence = 50
        ru = response.upper()
        if "DECISION: BUY"       in ru: decision = "BUY"
        elif "DECISION: SELL"    in ru: decision = "SELL"
        elif "STRONG BUY"        in ru and "DECISION" not in ru: decision = "BUY"
        elif "STRONG SELL"       in ru and "DECISION" not in ru: decision = "SELL"
        try:
            if "CONFIDENCE:" in ru:
                part   = ru.split("CONFIDENCE:")[1][:20]
                digits = "".join(c for c in part if c.isdigit())[:3]
                if digits:
                    confidence = int(digits)
        except Exception:
            pass

        self.memory.save_decision(
            pair=pair,
            decision=decision,
            reasoning=response[:300],
            price=indicators.get("current_price", market_data.get("price", 0)),
            indicators=indicators,
            confidence=confidence,
        )

        return response
