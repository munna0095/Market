"""
Strategic War Room — FastAPI Backend v3.0
TWO SEPARATE LOOPS:
  1. price_loop()  → runs every 5 seconds  (prices only, fast)
  2. agent_loop()  → runs every 60 seconds (AI analysis, slow)
This gives real-time price updates without AI blocking the feed.
"""
import asyncio
import json
import os
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv
load_dotenv()  # Load .env FIRST before any service initializes
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from services.trading_service import TradingService
from services.sentiment_service import SentimentService
from services.yfinance_service import YFinanceService
from services.nse_service import NSEService
from services.telegram_service import TelegramService
from agents.market_data_agent import MarketDataAgent
from agents.academic_agent import AcademicAgent
from agents.geopolitical_agent import GeopoliticalAgent
from agents.user_insight_agent import UserInsightAgent
from agents.quantitative_agent import QuantitativeAgent
from agents.orchestrator import OrchestratorAgent
from agents.graph_orchestrator import GraphOrchestrator
from services.world_feed import WorldFeedService
from agents.base_agent import _token_log
from services.database_service import (
    init_db, save_signal, get_signal_history, get_win_rate_by_pair
)

app = FastAPI(title="Strategic War Room — AI Trading Hub v3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Services & Agents ──────────────────────────────────────────────────────────
trading_service   = TradingService()
sentiment_service = SentimentService()
yf_service        = YFinanceService()
nse_service       = NSEService()
telegram_service  = TelegramService()
market_data_agent = MarketDataAgent()
academic_agent    = AcademicAgent()
geopolitical_agent= GeopoliticalAgent()
user_insight_agent= UserInsightAgent()
quantitative_agent= QuantitativeAgent()
orchestrator      = OrchestratorAgent()
world_feed_service = WorldFeedService()

# ── Graph Orchestrator (replaces manual sequential agent calls) ───────────────
graph = GraphOrchestrator(
    academic     = academic_agent,
    geo          = geopolitical_agent,
    quant        = quantitative_agent,
    user         = user_insight_agent,
    orchestrator = orchestrator,
)

_latest_signals: dict = {}
_world_news_cache: str = "Initializing global intelligence feed..."
MONITORED_PAIRS = ["EUR/USD", "USD/JPY", "BTC/USD", "NIFTY", "SENSEX"]


# ── WebSocket Connection Manager ───────────────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"[WS] Connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        print(f"[WS] Disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: str):
        dead = []
        for conn in self.active_connections:
            try:
                await conn.send_text(message)
            except Exception:
                dead.append(conn)
        for d in dead:
            self.disconnect(d)

manager = ConnectionManager()

# ── REST Endpoints ─────────────────────────────────────────────────────────────
@app.get("/")
def read_root():
    return {"status": "running", "message": "Strategic War Room API v3.0"}

@app.get("/portfolio")
@app.get("/api/portfolio")
def get_portfolio():
    return trading_service.get_status()

@app.get("/api/history/{pair}/{timeframe}")
async def get_history(pair: str, timeframe: str):
    p = pair.replace("_", "/").upper()
    if "/" not in p and len(p) == 6:
        p = p[:3] + "/" + p[3:]
    actual_pair = p
    resolution_map = {
        "1M": "1", "1": "1", "5M": "5", "5": "5",
        "15M": "15", "15": "15", "30M": "30", "30": "30",
        "1H": "60", "60": "60", "4H": "240", "240": "240",
        "1D": "D", "D": "D", "1W": "W", "W": "W"
    }
    resolution = resolution_map.get(timeframe.upper(), "D")
    try:
        candles = await market_data_agent.get_candles(actual_pair, resolution)
        return {"data": candles, "pair": actual_pair, "timeframe": timeframe, "count": len(candles)}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e), "data": []})

@app.get("/api/news")
async def get_news():
    try:
        news = await market_data_agent.get_forex_news()
        return {"data": news, "count": len(news)}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e), "data": []})

@app.get("/api/signals")
def get_signals():
    return {"signals": _latest_signals}

@app.get("/api/prices")
async def get_prices():
    prices = await market_data_agent.get_all_prices(MONITORED_PAIRS)
    return {"data": prices}

