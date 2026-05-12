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
from datetime import datetime, timedelta, timezone
import pandas as pd
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv
load_dotenv()  # Load .env FIRST before any service initializes
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

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
from services.angelone_service import angel_service
from services.database_service import (
    init_db, save_signal, get_signal_history, get_win_rate_by_pair
)

app = FastAPI(title="Strategic War Room — AI Trading Hub v3.0")

# Serve frontend static files
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

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
_nse_cycle_data: dict = {}
_loop_tasks: dict = {"price": None, "agent": None, "outcome": None}
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
async def root():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"status": "running", "message": "Strategic War Room API v3.0"}

@app.get("/app.js")
async def serve_js():
    return FileResponse(os.path.join(FRONTEND_DIR, "app.js"))

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
    # Override NIFTY + SENSEX with AngelOne real-time price
    for pair in ["NIFTY", "SENSEX"]:
        if isinstance(prices, dict) and pair in prices:
            cached = angel_service.get_cached_price(pair)
            if cached:
                prices[pair]["price"]  = cached["price"]
                prices[pair]["source"] = "AngelOne-RT"
            else:
                live = await angel_service.get_ltp_async(pair)
                if live:
                    prices[pair]["price"]  = live
                    prices[pair]["source"] = "AngelOne-LTP"
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

@app.get("/api/agent-summary")
async def get_agent_summary():
    """Returns what each agent last found — for readable UI display."""
    result = {}
    for pair, data in _latest_signals.items():
        result[pair] = {
            "pair":              pair,
            "decision":          data.get("decision", "—"),
            "confidence":        data.get("confidence", 0),
            "htf_1h":            data.get("htf_1h", "UNKNOWN"),
            "quant_summary":     data.get("quant_summary", "Not yet run"),
            "academic_summary":  data.get("academic_summary", "Not yet run"),
            "geo_summary":       data.get("geo_summary", "Not yet run"),
            "boss_reasoning":    data.get("boss_reasoning", "Not yet run"),
            "indicators":        data.get("indicators", {}),
            "last_updated":      data.get("datetime", "—"),
            "stop_loss":         data.get("stop_loss"),
            "target":            data.get("target"),
            "price":             data.get("price"),
        }
    return {"data": result, "count": len(result)}

