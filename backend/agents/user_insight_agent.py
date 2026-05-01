"""
User Insight Agent — with Memory & Indicator Context
Represents the user's personal predictions in agent debates.
Reads user notes + remembers how past user predictions performed.
"""
import os
from .base_agent import BaseAgent
from .memory_manager import MemoryManager


class UserInsightAgent(BaseAgent):
    def __init__(self):
        instruction = (
            "You are the Personal Insight Agent — you represent the user's personal market view. "
            "You read the user's stored notes and trading ideas, then check how they align with "
            "the current technical picture and news. You are the user's advocate in the discussion. "
            "You have MEMORY and track whether the user's past predictions were correct. "
            "Be honest: if the user's intuition is going against key indicators, say so diplomatically. "
            "If their insight aligns well with the data, amplify it with confidence. "
            "ALWAYS end with: DECISION: BUY / SELL / HOLD | CONFIDENCE: X%"
        )
        super().__init__("User Insight Agent", "gemini-2.5-flash", instruction)
        self.insights_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "user_insights"
        )
        self.memory = MemoryManager("user_insight_agent")

    def _load_user_insights(self) -> str:
        if not os.path.exists(self.insights_dir):
            return "No personal insights provided by the user yet."
        try:
            notes = []
            files = sorted(os.listdir(self.insights_dir))[-10:]  # Last 10 files
            for filename in files:
                if filename.endswith(".txt"):
                    with open(os.path.join(self.insights_dir, filename), "r", encoding="utf-8") as f:
                        content = f.read().strip()
                        if content:
                            # Extract timestamp from filename
                            ts = filename.replace("web_input_", "").replace(".txt", "")
                            notes.append(f"[Note {ts}]: {content}")
            return "\n".join(notes) if notes else "No personal insights provided by the user yet."
        except Exception as e:
            return f"Error loading insights: {e}"

    async def analyze(self, market_data: dict, indicators: dict = None, pair: str = "EUR/USD") -> str:
        indicators = indicators or {}
        user_notes = self._load_user_insights()

        # Memory context
        past_summary = self.memory.get_summary(pair=pair, n=5)
        bias = self.memory.get_bias(pair=pair)

        current_price = indicators.get("current_price", market_data.get("price", "N/A") if market_data else "N/A")
        trend = indicators.get("trend", "N/A")
        rsi_signal = indicators.get("rsi_signal", "N/A")

        prompt = f"""
═══════════════════════════════════════
USER INSIGHT AGENT — PERSONAL VIEW REPORT
Pair: {pair} | Price: {current_price}
═══════════════════════════════════════

📝 USER'S PERSONAL NOTES & PREDICTIONS:
{user_notes}

📊 CURRENT MARKET SNAPSHOT:
  Pair          : {pair}
  Current Price : {current_price}
  Trend         : {trend}
  RSI Signal    : {rsi_signal}
  MACD Signal   : {indicators.get('macd_signal', 'N/A')}

🧠 YOUR MEMORY (How user predictions performed for {pair}):
{past_summary}
  Recent advocacy bias: {bias}

═══════════════════════════════════════
YOUR TASK:

1. USER VOICE: Summarize what the user is thinking about {pair}
   (If no notes, say: "No user prediction submitted — defaulting to data-driven view")

2. ALIGNMENT CHECK: Does the user's view align with the technical indicators?
   Be specific: RSI says {rsi_signal}, trend is {trend} — does user agree?

3. ADVOCATE: Present the user's case to the other agents persuasively

4. HONESTY NOTE: If user's view contradicts the data strongly, diplomatically say so
   and suggest what to watch before acting on their prediction

5. LEARNING: Has the user's intuition historically been correct for {pair}?

DECISION: BUY / SELL / HOLD  (representing user's best interest)
CONFIDENCE: X%
═══════════════════════════════════════
"""
        response = await self.get_response(prompt)

        # Store decision in memory
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
            indicators=indicators,
            confidence=confidence
        )

        return response