@app.get("/api/watchlist_prices")
async def get_watchlist_prices():
    from services.yfinance_service import YF_SYMBOLS
    pairs = list(YF_SYMBOLS.keys())
    results = await asyncio.gather(*[yf_service.get_price(p) for p in pairs], return_exceptions=True)
    data = {}
    for pair, r in zip(pairs, results):
        if isinstance(r, dict) and r:
            data[pair] = {"price": r["price"], "change_pct": r["change_pct"]}
    return {"data": data}

@app.get("/api/indicators/{pair}")
async def get_indicators(pair: str):
    actual_pair = pair.replace("_", "/").upper()
    indicators = await market_data_agent.get_indicators(actual_pair, "D")
    return {"pair": actual_pair, "indicators": indicators}

from services.backtest_service import run_backtest

@app.get("/api/backtest")
async def get_backtest(pair: str = "BTC/USD"):
    supported = ["EUR/USD", "USD/JPY", "BTC/USD", "NIFTY", "SENSEX"]
    if pair not in supported:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"Unsupported pair. Use: {supported}")
    try:
        result = await asyncio.to_thread(run_backtest, pair)
        return result
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/signals/history")
async def signals_history_endpoint(pair: str = None, limit: int = 50):
    """Return recent agent signals with outcomes."""
    return get_signal_history(pair=pair, limit=limit)

@app.get("/api/signals/performance")
async def signals_performance_endpoint():
    """Return WIN/LOSS performance summary per pair."""
    return get_win_rate_by_pair()

@app.get("/api/token-usage")
async def get_token_usage():
    return {
        "groq":              _token_log["groq"],
        "openrouter":        _token_log["openrouter"],
        "gemini":            _token_log["gemini"],
        "total_today":       sum(_token_log.values()),
        "groq_limit":        500_000,
        "gemini_limit":      1_000_000,
        "groq_remaining":    500_000  - _token_log["groq"],
        "gemini_remaining":  1_000_000 - _token_log["gemini"],
    }

@app.post("/api/refresh_agents")
async def refresh_agents_endpoint(pair: str = "EUR/USD"):
    """Trigger immediate agent analysis for one pair — NO Telegram (manual refresh)."""
    actual_pair = pair.replace("_", "/").upper()
    try:
        market_summary = await market_data_agent.get_market_summary([actual_pair])
        news_text = market_summary.get("news_text", "")
        await _run_agents_for_pair(actual_pair, market_summary, news_text, send_telegram=False)
        return {"status": "ok", "pair": actual_pair,
                "signal": _latest_signals.get(actual_pair, {})}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ── TradingView Webhook ────────────────────────────────────────────────────────

class TradingViewAlert(BaseModel):
    symbol: str
    price: float
    rsi: Optional[float] = None
    ema9: Optional[float] = None
    ema21: Optional[float] = None
    ema50: Optional[float] = None
    macd: Optional[float] = None
    volume: Optional[float] = None
    timeframe: Optional[str] = "10"
    strategy: Optional[str] = "Trinetra"
    high: Optional[float] = None
    low: Optional[float] = None
    open: Optional[float] = None