@app.get("/api/token-usage")
async def get_token_usage():
    groq_used    = _token_log.get("groq", 0)
    openrouter   = _token_log.get("openrouter", 0)
    gemini_used  = _token_log.get("gemini", 0)
    return {
        "groq":              groq_used,
        "openrouter":        openrouter,
        "gemini":            gemini_used,
        "total_today":       groq_used + openrouter + gemini_used,
        "groq_limit":        500_000,
        "gemini_limit":      1_000_000,
        "groq_remaining":    500_000   - groq_used,
        "gemini_remaining":  1_000_000 - gemini_used,
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

    # ── VIX FILTER: skip signals on high fear days (uses pre-fetched cache) ──
    if target_pair in ["NIFTY", "SENSEX"]:
        vix_val = _nse_cycle_data.get("vix")
        if vix_val is not None:
            print(f"[VIX] India VIX = {vix_val:.2f}")
            sig_dict = _latest_signals.get(target_pair, {})
            sig_dict["vix_value"] = vix_val
            if vix_val > 18:
                print(f"[VIX] HIGH FEAR ({vix_val:.2f} > 18) — skipping {target_pair}")
                sig_dict["vix_blocked"] = True
                _latest_signals[target_pair] = sig_dict
                return
            sig_dict["vix_blocked"] = False
            _latest_signals[target_pair] = sig_dict
    # ── END VIX FILTER ──────────────────────────────────────────────────

    # ── PREV DAY BIAS: store yesterday's direction (uses pre-fetched cache) ──
    if target_pair in ["NIFTY", "SENSEX"]:
        bias = _nse_cycle_data.get(f"{target_pair}_bias")
        if bias:
            print(f"[PrevDay] {target_pair} yesterday = {bias}")
            sig_dict = _latest_signals.get(target_pair, {})
            sig_dict["prev_day_bias"] = bias
            _latest_signals[target_pair] = sig_dict
    # ── END PREV DAY BIAS ────────────────────────────────────────────────

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

        def _extract(val):
            if isinstance(val, dict):
                return str(val.get("analysis", "") or val.get("thought", "") or "")[:300]
            return str(val or "")[:300]
        _latest_signals[target_pair]["quant_summary"]    = _extract(final.get("_quant_result"))
        _latest_signals[target_pair]["academic_summary"] = _extract(final.get("_academic_result"))
        _latest_signals[target_pair]["geo_summary"]      = _extract(final.get("_geo_result"))
        _latest_signals[target_pair]["boss_reasoning"]   = str(final.get("thought", ""))[:300]
        _latest_signals[target_pair]["indicators"] = {
            "rsi":  price_data.get("rsi"),
            "macd": price_data.get("macd"),
            "adx":  price_data.get("adx"),
            "ema20": price_data.get("ema_20"),
            "ema50": price_data.get("ema_50"),
        }

        # Persist signal to database
        decision   = final.get("decision", "HOLD")
        confidence = int(final.get("confidence", 0))

        # ATR-based stop-loss and target calculation
        stop_loss = None
        target    = None
        try:
            import yfinance as yf
            _TICKERS = {
                "NIFTY":   "^NSEI",  "SENSEX":  "^BSESN",
                "BTC/USD": "BTC-USD","EUR/USD": "EURUSD=X","USD/JPY": "JPY=X",
            }
            ticker = _TICKERS.get(target_pair)
            if ticker:
                df_atr = yf.download(ticker, period="5d", interval="15m", progress=False)
                if isinstance(df_atr.columns, pd.MultiIndex):
                    df_atr.columns = [c[0] for c in df_atr.columns]
                high       = df_atr["High"]
                low        = df_atr["Low"]
                close_atr  = df_atr["Close"]
                prev_close = close_atr.shift(1)
                tr = pd.concat([
                    high - low,
                    (high - prev_close).abs(),
                    (low  - prev_close).abs(),
                ], axis=1).max(axis=1)
                atr   = float(tr.ewm(span=14, adjust=False).mean().iloc[-1])
                entry = float(final.get("price", 0))
                if decision == "BUY":
                    stop_loss = round(entry - (atr * 1.0), 4)
                    target    = round(entry + (atr * 2.0), 4)
                elif decision == "SELL":
                    stop_loss = round(entry + (atr * 1.0), 4)
                    target    = round(entry - (atr * 2.0), 4)
        except Exception as e:
            print(f"[ATR] Calculation failed: {e}")

        _latest_signals[target_pair]["stop_loss"] = stop_loss
        _latest_signals[target_pair]["target"]    = target
        _latest_signals[target_pair]["datetime"]  = datetime.now(timezone.utc).replace(tzinfo=None).strftime("%Y-%m-%d %H:%M")

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
                source     = "webhook" if force_run else "agent_loop",
                stop_loss  = stop_loss,
                target     = target,
            )
            print(f"[DB] Signal saved -> {target_pair} {final.get('decision')} id={sig_id}")
        except Exception as e:
            print(f"[DB] Save signal error: {e}")

        # Send signal to Telegram (only if confidence >= 65% and auto cycle)
        if send_telegram and confidence >= 65 and decision in ["BUY", "SELL", "STRONG BUY", "STRONG SELL"]:
            sl_text = f"{stop_loss:.4f}" if stop_loss else "N/A"
            tp_text = f"{target:.4f}"    if target    else "N/A"
            await telegram_service.send_signal(
                agent_name="Boss Agent",
                pair=target_pair,
                decision=decision,
                confidence=confidence,
                entry=round(float(final["price"]), 2),
                stop=sl_text,
                target=tp_text,
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
    await asyncio.sleep(60)  # Check every 1 minute instead of 1 hour
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
                    close_col = data["Close"]
                    if isinstance(close_col, pd.DataFrame):
                        close_col = close_col.iloc[:, 0]
                    current  = float(close_col.iloc[-1])
                    # Use real-time AngelOne price for NSE pairs if available
                    if sig["pair"] in ("NIFTY", "SENSEX"):
                        _cached = angel_service.get_cached_price(sig["pair"])
                        if _cached and _cached.get("price"):
                            current = float(_cached["price"])
                    entry    = sig["price_at_signal"]
                    if not entry or entry == 0:
                        continue

                    sl       = sig.get("stop_loss")
                    tp       = sig.get("target")
                    dec      = sig["decision"]

                    if sl and tp:
                        if dec == "BUY":
                            if current >= tp:
                                outcome = "WIN"
                            elif current <= sl:
                                outcome = "LOSS"
                            else:
                                outcome = "PENDING"
                        elif dec == "SELL":
                            if current <= tp:
                                outcome = "WIN"
                            elif current >= sl:
                                outcome = "LOSS"
                            else:
                                outcome = "PENDING"
                        else:
                            outcome = "NEUTRAL"
                    else:
                        # Fallback: 0.2% threshold
                        pct = (current - entry) / entry
                        if dec == "BUY":
                            outcome = "WIN" if pct > 0.002 else "LOSS" if pct < -0.002 else "NEUTRAL"
                        elif dec == "SELL":
                            outcome = "WIN" if pct < -0.002 else "LOSS" if pct > 0.002 else "NEUTRAL"
                        else:
                            outcome = "NEUTRAL"

                    if outcome == "PENDING":
                        continue  # SL/TP not hit yet — leave in PENDING state

                    update_outcome(
                        signal_id = sig["id"],
                        outcome   = outcome,
                        price_1h  = current,
                    )
                    print(f"[Outcome] {sig['pair']} {sig['decision']} "
                          f"-> {outcome} (price={current})")

                    # Send immediate Telegram alert
                    entry     = float(sig.get("price_at_signal") or 0)
                    sl        = float(sig.get("stop_loss") or 0)
                    tp        = float(sig.get("target") or 0)
                    pair_name = sig["pair"]
                    dp        = 2 if pair_name in ("NIFTY", "SENSEX", "BTC/USD") else 4
                    sym       = "₹" if pair_name in ("NIFTY", "SENSEX") else ""
                    fmt_v     = lambda v: f"{sym}{v:,.{dp}f}"
                    pnl_pts   = round(current - entry, dp) if sig["decision"] == "BUY" else round(entry - current, dp)
                    pnl_pct   = round((abs(pnl_pts) / entry) * 100, 2) if entry else 0

                    if outcome == "WIN":
                        msg = (f"\U0001f3af TARGET HIT — {pair_name}\n"
                               f"Signal: {sig['decision']} @ {fmt_v(entry)}\n"
                               f"Exit:   {fmt_v(current)}\n"
                               f"P&L:    +{abs(pnl_pts):,.{dp}f} pts (+{pnl_pct}%)\n"
                               f"Result: ✅ WIN")
                    else:
                        msg = (f"\U0001f6d1 STOP LOSS HIT — {pair_name}\n"
                               f"Signal: {sig['decision']} @ {fmt_v(entry)}\n"
                               f"Exit:   {fmt_v(current)}\n"
                               f"P&L:    -{abs(pnl_pts):,.{dp}f} pts (-{pnl_pct}%)\n"
                               f"Result: ❌ LOSS")
                    await telegram_service.send_message(msg)

                except Exception as e:
                    print(f"[Outcome] Error on signal {sig.get('id')}: {e}")

        except Exception as e:
            print(f"[Outcome] Loop error: {e}")

        await asyncio.sleep(60)  # Check every 1 minute instead of 1 hour


# ── LOOP 2: AI Agent Loop — SMART session-aware ────────────────────────────────
async def agent_loop():
    """
    SMART activation — only runs agents during relevant market sessions.
    Saves 70-80% tokens vs 24/7 mode.
    """
    print("[Agent Loop] Starting — SMART session-aware mode")
    await asyncio.sleep(10)

    while True:
        try:
            # Get current IST time
            now_utc    = datetime.now(timezone.utc).replace(tzinfo=None)
            ist_offset = 330  # IST = UTC + 5:30 = 330 minutes
            ist_total  = now_utc.hour * 60 + now_utc.minute + ist_offset
            ist_hour   = (ist_total // 60) % 24
            ist_minute = ist_total % 60
            ist_time   = ist_hour * 60 + ist_minute
            weekday    = now_utc.weekday()  # 0=Mon, 6=Sun

            pairs_to_run = []

            # ── NIFTY / SENSEX: only during NSE hours Mon-Fri ──
            NSE_OPEN  = 9 * 60 + 20
            NSE_CLOSE = 15 * 60 + 0

            # Best signal windows only (avoid choppy 11AM-1PM)
            MORNING_START = 9 * 60 + 20   # 9:20 AM
            MORNING_END   = 10 * 60 + 30  # 10:30 AM
            AFTERNOON_START = 13 * 60 + 30  # 1:30 PM
            AFTERNOON_END   = 14 * 60 + 30  # 2:30 PM

            in_best_window = (
                (MORNING_START <= ist_time <= MORNING_END) or
                (AFTERNOON_START <= ist_time <= AFTERNOON_END)
            )

            if weekday < 5 and NSE_OPEN <= ist_time <= NSE_CLOSE and in_best_window:
                pairs_to_run += ["NIFTY", "SENSEX"]

            # ── BTC: Asian + London + NY session opens ──
            BTC_WINDOWS = [
                (2*60,  2*60+45),   # 2:00-2:45 AM IST (Asian open)
                (13*60, 13*60+45),  # 1:00-1:45 PM IST (London open)
                (20*60, 20*60+45),  # 8:00-8:45 PM IST (NY open)
            ]
            for start, end in BTC_WINDOWS:
                if start <= ist_time <= end:
                    pairs_to_run.append("BTC/USD")
                    break

            # ── Forex: London + NY sessions only ──
            FOREX_WINDOWS = [
                (13*60+30, 16*60),  # 1:30-4:00 PM IST (London)
                (18*60+30, 21*60),  # 6:30-9:00 PM IST (NY)
            ]
            for start, end in FOREX_WINDOWS:
                if start <= ist_time <= end:
                    pairs_to_run += ["EUR/USD", "USD/JPY"]
                    break

            # Remove duplicates while preserving order
            seen = set()
            unique_pairs = []
            for p in pairs_to_run:
                if p not in seen:
                    seen.add(p)
                    unique_pairs.append(p)

            if unique_pairs:
                print(f"[Agent Loop] SMART: {ist_hour:02d}:{ist_minute:02d} IST "
                      f"— Running {unique_pairs}")
                market_summary = await market_data_agent.get_market_summary(unique_pairs)
                news_text = world_feed_service._last_feed if hasattr(world_feed_service, '_last_feed') else ""

                # Pre-fetch VIX + PrevDay ONCE for all NSE pairs this cycle
                _nse_cycle_data.clear()
                if any(p in unique_pairs for p in ["NIFTY", "SENSEX"]):
                    try:
                        import yfinance as _yf
                        _vd = _yf.download("^INDIAVIX", period="2d", interval="1d", progress=False)
                        if isinstance(_vd.columns, pd.MultiIndex): _vd.columns = [c[0] for c in _vd.columns]
                        if not _vd.empty: _nse_cycle_data["vix"] = float(_vd["Close"].iloc[-1])
                        for _sp, _st in [("NIFTY", "^NSEI"), ("SENSEX", "^BSESN")]:
                            _pd = _yf.download(_st, period="5d", interval="1d", progress=False)
                            if isinstance(_pd.columns, pd.MultiIndex): _pd.columns = [c[0] for c in _pd.columns]
                            if len(_pd) >= 2:
                                _nse_cycle_data[f"{_sp}_bias"] = (
                                    "BULLISH" if float(_pd["Close"].iloc[-2]) > float(_pd["Open"].iloc[-2])
                                    else "BEARISH"
                                )
                    except Exception as _e:
                        print(f"[PreFetch] {_e}")

                for pair in unique_pairs:
                    await _run_agents_for_pair(pair, market_summary, news_text)
                    await asyncio.sleep(5)
            else:
                print(f"[Agent Loop] SMART: {ist_hour:02d}:{ist_minute:02d} IST "
                      f"— No active sessions, sleeping")

        except Exception as e:
            print(f"[Agent Loop] Error: {e}")

        await asyncio.sleep(900)  # check every 15 minutes


# ── LOOP 4: Watchdog — auto-restart dead loops ───────────────────────
async def watchdog_loop():
    """Every 5 min: check background loops, restart if dead."""
    await asyncio.sleep(120)        # wait 2 min after boot
    while True:
        try:
            restarted = []
            for name, task in list(_loop_tasks.items()):
                if task is None or task.done():
                    print(f"[Watchdog] {name} loop DEAD — restarting")
                    if name == "price":
                        _loop_tasks["price"]   = asyncio.create_task(price_loop())
                    elif name == "agent":
                        _loop_tasks["agent"]   = asyncio.create_task(agent_loop())
                    elif name == "outcome":
                        _loop_tasks["outcome"] = asyncio.create_task(outcome_checker_loop())
                    restarted.append(name)
            if restarted:
                await telegram_service.send_watchdog_alert(restarted)
        except Exception as e:
            print(f"[Watchdog] Error: {e}")
        await asyncio.sleep(300)    # check every 5 minutes


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

    # AngelOne real-time feed for NIFTY + SENSEX
    if angel_service.login():
        asyncio.create_task(angel_service.refresh_prices_loop(["NIFTY", "SENSEX"], interval=3))
        print("[Startup] AngelOne real-time feed started — NIFTY + SENSEX every 3s")
    else:
        print("[Startup] AngelOne login failed — using yfinance fallback for prices")

    _loop_tasks["price"]   = asyncio.create_task(price_loop())
    _loop_tasks["agent"]   = asyncio.create_task(agent_loop())
    _loop_tasks["outcome"] = asyncio.create_task(outcome_checker_loop())
    asyncio.create_task(watchdog_loop())
    print("[Startup] Outcome checker + watchdog started — runs every 1 hour")
    print("[Startup] All loops started.")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
