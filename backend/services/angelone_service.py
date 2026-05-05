"""
AngelOne SmartAPI Service — Real-time NSE/BSE data.
Replaces yfinance for LIVE prices of NIFTY and SENSEX.
yfinance is kept ONLY for historical backtest data.

Tokens confirmed from scrip master:
  NIFTY  → 99926000, NSE
  SENSEX → 99919000, BSE
"""
import os
import time
import asyncio
import threading
import pyotp
from dotenv import load_dotenv
from SmartApi import SmartConnect

load_dotenv()

ANGEL_TOKENS = {
    "NIFTY":  {"token": "99926000", "symbol": "Nifty 50",  "exchange": "NSE"},
    "SENSEX": {"token": "99919000", "symbol": "SENSEX",    "exchange": "BSE"},
}

class AngelOneService:
    def __init__(self):
        self.api_key   = os.getenv("ANGEL_API_KEY", "")
        self.client_id = os.getenv("ANGEL_CLIENT_ID", "")
        self.password  = os.getenv("ANGEL_PASSWORD", "")
        self.totp_key  = os.getenv("ANGEL_TOTP_KEY", "")
        self.obj       = None
        self._cache    = {}   # {"NIFTY": {"price": 24150, "ts": 1234567}}
        self._lock     = threading.Lock()
        self._logged_in = False

    def login(self) -> bool:
        try:
            totp = pyotp.TOTP(self.totp_key).now()
            self.obj = SmartConnect(api_key=self.api_key)
            data = self.obj.generateSession(self.client_id, self.password, totp)
            if data["status"]:
                self._logged_in = True
                print("[AngelOne] Login successful")
                return True
            print(f"[AngelOne] Login failed: {data}")
            return False
        except Exception as e:
            print(f"[AngelOne] Login error: {e}")
            return False

    def get_ltp(self, pair: str) -> float | None:
        """Get Last Traded Price via REST API."""
        try:
            if not self._logged_in or not self.obj:
                return None
            info = ANGEL_TOKENS.get(pair)
            if not info:
                return None
            data = self.obj.ltpData(info["exchange"], info["symbol"], info["token"])
            if data and data.get("status") and data.get("data"):
                ltp = float(data["data"]["ltp"])
                with self._lock:
                    self._cache[pair] = {"price": ltp, "ts": time.time()}
                return ltp
        except Exception as e:
            print(f"[AngelOne] LTP error {pair}: {e}")
        return None

    def get_cached_price(self, pair: str) -> dict | None:
        """Return cached price if fresher than 10 seconds."""
        with self._lock:
            cached = self._cache.get(pair)
            if cached and (time.time() - cached["ts"]) < 10:
                return cached
        return None

    async def get_ltp_async(self, pair: str) -> float | None:
        """Async wrapper for LTP fetch."""
        return await asyncio.to_thread(self.get_ltp, pair)

    def relogin_if_needed(self) -> bool:
        """Re-login if session expired. Call this if LTP returns None."""
        print("[AngelOne] Re-logging in...")
        self._logged_in = False
        return self.login()

    async def refresh_prices_loop(self, pairs: list = ["NIFTY", "SENSEX"], interval: int = 3):
        """Background loop — refreshes prices every 3 seconds during market hours."""
        import datetime
        while True:
            try:
                now = datetime.datetime.now()
                # Only fetch during NSE market hours Mon-Fri 9:15-15:30
                is_weekday = now.weekday() < 5
                market_open = now.replace(hour=9, minute=15, second=0)
                market_close = now.replace(hour=15, minute=30, second=0)
                in_market = market_open <= now <= market_close

                if is_weekday and in_market:
                    for pair in pairs:
                        ltp = await self.get_ltp_async(pair)
                        if ltp:
                            print(f"[AngelOne] {pair}: ₹{ltp:,.2f}")
                        else:
                            # Session may have expired — re-login once
                            self.relogin_if_needed()
                            break
                await asyncio.sleep(interval)
            except Exception as e:
                print(f"[AngelOne] Refresh loop error: {e}")
                await asyncio.sleep(10)


# Global singleton
angel_service = AngelOneService()