@app.post("/webhook/tradingview")
async def tradingview_webhook(alert: TradingViewAlert):
    """
    Receives alert from TradingView Pine Script.
    Instantly runs agents and sends Telegram signal.
    """
    print(f"[WEBHOOK] TradingView alert: {alert.symbol} @ {alert.price}")

    symbol_map = {
        "NIFTY": "NIFTY",
        "NSE:NIFTY1!": "NIFTY",
        "NSEIX:NIFTY1!": "NIFTY",
        "SENSEX": "SENSEX",
        "BTCUSDT": "BTC/USD",
        "EURUSD": "EUR/USD",
    }
    pair = symbol_map.get(alert.symbol.upper(), alert.symbol.upper())

    try:
        # ── Log market status for Indian indices (no early return — TV alert always runs agents) ──
        from services.nse_service import is_nse_market_open, NSE_PAIRS
        if pair in NSE_PAIRS:
            market_status = is_nse_market_open()
            if not market_status["is_open"]:
                print(f"[WEBHOOK] {pair} — {market_status['status']} — running analysis on TV price {alert.price}")

        market_summary = await market_data_agent.get_market_summary([pair])
        news_text = market_summary.get("news_text", "")

        # If market is closed / price unavailable, inject alert's own price data
        pair_data = market_summary.setdefault("pairs", {}).setdefault(pair, {})
        if not pair_data.get("price_data"):
            pair_data["price_data"] = {
                "price":      alert.price,
                "high":       alert.high  or alert.price,
                "low":        alert.low   or alert.price,
                "open":       alert.open  or alert.price,
                "change_pct": 0.0,
                "source":     "TradingView",
            }
            print(f"[WEBHOOK] Using TV price data for {pair}: {alert.price}")

        # Inject TradingView indicator values if provided
        indicators = pair_data.setdefault("indicators", {})
        if alert.rsi:    indicators["rsi"]    = alert.rsi
        if alert.ema9:   indicators["ema9"]   = alert.ema9
        if alert.ema21:  indicators["ema21"]  = alert.ema21
        if alert.ema50:  indicators["ema50"]  = alert.ema50
        if alert.macd:   indicators["macd"]   = alert.macd
        if alert.volume: indicators["volume"] = alert.volume
        if alert.rsi or alert.ema9:
            print(f"[WEBHOOK] Injected TV indicators: RSI={alert.rsi}, EMA9={alert.ema9}")

        signal_before = _latest_signals.get(pair, {}).get("decision")
        await _run_agents_for_pair(pair, market_summary, news_text, send_telegram=True, force_run=True)
        signal = _latest_signals.get(pair, {})
        decision = signal.get("decision")

        # Detect if agents failed (signal unchanged or still shows closed-market status)
        agents_failed = (decision == signal_before) or (decision in ("MARKET CLOSED", "PRE-MARKET", None))
        print(f"[WEBHOOK] Result: {pair} -> {decision} {signal.get('confidence')}% | agents_failed={agents_failed}")

        if agents_failed:
            return {
                "ok":       True,
                "pair":     pair,
                "decision": "NO_SIGNAL",
                "confidence": 0,
                "price":    alert.price,
                "reason":   "All AI providers busy or quota exceeded — try again in a few minutes",
            }
        return {
            "ok":         True,
            "pair":       pair,
            "decision":   decision,
            "confidence": signal.get("confidence"),
            "price":      alert.price,
        }

    except Exception as e:
        print(f"[WEBHOOK ERROR] {e}")
        await telegram_service.send_error("Webhook Error", str(e)[:100])
        return {"ok": False, "error": str(e)}


@app.get("/webhook/test")
async def test_webhook():
    """Test that the webhook endpoint is live."""
    return {
        "status": "Webhook endpoint active",
        "endpoint": "POST /webhook/tradingview",
        "test_payload": {
            "symbol": "NIFTY",
            "price": 24000,
            "rsi": 45.5,
            "ema9": 23950,
            "ema21": 23800,
            "ema50": 23500,
            "timeframe": "10",
        },
    }


# ── WebSocket Endpoint ─────────────────────────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        await websocket.send_text(json.dumps({
            "type": "portfolio_update",
            "portfolio": trading_service.get_status()
        }))
        if _latest_signals:
            await websocket.send_text(json.dumps({
                "type": "signals_snapshot", "signals": _latest_signals
            }))
        while True:
            data = await websocket.receive_text()
            msg  = json.loads(data)
            msg_type = msg.get("type")

            if msg_type == "user_insight":
                content = msg.get("content", "").strip()
                if content:
                    os.makedirs("user_insights", exist_ok=True)
                    ts = int(asyncio.get_event_loop().time())
                    with open(f"user_insights/web_input_{ts}.txt", "w", encoding="utf-8") as f:
                        f.write(content)
                    print(f"[WS] Insight saved: {content[:50]}...")

            elif msg_type == "execute_trade":
                symbol = msg.get("symbol", "EUR/USD")
                side   = msg.get("side", "buy")
                amount = float(msg.get("amount", 1000))
                price  = float(msg.get("price", 0))
                success, result_msg = trading_service.execute_trade(symbol, side, amount, price)
                await manager.broadcast(json.dumps({
                    "type": "portfolio_update",
                    "portfolio": trading_service.get_status()
                }))
                await manager.broadcast(json.dumps({
                    "type": "system_status",
                    "status": "info" if success else "warning",
                    "message": f"Trade {side.upper()} {symbol} @ {price}: {result_msg}"
                }))

            elif msg_type == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"[WS] Error: {e}")
        manager.disconnect(websocket)


