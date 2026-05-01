"""
Orchestrator Agent — "The General" with Memory & Structured Decisions
Synthesizes all 3 agent views into a final, decisive trading call.
Returns structured JSON with decision, confidence, and reasoning.
"""
from .base_agent import BaseAgent
from .memory_manager import MemoryManager


class OrchestratorAgent(BaseAgent):
    def __init__(self):
        instruction = (
            "You are the Strategic Orchestrator — The General. You lead a council of expert analysts "
            "and make the FINAL trading decision. You receive reports from: "
            "  1. Academic Analyst (technical indicators, book principles) "
            "  2. Geopolitical Analyst (macro events, central banks, news) "
            "  3. User Insight Agent (user's personal prediction) "
            "  4. Quantitative Analyst (precise mathematical indicators, probabilities) "
            "You synthesize ALL views, weigh conflicting signals, and issue one clear command. "
            "You have MEMORY of past council decisions and you track your win/loss record. "
            "You must be decisive — markets reward clarity over hesitation. "
            "FORMAT YOUR RESPONSE AS: "
            "FINAL DECISION: BUY / SELL / HOLD "
            "CONFIDENCE: X% "
            "REASONING: [Your synthesis] "
            "RISK LEVEL: LOW / MEDIUM / HIGH "
            "STOP LOSS SUGGESTION: [price level or % away]"
        )
        super().__init__("Orchestrator", "gemini-2.5-flash", instruction)
        self.memory = MemoryManager("orchestrator")

    async def debate(
        self,
        academic_view: str,
        geopolitical_view: str,
        user_view: str,
        quantitative_view: str,
        market_data: dict,
        indicators: dict = None,
        pair: str = "EUR/USD"
    ) -> dict:
        indicators = indicators or {}
        current_price = indicators.get("current_price", market_data.get("price", 0) if market_data else 0)

        # Memory context
        past_summary = self.memory.get_summary(pair=pair, n=5)
        bias = self.memory.get_bias(pair=pair)
        streak = self.memory.get_streak(pair=pair)

        prompt = f"""
═══════════════════════════════════════════════════════
STRATEGIC COUNCIL — FINAL DECISION SESSION
Pair: {pair} | Current Price: {current_price}
═══════════════════════════════════════════════════════

📈 MARKET SNAPSHOT:
  Price    : {current_price}
  EMA-20   : {indicators.get('ema_20', 'N/A')} | EMA-50: {indicators.get('ema_50', 'N/A')}
  Trend    : {indicators.get('trend', 'N/A')}
  RSI(14)  : {indicators.get('rsi', 'N/A')} → {indicators.get('rsi_signal', 'N/A')}
  MACD     : {indicators.get('macd', 'N/A')} → {indicators.get('macd_signal', 'N/A')}

════════════════════════════════════════
📚 ACADEMIC ANALYST REPORT:
{academic_view[:600]}

════════════════════════════════════════
🌍 GEOPOLITICAL ANALYST REPORT:
{geopolitical_view[:600]}

════════════════════════════════════════
👤 USER INSIGHT AGENT REPORT:
{user_view[:600]}

════════════════════════════════════════
⚙️ QUANTITATIVE ANALYST REPORT:
{quantitative_view[:600]}

════════════════════════════════════════
🧠 YOUR PAST COUNCIL DECISIONS FOR {pair}:
{past_summary}
  Council's recent bias: {bias}
  Decision streak: {streak}

════════════════════════════════════════
YOUR COMMAND:

1. AGREEMENT MATRIX: Do the 4 analysts agree or conflict? 
   (Unanimous → high confidence. 3-vs-1 → medium. All different → hold/wait)

2. WEIGHT THE VIEWS: 
   - If technicals strongly oppose macro → lean technical for short-term
   - If macro is a major event (Fed, CPI) → macro overrides technical

3. LEARNING: Have your past decisions for {pair} been accurate?
   What would you do differently?

Now issue your FINAL COMMAND:

FINAL DECISION: BUY / SELL / HOLD
CONFIDENCE: X%
REASONING: [Clear synthesis of all views]
RISK LEVEL: LOW / MEDIUM / HIGH
STOP LOSS SUGGESTION: [price or % level]
═══════════════════════════════════════════════════════
"""
        response = await self.get_response(prompt)

        # Parse structured fields from response
        decision = "HOLD"
        confidence = 50
        risk_level = "MEDIUM"
        resp_upper = response.upper()

        if "FINAL DECISION: BUY" in resp_upper:
            decision = "BUY"
        elif "FINAL DECISION: SELL" in resp_upper:
            decision = "SELL"

        try:
            if "CONFIDENCE:" in resp_upper:
                part = resp_upper.split("CONFIDENCE:")[1][:20]
                digits = ''.join(c for c in part if c.isdigit())[:3]
                if digits:
                    confidence = int(digits)
        except Exception:
            pass

        if "RISK LEVEL: LOW" in resp_upper:
            risk_level = "LOW"
        elif "RISK LEVEL: HIGH" in resp_upper:
            risk_level = "HIGH"

        # Save to memory
        self.memory.save_decision(
            pair=pair,
            decision=decision,
            reasoning=response[:300],
            price=float(current_price) if isinstance(current_price, (int, float)) else 0,
            indicators=indicators,
            confidence=confidence
        )

        return {
            "thought": response,
            "decision": decision,
            "confidence": confidence,
            "risk_level": risk_level,
            "pair": pair,
            "price": current_price
        }
