"""
Telegram Bot Service
Sends trading signals to your Telegram chat
"""
import os
from datetime import datetime
from dotenv import load_dotenv
from telegram import Bot
from telegram.error import TelegramError

load_dotenv()  # Ensure .env is loaded before reading tokens


class TelegramService:
    """
    Send trading signals, alerts, and reports to Telegram
    """
    
    def __init__(self):
        self.token = os.getenv("TELEGRAM_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        
        if not self.token or not self.chat_id:
            print("[Telegram] WARNING: TELEGRAM_TOKEN or TELEGRAM_CHAT_ID not set in .env")
            self.bot = None
        else:
            self.bot = Bot(token=self.token)
    
    async def send_signal(self, agent_name: str, pair: str, decision: str, confidence: int, 
                         entry: float = None, stop: float = None, target: float = None, 
                         reasoning: str = None) -> bool:
        """
        Send trading signal to Telegram
        
        Example:
        🟢 Boss Agent
        ━━━━━━━━━━━━━━━━━
        Pair: NIFTY
        Decision: BUY
        Confidence: 82%
        ━━━━━━━━━━━━━━━━━
        Entry: 24175
        Stop Loss: 24050
        Target: 24300
        ━━━━━━━━━━━━━━━━━
        Reasoning: [2-line summary]
        """
        if not self.bot:
            print("[Telegram] Bot not initialized")
            return False
        
        try:
            # Decision emoji
            emoji_map = {
                "BUY": "🟢",
                "SELL": "🔴",
                "HOLD": "🟡",
                "STRONG BUY": "🟢🟢",
                "STRONG SELL": "🔴🔴"
            }
            emoji = emoji_map.get(decision, "⚪")
            
            # Clean reasoning - remove markdown tables and headers
            clean_reasoning = ""
            if reasoning:
                lines = reasoning.split('\n')
                clean_lines = []
                for line in lines:
                    # Skip table rows, headers, dividers
                    if '|' in line or line.startswith('#') or line.startswith('---'):
                        continue
                    line = line.strip()
                    if line and len(line) > 10:
                        clean_lines.append(line)
                clean_reasoning = ' '.join(clean_lines[:2])[:200]  # Max 2 sentences

            # Format message
            message = (
                f"{emoji} *{agent_name}*\n"
                f"━━━━━━━━━━━━━━━━━\n"
                f"*Symbol:* {pair}\n"
                f"*Decision:* {decision}\n"
                f"*Confidence:* {confidence}%\n"
                f"━━━━━━━━━━━━━━━━━\n"
                f"*Entry:* {entry if entry else 'N/A'}\n"
                f"*Stop Loss:* {stop if stop else 'N/A'}\n"
                f"*Target:* {target if target else 'N/A'}\n"
            )
            if clean_reasoning:
                message += f"━━━━━━━━━━━━━━━━━\n*Reasoning:* {clean_reasoning}\n"

            message += f"━━━━━━━━━━━━━━━━━\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}"
            
            # Send to Telegram
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode="Markdown"
            )
            
            print(f"[Telegram] Signal sent: {agent_name} - {pair} - {decision}")
            return True
        
        except TelegramError as e:
            print(f"[Telegram] ERROR: {e}")
            return False
        except Exception as e:
            print(f"[Telegram] Service error: {str(e)}")
            return False
    
    async def send_error(self, title: str, error_msg: str) -> bool:
        """Send error alert to Telegram"""
        if not self.bot:
            return False
        
        try:
            message = f"""⚠️ *ERROR ALERT*
━━━━━━━━━━━━━━━━━
*Type:* {title}
*Message:* {error_msg}
━━━━━━━━━━━━━━━━━
⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
            
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode="Markdown"
            )
            return True
        except Exception as e:
            print(f"Error sending Telegram alert: {e}")
            return False
    
    async def send_daily_report(self, stats: dict) -> bool:
        """Send daily trading report"""
        if not self.bot:
            return False
        
        try:
            message = f"""📊 *DAILY TRADING REPORT*
━━━━━━━━━━━━━━━━━
*Signals Generated:* {stats.get('total_signals', 0)}
*Win Rate:* {stats.get('win_rate', 0):.1f}%
*Best Agent:* {stats.get('best_agent', 'N/A')}
*Total P&L:* {stats.get('pnl', 0):.2f}%
*Average Confidence:* {stats.get('avg_confidence', 0):.1f}%
━━━━━━━━━━━━━━━━━
📈 Top Signal: {stats.get('top_signal', 'N/A')}
━━━━━━━━━━━━━━━━━
⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
            
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode="Markdown"
            )
            return True
        except Exception as e:
            print(f"Error sending daily report: {e}")
            return False
    
    async def send_market_update(self, market_data: dict) -> bool:
        """Send market status update"""
        if not self.bot:
            return False
        
        try:
            nifty_change = market_data.get('nifty_change_pct', 0)
            emoji = "🟢" if nifty_change >= 0 else "🔴"
            
            message = f"""{emoji} *MARKET STATUS*
━━━━━━━━━━━━━━━━━
*NIFTY:* {market_data.get('nifty_price', 'N/A')} ({nifty_change:+.2f}%)
*SENSEX:* {market_data.get('sensex_price', 'N/A')} ({market_data.get('sensex_change', 0):+.2f}%)
*VIX:* {market_data.get('vix', 'N/A')}
━━━━━━━━━━━━━━━━━
*FII Flow:* ₹{market_data.get('fii_flow', 0)}Cr
*DII Flow:* ₹{market_data.get('dii_flow', 0)}Cr
━━━━━━━━━━━━━━━━━
⏰ {datetime.now().strftime('%H:%M:%S')}"""
            
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode="Markdown"
            )
            return True
        except Exception as e:
            print(f"Error sending market update: {e}")
            return False
    
    async def send_test_message(self) -> bool:
        """Send startup message to verify connection"""
        if not self.bot:
            return False
        
        try:
            message = (
                "🔱 *Arun-Dev Trading System ONLINE*\n"
                "━━━━━━━━━━━━━━━━━\n"
                "Monitoring: NIFTY | SENSEX | BTC | EUR/USD\n"
                "AI Engine: Groq -> OpenRouter -> Gemini (auto-fallback)\n"
                "Agent Loop: Every 15 minutes\n"
                "━━━━━━━━━━━━━━━━━\n"
                f"Started: {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}"
            )
            
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode="Markdown"
            )
            print("[Telegram] Startup message sent successfully")
            return True
        except Exception as e:
            print(f"[Telegram] Failed to send startup message: {e}")
            return False


