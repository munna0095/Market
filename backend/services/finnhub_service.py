"""
Finnhub Service — Real-time market data
Docs: https://finnhub.io/docs/api
Free tier: Crypto quotes/candles ✅ | Forex news ✅ | Forex quotes/rates ❌ (premium)
"""
import os
import httpx
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

# Only crypto pairs can use Finnhub quotes on free tier
# Forex pairs use Alpha Vantage as primary
CRYPTO_PAIRS = {
    "BTC/USD": "BINANCE:BTCUSDT",
    "ETH/USD": "BINANCE:ETHUSDT",
}

RESOLUTION_DAYS = {
    "1": 1, "5": 3, "15": 7, "30": 14,
    "60": 30, "240": 60, "D": 365, "W": 730
}


class FinnhubService:
    def __init__(self):
        self.api_key = os.getenv("FINNHUB_API_KEY", "")
        self.base_url = "https://finnhub.io/api/v1"

    def _headers(self):
        return {"X-Finnhub-Token": self.api_key}

    async def get_crypto_quote(self, pair: str) -> dict | None:
        """
        Get real-time crypto quote from Finnhub (free tier supported).
        Only works for crypto pairs like BTC/USD, ETH/USD.
        """
        symbol = CRYPTO_PAIRS.get(pair)
        if not symbol:
            return None
        async with httpx.AsyncClient(timeout=10) as client:
            try:
                r = await client.get(
                    f"{self.base_url}/quote",
                    params={"symbol": symbol},
                    headers=self._headers()
                )
                data = r.json()
                if data.get("c") and float(data["c"]) > 0:
                    prev = float(data.get("pc", data["c"]))
                    change_pct = round(((float(data["c"]) - prev) / prev) * 100, 4) if prev else 0
                    return {
                        "pair": pair,
                        "price": float(data["c"]),
                        "high": float(data.get("h", 0)),
                        "low": float(data.get("l", 0)),
                        "open": float(data.get("o", 0)),
                        "prev_close": prev,
                        "change_pct": change_pct,
                        "source": "Finnhub"
                    }
            except Exception as e:
                print(f"[Finnhub] Crypto quote error for {pair}: {e}")
        return None

    async def get_crypto_candles(self, pair: str, resolution: str = "D") -> list:
        """
        Fetch OHLCV candle data for CRYPTO pairs only (free tier supported).
        For forex pairs, use AlphaVantageService instead.
        resolution: "1", "5", "15", "30", "60", "D", "W"
        """
        symbol = CRYPTO_PAIRS.get(pair)
        if not symbol:
            return []

        days = RESOLUTION_DAYS.get(resolution, 100)
        to_ts = int(datetime.now().timestamp())
        from_ts = int((datetime.now() - timedelta(days=days)).timestamp())

        async with httpx.AsyncClient(timeout=15) as client:
            try:
                r = await client.get(
                    f"{self.base_url}/crypto/candle",
                    params={
                        "symbol": symbol,
                        "resolution": resolution,
                        "from": from_ts,
                        "to": to_ts
                    },
                    headers=self._headers()
                )
                data = r.json()
                if data.get("s") == "ok" and data.get("t"):
                    candles = []
                    for i in range(len(data["t"])):
                        candles.append({
                            "time": data["t"][i],
                            "open": data["o"][i],
                            "high": data["h"][i],
                            "low": data["l"][i],
                            "close": data["c"][i],
                            "volume": data["v"][i] if data.get("v") else 0
                        })
                    return candles
                else:
                    print(f"[Finnhub] Crypto candle status: {data.get('s')} for {pair}/{resolution}")
            except Exception as e:
                print(f"[Finnhub] Crypto candle error for {pair}: {e}")
        return []

    async def get_forex_news(self, limit: int = 8) -> list:
        """
        Fetch latest forex market news.
        Returns list of {headline, summary, source, url, datetime}
        """
        async with httpx.AsyncClient(timeout=10) as client:
            try:
                r = await client.get(
                    f"{self.base_url}/news",
                    params={"category": "forex"},
                    headers=self._headers()
                )
                data = r.json()
                if isinstance(data, list):
                    return [
                        {
                            "headline": item.get("headline", ""),
                            "summary": item.get("summary", ""),
                            "source": item.get("source", ""),
                            "url": item.get("url", ""),
                            "datetime": item.get("datetime", 0)
                        }
                        for item in data[:limit]
                    ]
            except Exception as e:
                print(f"[Finnhub] News error: {e}")
        return []

    async def get_general_news(self, limit: int = 5) -> list:
        """Fetch general financial market news."""
        async with httpx.AsyncClient(timeout=10) as client:
            try:
                r = await client.get(
                    f"{self.base_url}/news",
                    params={"category": "general"},
                    headers=self._headers()
                )
                data = r.json()
                if isinstance(data, list):
                    return [item.get("headline", "") for item in data[:limit]]
            except Exception as e:
                print(f"[Finnhub] General news error: {e}")
        return []

    async def symbol_search(self, query: str) -> dict:
        """Search for forex/crypto symbols. Docs: /docs/api/symbol-search"""
        async with httpx.AsyncClient(timeout=10) as client:
            try:
                r = await client.get(
                    f"{self.base_url}/search",
                    params={"q": query},
                    headers=self._headers()
                )
                return r.json()
            except Exception as e:
                print(f"[Finnhub] Symbol search error: {e}")
        return {}

    async def get_forex_rates(self, base: str = "USD") -> dict:
        """Get all forex rates relative to a base currency."""
        async with httpx.AsyncClient(timeout=10) as client:
            try:
                r = await client.get(
                    f"{self.base_url}/forex/rates",
                    params={"base": base},
                    headers=self._headers()
                )
                data = r.json()
                return data.get("quote", {})
            except Exception as e:
                print(f"[Finnhub] Rates error: {e}")
        return {}
