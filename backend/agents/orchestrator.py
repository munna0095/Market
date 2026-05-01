"""
Orchestrator Agent — synthesizes all agent reports into one final decision.
Receives outputs from Academic, Geopolitical, Quantitative, and User agents,
then issues the master BUY / SELL / HOLD with confidence and risk level.
"""
from .base_agent import BaseAgent
from .memory_manager import MemoryManager


class OrchestratorAgent(BaseAgent):
    def __init__(self):
        instruction = (
            "You are the Strategic War Room Orchestrator — the final decision-maker. "
            "You receive analysis from multiple specialist agents and synthesize them into "
            "ONE authoritative trading decision. You weigh each agent's confidence, "
            "resolve conflicts between bullish/bearish views, and output a clear verdict. "
            "Consider: technical signals, macro/geopolitical context, user insights, "
            "and quantitative data. Be decisive — markets wait for no one. "
            "Always end with:\n"
            "DECISION: BUY / SELL / HOLD\n"
            "CONFIDENCE: X%\n"
            "RISK: LOW / MEDIUM / HIGH"
        )
        super().__init__("Orchestrator", "gemini-2.5-flash", instruction)
        self.memory = MemoryManager("orchestrator")

    async def synthesize(
        self,
        pair: str,
        price_data: dict,
        indicators: dict,
        agent_reports: dict,
    ) -> dict:
        """
        agent_reports: {agent_name: report_text, ...}
        Returns: {decision, confidence, risk_level, thought}
        """
        reports_text = ""
        for agent_name, report in agent_reports.items():
            if report:
                reports_text += f"\n── {agent_name} ──\n{report}\n"

        past_summary = self.memory.get_summary(pair=pair, n=3)
        price = price_data.get("price", 0)

        prompt = f"""
═══════════════════════════════════════
STRATEGIC WAR ROOM — FINAL SYNTHESIS
Pair: {pair} | Price: {price}
═══════════════════════════════════════

AGENT REPORTS:
{reports_text if reports_text else "No agent reports available."}

MARKET INDICATORS:
  • Trend : {indicators.get('trend', 'N/A')}
  • RSI   : {indicators.get('rsi', 'N/A')} → {indicators.get('rsi_signal', 'N/A')}
  • MACD  : {indicators.get('macd_signal', 'N/A')}

PAST ORCHESTRATOR DECISIONS ({pair}):
{past_summary}

YOUR TASK:
1. Identify consensus or conflict between agents
2. State which agent(s) you weight most heavily and why
3. Give the final synthesized reasoning (2-3 sentences)
4. Issue the master decision

DECISION: BUY / SELL / HOLD
CONFIDENCE: X%
RISK: LOW / MEDIUM / HIGH
═══════════════════════════════════════
"""
        response = await self.get_response(prompt)

        if not response or "ANALYSIS_UNAVAILABLE" in response:
            return {"decision": "HOLD", "confidence": 0,
                    "thought": response or "", "price": price,
                    "risk_level": "MEDIUM",
                    "reason": "All AI providers exhausted"}

        decision, confidence, risk_level = "HOLD", 50, "MEDIUM"
        ru = response.upper()
        if "DECISION: BUY" in ru:    decision = "BUY"
        elif "DECISION: SELL" in ru:  decision = "SELL"
        if "RISK: LOW" in ru:         risk_level = "LOW"
        elif "RISK: HIGH" in ru:      risk_level = "HIGH"
        try:
            if "CONFIDENCE:" in ru:
                part = ru.split("CONFIDENCE:")[1][:15]
                digits = ''.join(c for c in part if c.isdigit())[:3]
                if digits: confidence = int(digits)
        except Exception:
            pass

        self.memory.save_decision(
            pair=pair, decision=decision, reasoning=response[:300],
            price=price, indicators=indicators, confidence=confidence
        )

        return {
            "decision":   decision,
            "confidence": confidence,
            "risk_level": risk_level,
            "thought":    response,
            "price":      price,
        }