# ── LOOP 1: Fast Price Loop (every 5 seconds) ──────────────────────────────────
async def price_loop():
    """
    Runs every 5 seconds. Fetches ONLY prices — no AI, no blocking.
    Gives near real-time price updates to the UI.
    """
    print("[Price Loop] Starting — 1s interval")
    while True:
        try:
            for pair in MONITORED_PAIRS:
                price_data = await market_data_agent.get_realtime_price(pair)
                if not price_data:
                    continue
                indicators = market_data_agent._indicators_cache.get(pair, {})
                await manager.broadcast(json.dumps({
                    "type":       "price_update",
                    "symbol":     pair,
                    "price":      price_data.get("price", 0),
                    "change_pct": price_data.get("change_pct", 0),
                    "high":       price_data.get("high", 0),
                    "low":        price_data.get("low", 0),
                    "source":     price_data.get("source", "Live"),
                    "indicators": indicators
                }))
        except Exception as e:
            print(f"[Price Loop] Error: {e}")
        await asyncio.sleep(1)   # ← 1 second refresh (fast)

# ── Shared helper: run graph agents for one pair and broadcast results ─────────
async def _run_agents_for_pair(target_pair: str, market_summary: dict,
                                news_text: str, send_telegram: bool = True,
                                force_run: bool = False) -> None:
    from services.nse_service import is_nse_market_open, NSE_PAIRS

    # ── Market closed check for Indian indices (skipped when force_run=True, e.g. webhook) ──
    if target_pair in NSE_PAIRS and not force_run:
        market_status = is_nse_market_open()
        if not market_status["is_open"]:
            status_msg = (
                f"[{target_pair}] {market_status['status']} — "
                f"{market_status['reason']} | "
                f"Next open: {market_status.get('next_open', 'N/A')} | "
                f"IST: {market_status['current_time_ist']}"
            )
            print(status_msg)
            # Store a clear closed status in signals
            _latest_signals[target_pair] = {
                "decision":   market_status["status"],
                "confidence": 0,
                "risk_level": "N/A",
                "price":      market_summary.get("pairs", {}).get(target_pair, {}).get("price_data", {}).get("price", 0),
                "reason":     market_status["reason"],
                "next_open":  market_status.get("next_open"),
                "market_ist": market_status["current_time_ist"],
            }
            return  # Skip agents for closed market
    pair_data  = market_summary.get("pairs", {}).get(target_pair, {})
    price_data = pair_data.get("price_data")
    indicators = pair_data.get("indicators", {})
    if not price_data:
        print(f"[Agent Loop] No price data for {target_pair}, skipping")
        return
    try:
        final = await graph.run(
            pair       = target_pair,
            price_data = price_data,
            indicators = indicators,
            news_text  = news_text + "\n\n" + _world_news_cache,
        )
        selected = final.get("selected_agents", [])
        skipped  = final.get("skipped_agents",  [])
        print(f"[Graph] {target_pair} | ran={selected} | skipped={skipped}")

        # Broadcast individual agent thoughts
        agent_result_map = {
            academic_agent.name:     final.get("_academic_result"),
            geopolitical_agent.name: final.get("_geo_result"),
            user_insight_agent.name: final.get("_user_result"),
            quantitative_agent.name: final.get("_quant_result"),
        }
        for agent_name, thought in agent_result_map.items():
            if thought:
                await manager.broadcast(json.dumps({
                    "type":  "agent_thought",
                    "agent": agent_name,
                    "thought": thought,
                    "pair":  target_pair,
                    "price": price_data.get("price", 0),
                }))

        _latest_signals[target_pair] = {
            "decision":        final["decision"],
            "confidence":      final["confidence"],
            "risk_level":      final["risk_level"],
            "price":           final["price"],
            "selected_agents": selected,
            "skipped_agents":  skipped,
        }

        # Persist signal to database
        decision   = final.get("decision", "HOLD")
        confidence = int(final.get("confidence", 0))
        try:
            def _safe_float(val):
                """Extract scalar float from any value safely."""
                if val is None:
                    return None
                if isinstance(val, dict):
                    val = list(val.values())[0] if val else None
                try:
                    return float(val)
                except (TypeError, ValueError):
                    return None

            sig_id = save_signal(
                pair       = target_pair,
                decision   = final.get("decision", "HOLD"),
                confidence = int(final.get("confidence", 0)),
                price      = _safe_float(final.get("price")) or 0.0,
                rsi        = _safe_float(indicators.get("rsi")),
                macd       = _safe_float(indicators.get("macd")),
                adx        = _safe_float(indicators.get("adx")),
                regime     = "TRENDING" if (_safe_float(indicators.get("adx")) or 0) > 20
                             else "RANGING",
                provider   = final.get("provider", "unknown"),
                source     = "webhook" if force_run else "agent_loop"
            )
            print(f"[DB] Signal saved -> {target_pair} {final.get('decision')} id={sig_id}")
        except Exception as e:
            print(f"[DB] Save signal error: {e}")

        # Send signal to Telegram (only if confidence >= 65% and auto cycle)
        if send_telegram and confidence >= 65 and decision in ["BUY", "SELL", "STRONG BUY", "STRONG SELL"]:
            await telegram_service.send_signal(
                agent_name="Boss Agent",
                pair=target_pair,
                decision=decision,
                confidence=confidence,
                entry=round(float(final["price"]), 2),
                stop=None,
                target=None,
                reasoning=final.get("thought", "")[:150]
            )
        else:
            print(f"[Telegram] Skipped {target_pair}: {decision} @ {confidence}% (below threshold or HOLD)")

        # Broadcast orchestrator (boss) decision
        await manager.broadcast(json.dumps({
            "type":            "agent_thought",
            "agent":           orchestrator.name,
            "thought":         final["thought"],
            "pair":            target_pair,
            "decision":        final["decision"],
            "confidence":      final["confidence"],
            "risk_level":      final["risk_level"],
            "price":           final["price"],
            "selected_agents": selected,
            "skipped_agents":  skipped,
        }))
    except Exception as e:
        print(f"[Agent Loop] Graph error for {target_pair}: {e}")
        import traceback; traceback.print_exc()
        await manager.broadcast(json.dumps({
            "type": "system_status", "status": "warning",
            "message": f"Agent analysis error for {target_pair}: {str(e)[:80]}"
        }))


