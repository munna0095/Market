"""
Quantitative Agent — Pure technical/numerical analysis using indicators.
Always runs first (cheapest, fastest, zero news dependency).
"""
from .base_agent import BaseAgent
from .memory_manager import MemoryManager


class QuantitativeAgent(BaseAgent):
    def __init__(self):
        instruction = (
            "You are the Quantitative Analyst — a pure numbers-driven trading expert. "
            "You ONLY use technical indicators: EMA crossovers, RSI levels, MACD histogram, "
            "Bollinger Band %B, ATR volatility, and trend direction. "
            "You do NOT care about news or sentiment — only price action and math. "
            "Be precise and brief. Always end with:\n"
            "DECISION: BUY / SELL / HOLD | CONFIDENCE: X%"
        )
        super().__init__("Quantitative Analyst", "gemini-2.5-flash", instruction)
        self.memory = MemoryManager("quantitative_analyst")

    async def analyze(self, market_data: dict, indicators: dict = None, pair: str = "EUR/USD") -> str:
        indicators = indicators or {}
        past_summary = self.memory.get_summary(pair=pair, n=3)

        prompt = f"""
═══════════════════════════════════════
QUANTITATIVE ANALYST — TECHNICAL REPORT
Pair: {pair}
═══════════════════════════════════════

📊 MARKET DATA:
{market_data}

📈 INDICATORS:
  • Price      : {indicators.get('current_price', 'N/A')}
  • EMA-20     : {indicators.get('ema_20', 'N/A')} ({indicators.get('price_vs_ema20', 'N/A')} price)
  • EMA-50     : {indicators.get('ema_50', 'N/A')} ({indicators.get('price_vs_ema50', 'N/A')} price)
  • Trend      : {indicators.get('trend', 'N/A')}
  • RSI (14)   : {indicators.get('rsi', 'N/A')} → {indicators.get('rsi_signal', 'N/A')}
  • MACD       : {indicators.get('macd', 'N/A')} → {indicators.get('macd_signal', 'N/A')}
  • BB %B      : {indicators.get('bb_pct_b', 'N/A')}
  • ATR        : {indicators.get('atr', 'N/A')}

🧠 PAST QUANT CALLS ({pair}):
{past_summary}

TASK: Identify the 2 strongest quantitative signals, state your edge, and give your decision.

DECISION: BUY / SELL / HOLD
CONFIDENCE: X%
═══════════════════════════════════════
"""
        response = await self.get_response(prompt)

        decision, confidence = "HOLD", 50
        ru = response.upper()
        if "DECISION: BUY" in ru:   decision = "BUY"
        elif "DECISION: SELL" in ru: decision = "SELL"
        try:
            if "CONFIDENCE:" in ru:
                part = ru.split("CONFIDENCE:")[1][:15]
                digits = ''.join(c for c in part if c.isdigit())[:3]
                if digits: confidence = int(digits)
        except Exception:
            pass

        self.memory.save_decision(
            pair=pair, decision=decision, reasoning=response[:300],
            price=indicators.get("current_price", 0),
            indicators=indicators, confidence=confidence
        )
        return response
