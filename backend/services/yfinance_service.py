"""
Yahoo Finance Service (yfinance) — Free, unlimited, real-time market data.
Replaces Alpha Vantage for forex candles and prices.
Provides:  real-time prices, full OHLCV history, all major pairs + crypto.
"""
import asyncio
import yfinance as yf

# Yahoo Finance symbol mapping
YF_SYMBOLS = {
    # Forex Majors
    "EUR/USD": "EURUSD=X",
    "GBP/USD": "GBPUSD=X",
    "USD/JPY": "USDJPY=X",
    "USD/CHF": "USDCHF=X",
    "AUD/USD": "AUDUSD=X",
    "NZD/USD": "NZDUSD=X",
    "USD/CAD": "USDCAD=X",
    # Forex Crosses
    "EUR/GBP": "EURGBP=X",
    "EUR/JPY": "EURJPY=X",
    "GBP/JPY": "GBPJPY=X",
    # Commodities
    "XAU/USD": "GC=F",
    "XAG/USD": "SI=F",
    # Crypto
    "BTC/USD": "BTC-USD",
    "ETH/USD": "ETH-USD",
    "XRP/USD": "XRP-USD",
    # India Forex
    "USD/INR": "USDINR=X",
    "EUR/INR": "EURINR=X",
    "GBP/INR": "GBPINR=X",
    # India Indices
    "NIFTY":   "^NSEI",
    "NIFTY50": "^NSEI",
    "SENSEX":  "^BSESN",
}

# Resolution → yfinance interval
YF_INTERVAL = {
    "1":   "1m",   "5":   "5m",   "15":  "15m",
    "30":  "30m",  "60":  "1h",   "240": "1h",   # 240 = 4H, aggregated below
    "D":   "1d",   "W":   "1wk",
}

# Resolution → look-back period for enough bars
YF_PERIOD = {
    "1":   "1d",   "5":   "5d",   "15":  "7d",
    "30":  "14d",  "60":  "60d",  "240": "6mo",
    "D":   "2y",   "W":   "5y",
}


class YFinanceService:

    # ── Synchronous helpers (run in executor) ─────────────────────────────────

    def _sync_price(self, symbol: str) -> dict | None:
        try:
            ticker = yf.Ticker(symbol)
            fi = ticker.fast_info
            price = getattr(fi, "last_price", None) or getattr(fi, "lastPrice", None)
            if not price or price <= 0:
                hist = ticker.history(period="1d", interval="5m")
                if not hist.empty:
                    price = float(hist["Close"].iloc[-1])
            if not price or price <= 0:
                return None

            prev  = getattr(fi, "previous_close", None) or getattr(fi, "previousClose", None) or price
            prev  = float(prev) if prev else price
            chg   = round(((float(price) - prev) / prev) * 100, 4) if prev else 0
            return {
                "price":      round(float(price), 6),
                "high":       round(float(getattr(fi, "day_high",  None) or price), 6),
                "low":        round(float(getattr(fi, "day_low",   None) or price), 6),
                "open":       round(float(getattr(fi, "open",      None) or price), 6),
                "prev_close": round(prev, 6),
                "change_pct": chg,
                "source":     "Yahoo Finance",
            }
        except Exception as e:
            print(f"[YFinance] Price error {symbol}: {e}")
        return None

    def _sync_candles(self, symbol: str, resolution: str) -> list:
        import traceback
        try:
            is_4h    = resolution == "240"
            interval = "1h" if is_4h else YF_INTERVAL.get(resolution, "1d")
            period   = YF_PERIOD.get(resolution, "1y")

            print(f"[YFinance] Fetching {symbol} interval={interval} period={period}")
            ticker = yf.Ticker(symbol)
            hist   = ticker.history(period=period, interval=interval, auto_adjust=False)

            if hist is None or hist.empty:
                # Retry with a shorter period (handles yfinance rate limits)
                fallback_period = {"1m": "2d", "5m": "3d", "15m": "5d",
                                   "30m": "7d", "1h": "30d"}.get(interval)
                if fallback_period:
                    print(f"[YFinance] Empty for {symbol}/{interval}, retrying period={fallback_period}")
                    hist = ticker.history(period=fallback_period, interval=interval, auto_adjust=False)
                if hist is None or hist.empty:
                    print(f"[YFinance] Still empty for {symbol}/{interval}")
                    return []

            if is_4h:
                hist = (
                    hist
                    .resample("4h", closed="left", label="left")
                    .agg({"Open": "first", "High": "max", "Low": "min",
                          "Close": "last", "Volume": "sum"})
                    .dropna(subset=["Open", "Close"])
                )

            candles = []
            prev_close = None
            for ts, row in hist.iterrows():
                try:
                    t = int(ts.timestamp())
                    o, h, l, c = float(row["Open"]), float(row["High"]), float(row["Low"]), float(row["Close"])
                    v = int(row.get("Volume", 0) or 0)
                    if o > 0 and c > 0:
                        # For 1m/5m yfinance sometimes returns O=H=L=C (flat doji).
                        # Reconstruct realistic candles using consecutive close prices.
                        if resolution in ("1", "5") and prev_close is not None and abs(h - l) < 1e-9:
                            o = prev_close
                            h = max(o, c)
                            l = min(o, c)
                        prev_close = c
                        # Round each field then clamp H/L so integrity holds after rounding.
                        ro, rc = round(o, 6), round(c, 6)
                        rh = max(round(h, 6), ro, rc)
                        rl = min(round(l, 6), ro, rc)
                        candles.append({"time": t, "open": ro, "high": rh,
                                        "low": rl, "close": rc, "volume": v})
                except Exception:
                    pass
            print(f"[YFinance] {symbol}/{resolution} -> {len(candles)} candles")
            return candles
        except Exception as e:
            print(f"[YFinance] Candle error {symbol}/{resolution}: {e}")
            traceback.print_exc()
        return []

    # ── Async public API ──────────────────────────────────────────────────────

    async def get_price(self, pair: str) -> dict | None:
        sym = YF_SYMBOLS.get(pair)
        if not sym:
            return None
        result = await asyncio.to_thread(self._sync_price, sym)
        if result:
            result["pair"] = pair
        return result

    async def get_candles(self, pair: str, resolution: str = "D") -> list:
        sym = YF_SYMBOLS.get(pair)
        if not sym:
            return []
        return await asyncio.to_thread(self._sync_candles, sym, resolution)

    def supports(self, pair: str) -> bool:
        return pair in YF_SYMBOLS