# ── LOOP 3: Outcome Checker (every 1 hour) ────────────────────────────────────
async def outcome_checker_loop():
    """Every hour: check price movement for PENDING signals → WIN/LOSS."""
    await asyncio.sleep(3600)
    while True:
        try:
            from services.database_service import get_pending_outcomes, update_outcome
            import yfinance as yf

            pending = get_pending_outcomes()
            print(f"[Outcome] Checking {len(pending)} pending signals")

            TICKERS = {
                "NIFTY":   "^NSEI",
                "SENSEX":  "^BSESN",
                "BTC/USD": "BTC-USD",
                "EUR/USD": "EURUSD=X",
                "USD/JPY": "JPY=X",
            }

            for sig in pending:
                try:
                    ticker = TICKERS.get(sig["pair"])
                    if not ticker:
                        continue
                    data = yf.download(
                        ticker, period="1d", interval="1h", progress=False
                    )
                    if data.empty:
                        continue
                    current = float(data["Close"].iloc[-1])
                    entry   = sig["price_at_signal"]
                    if not entry or entry == 0:
                        continue

                    pct = (current - entry) / entry

                    if sig["decision"] == "BUY":
                        outcome = "WIN"  if pct >  0.002 else \
                                  "LOSS" if pct < -0.002 else "NEUTRAL"
                    elif sig["decision"] == "SELL":
                        outcome = "WIN"  if pct < -0.002 else \
                                  "LOSS" if pct >  0.002 else "NEUTRAL"
                    else:
                        outcome = "NEUTRAL"

                    update_outcome(
                        signal_id = sig["id"],
                        outcome   = outcome,
                        price_1h  = current,
                    )
                    print(f"[Outcome] {sig['pair']} {sig['decision']} "
                          f"-> {outcome} ({pct*100:.2f}%)")

                except Exception as e:
                    print(f"[Outcome] Error on signal {sig.get('id')}: {e}")

        except Exception as e:
            print(f"[Outcome] Loop error: {e}")

        await asyncio.sleep(3600)


