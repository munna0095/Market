"""
Memory Manager — Persistent rolling memory for each AI agent.
Each agent stores its decisions in a JSON file under backend/memory/.
Agents can read their past decisions to learn, detect bias, and improve.
"""
import json
import os
from datetime import datetime


class MemoryManager:
    def __init__(self, agent_name: str, max_entries: int = 50):
        self.agent_name = agent_name
        self.max_entries = max_entries
        # Memory stored at backend/memory/
        self.memory_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "memory"
        )
        os.makedirs(self.memory_dir, exist_ok=True)
        safe_name = agent_name.lower().replace(" ", "_").replace("/", "_")
        self.memory_file = os.path.join(self.memory_dir, f"{safe_name}_memory.json")
        self.memory = self._load()

    def _load(self) -> list:
        if os.path.exists(self.memory_file):
            try:
                with open(self.memory_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def _persist(self):
        try:
            with open(self.memory_file, "w", encoding="utf-8") as f:
                json.dump(self.memory, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[Memory] Failed to persist for {self.agent_name}: {e}")

    def save_decision(
        self,
        pair: str,
        decision: str,
        reasoning: str,
        price: float,
        indicators: dict = None,
        confidence: int = 50
    ) -> dict:
        """Save a trading decision to memory."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "pair": pair,
            "decision": decision.upper(),
            "reasoning": reasoning[:300],
            "price": price,
            "confidence": confidence,
            "indicators": indicators or {}
        }
        self.memory.append(entry)
        # Rolling window — keep only the last max_entries
        if len(self.memory) > self.max_entries:
            self.memory = self.memory[-self.max_entries:]
        self._persist()
        return entry

    def get_recent(self, n: int = 10, pair: str = None) -> list:
        """Return the n most recent decisions, optionally filtered by pair."""
        if pair:
            filtered = [m for m in self.memory if m.get("pair") == pair]
            return filtered[-n:]
        return self.memory[-n:]

    def get_summary(self, pair: str = None, n: int = 5) -> str:
        """Return a human-readable summary of past decisions for prompt injection."""
        recent = self.get_recent(n, pair)
        if not recent:
            return "No past decisions recorded yet. This is your first analysis."
        lines = []
        for m in recent:
            ts = m["timestamp"][:16].replace("T", " ")
            rsi = m.get("indicators", {}).get("rsi", "?")
            trend = m.get("indicators", {}).get("trend", "?")
            lines.append(
                f"  [{ts}] {m['pair']} → {m['decision']} "
                f"@ {m['price']} | RSI:{rsi} Trend:{trend} "
                f"| Confidence:{m.get('confidence', '?')}%"
            )
        return "\n".join(lines)

    def get_bias(self, pair: str, n: int = 5) -> str:
        """Detect bullish/bearish bias from recent decisions."""
        recent = self.get_recent(n, pair)
        if not recent:
            return "neutral (no history)"
        decisions = [m["decision"].upper() for m in recent]
        buys = sum(1 for d in decisions if "BUY" in d)
        sells = sum(1 for d in decisions if "SELL" in d)
        holds = sum(1 for d in decisions if "HOLD" in d)
        total = len(decisions)
        if buys > sells and buys > holds:
            return f"BULLISH (Buy {buys}/{total} recent calls)"
        elif sells > buys and sells > holds:
            return f"BEARISH (Sell {sells}/{total} recent calls)"
        return f"NEUTRAL (Hold {holds}/{total} recent calls)"

    def get_streak(self, pair: str) -> str:
        """Detect if agent is on a consistent decision streak."""
        recent = self.get_recent(5, pair)
        if len(recent) < 3:
            return "insufficient history"
        last = recent[-1]["decision"]
        streak = sum(1 for m in recent if m["decision"] == last)
        return f"{last} streak: {streak} consecutive calls"

    def count(self) -> int:
        return len(self.memory)
