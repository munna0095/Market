"""
AgentState — shared state that flows through every graph node.
Only the fields a node needs are populated; unselected agents stay None.
"""
from typing import Optional, List
from dataclasses import dataclass, field


@dataclass
class AgentState:
    # ── Input ──────────────────────────────────────────────
    pair:        str  = ""
    price_data:  dict = field(default_factory=dict)
    indicators:  dict = field(default_factory=dict)
    news_text:   str  = ""

    # ── Router decision (zero LLM tokens) ─────────────────
    selected_agents: List[str] = field(default_factory=list)
    skipped_agents:  List[str] = field(default_factory=list)
    routing_reason:  str       = ""

    # ── Agent results (None = skipped this cycle) ──────────
    academic_result:      Optional[str] = None
    geopolitical_result:  Optional[str] = None
    quantitative_result:  Optional[str] = None
    user_result:          Optional[str] = None

    # ── Final decision ─────────────────────────────────────
    final_decision: Optional[dict] = None
