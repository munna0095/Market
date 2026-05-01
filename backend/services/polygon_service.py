"""
Polygon.io Service — Same data source as Massive Market Data MCP in Claude.ai.
Your backend calls Polygon directly via HTTP — works with Antigravity/Uvicorn.

SETUP:
  1. Free key at https://polygon.io
  2. Add to .env:  POLYGON_API_KEY=your_key_here

FREE TIER:
  Crypto OHLCV, RSI, MACD  YES
  Forex last quote          YES
  Market status             YES
  Forex real-time stream    NO (paid only)
"""
import os
import httpx
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

BASE_URL     = "https://api.polygon.io"
CRYPTO_PAIRS = {"BTC/USD", "ETH/USD", "BNB/USD", "SOL/USD", "XRP/USD"}


class PolygonService:
    def __init__(self):
        self.api_key = os.getenv("POLYGON_API_KEY", "")
        if not self.api_key:
            print("[Polygon] WARNING: POLYGON_API_KEY not set in .env")

    def _params(self, extra: dict = None) -> dict:
        base = {"apiKey": self.api_key}
        if extra:
            base.update(extra)
        return base

    def _crypto_ticker(self, pair: str) -> str:
        return "X:" + pair.replace("/", "")

    def _forex_ticker(self, pair: str) -> str:
        return "C:" + pair.replace("/", "")

    # ─── Crypto OHLCV Candles ─────────────────────────────────────────────────

    async def get_crypto_candles(self, pair: str, resolution: str = "D") -> list:
        """Fetch OHLCV — compatible with your existing candle format."""
        ticker = self._crypto_ticker(pair)
        res_map = {
            "1": ("1", "minute"), "5": ("5", "minute"),
            "15": ("15", "minute"), "30": ("30", "minute"),
            "60": ("1", "hour"), "240": ("4", "hour"),
            "D": ("1", "day"), "W": ("1", "week"),
        }
        mult, span = res_map.get(str(resolution), ("1", "day"))
        end   = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - timedelta(days=200)).strftime("%Y-%m-%d")
        url   = f"{BASE_URL}/v2/aggs/ticker/{ticker}/range/{mult}/{span}/{start}/{end}"
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                r    = await c.get(url, params=self._params({"adjusted": "true", "limit": 200, "sort": "asc"}))
                data = r.json()
            results = data.get("results", [])
            candles = [{"time": b["t"] // 1000, "open": b["o"], "high": b["h"],
                        "low": b["l"], "close": b["c"], "volume": b.get("v", 0)}
                       for b in results]
            print(f"[Polygon] {pair}: {len(candles)} candles ({span})")
            return candles
        except Exception as e:
            print(f"[Polygon] Candle error {pair}: {e}")
            return []

    # ─── RSI direct from API ──────────────────────────────────────────────────

    async def get_rsi(self, pair: str, window: int = 14) -> float | None:
        """Fetch RSI from Polygon — replaces manual Python rsi() math."""
        ticker = self._crypto_ticker(pair)
        url    = f"{BASE_URL}/v1/indicators/rsi/{ticker}"
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r    = await c.get(url, params=self._params({"timespan": "day", "window": window, "limit": 1}))
                data = r.json()
            values = data.get("results", {}).get("values", [])
            if values:
                val = round(values[0]["value"], 2)
                print(f"[Polygon] {pair} RSI({window}) = {val}")
                return val
        except Exception as e:
            print(f"[Polygon] RSI error {pair}: {e}")
        return None

    # ─── MACD direct from API ─────────────────────────────────────────────────

    async def get_macd(self, pair: str) -> dict | None:
        """Fetch MACD from Polygon — replaces manual EMA12-EMA26 math."""
        ticker = self._crypto_ticker(pair)
        url    = f"{BASE_URL}/v1/indicators/macd/{ticker}"
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r    = await c.get(url, params=self._params({
                    "timespan": "day", "short_window": 12,
                    "long_window": 26, "signal_window": 9, "limit": 1
                }))
                data = r.json()
            values = data.get("results", {}).get("values", [])
            if values:
                v   = values[0]
                val = round(v.get("value", 0), 6)
                print(f"[Polygon] {pair} MACD = {val}")
                return {"macd": val, "signal": round(v.get("signal", 0), 6),
                        "histogram": round(v.get("histogram", 0), 6),
                        "macd_signal": "BULLISH" if val > 0 else "BEARISH"}
        except Exception as e:
            print(f"[Polygon] MACD error {pair}: {e}")
        return None

    # ─── Forex Quote ──────────────────────────────────────────────────────────

    async def get_forex_quote(self, pair: str) -> dict | None:
        """Fetch forex bid/ask — use as fallback/upgrade over Alpha Vantage."""
        try:
            from_sym, to_sym = pair.split("/")
            url = f"{BASE_URL}/v1/last_quote/currencies/{from_sym}/{to_sym}"
            async with httpx.AsyncClient(timeout=10) as c:
                r    = await c.get(url, params=self._params())
                data = r.json()
            last = data.get("last", {})
            if last:
                ask = float(last.get("ask", 0))
                bid = float(last.get("bid", 0))
                mid = round((ask + bid) / 2, 6)
                return {"pair": pair, "price": mid, "ask": ask,
                        "bid": bid, "spread": round(ask - bid, 6), "source": "Polygon"}
        except Exception as e:
            print(f"[Polygon] Forex quote error {pair}: {e}")
        return None

    # ─── Market Status ────────────────────────────────────────────────────────

    async def get_market_status(self) -> dict:
        """Check if forex/crypto markets are open right now."""
        try:
            async with httpx.AsyncClient(timeout=8) as c:
                r    = await c.get(f"{BASE_URL}/v1/marketstatus/now", params=self._params())
                data = r.json()
            return {
                "forex":  data.get("currencies", {}).get("fx", "unknown"),
                "crypto": data.get("currencies", {}).get("crypto", "unknown"),
                "market": data.get("market", "unknown")
            }
        except Exception as e:
            print(f"[Polygon] Market status error: {e}")
        return {"forex": "unknown", "crypto": "unknown", "market": "unknown"}

    # ─── Full Indicator Set (API RSI/MACD + computed EMA) ────────────────────

    async def get_full_indicators(self, pair: str, candles: list) -> dict:
        """
        Drop-in replacement for MarketDataAgent.compute_indicators() for crypto.
        EMA computed from candles (needed for chart lines).
        RSI + MACD fetched from Polygon API (more accurate than manual math).
        Falls back to manual computation if API call fails.
        """
        if not candles or len(candles) < 14:
            return {}

        closes = [c["close"] for c in candles]

        def ema(data, period):
            if len(data) < period:
                return data[-1] if data else 0.0
            k, val = 2 / (period + 1), sum(data[:period]) / period
            for p in data[period:]:
                val = p * k + val * (1 - k)
            return round(val, 6)

        ema20   = ema(closes, 20)
        ema50   = ema(closes, 50) if len(closes) >= 50 else ema(closes, len(closes))
        current = closes[-1]
        trend   = "UPTREND" if ema20 > ema50 else "DOWNTREND"

        # Polygon API RSI (fallback: manual)
        rsi_val = await self.get_rsi(pair)
        if rsi_val is None:
            period = 14
            gains  = [max(closes[i] - closes[i-1], 0) for i in range(-period, 0)]
            losses = [max(closes[i-1] - closes[i], 0) for i in range(-period, 0)]
            ag, al = sum(gains)/period, sum(losses)/period
            rsi_val = round(100 - (100 / (1 + ag/al)), 2) if al else 100.0

        rsi_signal = "OVERSOLD" if rsi_val < 30 else ("OVERBOUGHT" if rsi_val > 70 else "NEUTRAL")

        # Polygon API MACD (fallback: manual)
        macd_data = await self.get_macd(pair)
        if macd_data:
            macd_val, macd_signal = macd_data["macd"], macd_data["macd_signal"]
        else:
            ema12 = ema(closes[-40:] if len(closes) >= 40 else closes, 12)
            ema26 = ema(closes, 26) if len(closes) >= 26 else closes[-1]
            macd_val    = round(ema12 - ema26, 6)
            macd_signal = "BULLISH" if macd_val > 0 else "BEARISH"

        return {
            "current_price":    round(current, 6),
            "ema_20":           ema20,
            "ema_50":           ema50,
            "rsi":              rsi_val,
            "macd":             macd_val,
            "trend":            trend,
            "rsi_signal":       rsi_signal,
            "macd_signal":      macd_signal,
            "price_vs_ema20":   "ABOVE" if current > ema20 else "BELOW",
            "price_vs_ema50":   "ABOVE" if current > ema50 else "BELOW",
            "candles_analyzed": len(candles),
            "indicator_source": "Polygon API (RSI/MACD) + computed (EMA)"
        }
