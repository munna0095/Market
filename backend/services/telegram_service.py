"""
Telegram Bot Service - Arun-Dev Strategic War Room
All emojis via Unicode escapes only - no literal emoji bytes in source.
"""
import os
from datetime import datetime
from dotenv import load_dotenv
from telegram import Bot
from telegram.error import TelegramError

load_dotenv()

SEP     = "━" * 17        # thick line: ━━━━━━━━━━━━━━━━━
IST_FMT = "%d-%m-%Y %H:%M:%S"

# emoji constants
_PHONE   = "\U0001f4f1"   # 📱
_WARN    = "⚠️"  # ⚠️
_OK      = "✅"        # ✅
_FAIL    = "❌"        # ❌
_GREEN   = "\U0001f7e2"   # 🟢
_RED     = "\U0001f534"   # 🔴
_YELLOW  = "\U0001f7e1"   # 🟡
_CLOCK   = "⏰"        # ⏰
_TROPHY  = "\U0001f3c6"   # 🏆
_CHART   = "\U0001f4ca"   # 📊
_ARROW   = "→"        # →
_TREND   = "\U0001f4c8"   # 📈


class TelegramService:

    def __init__(self):
        self.token   = os.getenv("TELEGRAM_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        if not self.token or not self.chat_id:
            print("[Telegram] WARNING: TELEGRAM_TOKEN or TELEGRAM_CHAT_ID not set")
            self.bot = None
        else:
            self.bot = Bot(token=self.token)

    async def _send(self, text: str) -> bool:
        """Internal - raw send with Markdown. All public methods call this."""
        if not self.bot:
            print("[Telegram] Bot not initialized - skipping")
            return False
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=text,
                parse_mode="Markdown",
            )
            return True
        except TelegramError as e:
            print(f"[Telegram] TelegramError: {e}")
            return False
        except Exception as e:
            print(f"[Telegram] Error: {e}")
            return False

    # ── PUBLIC API ────────────────────────────────────────────────────

    async def send_message(self, text: str) -> bool:
        """Plain text message."""
        return await self._send(text)

    async def send_test_message(self) -> bool:
        """System startup notification."""
        now = datetime.now().strftime(IST_FMT)
        msg = (
            f"{_PHONE} *Arun-Dev Strategic War Room ONLINE*\n"
            f"{SEP}\n"
            f"Monitoring: NIFTY | SENSEX | BTC/USD | EUR/USD\n"
            f"AI Engine: Groq {_ARROW} OpenRouter {_ARROW} Gemini (auto-fallback)\n"
            f"Session: 9:20-10:30 AM & 1:30-2:30 PM IST only\n"
            f"{SEP}\n"
            f"{_CLOCK} Started: {now} IST"
        )
        ok = await self._send(msg)
        if ok:
            print("[Telegram] Startup message sent")
        return ok

    async def send_watchdog_alert(self, restarted_loops: list) -> bool:
        """Watchdog auto-heal notification."""
        loops_str = ", ".join(restarted_loops)
        now = datetime.now().strftime(IST_FMT)
        msg = (
            f"{_WARN} *WATCHDOG ALERT*\n"
            f"{SEP}\n"
            f"*Restarted:* {loops_str}\n"
            f"*Status:*    System self-healed {_OK}\n"
            f"{SEP}\n"
            f"{_CLOCK} {now} IST"
        )
        ok = await self._send(msg)
        if ok:
            print(f"[Telegram] Watchdog alert sent: {loops_str}")
        return ok

    async def send_signal(self, agent_name: str, pair: str, decision: str,
                          confidence: int, entry: float = None,
                          stop: float = None, target: float = None,
                          reasoning: str = None) -> bool:
        """Trading signal notification."""
        emoji_map = {
            "BUY":         _GREEN,
            "STRONG BUY":  _GREEN + _GREEN,
            "SELL":        _RED,
            "STRONG SELL": _RED + _RED,
            "HOLD":        _YELLOW,
        }
        emoji = emoji_map.get(decision, "?")

        rr = "N/A"
        try:
            if entry and stop and target and float(stop) != float(entry):
                ratio = abs(
                    (float(target) - float(entry)) /
                    (float(entry)  - float(stop))
                )
                rr = f"1:{round(ratio, 1)}"
        except Exception:
            pass

        clean = ""
        if reasoning:
            lines = [
                l.strip() for l in reasoning.split("\n")
                if l.strip()
                and "|" not in l
                and not l.startswith("#")
                and not l.startswith("---")
                and len(l.strip()) > 10
            ]
            clean = " ".join(lines[:2])[:200]

        now = datetime.now().strftime(IST_FMT)
        msg = (
            f"{emoji} *{agent_name}*\n"
            f"{SEP}\n"
            f"*Symbol:*     {pair}\n"
            f"*Decision:*   {decision}\n"
            f"*Confidence:* {confidence}%\n"
            f"{SEP}\n"
            f"*Entry:*      {entry if entry is not None else 'N/A'}\n"
            f"*Stop Loss:*  {stop if stop is not None else 'N/A'}\n"
            f"*Target:*     {target if target is not None else 'N/A'}\n"
            f"*R:R:*        {rr}\n"
        )
        if clean:
            msg += f"{SEP}\n*Reasoning:* {clean}\n"
        msg += f"{SEP}\n{_CLOCK} {now} IST"

        ok = await self._send(msg)
        if ok:
            print(f"[Telegram] Signal sent: {agent_name} {pair} {decision}")
        return ok

    async def send_outcome(self, pair: str, decision: str, outcome: str,
                           entry: float, exit_price: float) -> bool:
        """WIN / LOSS outcome notification."""
        if outcome == "WIN":
            emoji       = _OK
            result_line = f"*Result:* WIN {_TROPHY}"
        else:
            emoji       = _FAIL
            result_line = "*Result:* LOSS"

        try:
            pnl_pct = round(
                ((float(exit_price) - float(entry)) / float(entry)) * 100, 3
            )
            pnl_str = f"{pnl_pct:+.3f}%"
        except Exception:
            pnl_str = "N/A"

        now = datetime.now().strftime(IST_FMT)
        msg = (
            f"{emoji} *OUTCOME: {pair}*\n"
            f"{SEP}\n"
            f"*Signal:* {decision}\n"
            f"*Entry:*  {entry}\n"
            f"*Exit:*   {exit_price}\n"
            f"*Move:*   {pnl_str}\n"
            f"{SEP}\n"
            f"{result_line}\n"
            f"{SEP}\n"
            f"{_CLOCK} {now} IST"
        )
        return await self._send(msg)

    async def send_error(self, title: str, error_msg: str) -> bool:
        """Error alert notification."""
        now = datetime.now().strftime(IST_FMT)
        msg = (
            f"{_WARN} *ERROR ALERT*\n"
            f"{SEP}\n"
            f"*Type:*    {title}\n"
            f"*Message:* {error_msg[:300]}\n"
            f"{SEP}\n"
            f"{_CLOCK} {now} IST"
        )
        return await self._send(msg)

    async def send_daily_report(self, stats: dict) -> bool:
        """Daily trading report."""
        now = datetime.now().strftime(IST_FMT)
        msg = (
            f"{_CHART} *DAILY TRADING REPORT*\n"
            f"{SEP}\n"
            f"*Signals:*    {stats.get('total_signals', 0)}\n"
            f"*Win Rate:*   {stats.get('win_rate', 0):.1f}%\n"
            f"*Best Agent:* {stats.get('best_agent', 'N/A')}\n"
            f"*Avg Conf:*   {stats.get('avg_confidence', 0):.1f}%\n"
            f"{SEP}\n"
            f"{_TREND} Top Signal: {stats.get('top_signal', 'N/A')}\n"
            f"{SEP}\n"
            f"{_CLOCK} {now} IST"
        )
        return await self._send(msg)
