"""
NSE (National Stock Exchange) Data Service
Fetches NIFTY 50, SENSEX, and individual Indian stocks
"""
import yfinance as yf
import pandas as pd
from datetime import datetime
import pytz


# NSE Market Hours (IST)
NSE_OPEN_HOUR   = 9
NSE_OPEN_MIN    = 15
NSE_CLOSE_HOUR  = 15
NSE_CLOSE_MIN   = 30
IST = pytz.timezone("Asia/Kolkata")

def is_nse_market_open() -> dict:
    """
    Check if NSE market is currently open.
    Returns: { is_open, reason, current_time_ist, status }
    """
    now_ist = datetime.now(IST)
    weekday = now_ist.weekday()  # 0=Mon, 6=Sun

    if weekday >= 5:  # Saturday or Sunday
        return {
            "is_open": False,
            "status": "MARKET CLOSED",
            "reason": f"Weekend ({now_ist.strftime('%A')})",
            "current_time_ist": now_ist.strftime("%H:%M:%S"),
            "next_open": "Monday 09:15 IST"
        }

    market_open  = now_ist.replace(hour=NSE_OPEN_HOUR,  minute=NSE_OPEN_MIN,  second=0)
    market_close = now_ist.replace(hour=NSE_CLOSE_HOUR, minute=NSE_CLOSE_MIN, second=0)

    if now_ist < market_open:
        return {
            "is_open": False,
            "status": "PRE-MARKET",
            "reason": f"Market opens at 09:15 IST",
            "current_time_ist": now_ist.strftime("%H:%M:%S"),
            "next_open": "Today 09:15 IST"
        }

    if now_ist > market_close:
        return {
            "is_open": False,
            "status": "MARKET CLOSED",
            "reason": f"Market closed at 15:30 IST",
            "current_time_ist": now_ist.strftime("%H:%M:%S"),
            "next_open": "Tomorrow 09:15 IST" if weekday < 4 else "Monday 09:15 IST"
        }

    return {
        "is_open": True,
        "status": "MARKET OPEN",
        "reason": "Trading hours active",
        "current_time_ist": now_ist.strftime("%H:%M:%S"),
        "next_open": None
    }


# Indian index symbols
NSE_PAIRS = ["NIFTY", "SENSEX", "NIFTY50", "BANKNIFTY"]


