import httpx
import asyncio

class SentimentService:
    def __init__(self):
        self.crypto_fear_greed_url = "https://api.alternative.me/fng/"
        # Forex sentiment is often derived from retail positioning (IG, etc.) 
        # For now we'll simulate a "Market Pressure" derived from actual volatility if no API is available.
        
    async def get_crypto_sentiment(self):
        """Fetches the Fear & Greed Index for Crypto."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(self.crypto_fear_greed_url)
                data = response.json()
                if "data" in data and len(data["data"]) > 0:
                    val = data["data"][0]
                    return {
                        "value": val["value"],
                        "classification": val["value_classification"],
                        "timestamp": val["timestamp"]
                    }
        except Exception as e:
            print(f"Sentiment API Error: {e}")
        return {"value": "50", "classification": "Neutral"}

    async def get_market_pressure(self, price_history):
        """
        Derives 'Pressure' and 'Fear' from price action.
        High volatility usually correlates with high Fear.
        """
        # Placeholder for simple math-based sentiment
        # In a real app, this would use more complex technical indicators
        return "Medium"
