import os
import httpx
from dotenv import load_dotenv

load_dotenv()

class AlphaVantageService:
    def __init__(self):
        self.api_key = os.getenv("ALPHA_VANTAGE_API_KEY")
        self.base_url = "https://www.alphavantage.co/query"

    async def get_realtime_rate(self, from_symbol, to_symbol="USD"):
        """
        Fetches real-time exchange rate for Forex or Crypto.
        """
        params = {
            "function": "CURRENCY_EXCHANGE_RATE",
            "from_currency": from_symbol,
            "to_currency": to_symbol,
            "apikey": self.api_key
        }
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(self.base_url, params=params)
                data = response.json()
                
                if "Realtime Currency Exchange Rate" in data:
                    return data["Realtime Currency Exchange Rate"]
                elif "Note" in data:
                    print(f"AlphaVantage API Note: {data['Note']}")
                return None
            except Exception as e:
                print(f"AlphaVantage API Error: {e}")
                return None

    async def get_intraday_data(self, from_symbol, to_symbol="USD", interval="5min"):
        """
        Fetches intraday time series for charts.
        """
        params = {
            "function": "FX_INTRADAY",
            "from_symbol": from_symbol,
            "to_symbol": to_symbol,
            "interval": interval,
            "apikey": self.api_key
        }
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(self.base_url, params=params)
                return response.json()
            except Exception as e:
                print(f"AlphaVantage API Error: {e}")
                return {}

    async def get_crypto_intraday(self, symbol, market="USD"):
        """
        Fetches intraday data for Crypto.
        """
        params = {
            "function": "CRYPTO_INTRADAY",
            "symbol": symbol,
            "market": market,
            "interval": "5min",
            "apikey": self.api_key
        }
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(self.base_url, params=params)
                return response.json()
            except Exception as e:
                print(f"AlphaVantage API Error: {e}")
                return {}