# ── LOOP 2: AI Agent Loop (every 5 minutes) ────────────────────────────────────
async def agent_loop():
    """
    Runs every 5 minutes. Analyzes ALL monitored pairs each cycle.
    Sends signals, news, sentiment. Does NOT block price_loop.
    """
    print("[Agent Loop] Starting — 900s interval, all pairs per cycle")
    loop_count = 0
    while True:
        loop_count += 1
        print(f"\n[Agent Loop] Cycle #{loop_count}")
        try:
            market_summary = await market_data_agent.get_market_summary(MONITORED_PAIRS)
            news_text = market_summary.get("news_text", "")
            news_list = market_summary.get("news", [])

            global _world_news_cache
            # Refresh world news every 6 loops (30 minutes)
            if loop_count == 1 or loop_count % 6 == 0:
                try:
                    print("[Agent Loop] Refreshing Global Intelligence feed...")
                    _world_news_cache = await asyncio.get_event_loop().run_in_executor(
                        None, world_feed_service.fetch_top_10_events
                    )
                except Exception as e:
                    print(f"[Agent Loop] World news refresh error: {e}")

            if news_list:
                await manager.broadcast(json.dumps({
                    "type": "news_update",
                    "headlines": [n.get("headline", "") for n in news_list[:6]],
                    "news": news_list[:6]
                }))

            try:
                sentiment_data = await sentiment_service.get_crypto_sentiment()
                await manager.broadcast(json.dumps({
                    "type": "market_sentiment", "data": sentiment_data
                }))
            except Exception as e:
                print(f"[Agent Loop] Sentiment error: {e}")

            # ── SMART PAIR SELECTION (save tokens) ────────────────────────
            # NSE pairs: only during market hours (9:15-15:30 IST Mon-Fri)
            # Forex/Crypto: always analyze
            from services.nse_service import is_nse_market_open, NSE_PAIRS
            nse_open = is_nse_market_open()["is_open"]

            pairs_to_analyze = []
            for p in MONITORED_PAIRS:
                if p in NSE_PAIRS:
                    if nse_open:
                        pairs_to_analyze.append(p)
                    else:
                        print(f"[Agent Loop] Skipping {p} — NSE market closed (saving tokens)")
                        _latest_signals[p] = {"decision": "MARKET CLOSED", "confidence": 0}
                else:
                    pairs_to_analyze.append(p)  # Forex/Crypto always runs

            print(f"[Agent Loop] Analyzing {len(pairs_to_analyze)}/{len(MONITORED_PAIRS)} pairs: {pairs_to_analyze}")
            for target_pair in pairs_to_analyze:
                print(f"[Agent Loop] AI analysis → {target_pair}")
                await _run_agents_for_pair(target_pair, market_summary, news_text)
                await asyncio.sleep(5)  # 5s gap between pairs to avoid simultaneous API bursts

        except Exception as e:
            print(f"[Agent Loop] Critical error #{loop_count}: {e}")
        await asyncio.sleep(900)  # 15 minutes (saves 3x tokens vs 5 min)

@app.on_event("startup")
async def startup_event():
    init_db()
    print("[DB] Database initialized — all tables ready")

    print("[Startup] Strategic War Room v3.0 initializing...")

    # Test Telegram connection
    print("[Startup] Testing Telegram connection...")
    telegram_ok = await telegram_service.send_test_message()
    if telegram_ok:
        print("[Telegram] Connected and ready!")
    else:
        print("[Telegram] Connection failed - check credentials in .env")

    asyncio.create_task(price_loop())              # Fast: 1s
    asyncio.create_task(agent_loop())              # Slow: 900s
    asyncio.create_task(outcome_checker_loop())    # Hourly WIN/LOSS checker
    print("[Startup] Outcome checker started — runs every 1 hour")
    print("[Startup] All loops started.")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
