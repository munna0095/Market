"""
Geopolitical Analyst Agent — with Real News Feed & Memory
Uses REAL forex news from Finnhub to analyze macro impacts.
Monitors: Middle East (oil), Russia/Ukraine (energy), US/China (trade), central banks.
"""
from .base_agent import BaseAgent
from .memory_manager import MemoryManager


class GeopoliticalAgent(BaseAgent):
    def __init__(self):
        instruction = (
            "You are the Geopolitical Analyst — you monitor global events and predict their market impact. "
            "You focus on: central bank decisions (Fed, ECB, BOJ), geopolitical conflicts (Middle East oil, "
            "Russia/Ukraine energy), trade wars (US/China tariffs), economic data releases (CPI, NFP, GDP). "
            "You have MEMORY of past geopolitical events and their market effects. "
            "You understand how news affects specific currency pairs: "
            "  • USD strength/weakness → all USD pairs "
            "  • Oil price moves → USD/CAD, NOK "
            "  • Risk-off events → JPY and CHF strengthen "
            "  • EU tensions → EUR weakens "
            "ALWAYS end with: DECISION: BUY / SELL / HOLD | CONFIDENCE: X%"
        )
        super().__init__("Geopolitical Analyst", "gemini-2.5-flash", instruction)
        self.memory = MemoryManager("geopolitical_analyst")

    async def analyze(self, news_text: str, market_data: dict, pair: str = "EUR/USD") -> str:
        # Memory context
        past_summary = self.memory.get_summary(pair=pair, n=5)
        bias = self.memory.get_bias(pair=pair)

        # Extract price for context
        current_price = market_data.get("price", "N/A") if market_data else "N/A"
        change_pct = market_data.get("change_pct", 0) if market_data else 0

        prompt = f"""
═══════════════════════════════════════
GEOPOLITICAL ANALYST — MACRO ANALYSIS REPORT
Pair: {pair} | Current Price: {current_price} ({change_pct:+.4f}%)
═══════════════════════════════════════

📰 NEWS & GLOBAL INTELLIGENCE FEED:
{news_text if news_text else "No current news available — use general macro knowledge."}

📊 MARKET DATA:
  Pair          : {pair}
  Current Price : {current_price}
  24H Change    : {change_pct:+.4f}%

🧠 YOUR MACRO MEMORY (Past Calls for {pair}):
{past_summary}
  Your recent macro bias: {bias}

═══════════════════════════════════════
YOUR TASK — Answer ALL of these:

1. HEADLINE IMPACT: Which of the news items above directly affects {pair}?
   (If none match exactly, use your macro knowledge about current world events)

2. CENTRAL BANK WATCH: What are the Fed, ECB, and BOJ doing right now?
   How does that affect {pair}?

3. RISK SENTIMENT: Is the market in risk-on or risk-off mode?
   What does that mean for {pair}?

4. SHORT-TERM VIEW (1-3 days): What's the directional bias?
5. MEDIUM-TERM VIEW (1-4 weeks): Any macro trend forming?

6. LEARNING: What did you get right or wrong in past macro calls?

DECISION: BUY / SELL / HOLD
CONFIDENCE: X%
═══════════════════════════════════════
"""
        response = await self.get_response(prompt)

        # Parse and store in memory
        decision = "HOLD"
        confidence = 50
        resp_upper = response.upper()
        if "DECISION: BUY" in resp_upper:
            decision = "BUY"
        elif "DECISION: SELL" in resp_upper:
            decision = "SELL"
        try:
            if "CONFIDENCE:" in resp_upper:
                part = resp_upper.split("CONFIDENCE:")[1][:20]
                digits = ''.join(c for c in part if c.isdigit())[:3]
                if digits:
                    confidence = int(digits)
        except Exception:
            pass

        self.memory.save_decision(
            pair=pair,
            decision=decision,
            reasoning=response[:300],
            price=float(current_price) if isinstance(current_price, (int, float)) else 0,
            confidence=confidence
        )

        return response
