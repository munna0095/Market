"""
Quantitative Analyst Agent
Specializes in precise numerical analysis of technical indicators (MACD, RSI, EMAs) and price action.
Generates purely data-driven probability forecasts.
"""
from .base_agent import BaseAgent


class QuantitativeAgent(BaseAgent):
    def __init__(self):
        instruction = (
            "You are the Quantitative Analyst Agent. You ignore news and sentiment. "
            "You focus purely on raw data, technical indicators (RSI, MACD, Moving Averages), "
            "and mathematical probabilities. "
            "Provide precise, data-driven analysis and predictions based on the technical readings provided. "
            "Your output should be concise, mentioning specific figures and percentage probabilities."
        )
        super().__init__("Quantitative Analyst", "gemini-2.5-flash", instruction)

    async def analyze(self, price_data: dict, indicators: dict, pair: str = "EUR/USD") -> str:
        prompt = f"""
        Execute a precise quantitative analysis for {pair}.
        
        PRICE ACTION:
        Current: {price_data.get('price')}
        24h Change: {price_data.get('change_pct')}%
        High: {price_data.get('high')}
        Low: {price_data.get('low')}
        
        INDICATORS:
        RSI (14): {indicators.get('rsi')}
        RSI Signal: {indicators.get('rsi_signal')}
        MACD: {indicators.get('macd')}
        MACD Signal: {indicators.get('macd_signal')}
        EMA 20: {indicators.get('ema_20')}
        EMA 50: {indicators.get('ema_50')}
        Overall Trend: {indicators.get('trend')}
        
        Deliver a highly precise, quantitative forecast. Include specific numbers and a clear percentage confidence.
        """
        try:
            return await self.get_response(prompt)
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise Exception(f"Quantitative Agent failed: {e}")
