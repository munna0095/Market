import os
import sqlite3
from datetime import date
from groq import AsyncGroq
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

GROQ_MODEL   = "llama-3.3-70b-versatile"
GEMINI_MODEL = "gemini-flash-latest"
DB_PATH      = "trading_signals.db"


def _load_token_log() -> dict[str, int]:
    """Load today's token usage from DB on startup."""
    today = date.today().isoformat()
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS token_usage (
                    date TEXT, provider TEXT, tokens INTEGER,
                    PRIMARY KEY (date, provider)
                )
            """)
            rows = conn.execute(
                "SELECT provider, tokens FROM token_usage WHERE date=?", (today,)
            ).fetchall()
            return {r[0]: r[1] for r in rows} if rows else {"groq": 0, "openrouter": 0, "gemini": 0}
    except Exception:
        return {"groq": 0, "openrouter": 0, "gemini": 0}


# Loaded from DB on import — survives restarts within the same calendar day
_token_log: dict[str, int] = _load_token_log()

DAILY_BUDGETS = {
    "groq":       450_000,
    "gemini":     800_000,
    "openrouter": 99_999_999,
}


def _provider_ok(provider_key: str) -> bool:
    used = _token_log.get(provider_key, 0)
    limit = DAILY_BUDGETS.get(provider_key, 99_999_999)
    return used < limit


def _track(provider: str, tokens: int, agent_name: str) -> None:
    prev = _token_log.get(provider, 0)
    _token_log[provider] = prev + tokens
    today = date.today().isoformat()
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""
                INSERT INTO token_usage (date, provider, tokens) VALUES (?, ?, ?)
                ON CONFLICT(date, provider) DO UPDATE SET tokens=tokens + ?
            """, (today, provider, tokens, tokens))
    except Exception:
        pass
    print(f"[TOKEN] {provider} | +{tokens} | total_today={_token_log[provider]} | agent={agent_name}")
    if provider == "groq" and _token_log["groq"] > 400_000:
        if prev <= 400_000:
            print("[BUDGET WARNING] Groq at 80% daily limit (400K/450K)")


class BaseAgent:
    def __init__(self, name, model_name=GROQ_MODEL, system_instruction=""):
        self.name       = name
        self.model_name = model_name   # stored for subclass inspection
        self._system_instruction = system_instruction
        self._groq   = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))
        self._gemini = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    async def _call_groq(self, prompt: str) -> str:
        messages = []
        if self._system_instruction:
            messages.append({"role": "system", "content": self._system_instruction})
        messages.append({"role": "user", "content": prompt})
        resp = await self._groq.chat.completions.create(
            model=GROQ_MODEL,
            messages=messages,
            temperature=0.7,
            max_tokens=2048,
        )
        try:
            _track("groq", resp.usage.total_tokens, self.name)
        except Exception:
            pass
        return resp.choices[0].message.content

    async def _call_gemini(self, prompt: str) -> str:
        resp = await self._gemini.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=self._system_instruction,
            ),
        )
        try:
            _track("gemini", resp.usage_metadata.total_token_count, self.name)
        except Exception:
            pass
        return resp.text

    async def _call_openrouter(self, prompt: str, model: str) -> str:
        """Call OpenRouter FREE models - one key for 100+ models"""
        import httpx
        headers = {
            "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://168.144.64.203",
            "X-Title": "Arun-Dev Trading System"
        }
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": self._system_instruction},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 1500
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload
            )
            resp.raise_for_status()
            data = resp.json()
        try:
            tokens = data.get("usage", {}).get("total_tokens", 0)
            if tokens:
                _track("openrouter", tokens, self.name)
        except Exception:
            pass
        return data["choices"][0]["message"]["content"]

    async def get_response(self, prompt: str) -> str:
        import asyncio
        providers = [
            ("groq",     "groq",       lambda: self._call_groq(prompt)),
            ("nemotron", "openrouter", lambda: self._call_openrouter(prompt, "nvidia/nemotron-3-super-120b-a12b:free")),
            ("hy3",      "openrouter", lambda: self._call_openrouter(prompt, "tencent/hy3-preview:free")),
            ("gemini",   "gemini",     lambda: self._call_gemini(prompt)),
        ]
        for name, pkey, call in providers:
            if not _provider_ok(pkey):
                print(f"[{self.name}] {name} BUDGET EXHAUSTED — skipping")
                continue
            try:
                result = await asyncio.wait_for(call(), timeout=20.0)
                if result is None:
                    raise ValueError("Provider returned None")
                print(f"[{self.name}] SUCCESS via {name}")
                return result
            except asyncio.TimeoutError:
                print(f"[{self.name}] {name} TIMEOUT(20s) — trying next")
            except Exception as e:
                print(f"[{self.name}] {name} failed: {str(e)[:80]} — trying next")

        print(f"[{self.name}] ALL providers failed")
        return "ANALYSIS_UNAVAILABLE: All providers exhausted"
