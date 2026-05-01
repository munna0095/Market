"""
Market Data Agent — Dedicated data fetcher for all market data.
Uses Finnhub as primary source, Alpha Vantage as fallback.
Handles: real-time prices, OHLCV candles, forex news, technical indicators.
Maintains a cache so the system NEVER goes blank during rate limits.
"""
import sys
import os
import asyncio

# Allow importing from backend/services when running from backend/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.finnhub_service import FinnhubService, CRYPTO_PAIRS
from services.alpha_vantage import AlphaVantageService
from services.yfinance_service import YFinanceService
from services.indicators_service import compute_all as _compute_advanced_indicators
from agents.memory_manager import MemoryManager

FOREX_PAIRS = ["EUR/USD", "USD/JPY", "GBP/USD", "USD/CHF"]


class MarketDataAgent:
    """
    The Market Data Agent is NOT an AI agent — it is a smart data manager.
    It is the single source of truth for all price and news data in the system.

    Data priority:
      Prices  → YFinance (primary) → Finnhub (crypto) → Alpha Vantage → cache
      Candles → YFinance (primary, all pairs) → Finnhub (crypto fallback) → cache
    """
    name = "Market Data Agent"

    def __init__(self):
        self.finnhub = FinnhubService()
        self.av      = AlphaVantageService()
        self.yf      = YFinanceService()
        self.memory  = MemoryManager("market_data_agent")

        # Caches — populated as data arrives
        self._price_cache: dict = {}        # {pair: price_dict}
        self._candle_cache: dict = {}       # {"EUR/USD_D": [candles]}
        self._news_cache: list = []         # Latest forex news headlines
        self._indicators_cache: dict = {}   # {pair: indicators_dict}

    # ─── Prices ──────────────────────────────────────────────────────────────

    async def get_realtime_price(self, pair: str) -> dict | None:
        """
        Priority:
          1. Yahoo Finance (yfinance) — free, real-time, all pairs
          2. Finnhub — crypto fallback
          3. Cache — last known value
        """
        # ── 1. Yahoo Finance (primary for all pairs) ──────────────────────────
        try:
            data = await self.yf.get_price(pair)
            if data and data.get("price", 0) > 0:
                # Carry forward change_pct relative to our cached prev price
                prev = self._price_cache.get(pair, {}).get("price", 0)
                if prev and prev != data["price"]:
                    data["change_pct"] = round(((data["price"] - prev) / prev) * 100, 4)
                self._price_cache[pair] = data
                return data
        except Exception as e:
            print(f"[MarketDataAgent] YFinance price failed for {pair}: {e}")

        # ── 2. Finnhub (crypto only) ──────────────────────────────────────────
        if pair in CRYPTO_PAIRS:
            try:
                data = await self.finnhub.get_crypto_quote(pair)
                if data and data.get("price", 0) > 0:
                    self._price_cache[pair] = data
                    return data
            except Exception as e:
                print(f"[MarketDataAgent] Finnhub crypto price failed for {pair}: {e}")

        # ── 3. Cache fallback ─────────────────────────────────────────────────
        if pair in self._price_cache:
            cached = self._price_cache[pair].copy()
            cached["source"] = "Cache (offline)"
            return cached

        return None

    async def get_all_prices(self, pairs: list) -> dict:
        """Fetch prices for multiple pairs concurrently."""
        results = await asyncio.gather(
            *[self.get_realtime_price(pair) for pair in pairs],
            return_exceptions=True
        )
        prices = {}
        for pair, result in zip(pairs, results):
            if isinstance(result, Exception) or result is None:
                if pair in self._price_cache:
                    prices[pair] = self._price_cache[pair]
            else:
                prices[pair] = result
        return prices

    # ─── OHLCV Candles ───────────────────────────────────────────────────────

    async def get_candles(self, pair: str, resolution: str = "D") -> list:
        """
        Fetch OHLCV candle history.
        Priority: Yahoo Finance (all pairs, free) → Finnhub (crypto fallback) → cache
        """
        cache_key = f"{pair}_{resolution}"

        # ── 1. Yahoo Finance (primary — all pairs, free, accurate) ────────────
        try:
            candles = await self.yf.get_candles(pair, resolution)
            if candles and len(candles) >= 5:
                # Update indicators from freshest daily candles
                if resolution == "D":
                    indicators = self.compute_indicators(candles)
                    if indicators:
                        self._indicators_cache[pair] = indicators
                self._candle_cache[cache_key] = candles
                print(f"[MarketDataAgent] YFinance: {len(candles)} candles for {pair}/{resolution}")
                return candles
        except Exception as e:
            print(f"[MarketDataAgent] YFinance candle failed for {pair}/{resolution}: {e}")

        # ── 2. Finnhub (crypto fallback) ──────────────────────────────────────
        if pair in CRYPTO_PAIRS:
            try:
                candles = await self.finnhub.get_crypto_candles(pair, resolution)
                if candles:
                    self._candle_cache[cache_key] = candles
                    return candles
            except Exception as e:
                print(f"[MarketDataAgent] Finnhub candle failed: {e}")

        # ── 3. Cache ──────────────────────────────────────────────────────────
        cached = self._candle_cache.get(cache_key, [])
        if cached:
            print(f"[MarketDataAgent] Using cached candles for {pair}/{resolution}")
        return cached

    # ─── Technical Indicators ────────────────────────────────────────────────

    def compute_indicators(self, candles: list) -> dict:
        """
        Compute EMA-20, EMA-50, RSI-14, and MACD from candle close prices.
        All computed in pure Python — no external TA library needed.
        """
        if not candles or len(candles) < 14:
            return {}

        closes = [c["close"] for c in candles]

        def ema(data: list, period: int) -> float:
            """Exponential Moving Average."""
            if len(data) < period:
                return data[-1] if data else 0.0
            k = 2 / (period + 1)
            val = sum(data[:period]) / period  # SMA seed
            for price in data[period:]:
                val = price * k + val * (1 - k)
            return round(val, 6)

        def rsi(data: list, period: int = 14) -> float:
            """Relative Strength Index."""
            if len(data) < period + 1:
                return 50.0
            gains, losses = [], []
            for i in range(-period, 0):
                diff = data[i] - data[i - 1]
                gains.append(max(diff, 0))
                losses.append(max(-diff, 0))
            avg_gain = sum(gains) / period
            avg_loss = sum(losses) / period
            if avg_loss == 0:
                return 100.0
            rs = avg_gain / avg_loss
            return round(100 - (100 / (1 + rs)), 2)

        # Compute indicators
        ema20 = ema(closes, 20)
        ema50 = ema(closes, 50) if len(closes) >= 50 else ema(closes, len(closes))
        rsi_val = rsi(closes)

        # MACD = EMA12 - EMA26
        ema12 = ema(closes[-40:] if len(closes) >= 40 else closes, 12)
        ema26 = ema(closes, 26) if len(closes) >= 26 else closes[-1]
        macd = round(ema12 - ema26, 6)

        current = closes[-1]
        trend = "UPTREND" if ema20 > ema50 else "DOWNTREND"
        rsi_signal = "OVERSOLD" if rsi_val < 30 else ("OVERBOUGHT" if rsi_val > 70 else "NEUTRAL")
        macd_signal = "BULLISH" if macd > 0 else "BEARISH"

        # Price vs EMA levels
        price_vs_ema20 = "ABOVE" if current > ema20 else "BELOW"
        price_vs_ema50 = "ABOVE" if current > ema50 else "BELOW"

        # Bollinger Bands (20-period, 2 std dev)
        bb_period = 20
        if len(closes) >= bb_period:
            bb_window = closes[-bb_period:]
            bb_mean = sum(bb_window) / bb_period
            bb_var = sum((x - bb_mean) ** 2 for x in bb_window) / bb_period
            bb_std = bb_var ** 0.5
            bb_upper = round(bb_mean + 2 * bb_std, 6)
            bb_lower = round(bb_mean - 2 * bb_std, 6)
            bb_mid   = round(bb_mean, 6)
            bb_bandwidth = round((bb_upper - bb_lower) / bb_mean * 100, 4) if bb_mean else 0
            bb_pct_b = round((current - bb_lower) / (bb_upper - bb_lower), 4) if (bb_upper - bb_lower) else 0.5
        else:
            bb_upper = bb_lower = bb_mid = bb_bandwidth = bb_pct_b = None

        # ATR (Average True Range) — 14 period
        atr_period = 14
        if len(candles) >= atr_period + 1:
            trs = []
            for i in range(1, len(candles)):
                h  = candles[i]["high"]
                l  = candles[i]["low"]
                pc = candles[i - 1]["close"]
                trs.append(max(h - l, abs(h - pc), abs(l - pc)))
            atr_val = round(sum(trs[-atr_period:]) / atr_period, 6)
        else:
            atr_val = None

        indicators = {
            "current_price":  round(current, 6),
            "ema_20":         ema20,
            "ema_50":         ema50,
            "rsi":            rsi_val,
            "macd":           macd,
            "trend":          trend,
            "rsi_signal":     rsi_signal,
            "macd_signal":    macd_signal,
            "price_vs_ema20": price_vs_ema20,
            "price_vs_ema50": price_vs_ema50,
            "bb_upper":       bb_upper,
            "bb_mid":         bb_mid,
            "bb_lower":       bb_lower,
            "bb_bandwidth":   bb_bandwidth,
            "bb_pct_b":       bb_pct_b,
            "atr":            atr_val,
            "candles_analyzed": len(candles)
        }

        # Merge advanced indicators (Supertrend, ADX, EMA-200, StochRSI, OBV, VWAP, Volume)
        try:
            indicators.update(_compute_advanced_indicators(candles))
        except Exception as e:
            print(f"[MarketDataAgent] Advanced indicators error: {e}")

        return indicators

    async def get_indicators(self, pair: str, resolution: str = "D") -> dict:
        """Fetch candles and compute indicators, with caching."""
        candles = await self.get_candles(pair, resolution)
        indicators = self.compute_indicators(candles)
        if indicators:
            self._indicators_cache[pair] = indicators
        return indicators or self._indicators_cache.get(pair, {})

    # ─── News ────────────────────────────────────────────────────────────────

    async def get_forex_news(self) -> list:
        """
        Fetch forex news from Finnhub.
        Returns list of news dicts with headline, summary, source.
        """
        try:
            news = await self.finnhub.get_forex_news(limit=8)
            if news:
                self._news_cache = news
                return news
        except Exception as e:
            print(f"[MarketDataAgent] News fetch failed: {e}")
        return self._news_cache

    def format_news_for_agent(self, news: list) -> str:
        """Format news items into a text block for agent prompts."""
        if not news:
            return "No current forex news available."
        lines = []
        for item in news[:6]:
            headline = item.get("headline", "No headline")
            source = item.get("source", "Unknown")
            summary = item.get("summary", "")[:150]
            lines.append(f"📰 [{source}] {headline}")
            if summary:
                lines.append(f"   → {summary}")
        return "\n".join(lines)

    # ─── Full Market Summary ─────────────────────────────────────────────────

    async def get_market_summary(self, pairs: list) -> dict:
        """
        One-stop method: fetches prices, indicators, and news for all pairs.
        Used by the main market loop to package everything before calling agents.
        """
        # Fetch news once (shared across all pairs)
        news = await self.get_forex_news()
        news_text = self.format_news_for_agent(news)

        summary = {"news": news, "news_text": news_text, "pairs": {}}

        for pair in pairs:
            price_data = await self.get_realtime_price(pair)
            indicators = await self.get_indicators(pair, "D")
            summary["pairs"][pair] = {
                "price_data": price_data,
                "indicators": indicators
            }

        return summary
