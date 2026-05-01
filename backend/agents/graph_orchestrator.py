"""
GraphOrchestrator — graph-based agent pipeline.

Graph topology:
  START
    ↓
  [market_data_node]  ← always runs, populates price + indicators
    ↓
  [router_node]       ← rule-based (0 LLM tokens), picks which agents to call
    ↓
  [parallel agent nodes] ← only selected agents run, concurrently
    ↓
  [decision_node]     ← orchestrator synthesizes only what ran
    ↓
  END

Token savings vs. linear pipeline:
  • Router is pure Python (zero API calls)
  • Skipped agents = 0 tokens that cycle
  • Selected agents run in parallel (no sequential sleep delays)
  • Orchestrator prompt only includes reports that actually exist
"""
import asyncio
import os
from typing import Dict, List
from .graph_state import AgentState


# ── Routing thresholds ────────────────────────────────────────────────────────
RSI_EXTREME_THRESHOLD  = 15   # |RSI - 50| > 15 → strong signal, add academic
NEWS_PRESENT_MIN_CHARS = 80   # news_text longer than this → add geopolitical
USER_INSIGHTS_DIR      = "user_insights"

STRONG_TRENDS = {"STRONG_UP", "STRONG_DOWN", "BULLISH", "BEARISH",
                 "UPTREND", "DOWNTREND"}


def _router(state: AgentState) -> AgentState:
    """
    Pure rule-based router — no LLM, no API call, zero tokens.
    Reads indicators + news length to decide which agents are worth calling.
    """
    indicators = state.indicators
    news_text  = state.news_text

    try:
        rsi = float(indicators.get("rsi", 50))
    except (TypeError, ValueError):
        rsi = 50.0

    trend = str(indicators.get("trend", "")).upper()

    selected: List[str] = []
    reasons:  List[str] = []

    # Quantitative: always — fastest, most token-efficient, purely numerical
    selected.append("quant")
    reasons.append("quant always runs")

    # Academic: strong RSI extreme OR clear trend direction
    if abs(rsi - 50) > RSI_EXTREME_THRESHOLD or trend in STRONG_TRENDS:
        selected.append("academic")
        reasons.append(f"RSI={rsi:.1f} or trend={trend}")

    # Geopolitical: only when there is meaningful news to analyze
    if len(news_text) > NEWS_PRESENT_MIN_CHARS:
        selected.append("geo")
        reasons.append("news present")

    # User insight: only when the user has submitted something
    if os.path.isdir(USER_INSIGHTS_DIR) and os.listdir(USER_INSIGHTS_DIR):
        selected.append("user")
        reasons.append("user insights found")

    all_agents = {"academic", "geo", "quant", "user"}
    skipped    = sorted(all_agents - set(selected))

    state.selected_agents = selected
    state.skipped_agents  = skipped
    state.routing_reason  = " | ".join(reasons)
    return state


async def _run_agents_sequential(
    state:   AgentState,
    agents:  dict,
) -> AgentState:
    """
    Run only the selected agents one at a time with a 2s gap between each.
    Sequential execution avoids simultaneous API bursts that trigger 429s.
    """
    selected = state.selected_agents
    result_map: Dict[str, str] = {}

    agent_calls = []
    if "academic" in selected and "academic" in agents:
        agent_calls.append(("academic", lambda: agents["academic"].analyze(state.price_data, state.indicators, state.pair)))
    if "geo" in selected and "geo" in agents:
        agent_calls.append(("geo", lambda: agents["geo"].analyze(state.news_text, state.price_data, state.pair)))
    if "quant" in selected and "quant" in agents:
        agent_calls.append(("quant", lambda: agents["quant"].analyze(state.price_data, state.indicators, state.pair)))
    if "user" in selected and "user" in agents:
        agent_calls.append(("user", lambda: agents["user"].analyze(state.price_data, state.indicators, state.pair)))

    for i, (name, call) in enumerate(agent_calls):
        try:
            result = await call()
            if result is None or (isinstance(result, str) and "ANALYSIS_UNAVAILABLE" in result):
                result_map[name] = "No analysis available from this agent."
            else:
                result_map[name] = result
        except Exception as e:
            result_map[name] = f"Agent error: {e}"
            print(f"[{name}] analyze failed: {e}")
        if i < len(agent_calls) - 1:
            await asyncio.sleep(2)

    state.academic_result     = result_map.get("academic")
    state.geopolitical_result = result_map.get("geo")
    state.quantitative_result = result_map.get("quant")
    state.user_result         = result_map.get("user")
    return state


_SKIPPED_MSG = "⟳ Not analyzed this cycle (routed out)"


async def _decision_node(state: AgentState, orchestrator) -> AgentState:
    """
    Orchestrator synthesizes only the reports that actually ran.
    Skipped agents get a placeholder so the prompt stays consistent.
    """
    agent_reports = {
        "Academic":      state.academic_result     or _SKIPPED_MSG,
        "Geopolitical":  state.geopolitical_result or _SKIPPED_MSG,
        "User Insight":  state.user_result         or _SKIPPED_MSG,
        "Quantitative":  state.quantitative_result or _SKIPPED_MSG,
    }
    final = await orchestrator.synthesize(
        pair         = state.pair,
        price_data   = state.price_data,
        indicators   = state.indicators,
        agent_reports= agent_reports,
    )
    final["selected_agents"]   = state.selected_agents
    final["skipped_agents"]    = state.skipped_agents
    final["routing_reason"]    = state.routing_reason
    # Pass agent results through so callers can broadcast individual thoughts
    final["_academic_result"]  = state.academic_result
    final["_geo_result"]       = state.geopolitical_result
    final["_quant_result"]     = state.quantitative_result
    final["_user_result"]      = state.user_result
    state.final_decision       = final
    return state


# ── Public interface ──────────────────────────────────────────────────────────

class GraphOrchestrator:
    """
    Drop-in replacement for the manual agent calls in agent_loop().

    Usage:
        graph = GraphOrchestrator(
            academic=academic_agent,
            geo=geopolitical_agent,
            quant=quantitative_agent,
            user=user_insight_agent,
            orchestrator=orchestrator,
        )
        result = await graph.run(pair, price_data, indicators, news_text)

    result keys:
        decision, confidence, risk_level, price, thought   ← same as before
        selected_agents, skipped_agents, routing_reason    ← new graph metadata
    """

    def __init__(self, *, academic, geo, quant, user, orchestrator):
        self._agents = {
            "academic": academic,
            "geo":      geo,
            "quant":    quant,
            "user":     user,
        }
        self._orchestrator = orchestrator

    async def run(
        self,
        pair:       str,
        price_data: dict,
        indicators: dict,
        news_text:  str,
    ) -> dict:
        state = AgentState(
            pair=pair,
            price_data=price_data,
            indicators=indicators,
            news_text=news_text,
        )

        # Node 1 — router (sync, 0 tokens)
        state = _router(state)

        # Node 2 — sequential agent execution (2s gap to avoid 429 bursts)
        state = await _run_agents_sequential(state, self._agents)

        # Node 3 — orchestrator decision
        state = await _decision_node(state, self._orchestrator)

        return state.final_decision

    def describe_graph(self) -> str:
        return (
            "GraphOrchestrator topology:\n"
            "  START → router_node (0 tokens)\n"
            "        ↓ conditional\n"
            "  [academic | geo | quant | user] run in parallel\n"
            "        ↓\n"
            "  decision_node (orchestrator)\n"
            "        ↓\n"
            "  END\n"
        )