class NSEService:
    """
    Provides NIFTY 50, SENSEX, and Indian stock data
    Uses YFinance as primary source
    """
    
    # NSE Symbol Mappings
    SYMBOLS = {
        "NIFTY": "^NSEI",           # NIFTY 50 Index
        "SENSEX": "^BSESN",         # BSE SENSEX Index
        "NIFTY_IT": "^NSEITÄT",     # NIFTY IT Index (if available)
        "BANK_NIFTY": "^CNXIT",     # NIFTY Bank Index
    }
    
    def __init__(self):
        self.cache = {}
        self.cache_ttl = 60  # seconds
        self.last_update = {}
    
    def _is_cache_valid(self, symbol: str) -> bool:
        """Check if cached data is still fresh"""
        if symbol not in self.last_update:
            return False
        elapsed = (datetime.now() - self.last_update[symbol]).total_seconds()
        return elapsed < self.cache_ttl
    
    async def get_nifty_price(self) -> dict:
        """
        Get live NIFTY 50 price
        Returns: {price, high, low, open, change, change_pct}
        """
        symbol = self.SYMBOLS["NIFTY"]
        
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.fast_info
            
            return {
                "symbol": "NIFTY",
                "price": float(info.get("lastPrice", 0)),
                "high": float(info.get("fiftyTwoWeekHigh", 0)),
                "low": float(info.get("fiftyTwoWeekLow", 0)),
                "open": float(info.get("open", 0)),
                "previous_close": float(info.get("previousClose", 0)),
                "change": float(info.get("lastPrice", 0)) - float(info.get("previousClose", 0)),
                "change_pct": float(info.get("lastPrice", 0) / info.get("previousClose", 1) - 1) * 100,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            print(f"[NSE] Error fetching NIFTY price: {e}")
            return {"error": str(e)}
    
    async def get_sensex_price(self) -> dict:
        """Get live SENSEX (BSE) price"""
        symbol = self.SYMBOLS["SENSEX"]
        
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.fast_info
            
            return {
                "symbol": "SENSEX",
                "price": float(info.get("lastPrice", 0)),
                "change_pct": float(info.get("lastPrice", 0) / info.get("previousClose", 1) - 1) * 100,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            print(f"[NSE] Error fetching SENSEX price: {e}")
            return {"error": str(e)}
    
    async def get_nifty_candles(self, timeframe: str = "1h", days: int = 30) -> pd.DataFrame:
        """
        Get NIFTY historical candles (OHLCV)
        Timeframes: 1m, 5m, 15m, 1h, 1d
        """
        symbol = self.SYMBOLS["NIFTY"]
        
        try:
            ticker = yf.Ticker(symbol)
            
            # Map timeframe to period
            if timeframe in ["1m", "5m", "15m"]:
                period = "7d"  # Intraday data available for 7 days
            elif timeframe == "1h":
                period = "60d"  # 1H data available for 60 days
            else:
                period = f"{days}d"
            
            df = ticker.history(period=period, interval=timeframe, auto_adjust=False)
            
            # Rename columns to standard OHLCV format
            df.columns = ['Open', 'High', 'Low', 'Close', 'Volume', 'Dividends', 'Stock Splits']
            df = df[['Open', 'High', 'Low', 'Close', 'Volume']]
            
            return df
        
        except Exception as e:
            print(f"[NSE] Error fetching NIFTY candles: {e}")
            return pd.DataFrame()
    
    async def get_nifty_daily_candles(self, days: int = 250) -> pd.DataFrame:
        """
        Get NIFTY daily candles (for swing trading)
        250 days = ~1 year of trading data
        """
        symbol = self.SYMBOLS["NIFTY"]
        
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=f"{days}d", interval="1d", auto_adjust=False)
            
            # Keep only OHLCV
            df = df[['Open', 'High', 'Low', 'Close', 'Volume']]
            df.columns = ['open', 'high', 'low', 'close', 'volume']
            
            return df
        
        except Exception as e:
            print(f"[NSE] Error fetching daily candles: {e}")
            return pd.DataFrame()
    
    async def get_nifty_50_constituents(self) -> list:
        """
        Get list of NIFTY 50 stocks (top 50 companies)
        Format: [{"symbol": "TCS.NS", "name": "Tata Consultancy Services"}, ...]
        """
        # This is a mock list - in production, fetch from NSE website
        constituents = [
            {"symbol": "RELIANCE.NS", "name": "Reliance Industries"},
            {"symbol": "TCS.NS", "name": "Tata Consultancy Services"},
            {"symbol": "INFY.NS", "name": "Infosys"},
            {"symbol": "HDFC.NS", "name": "HDFC Bank"},
            {"symbol": "LT.NS", "name": "Larsen & Toubro"},
            {"symbol": "MARUTI.NS", "name": "Maruti Suzuki"},
            {"symbol": "BAJAJFINSV.NS", "name": "Bajaj Finserv"},
            {"symbol": "WIPRO.NS", "name": "Wipro"},
            {"symbol": "ITC.NS", "name": "ITC Limited"},
            {"symbol": "HDFCLIFE.NS", "name": "HDFC Life"},
            # Add more as needed
        ]
        return constituents
    
    async def get_stock_price(self, symbol: str) -> dict:
        """
        Get individual stock price
        Example: "TCS.NS" for Tata Consultancy Services
        """
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.fast_info
            
            return {
                "symbol": symbol,
                "price": float(info.get("lastPrice", 0)),
                "change_pct": float(info.get("lastPrice", 0) / info.get("previousClose", 1) - 1) * 100
            }
        except Exception as e:
            print(f"[NSE] Error fetching {symbol}: {e}")
            return {"error": str(e)}
    
    async def get_market_status(self) -> dict:
        """
        Check if NSE market is open (9:15 AM - 3:30 PM IST, Mon-Fri)
        """
        now = datetime.now()
        # Note: This is simplified - doesn't account for holidays
        is_weekday = now.weekday() < 5  # Mon-Fri
        market_open = now.hour >= 9 and now.minute >= 15
        market_close = now.hour >= 15 and now.minute >= 30
        is_open = is_weekday and market_open and not market_close
        
        return {
            "is_open": is_open,
            "market_hours": "9:15 AM - 3:30 PM IST",
            "current_time_ist": now.strftime("%H:%M:%S"),
            "day": now.strftime("%A")
        }


