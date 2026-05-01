/**
 * Strategic War Room — Frontend App
 * TradingView-style real-time dashboard
 * Connects to FastAPI backend via WebSocket + REST
 */

// ── Config ────────────────────────────────────────────────────────────────────
const API_URL    = "http://localhost:8000";
const WS_URL     = "ws://localhost:8000/ws";
const IST_OFFSET = 19800;   // UTC+5:30 in seconds — added to all chart timestamps

// ── State ─────────────────────────────────────────────────────────────────────
let currentPair      = "EUR/USD";
let currentTimeframe = "1D";
let ws               = null;
let chart            = null;
let candleSeries     = null;
let emaSeries20      = null;
let emaSeries50      = null;
let signalMarkers    = [];
let portfolio        = { balance: 10000, positions: [] };
let priceCache       = {};   // {pair: {price, change_pct}}
let indicatorsCache  = {};   // {pair: indicators}
let chartInitialized = false;
let wsReconnectTimer = null;
let bbUpperSeries    = null;
let bbMidSeries      = null;
let bbLowerSeries    = null;
let volumeSeries     = null;
let predictionLines  = [];
let bbVisible        = true;
let volVisible       = true;
let isDarkMode       = false;

// ── Drawing Tool State ────────────────────────────────────────────────────────
let activeTool       = 'cursor';
let drawings         = [];
let drawingState     = null;   // ghost line while trendline 2nd click pending
let magnetMode       = false;
let drawingsLocked   = false;
let drawingsVisible  = true;
let svgEl            = null;
let drawingIdCtr     = 0;
let _drawFirstClick  = null;   // first click coords for two-click tools (trendline)

// ── Chart Type State ──────────────────────────────────────────────────────────
let currentChartType = 'candlestick';
let altSeries        = null;   // bar/line/area series (swapped for candleSeries)
let lastCandleData   = [];     // raw OHLCV stored for HA computation + re-apply
let mainSeries       = null;   // always points to the active price series

// ── Precision by pair ─────────────────────────────────────────────────────────
const PAIR_DECIMALS = {
    "EUR/USD": 4, "GBP/USD": 4, "USD/CHF": 4, "AUD/USD": 4, "NZD/USD": 4, "USD/CAD": 4,
    "EUR/GBP": 4, "EUR/JPY": 3, "GBP/JPY": 3, "USD/JPY": 3,
    "XAU/USD": 2, "XAG/USD": 3,
    "BTC/USD": 2, "ETH/USD": 2, "XRP/USD": 4,
    "USD/INR": 2, "EUR/INR": 2, "GBP/INR": 2,
    "NIFTY50": 2, "SENSEX": 2,
};
const PAIR_CLASS = { "EUR/USD": "academic", "USD/JPY": "geo", "BTC/USD": "market" };

function decimals(pair) { return PAIR_DECIMALS[pair] || 4; }
function fmtPrice(price, pair) {
    return typeof price === "number" ? price.toFixed(decimals(pair)) : "–";
}

// ── Chart Initialization ──────────────────────────────────────────────────────
function initChart() {
    const container = document.getElementById("chart-container");
    if (!container || chartInitialized) return;

    chart = LightweightCharts.createChart(container, {
        layout: {
            background: { type: "solid", color: "#ffffff" },
            textColor: "#333333",
            fontFamily: "JetBrains Mono, monospace",
        },
        grid: {
            vertLines: { color: "#f0f0f0" },
            horzLines: { color: "#f0f0f0" },
        },
        crosshair: {
            mode: LightweightCharts.CrosshairMode.Normal,
            vertLine: {
                color: "#333333",
                width: 1,
                style: 0,
                labelBackgroundColor: "#333333",
            },
            horzLine: {
                color: "#333333",
                width: 1,
                style: 0,
                labelBackgroundColor: "#333333",
            },
        },
        localization: {
            timeFormatter: (ts) => {
                const d = new Date(ts * 1000);
                const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
                const day   = d.getUTCDate();
                const mon   = months[d.getUTCMonth()];
                const yr    = String(d.getUTCFullYear()).slice(2);
                const hh    = String(d.getUTCHours()).padStart(2,'0');
                const mm    = String(d.getUTCMinutes()).padStart(2,'0');
                return `${day} ${mon} '${yr}  ${hh}:${mm}`;
            },
        },
        timeScale: {
            borderColor: "#e0e3eb",
            timeVisible: true,
            secondsVisible: false,
        },
        rightPriceScale: {
            borderColor: "#e0e3eb",
        },
        handleScroll: true,
        handleScale: true,
    });

    // Candlestick series
    candleSeries = chart.addCandlestickSeries({
        upColor:        "#26a69a",
        downColor:      "#ef5350",
        borderVisible:  false,
        wickUpColor:    "#26a69a",
        wickDownColor:  "#ef5350",
        priceFormat:    { type: "price", precision: 4, minMove: 0.0001 },
    });

    // EMA-20 line
    emaSeries20 = chart.addLineSeries({
        color: "rgba(41, 98, 255, 0.6)",
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: true,
        title: "EMA20",
    });

    // EMA-50 line
    emaSeries50 = chart.addLineSeries({
        color: "rgba(227, 179, 65, 0.6)",
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: true,
        title: "EMA50",
    });

    // Bollinger Band series
    bbUpperSeries = chart.addLineSeries({
        color: "rgba(156, 108, 245, 0.5)",
        lineWidth: 1,
        lineStyle: 2,
        priceLineVisible: false,
        lastValueVisible: false,
        title: "BB+",
    });
    bbMidSeries = chart.addLineSeries({
        color: "rgba(156, 108, 245, 0.3)",
        lineWidth: 1,
        lineStyle: 2,
        priceLineVisible: false,
        lastValueVisible: false,
        title: "BB mid",
    });
    bbLowerSeries = chart.addLineSeries({
        color: "rgba(156, 108, 245, 0.5)",
        lineWidth: 1,
        lineStyle: 2,
        priceLineVisible: false,
        lastValueVisible: false,
        title: "BB-",
    });

    // Volume histogram
    volumeSeries = chart.addHistogramSeries({
        priceFormat: { type: "volume" },
        priceScaleId: "volume",
    });
    chart.priceScale("volume").applyOptions({
        scaleMargins: { top: 0.85, bottom: 0 },
    });

    // Auto-resize
    const ro = new ResizeObserver(() => {
        if (container.clientWidth > 0 && container.clientHeight > 0) {
            chart.applyOptions({
                width: container.clientWidth,
                height: container.clientHeight,
            });
        }
    });
    ro.observe(container);

    mainSeries = candleSeries;

    // Re-render SVG drawings whenever the visible range or price scale changes
    chart.timeScale().subscribeVisibleTimeRangeChange(() => renderAllDrawings());

    chartInitialized = true;
    console.log("[Chart] Initialized");

    initDrawingOverlay();
}

// ── Load Chart Data from Backend ─────────────────────────────────────────────
async function loadChartData(pair = currentPair, timeframe = currentTimeframe) {
    showChartLoading(true);
    const urlPair = pair.replace("/", "_");
    try {
        const res = await fetch(`${API_URL}/api/history/${urlPair}/${timeframe}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json = await res.json();
        // Convert UTC → IST by shifting every timestamp by +19800 s
        const candles = (json.data || []).map(c => ({ ...c, time: c.time + IST_OFFSET }));

        if (candles.length > 0) {
            lastCandleData = candles;
            applyChartTypeData(candles);
            buildEMALines(candles);
            buildVolumeData(candles);
            // For intraday timeframes, scroll to the most recent N candles
            // so each candle is wide enough to see individually.
            const visibleBars = { '1M': 80, '5M': 100, '15M': 120, '1H': 150, '4H': 168 };
            const defaultBars = visibleBars[timeframe];
            if (defaultBars && candles.length > defaultBars) {
                const last = candles[candles.length - 1];
                const first = candles[candles.length - defaultBars];
                chart.timeScale().setVisibleRange({ from: first.time, to: last.time + TF_SECONDS[timeframe] * 5 });
            } else {
                chart.timeScale().fitContent();
            }
            initLiveCandleFromHistory();
            console.log(`[Chart] Loaded ${candles.length} candles for ${pair}/${timeframe}`);
        } else {
            console.warn("[Chart] No candle data returned — using mock");
            const mockData = generateMockCandles(pair, timeframe);
            lastCandleData = mockData;
            applyChartTypeData(mockData);
            buildEMALines(mockData);
            buildVolumeData(mockData);
            chart.timeScale().fitContent();
            initLiveCandleFromHistory();
        }
    } catch (err) {
        console.warn("[Chart] Load failed, showing mock data:", err);
        const mockData = generateMockCandles(pair, timeframe);
        lastCandleData = mockData;
        applyChartTypeData(mockData);
        buildEMALines(mockData);
        buildVolumeData(mockData);
        chart.timeScale().fitContent();
        initLiveCandleFromHistory();
    }
    showChartLoading(false);
}

function showChartLoading(visible) {
    const el = document.getElementById("chart-loading");
    if (el) el.style.display = visible ? "flex" : "none";
}

// ── Build EMA data from candle closes ────────────────────────────────────────
function buildEMALines(candles) {
    if (!emaSeries20 || !emaSeries50) return;
    if (candles.length < 20) {
        emaSeries20.setData([]);
        emaSeries50.setData([]);
        return;
    }

    function calcEMA(period) {
        const k = 2 / (period + 1);
        const data = [];
        let prev = null;
        for (let i = 0; i < candles.length; i++) {
            const c = candles[i].close;
            if (i < period - 1) {
                prev = null; continue;
            } else if (i === period - 1) {
                prev = candles.slice(0, period).reduce((s, x) => s + x.close, 0) / period;
            } else {
                prev = c * k + prev * (1 - k);
            }
            if (prev !== null) {
                data.push({ time: candles[i].time, value: parseFloat(prev.toFixed(6)) });
            }
        }
        return data;
    }

    emaSeries20.setData(calcEMA(20));
    if (candles.length >= 50) emaSeries50.setData(calcEMA(50));

    buildBBLines(candles);
}

function buildBBLines(candles) {
    if (!bbUpperSeries || !bbMidSeries || !bbLowerSeries) return;
    const period = 20;
    const mult   = 2.0;
    if (candles.length < period) {
        bbUpperSeries.setData([]);
        bbMidSeries.setData([]);
        bbLowerSeries.setData([]);
        return;
    }
    const upper = [], mid = [], lower = [];
    for (let i = period - 1; i < candles.length; i++) {
        const window = candles.slice(i - period + 1, i + 1).map(c => c.close);
        const avg    = window.reduce((a, b) => a + b, 0) / period;
        const std    = Math.sqrt(window.reduce((a, b) => a + (b - avg) ** 2, 0) / period);
        upper.push({ time: candles[i].time, value: parseFloat((avg + mult * std).toFixed(6)) });
        mid.push(  { time: candles[i].time, value: parseFloat(avg.toFixed(6)) });
        lower.push({ time: candles[i].time, value: parseFloat((avg - mult * std).toFixed(6)) });
    }
    bbUpperSeries.setData(bbVisible ? upper : []);
    bbMidSeries.setData(bbVisible ? mid : []);
    bbLowerSeries.setData(bbVisible ? lower : []);
}

function buildVolumeData(candles) {
    if (!volumeSeries) return;
    const data = candles.map(c => ({
        time:  c.time,
        value: c.volume && c.volume > 0
               ? c.volume
               : Math.abs(c.high - c.low) * 100000,
        // Green vol for up candle, red for down — 0.5 opacity matching candle colors
        color: c.close >= c.open
               ? "rgba(38, 166, 154, 0.50)"
               : "rgba(242, 54, 69, 0.50)",
    }));
    volumeSeries.setData(volVisible ? data : []);
}

function toggleBB(btn) {
    bbVisible = !bbVisible;
    btn.classList.toggle("active", bbVisible);
    if (bbUpperSeries) {
        bbUpperSeries.applyOptions({ visible: bbVisible });
        bbMidSeries.applyOptions({ visible: bbVisible });
        bbLowerSeries.applyOptions({ visible: bbVisible });
    }
}

function toggleVol(btn) {
    volVisible = !volVisible;
    btn.classList.toggle("active", volVisible);
    if (volumeSeries) volumeSeries.applyOptions({ visible: volVisible });
}

function toggleDarkMode() {
    isDarkMode = !isDarkMode;
    document.documentElement.setAttribute("data-theme", isDarkMode ? "dark" : "light");
    const btn = document.getElementById("dark-toggle");
    if (btn) btn.innerHTML = isDarkMode
        ? `<i data-lucide="sun" style="width:14px;height:14px"></i>`
        : `<i data-lucide="moon" style="width:14px;height:14px"></i>`;
    lucide.createIcons();

    if (chart) {
        const bg   = isDarkMode ? "#0d1117" : "#ffffff";
        const text = isDarkMode ? "#e6edf3" : "#333333";
        const grid = isDarkMode ? "#21262d" : "#f0f0f0";
        const xhair = isDarkMode ? "#aaaaaa" : "#333333";
        chart.applyOptions({
            layout: { background: { color: bg }, textColor: text },
            grid:   { vertLines: { color: grid }, horzLines: { color: grid } },
            crosshair: {
                vertLine: { color: xhair, labelBackgroundColor: xhair },
                horzLine: { color: xhair, labelBackgroundColor: xhair },
            },
        });
    }
}

function drawPredictionZone(decision, confidence, currentPrice, pair) {
    if (!candleSeries || !currentPrice) return;
    predictionLines.forEach(l => { try { candleSeries.removePriceLine(l); } catch(e) {} });
    predictionLines = [];

    const atr = indicatorsCache[pair]?.atr;
    if (!atr) return;

    const dir    = decision === "BUY" ? 1 : -1;
    const target = parseFloat((currentPrice + dir * atr * 1.5).toFixed(decimals(pair)));
    const sl     = parseFloat((currentPrice - dir * atr * 1.0).toFixed(decimals(pair)));
    const color  = decision === "BUY" ? "#26a69a" : "#ef5350";

    predictionLines.push(candleSeries.createPriceLine({
        price:             target,
        color:             color,
        lineWidth:         2,
        lineStyle:         1,
        axisLabelVisible:  true,
        title:             `AI Target ${confidence}%`,
    }));
    predictionLines.push(candleSeries.createPriceLine({
        price:             sl,
        color:             "rgba(239, 83, 80, 0.6)",
        lineWidth:         1,
        lineStyle:         3,
        axisLabelVisible:  true,
        title:             "AI Stop",
    }));

    // Pre-fill the SL/TP inputs
    const slInput = document.getElementById("sl-input");
    const tpInput = document.getElementById("tp-input");
    if (slInput) slInput.value = sl.toFixed(decimals(pair));
    if (tpInput) tpInput.value = target.toFixed(decimals(pair));
}

// ── Fallback mock candles ─────────────────────────────────────────────────────
function generateMockCandles(pair, timeframe="1D") {
    const seeds = { "EUR/USD": 1.085, "USD/JPY": 152.5, "BTC/USD": 65000 };
    const stepAmts  = { "EUR/USD": 0.003, "USD/JPY": 1.2, "BTC/USD": 1200 };
    
    // Determine seconds per candle
    const tb = { "1M": 60, "5M": 300, "15M": 900, "1H": 3600, "4H": 14400, "1D": 86400, "1W": 604800 };
    const tfSeconds = tb[timeframe] || 86400;
    
    // Adjust volatility step relative to timeframe size to prevent huge 1m jumps
    const tfRatio = Math.sqrt(tfSeconds / 86400); 
    const step = (stepAmts[pair] || 0.005) * tfRatio;

    let price = seeds[pair] || 1.0;
    const data = [];
    // Snap to real bucket boundary so mock candles align with live candle times.
    const currentBucket = Math.floor(Math.floor(Date.now() / 1000) / tfSeconds) * tfSeconds + IST_OFFSET;
    let t = currentBucket - 150 * tfSeconds;
    
    for (let i = 0; i < 150; i++) {
        const open  = price;
        const close = open + (Math.random() - 0.49) * step;
        const high  = Math.max(open, close) + Math.random() * step * 0.5;
        const low   = Math.min(open, close) - Math.random() * step * 0.5;
        data.push({ time: t, open, high, low, close });
        price = close;
        t += tfSeconds;
    }
    return data;
}

// ══════════════════════════════════════════════════════════════════════════════
// CHART TYPE SWITCHING
// ══════════════════════════════════════════════════════════════════════════════

function applyChartTypeData(candles) {
    if (currentChartType === 'candlestick') {
        candleSeries.setData(candles);
    } else if (currentChartType === 'heikinashi') {
        candleSeries.setData(computeHeikinAshi(candles));
    } else if (altSeries) {
        if (currentChartType === 'line' || currentChartType === 'area') {
            altSeries.setData(candles.map(c => ({ time: c.time, value: c.close })));
        } else if (currentChartType === 'bar') {
            altSeries.setData(candles);
        }
    }
}

function computeHeikinAshi(candles) {
    const ha = [];
    for (let i = 0; i < candles.length; i++) {
        const c = candles[i];
        const haClose = (c.open + c.high + c.low + c.close) / 4;
        const haOpen  = i === 0 ? (c.open + c.close) / 2 : (ha[i-1].open + ha[i-1].close) / 2;
        const haHigh  = Math.max(c.high, haOpen, haClose);
        const haLow   = Math.min(c.low, haOpen, haClose);
        ha.push({ time: c.time, open: haOpen, high: haHigh, low: haLow, close: haClose });
    }
    return ha;
}

function setChartType(type, btnEl) {
    // Always proceed (don't early-return on same type — user may click again to force refresh)
    currentChartType = type;

    // 1. Remove any existing alt series (bar/line/area)
    if (altSeries) {
        try { chart.removeSeries(altSeries); } catch (_) {}
        altSeries = null;
    }

    // 2. Hide or show candleSeries and create alt series as needed
    if (type === 'candlestick' || type === 'heikinashi') {
        candleSeries.applyOptions({ visible: true });
        mainSeries = candleSeries;

    } else if (type === 'bar') {
        candleSeries.applyOptions({ visible: false });
        altSeries = chart.addBarSeries({
            upColor:   '#26a69a',
            downColor: '#f23645',
            priceFormat: { type: 'price', precision: 4, minMove: 0.0001 },
        });
        mainSeries = altSeries;

    } else if (type === 'line') {
        candleSeries.applyOptions({ visible: false });
        altSeries = chart.addLineSeries({
            color:            '#2962ff',
            lineWidth:        2,
            priceLineVisible: false,
            lastValueVisible: true,
            priceFormat:      { type: 'price', precision: 4, minMove: 0.0001 },
        });
        mainSeries = altSeries;

    } else if (type === 'area') {
        candleSeries.applyOptions({ visible: false });
        altSeries = chart.addAreaSeries({
            lineColor:        '#2962ff',
            topColor:         'rgba(41,98,255,0.25)',
            bottomColor:      'rgba(41,98,255,0.02)',
            lineWidth:        2,
            priceLineVisible: false,
            lastValueVisible: true,
            priceFormat:      { type: 'price', precision: 4, minMove: 0.0001 },
        });
        mainSeries = altSeries;
    }

    // 3. Feed data into whichever series is now active
    if (lastCandleData.length > 0) applyChartTypeData(lastCandleData);

    // 4. Sync button active state across top-bar AND side dropdown
    document.querySelectorAll('.chart-type-option, .ct-btn').forEach(b => b.classList.remove('active'));
    if (btnEl) btnEl.classList.add('active');
    const altId   = `ct-${type}`;
    const topBtn  = document.getElementById(altId);
    const sideBtn = document.querySelector(`.chart-type-option[data-ctype="${type}"]`);
    if (topBtn  && topBtn  !== btnEl) topBtn.classList.add('active');
    if (sideBtn && sideBtn !== btnEl) sideBtn.classList.add('active');

    closeChartTypeMenu();
}

function toggleChartTypeMenu(e) {
    e.stopPropagation();
    const menu = document.getElementById('chart-type-menu');
    if (menu) menu.classList.toggle('open');
}

function closeChartTypeMenu() {
    const menu = document.getElementById('chart-type-menu');
    if (menu) menu.classList.remove('open');
}

document.addEventListener('click', () => closeChartTypeMenu());

// ══════════════════════════════════════════════════════════════════════════════
// DRAWING TOOLS — SVG OVERLAY
// ══════════════════════════════════════════════════════════════════════════════

function initDrawingOverlay() {
    svgEl = document.getElementById('chart-svg');
    if (!svgEl) return;

    const DRAW_COLOR = '#2962ff';
    const ONE_CLICK_TOOLS  = ['hline', 'hray', 'vline', 'crossline'];
    const TWO_CLICK_TOOLS  = ['trendline', 'ray', 'extended-line', 'trend-angle',
                               'regression-trend', 'rectangle', 'fibonacci', 'measure'];
    const THREE_CLICK_TOOLS = ['parallel-channel', 'flat-top',
                                'pitchfork', 'schiff-pitchfork', 'modified-schiff'];

    // ── Use LightweightCharts' own click event for reliable coordinate detection ──
    chart.subscribeClick((params) => {
        if (activeTool === 'cursor' || drawingsLocked) return;
        if (!params.point) return;

        const series = mainSeries || candleSeries;
        const price  = series ? series.coordinateToPrice(params.point.y) : null;
        const time   = params.time ?? null;
        if (price == null) return;

        if (ONE_CLICK_TOOLS.includes(activeTool)) {
            const d = { type: activeTool, color: DRAW_COLOR, width: 1 };
            if (activeTool === 'hline')    d.price = price;
            if (activeTool === 'hray')     { d.price = price; d.time = time; }
            if (activeTool === 'vline')    { if (!time) return; d.time = time; }
            if (activeTool === 'crossline'){ if (!time) return; d.time = time; d.price = price; }
            addDrawing(d);
            renderAllDrawings();
            setDrawingTool('cursor', document.getElementById('tool-cursor'));
            return;
        }

        if (TWO_CLICK_TOOLS.includes(activeTool) && time != null) {
            if (!_drawFirstClick) {
                _drawFirstClick = { time, price };
            } else {
                addDrawing({ type: activeTool, p1: _drawFirstClick, p2: { time, price }, color: DRAW_COLOR, width: 1.5 });
                _drawFirstClick = null;
                drawingState    = null;
                renderAllDrawings();
                setDrawingTool('cursor', document.getElementById('tool-cursor'));
            }
            return;
        }

        if (THREE_CLICK_TOOLS.includes(activeTool) && time != null) {
            _toolClickPoints.push({ time, price });
            if (_toolClickPoints.length === 1) {
                _drawFirstClick = _toolClickPoints[0];
            } else if (_toolClickPoints.length === 3) {
                const [p1, p2, p3] = _toolClickPoints;
                addDrawing({ type: activeTool, p1, p2, p3, color: DRAW_COLOR, width: 1.5 });
                _toolClickPoints = [];
                _drawFirstClick  = null;
                drawingState     = null;
                renderAllDrawings();
                setDrawingTool('cursor', document.getElementById('tool-cursor'));
            }
        }
    });

    // ── Ghost trendline + OHLC legend on crosshair move ────────────────────────
    const olLegend = document.getElementById('ohlc-legend');
    const olO = document.getElementById('ol-o');
    const olH = document.getElementById('ol-h');
    const olL = document.getElementById('ol-l');
    const olC = document.getElementById('ol-c');
    const olChg = document.getElementById('ol-chg');

    chart.subscribeCrosshairMove((params) => {
        // ── Ghost line for any 2-or-3-click tool awaiting next click ──
        const ghostTools = ['trendline','ray','extended-line','trend-angle','regression-trend',
                            'rectangle','fibonacci','measure','parallel-channel','flat-top',
                            'pitchfork','schiff-pitchfork','modified-schiff'];
        if (ghostTools.includes(activeTool) && _drawFirstClick && params.point && params.time) {
            const series = mainSeries || candleSeries;
            const price  = series ? series.coordinateToPrice(params.point.y) : null;
            if (price != null) {
                drawingState = { type: 'trendline', sc: _drawFirstClick, ec: { time: params.time, price } };
                renderAllDrawings();
                renderInProgress();
            }
        } else if (drawingState) {
            drawingState = null;
            renderAllDrawings();
        }

        // ── OHLC legend ──
        if (!olLegend) return;
        const d = params.seriesData?.get(candleSeries);
        if (!d || !params.time) {
            olLegend.style.opacity = '0';
            return;
        }
        const dp = decimals(currentPair);
        const o  = d.open  != null ? d.open.toFixed(dp)  : '–';
        const h  = d.high  != null ? d.high.toFixed(dp)  : '–';
        const l  = d.low   != null ? d.low.toFixed(dp)   : '–';
        const c  = d.close != null ? d.close.toFixed(dp) : '–';
        if (olO)  olO.textContent  = o;
        if (olH)  { olH.textContent = h; olH.className = 'ol-val ol-up'; }
        if (olL)  { olL.textContent = l; olL.className = 'ol-val ol-dn'; }
        if (olC)  olC.textContent  = c;
        if (olChg && d.open != null && d.close != null) {
            const diff = d.close - d.open;
            const pct  = d.open ? (diff / d.open * 100) : 0;
            const sign = diff >= 0 ? '+' : '';
            olChg.textContent = `${sign}${diff.toFixed(dp)} (${sign}${pct.toFixed(2)}%)`;
            olChg.className   = 'ol-val ' + (diff >= 0 ? 'ol-up' : 'ol-dn');
        }
        olLegend.style.opacity = '1';
    });

    // Periodically re-render drawings to track zoom/pan
    setInterval(() => { if (drawings.length > 0) renderAllDrawings(); }, 120);
}

function screenToChart(x, y) {
    try {
        const time  = chart.timeScale().coordinateToTime(x);
        const price = (mainSeries || candleSeries).coordinateToPrice(y);
        return { time, price };
    } catch (e) { return { time: null, price: null }; }
}

function chartToScreen(time, price) {
    try {
        const x = time  != null ? chart.timeScale().timeToCoordinate(time)                       : null;
        const y = price != null ? (mainSeries || candleSeries).priceToCoordinate(price)          : null;
        return { x, y };
    } catch (e) { return { x: null, y: null }; }
}

function snapPrice(rawPrice, x) {
    if (!magnetMode || lastCandleData.length === 0) return rawPrice;
    const time = chart.timeScale().coordinateToTime(x);
    if (!time) return rawPrice;
    let nearest = null, minDist = Infinity;
    for (const c of lastCandleData) {
        const d = Math.abs(c.time - time);
        if (d < minDist) { minDist = d; nearest = c; }
    }
    if (!nearest) return rawPrice;
    const candidates = [nearest.open, nearest.high, nearest.low, nearest.close];
    let snapP = rawPrice, snapD = Infinity;
    for (const p of candidates) { const d = Math.abs(p - rawPrice); if (d < snapD) { snapD = d; snapP = p; } }
    return snapP;
}

// (SVG mouse handlers removed — drawing now uses chart.subscribeClick in initDrawingOverlay)

function addDrawing(d) {
    d.id = ++drawingIdCtr;
    d.visible = true;
    drawings.push(d);
}

function eraseAt(x, y) {
    const THRESH = 8;
    drawings = drawings.filter(d => {
        if (d.type === 'hline') {
            const s = chartToScreen(d.time || 0, d.price);
            return s.y == null || Math.abs(s.y - y) > THRESH;
        }
        if (d.type === 'vline') {
            const s = chartToScreen(d.time, 0);
            return s.x == null || Math.abs(s.x - x) > THRESH;
        }
        return true;
    });
    renderAllDrawings();
}

// ── Render all stored drawings onto SVG ────────────────────────────────────────
function renderAllDrawings() {
    if (!svgEl) return;
    // Clear all drawing elements
    while (svgEl.firstChild) svgEl.removeChild(svgEl.firstChild);
    if (!drawingsVisible) return;

    // Expire measure drawings
    drawings = drawings.filter(d => !d.ttl || d.ttl > Date.now());

    for (const d of drawings) {
        if (!d.visible) continue;
        renderDrawing(d);
    }
}

function renderDrawing(d) {
    switch (d.type) {
        case 'hline':            renderHLine(d);           break;
        case 'hray':             renderHRay(d);            break;
        case 'vline':            renderVLine(d);           break;
        case 'crossline':        renderCrossLine(d);       break;
        case 'trendline':        renderTrendLine(d);       break;
        case 'ray':              renderRay(d);             break;
        case 'extended-line':    renderExtendedLine(d);    break;
        case 'trend-angle':      renderTrendAngle(d);      break;
        case 'parallel-channel': renderParallelChannel(d); break;
        case 'regression-trend': renderRegressionTrend(d); break;
        case 'flat-top':         renderFlatTop(d);         break;
        case 'pitchfork':        renderPitchfork(d, 'standard'); break;
        case 'schiff-pitchfork': renderPitchfork(d, 'schiff');   break;
        case 'modified-schiff':  renderPitchfork(d, 'modified'); break;
        case 'rectangle':        renderRectangle(d);       break;
        case 'fibonacci':        renderFibonacci(d);       break;
        case 'text':             renderText(d);            break;
        case 'note':             renderNote(d);            break;
        case 'measure':          renderMeasure(d);         break;
    }
}

function svgNode(tag, attrs) {
    const el = document.createElementNS('http://www.w3.org/2000/svg', tag);
    for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
    svgEl.appendChild(el);
    return el;
}

function renderHLine(d) {
    const s = chartToScreen(null, d.price);
    if (s.y == null) return;
    const w = svgEl.clientWidth || svgEl.getBoundingClientRect().width || 800;
    svgNode('line', { x1: 0, y1: s.y, x2: w, y2: s.y, stroke: d.color, 'stroke-width': d.width || 1, 'stroke-dasharray': '5,3', 'class': 'drawing-line' });
    svgNode('text', { x: w - 4, y: s.y - 4, fill: d.color, 'font-size': '10', 'text-anchor': 'end', 'class': 'drawing-label' }).textContent = (d.price || 0).toFixed(decimals(currentPair));
}

function renderHRay(d) {
    const s = chartToScreen(d.time, d.price);
    if (s.x == null) return;
    const w = svgEl.clientWidth || 800;
    svgNode('line', { x1: s.x, y1: s.y, x2: w, y2: s.y, stroke: d.color, 'stroke-width': d.width || 1, 'stroke-dasharray': '5,3', 'class': 'drawing-line' });
    svgNode('circle', { cx: s.x, cy: s.y, r: 3, fill: d.color });
    svgNode('text', { x: w - 4, y: s.y - 4, fill: d.color, 'font-size': '10', 'text-anchor': 'end', 'class': 'drawing-label' }).textContent = (d.price || 0).toFixed(decimals(currentPair));
}

function renderVLine(d) {
    const s = chartToScreen(d.time, null);
    if (s.x == null) return;
    const h = svgEl.clientHeight || svgEl.getBoundingClientRect().height || 600;
    svgNode('line', { x1: s.x, y1: 0, x2: s.x, y2: h, stroke: d.color, 'stroke-width': d.width || 1, 'stroke-dasharray': '5,3', 'class': 'drawing-line' });
}

function renderCrossLine(d) {
    const s = chartToScreen(d.time, d.price);
    if (s.x == null) return;
    const w = svgEl.clientWidth || 800;
    const h = svgEl.clientHeight || 600;
    svgNode('line', { x1: 0, y1: s.y, x2: w, y2: s.y, stroke: d.color, 'stroke-width': d.width||1, 'stroke-dasharray': '4,3', 'class': 'drawing-line' });
    svgNode('line', { x1: s.x, y1: 0, x2: s.x, y2: h, stroke: d.color, 'stroke-width': d.width||1, 'stroke-dasharray': '4,3', 'class': 'drawing-line' });
    svgNode('circle', { cx: s.x, cy: s.y, r: 3, fill: d.color });
}

function renderTrendLine(d) {
    const s1 = chartToScreen(d.p1.time, d.p1.price);
    const s2 = chartToScreen(d.p2.time, d.p2.price);
    if (s1.x == null || s2.x == null) return;
    svgNode('line', { x1: s1.x, y1: s1.y, x2: s2.x, y2: s2.y, stroke: d.color, 'stroke-width': d.width || 1.5, 'class': 'drawing-line' });
    svgNode('circle', { cx: s1.x, cy: s1.y, r: 3, fill: d.color });
    svgNode('circle', { cx: s2.x, cy: s2.y, r: 3, fill: d.color });
}

function _lineExtend(s1, s2, toLeft, toRight, w) {
    const dx = s2.x - s1.x, dy = s2.y - s1.y;
    if (Math.abs(dx) < 0.001) return { x1: s1.x, y1: toLeft ? 0 : s1.y, x2: s1.x, y2: toRight ? (svgEl.clientHeight||600) : s1.y };
    const slope = dy / dx;
    const x1e = toLeft  ? 0 : s1.x,  y1e = s1.y + slope * (x1e - s1.x);
    const x2e = toRight ? w : s2.x,  y2e = s1.y + slope * (x2e - s1.x);
    return { x1: x1e, y1: y1e, x2: x2e, y2: y2e };
}

function renderRay(d) {
    const s1 = chartToScreen(d.p1.time, d.p1.price);
    const s2 = chartToScreen(d.p2.time, d.p2.price);
    if (s1.x == null || s2.x == null) return;
    const w = svgEl.clientWidth || 800;
    const e = _lineExtend(s1, s2, false, true, w);
    svgNode('line', { x1: s1.x, y1: s1.y, x2: e.x2, y2: e.y2, stroke: d.color, 'stroke-width': d.width||1.5, 'class': 'drawing-line' });
    svgNode('circle', { cx: s1.x, cy: s1.y, r: 3, fill: d.color });
}

function renderExtendedLine(d) {
    const s1 = chartToScreen(d.p1.time, d.p1.price);
    const s2 = chartToScreen(d.p2.time, d.p2.price);
    if (s1.x == null || s2.x == null) return;
    const w = svgEl.clientWidth || 800;
    const e = _lineExtend(s1, s2, true, true, w);
    svgNode('line', { x1: e.x1, y1: e.y1, x2: e.x2, y2: e.y2, stroke: d.color, 'stroke-width': d.width||1.5, 'stroke-dasharray': '6,3', 'class': 'drawing-line' });
    svgNode('circle', { cx: s1.x, cy: s1.y, r: 3, fill: d.color });
    svgNode('circle', { cx: s2.x, cy: s2.y, r: 3, fill: d.color });
}

function renderTrendAngle(d) {
    renderTrendLine(d);
    const s1 = chartToScreen(d.p1.time, d.p1.price);
    const s2 = chartToScreen(d.p2.time, d.p2.price);
    if (s1.x == null || s2.x == null) return;
    const dx = s2.x - s1.x, dy = -(s2.y - s1.y);
    const angle = Math.atan2(dy, Math.abs(dx)) * 180 / Math.PI;
    const mx = (s1.x + s2.x) / 2, my = (s1.y + s2.y) / 2;
    svgNode('text', { x: mx + 5, y: my - 5, fill: d.color, 'font-size': '10', 'class': 'drawing-label' }).textContent = `${angle.toFixed(1)}°`;
}

function renderParallelChannel(d) {
    if (!d.p3) return;
    const s1 = chartToScreen(d.p1.time, d.p1.price);
    const s2 = chartToScreen(d.p2.time, d.p2.price);
    const s3 = chartToScreen(d.p3.time, d.p3.price);
    if (s1.x == null || s2.x == null || s3.x == null) return;
    const offsetY = s3.y - s1.y;
    svgNode('line', { x1: s1.x, y1: s1.y, x2: s2.x, y2: s2.y, stroke: d.color, 'stroke-width': d.width||1.5, 'class': 'drawing-line' });
    svgNode('line', { x1: s1.x, y1: s1.y+offsetY, x2: s2.x, y2: s2.y+offsetY, stroke: d.color, 'stroke-width': d.width||1.5, 'stroke-dasharray': '5,3', 'class': 'drawing-line' });
    svgNode('polygon', { points: `${s1.x},${s1.y} ${s2.x},${s2.y} ${s2.x},${s2.y+offsetY} ${s1.x},${s1.y+offsetY}`, fill: d.color+'15', stroke: 'none' });
    svgNode('line', { x1: s1.x, y1: s1.y, x2: s1.x, y2: s1.y+offsetY, stroke: d.color+'60', 'stroke-width': 0.8 });
    svgNode('line', { x1: s2.x, y1: s2.y, x2: s2.x, y2: s2.y+offsetY, stroke: d.color+'60', 'stroke-width': 0.8 });
}

function renderRegressionTrend(d) {
    const s1 = chartToScreen(d.p1.time, d.p1.price);
    const s2 = chartToScreen(d.p2.time, d.p2.price);
    if (s1.x == null || s2.x == null) return;
    const t1 = Math.min(d.p1.time, d.p2.time), t2 = Math.max(d.p1.time, d.p2.time);
    const pts = lastCandleData
        .filter(c => c.time >= t1 && c.time <= t2)
        .map(c => { const s = chartToScreen(c.time, c.close); return s.x != null ? {x: s.x, y: s.y} : null; })
        .filter(Boolean);
    if (pts.length < 2) { renderTrendLine(d); return; }
    const n = pts.length;
    const mx = pts.reduce((a,p)=>a+p.x,0)/n, my = pts.reduce((a,p)=>a+p.y,0)/n;
    const num = pts.reduce((a,p)=>a+(p.x-mx)*(p.y-my),0);
    const den = pts.reduce((a,p)=>a+(p.x-mx)**2,0);
    if (den === 0) return;
    const sl = num/den, ic = my - sl*mx;
    const x1r = pts[0].x, y1r = sl*x1r+ic, x2r = pts[n-1].x, y2r = sl*x2r+ic;
    const std = Math.sqrt(pts.reduce((a,p)=>a+(p.y-(sl*p.x+ic))**2,0)/n);
    svgNode('line', { x1: x1r, y1: y1r, x2: x2r, y2: y2r, stroke: d.color, 'stroke-width': 1.5 });
    svgNode('line', { x1: x1r, y1: y1r-2*std, x2: x2r, y2: y2r-2*std, stroke: d.color+'99', 'stroke-width': 1, 'stroke-dasharray': '5,3' });
    svgNode('line', { x1: x1r, y1: y1r+2*std, x2: x2r, y2: y2r+2*std, stroke: d.color+'99', 'stroke-width': 1, 'stroke-dasharray': '5,3' });
    svgNode('polygon', { points: `${x1r},${y1r-2*std} ${x2r},${y2r-2*std} ${x2r},${y2r+2*std} ${x1r},${y1r+2*std}`, fill: d.color+'12', stroke: 'none' });
}

function renderFlatTop(d) {
    if (!d.p3) return;
    const s1 = chartToScreen(d.p1.time, d.p1.price);
    const s2 = chartToScreen(d.p2.time, d.p2.price);
    const s3 = chartToScreen(d.p3.time, d.p3.price);
    if (s1.x == null || s2.x == null || s3.x == null) return;
    // Flat top: horizontal top (s1.y), angled bottom
    const topY = Math.min(s1.y, s2.y);
    svgNode('line', { x1: s1.x, y1: topY, x2: s2.x, y2: topY, stroke: d.color, 'stroke-width': d.width||1.5 });
    svgNode('line', { x1: s1.x, y1: s3.y, x2: s2.x, y2: s3.y + (s2.y - s1.y), stroke: d.color, 'stroke-width': d.width||1.5, 'stroke-dasharray': '5,3' });
    svgNode('polygon', { points: `${s1.x},${topY} ${s2.x},${topY} ${s2.x},${s3.y+(s2.y-s1.y)} ${s1.x},${s3.y}`, fill: d.color+'12', stroke: 'none' });
}

function renderPitchfork(d, variant) {
    if (!d.p3) return;
    const sp = chartToScreen(d.p1.time, d.p1.price);  // pivot/handle
    const s2 = chartToScreen(d.p2.time, d.p2.price);  // upper
    const s3 = chartToScreen(d.p3.time, d.p3.price);  // lower
    if (sp.x == null || s2.x == null || s3.x == null) return;
    const w = svgEl.clientWidth || 800;

    let px = sp.x, py = sp.y;
    if (variant === 'schiff') {
        px = sp.x + (s2.x + s3.x)/2 - sp.x;
        py = sp.y;
    } else if (variant === 'modified') {
        px = (sp.x + (s2.x+s3.x)/2) / 2;
        py = (sp.y + (s2.y+s3.y)/2) / 2;
    }

    const midX = (s2.x + s3.x) / 2, midY = (s2.y + s3.y) / 2;
    const dx = midX - px, dy = midY - py;
    const t = dx !== 0 ? (w - px) / dx : 10;

    // Median line
    svgNode('line', { x1: px, y1: py, x2: px + dx*t, y2: py + dy*t, stroke: d.color, 'stroke-width': 1.5, 'class': 'drawing-line' });
    // Upper prong (parallel to median, from p2)
    svgNode('line', { x1: s2.x, y1: s2.y, x2: s2.x + dx*t, y2: s2.y + dy*t, stroke: d.color, 'stroke-width': 1, 'stroke-dasharray': '5,3' });
    // Lower prong (parallel to median, from p3)
    svgNode('line', { x1: s3.x, y1: s3.y, x2: s3.x + dx*t, y2: s3.y + dy*t, stroke: d.color, 'stroke-width': 1, 'stroke-dasharray': '5,3' });
    // Handle connecting lines
    svgNode('line', { x1: px, y1: py, x2: s2.x, y2: s2.y, stroke: d.color+'70', 'stroke-width': 0.8 });
    svgNode('line', { x1: px, y1: py, x2: s3.x, y2: s3.y, stroke: d.color+'70', 'stroke-width': 0.8 });
    svgNode('line', { x1: s2.x, y1: s2.y, x2: s3.x, y2: s3.y, stroke: d.color+'70', 'stroke-width': 0.8 });
    svgNode('circle', { cx: px, cy: py, r: 3, fill: d.color });
    svgNode('circle', { cx: s2.x, cy: s2.y, r: 2.5, fill: d.color });
    svgNode('circle', { cx: s3.x, cy: s3.y, r: 2.5, fill: d.color });
}

function renderRectangle(d) {
    const s1 = chartToScreen(d.p1.time, d.p1.price);
    const s2 = chartToScreen(d.p2.time, d.p2.price);
    if (s1.x == null || s2.x == null) return;
    const x = Math.min(s1.x, s2.x), y = Math.min(s1.y, s2.y);
    const w = Math.abs(s2.x - s1.x), h = Math.abs(s2.y - s1.y);
    svgNode('rect', { x, y, width: w, height: h, stroke: d.color, 'stroke-width': d.width || 1, 'class': 'drawing-rect', fill: `${d.color}10` });
}

function renderFibonacci(d) {
    const priceHigh = Math.max(d.p1.price, d.p2.price);
    const priceLow  = Math.min(d.p1.price, d.p2.price);
    const priceRange = priceHigh - priceLow;
    const w = svgEl.clientWidth || 800;
    const fibLevels = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0];
    const fibColors = ['#26a69a','#2962ff','#9c6cf5','#f5a623','#9c6cf5','#2962ff','#ef5350'];
    fibLevels.forEach((lvl, i) => {
        const price = priceHigh - lvl * priceRange;
        const s = chartToScreen(null, price);
        if (s.y == null) return;
        svgNode('line', { x1: 0, y1: s.y, x2: w, y2: s.y, stroke: fibColors[i], 'stroke-width': 1, 'stroke-dasharray': '6,3', 'class': 'drawing-line' });
        svgNode('text', { x: 4, y: s.y - 3, fill: fibColors[i], 'font-size': '9.5', 'class': 'drawing-label' })
            .textContent = `${(lvl * 100).toFixed(1)}%  ${price.toFixed(decimals(currentPair))}`;
    });
    // Reference diagonal line
    const s1 = chartToScreen(d.p1.time, d.p1.price);
    const s2 = chartToScreen(d.p2.time, d.p2.price);
    if (s1.x != null && s2.x != null) {
        svgNode('line', { x1: s1.x, y1: s1.y, x2: s2.x, y2: s2.y, stroke: '#9c6cf5', 'stroke-width': 0.8, 'stroke-dasharray': '3,3', 'class': 'drawing-line' });
    }
}

function renderText(d) {
    const s = chartToScreen(d.time, d.price);
    if (s.x == null) return;
    const el = svgNode('text', { x: s.x, y: s.y, fill: d.color || '#131722', 'font-size': '13', 'class': 'drawing-label' });
    el.textContent = d.text || '';
}

function renderNote(d) {
    const s = chartToScreen(d.time, d.price);
    if (s.x == null) return;
    svgNode('circle', { cx: s.x, cy: s.y, r: 14, fill: (d.color || '#2962ff') + '22', stroke: d.color || '#2962ff', 'stroke-width': 1 });
    const el = svgNode('text', { x: s.x, y: s.y + 4, fill: d.color || '#2962ff', 'font-size': '11', 'text-anchor': 'middle', 'class': 'drawing-label' });
    el.textContent = d.text || '★';
}

function renderMeasure(d) {
    const s1 = chartToScreen(d.p1.time, d.p1.price);
    const s2 = chartToScreen(d.p2.time, d.p2.price);
    if (s1.x == null || s2.x == null) return;
    const x = Math.min(s1.x, s2.x), y = Math.min(s1.y, s2.y);
    const w = Math.abs(s2.x - s1.x), h = Math.abs(s2.y - s1.y);
    svgNode('rect', { x, y, width: w, height: h, stroke: d.color, 'stroke-width': 1, fill: d.color + '15', 'class': 'drawing-measure-box' });
    const labelEl = svgNode('text', { x: x + w / 2, y: y + h / 2 + 4, fill: d.color, 'font-size': '11', 'text-anchor': 'middle', 'class': 'drawing-label' });
    labelEl.textContent = d.label || '';
}

// ── In-progress ghost drawing (trendline awaiting 2nd click) ─────────────────
function renderInProgress() {
    if (!drawingState) return;
    const { type, sc, ec } = drawingState;
    if (!sc || !ec) return;
    const ghost = { p1: sc, p2: ec, color: 'rgba(41,98,255,0.55)', width: 1.5 };
    if (type === 'trendline') renderTrendLine(ghost);
}

// ── Text annotation input ──────────────────────────────────────────────────────
function showTextInput(x, y, coords) {
    const overlay = document.getElementById('text-input-overlay');
    const input   = document.getElementById('text-tool-input');
    if (!overlay || !input) return;
    overlay.style.display = 'block';
    overlay.style.left    = `${x + 4}px`;
    overlay.style.top     = `${y - 14}px`;
    input.value = '';
    input.focus();

    const isNote = activeTool === 'note';

    function commit() {
        const txt = input.value.trim();
        if (txt) {
            addDrawing({ type: activeTool, text: txt, time: coords.time, price: coords.price, color: '#131722' });
            renderAllDrawings();
        }
        overlay.style.display = 'none';
        input.removeEventListener('blur', commit);
        input.removeEventListener('keydown', onKey);
        setDrawingTool('cursor', document.getElementById('tool-cursor'));
    }
    function onKey(e) { if (e.key === 'Enter') commit(); if (e.key === 'Escape') { overlay.style.display = 'none'; } }
    input.addEventListener('blur', commit);
    input.addEventListener('keydown', onKey);
}

// ── Tool selection ─────────────────────────────────────────────────────────────
let _toolClickPoints = [];   // accumulate clicks for 3-click tools

function setDrawingTool(tool, btn) {
    activeTool      = tool;
    _drawFirstClick = null;
    _toolClickPoints = [];
    drawingState    = null;

    document.querySelectorAll('#drawing-toolbar .tool-btn[id^="tool-"]').forEach(b => {
        if (['tool-magnet','tool-lock','tool-eye','tool-trash'].includes(b.id)) return;
        b.classList.remove('active');
    });
    if (btn) btn.classList.add('active');

    if (!svgEl) return;
    if (tool === 'cursor') {
        svgEl.classList.remove('drawing-mode', 'eraser-mode');
    } else if (tool === 'eraser') {
        svgEl.classList.remove('drawing-mode');
        svgEl.classList.add('eraser-mode');
    } else {
        svgEl.classList.remove('eraser-mode');
        svgEl.classList.add('drawing-mode');
    }
}

// ── Tool Group Flyout ─────────────────────────────────────────────────────────
function toggleToolGroup(group, e) {
    if (e) e.stopPropagation();
    const flyout = document.getElementById(`flyout-${group}`);
    if (!flyout) return;
    const isOpen = flyout.classList.contains('open');
    document.querySelectorAll('.tool-group-flyout').forEach(f => f.classList.remove('open'));
    if (!isOpen) flyout.classList.add('open');
}

function selectGroupTool(tool, group, itemEl) {
    // Close flyout
    document.querySelectorAll('.tool-group-flyout').forEach(f => f.classList.remove('open'));
    // Mark item active inside flyout
    document.querySelectorAll(`#flyout-${group} .flyout-item`).forEach(b => b.classList.remove('active'));
    if (itemEl) itemEl.classList.add('active');
    // Activate the group button
    const groupBtn = document.getElementById(`tool-${group}-group`);
    setDrawingTool(tool, groupBtn);
}

// Close flyouts when clicking outside toolbar
document.addEventListener('click', (e) => {
    if (!e.target.closest('#drawing-toolbar')) {
        document.querySelectorAll('.tool-group-flyout').forEach(f => f.classList.remove('open'));
    }
});

function toggleMagnet(btn) {
    magnetMode = !magnetMode;
    btn.classList.toggle('toggled', magnetMode);
}

function toggleLockDrawings(btn) {
    drawingsLocked = !drawingsLocked;
    btn.classList.toggle('toggled', drawingsLocked);
    btn.querySelector('i')?.setAttribute('data-lucide', drawingsLocked ? 'lock' : 'unlock');
    lucide.createIcons();
}

function toggleDrawingsVisible(btn) {
    drawingsVisible = !drawingsVisible;
    btn.querySelector('i')?.setAttribute('data-lucide', drawingsVisible ? 'eye' : 'eye-off');
    lucide.createIcons();
    renderAllDrawings();
}

function deleteAllDrawings() {
    if (!confirm('Delete all drawings?')) return;
    drawings = [];
    renderAllDrawings();
}

// ── Live candle helpers ───────────────────────────────────────────────────────
let _lastLivePrice    = 0;
let _liveCandleOpen   = 0;
let _liveCandleHigh   = 0;
let _liveCandleLow    = 0;
let _liveCandleBucket = 0;   // tracks which bucket we're in; reset on bucket change
let _lastChartUpdateMs = 0;  // ms timestamp of last series.update() call

// Returns the Unix-second timestamp rounded DOWN to the current candle period.
// This is what LightweightCharts expects — must match the period of the loaded data.
const TF_SECONDS = { '1M': 60, '5M': 300, '15M': 900, '1H': 3600, '4H': 14400, '1D': 86400, '1W': 604800 };
function getCurrentCandleTime() {
    // Floor UTC bucket first, THEN add IST offset — so the result always matches
    // the historical bar timestamps (which are stored as utcBucket + IST_OFFSET).
    // Doing floor(utcNow + IST_OFFSET) instead would misalign for 1H/4H/1D where
    // IST_OFFSET is not an exact multiple of the interval.
    // Verified: 15M uses b=900; IST_OFFSET(19800) % 900 = 0, so bucket boundary is exact.
    const b = TF_SECONDS[currentTimeframe] || 86400;
    return Math.floor(Math.floor(Date.now() / 1000) / b) * b + IST_OFFSET;
}

// Called after new candle data is loaded; seeds the live candle from the last bar.
function initLiveCandleFromHistory() {
    if (lastCandleData.length === 0) return;
    const last = lastCandleData[lastCandleData.length - 1];
    _liveCandleBucket = getCurrentCandleTime();
    // If the last historical bar IS the current bucket, inherit its OHLC.
    // Otherwise start a fresh candle opening at the previous close.
    if (last.time >= _liveCandleBucket) {
        _liveCandleOpen = last.open;
        _liveCandleHigh = last.high;
        _liveCandleLow  = last.low;
        _lastLivePrice  = last.close;
    } else {
        _liveCandleOpen = last.close;
        _liveCandleHigh = last.close;
        _liveCandleLow  = last.close;
        _lastLivePrice  = last.close;
    }
}

// Writes one bar to the active series — called at most once per second.
function _pushLiveCandle(price) {
    const t = getCurrentCandleTime();

    // New bucket — open a fresh candle
    if (t !== _liveCandleBucket && _liveCandleBucket !== 0) {
        _liveCandleOpen   = _lastLivePrice || price;
        _liveCandleHigh   = price;
        _liveCandleLow    = price;
        _liveCandleBucket = t;
    }

    _liveCandleHigh = Math.max(_liveCandleHigh, price);
    _liveCandleLow  = Math.min(_liveCandleLow,  price);

    const bar = { time: t, open: _liveCandleOpen,
                  high: _liveCandleHigh, low: _liveCandleLow, close: price };
    try {
        if (currentChartType === 'candlestick' || currentChartType === 'heikinashi') {
            candleSeries.update(bar);
        } else if (altSeries) {
            if (currentChartType === 'bar') altSeries.update(bar);
            else altSeries.update({ time: t, value: price });
        }
    } catch (e) {}
}

function updateLiveCandle(price) {
    if (!candleSeries || price <= 0) return;

    // First tick — seed bucket and OHLC from history
    if (_liveCandleBucket === 0) {
        _liveCandleBucket = getCurrentCandleTime();
        if (_liveCandleOpen === 0) initLiveCandleFromHistory();
        if (_liveCandleOpen === 0) {
            _liveCandleOpen = price; _liveCandleHigh = price; _liveCandleLow = price;
        }
    }

    // Always track true high/low in memory on every tick
    _lastLivePrice  = price;
    _liveCandleHigh = Math.max(_liveCandleHigh, price);
    _liveCandleLow  = Math.min(_liveCandleLow,  price);

    // Throttle: push to chart at most once per second
    const now = Date.now();
    if (now - _lastChartUpdateMs < 1000) return;
    _lastChartUpdateMs = now;
    _pushLiveCandle(price);
}

// 1-second flush: ensures chart reflects latest price even during quiet WS periods
setInterval(() => {
    if (_lastLivePrice <= 0 || !candleSeries) return;
    const now = Date.now();
    if (now - _lastChartUpdateMs >= 1000) {
        _lastChartUpdateMs = now;
        _pushLiveCandle(_lastLivePrice);
    }
}, 1000);

// ── Candle Countdown Timer ────────────────────────────────────────────────────
function updateCountdownTimer() {
    const timeEl = document.getElementById('cd-time');
    const tfEl   = document.getElementById('cd-tf');
    const barEl  = document.getElementById('cd-bar-fill');
    if (!timeEl) return;

    const b       = TF_SECONDS[currentTimeframe] || 86400;
    const utcNow  = Math.floor(Date.now() / 1000);
    const elapsed = utcNow % b;
    const remain  = b - elapsed;
    const pct     = (elapsed / b) * 100;

    if (barEl) barEl.style.width = pct + '%';
    if (tfEl)  tfEl.textContent  = currentTimeframe;

    if (b >= 604800) {
        const d = Math.floor(remain / 86400);
        const h = Math.floor((remain % 86400) / 3600);
        const m = Math.floor((remain % 3600) / 60);
        timeEl.textContent = `${d}d ${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}`;
    } else if (b >= 3600) {
        const h = Math.floor(remain / 3600);
        const m = Math.floor((remain % 3600) / 60);
        const s = remain % 60;
        timeEl.textContent = `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
    } else {
        const m = Math.floor(remain / 60);
        const s = remain % 60;
        timeEl.textContent = `${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
    }
}
setInterval(updateCountdownTimer, 1000);
updateCountdownTimer();

// ── Watchlist Price Polling (non-WebSocket pairs) ─────────────────────────────
async function pollWatchlistPrices() {
    try {
        const res  = await fetch(`${API_URL}/api/watchlist_prices`);
        if (!res.ok) return;
        const json = await res.json();
        const data = json.data || {};
        for (const [pair, info] of Object.entries(data)) {
            // Populate priceCache so selectPair shows correct price immediately
            if (!priceCache[pair]) priceCache[pair] = {};
            priceCache[pair].price      = info.price;
            priceCache[pair].change_pct = info.change_pct;

            const id   = pair.replace(/\//g, '-');
            const dec  = decimals(pair);
            const isUp = info.change_pct >= 0;
            const pEl  = document.getElementById(`price-${id}`);
            const cEl  = document.getElementById(`wchg-${id}`);
            if (pEl) { pEl.textContent = info.price.toFixed(dec); pEl.style.color = isUp ? 'var(--green)' : 'var(--red)'; }
            if (cEl) { cEl.textContent = (isUp ? '+' : '') + info.change_pct.toFixed(4) + '%'; cEl.className = `watch-change ${isUp ? 'up' : 'down'}`; }

            // If this is the active pair and not in WebSocket feed, update header
            if (pair === currentPair && !['EUR/USD','USD/JPY','BTC/USD'].includes(pair)) {
                const hpEl = document.getElementById('header-price');
                const hcEl = document.getElementById('header-change');
                if (hpEl) { hpEl.textContent = info.price.toFixed(dec); hpEl.className = `header-price ${isUp ? 'up' : 'down'}`; }
                if (hcEl) { hcEl.textContent = (isUp?'+':'') + info.change_pct.toFixed(4) + '%'; hcEl.className = `header-change ${isUp?'up':'down'}`; hcEl.style.display = 'inline-block'; }
                updateLiveCandle(info.price);
            }
        }
    } catch (e) { /* silent fail */ }
}
setInterval(pollWatchlistPrices, 15000);

// ── Add agent signal marker to chart ─────────────────────────────────────────
function addSignalMarker(decision, confidence, price) {
    if (!candleSeries || !decision) return;
    const isBuy = decision.toUpperCase() === "BUY";
    const now   = getCurrentCandleTime();
    signalMarkers.push({
        time:     now,
        position: isBuy ? "belowBar" : "aboveBar",
        color:    isBuy ? "#26a69a" : "#ef5350",
        shape:    isBuy ? "arrowUp" : "arrowDown",
        text:     `${decision} ${confidence}%`,
    });
    // Cap to last 30 markers
    if (signalMarkers.length > 30) signalMarkers = signalMarkers.slice(-30);
    candleSeries.setMarkers(signalMarkers);
}

// ── WebSocket ─────────────────────────────────────────────────────────────────
function connectWS() {
    if (ws && ws.readyState === WebSocket.OPEN) return;
    ws = new WebSocket(WS_URL);

    ws.onopen = () => {
        setConnectionStatus(true);
        if (wsReconnectTimer) { clearTimeout(wsReconnectTimer); wsReconnectTimer = null; }
        console.log("[WS] Connected");
    };

    ws.onclose = () => {
        setConnectionStatus(false);
        console.warn("[WS] Disconnected — reconnecting in 3s");
        wsReconnectTimer = setTimeout(connectWS, 3000);
    };

    ws.onerror = (e) => console.error("[WS] Error:", e);

    ws.onmessage = (ev) => {
        try {
            const msg = JSON.parse(ev.data);
            handleMessage(msg);
        } catch (e) {
            console.error("[WS] Parse error:", e);
        }
    };
}

function setConnectionStatus(connected) {
    const el = document.getElementById("conn-status");
    const tx = document.getElementById("conn-text");
    if (!el || !tx) return;
    el.className  = "conn-status" + (connected ? " connected" : "");
    el.style.color = connected ? "var(--green)" : "var(--red)";
    tx.textContent = connected ? "LIVE" : "OFFLINE";
}

// ── Message Routing ───────────────────────────────────────────────────────────
function handleMessage(msg) {
    switch (msg.type) {
        case "price_update":     onPriceUpdate(msg);     break;
        case "agent_thought":    onAgentThought(msg);    break;
        case "market_sentiment": onSentiment(msg.data);  break;
        case "system_status":    onSystemStatus(msg);    break;
        case "portfolio_update": onPortfolioUpdate(msg.portfolio); break;
        case "news_update":      onNewsUpdate(msg);      break;
        case "signals_snapshot": restoreSignals(msg.signals); break;
        case "pong":             break;
        default: console.log("[WS] Unknown:", msg.type);
    }
}

// ── Price Update ──────────────────────────────────────────────────────────────
function onPriceUpdate(msg) {
    const { symbol, price, change_pct, indicators, source } = msg;
    priceCache[symbol] = { price, change_pct };
    if (indicators) indicatorsCache[symbol] = indicators;

    const dec  = decimals(symbol);
    const pFmt = price.toFixed(dec);
    const cFmt = (change_pct >= 0 ? "+" : "") + change_pct.toFixed(4) + "%";
    const isUp = change_pct >= 0;

    // Watchlist price
    const priceEl = document.getElementById(`price-${symbol.replace("/", "-")}`);
    if (priceEl) { priceEl.textContent = pFmt; priceEl.style.color = isUp ? "var(--green)" : "var(--red)"; }

    const chgEl = document.getElementById(`wchg-${symbol.replace("/", "-")}`);
    if (chgEl) { chgEl.textContent = cFmt; chgEl.className = `watch-change ${isUp ? "up" : "down"}`; }

    const srcEl = document.getElementById(`src-${symbol.replace("/", "-")}`);
    if (srcEl) srcEl.textContent = source || "Finnhub";

    // Header pair change %
    const hcEl = document.getElementById(`change-${symbol.replace("/", "-")}`);
    if (hcEl) { hcEl.textContent = cFmt; hcEl.className = `pair-change ${isUp ? "up" : "down"}`; }

    // If this is the active pair: update header + chart
    if (symbol === currentPair) {
        const hpEl = document.getElementById("header-price");
        if (hpEl) { hpEl.textContent = pFmt; hpEl.className = `header-price ${isUp ? "up" : "down"}`; }

        const hChEl = document.getElementById("header-change");
        if (hChEl) {
            hChEl.textContent = cFmt;
            hChEl.className = `header-change ${isUp ? "up" : "down"}`;
            hChEl.style.display = "inline-block";
        }

        // Update indicator bar
        if (indicators) updateIndicatorBar(indicators, symbol);

        // Update live candle
        updateLiveCandle(price);
    }
}

// ── Update indicator bar ──────────────────────────────────────────────────────
function updateIndicatorBar(ind, pair) {
    const ema20  = document.getElementById("ind-ema20");
    const ema50  = document.getElementById("ind-ema50");
    const rsi    = document.getElementById("ind-rsi");
    const macd   = document.getElementById("ind-macd");
    const trend  = document.getElementById("ind-trend");
    const dec    = decimals(pair);

    if (ema20 && ind.ema_20)   ema20.textContent  = parseFloat(ind.ema_20).toFixed(dec);
    if (ema50 && ind.ema_50)   ema50.textContent  = parseFloat(ind.ema_50).toFixed(dec);
    if (rsi && ind.rsi) {
        rsi.textContent = ind.rsi;
        rsi.className   = `ind-value ${ind.rsi < 30 ? "bullish" : ind.rsi > 70 ? "bearish" : "neutral"}`;
    }
    if (macd && ind.macd) {
        macd.textContent = parseFloat(ind.macd) > 0 ? `+${ind.macd}` : ind.macd;
        macd.className   = `ind-value ${ind.macd_signal === "BULLISH" ? "bullish" : "bearish"}`;
    }
    if (trend && ind.trend) {
        trend.textContent = ind.trend;
        trend.className   = `ind-value ${ind.trend === "UPTREND" ? "bullish" : "bearish"}`;
    }
    const bbPct = document.getElementById("ind-bb-pct");
    const atrEl = document.getElementById("ind-atr");
    if (bbPct && ind.bb_pct_b != null) {
        const pct = parseFloat(ind.bb_pct_b);
        bbPct.textContent = pct.toFixed(2);
        bbPct.className = `ind-value ${pct > 0.8 ? "bearish" : pct < 0.2 ? "bullish" : "neutral"}`;
    }
    if (atrEl && ind.atr != null) {
        atrEl.textContent = parseFloat(ind.atr).toFixed(decimals(pair));
        atrEl.className = "ind-value default";
    }
}

// ── Agent Thought ──────────────────────────────────────────────────────────────
function onAgentThought(msg) {
    const { agent, thought, pair, decision, confidence, risk_level, price } = msg;

    if (agent === "Orchestrator") {
        addBossCard(msg);
        // Update chart marker + signal indicator
        if (decision && pair === currentPair) {
            addSignalMarker(decision, confidence || 0, priceCache[currentPair]?.price);
            const sigEl = document.getElementById("ind-signal");
            if (sigEl) {
                const cls = decision === "BUY" ? "bullish" : decision === "SELL" ? "bearish" : "neutral";
                sigEl.textContent = `${decision} (${confidence || "?"}% confidence)`;
                sigEl.className   = `ind-value ${cls}`;
            }
            drawPredictionZone(decision, confidence || 50, priceCache[currentPair]?.price, currentPair);
        }
    } else {
        addAgentCard(agent, thought, pair, decision, confidence, risk_level);
    }
}

function _nowTS() {
    return new Date().toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function _keyReasoning(text) {
    // Strip markdown symbols, grab first ~200 chars broken at a sentence boundary
    const clean = text
        .replace(/\*\*/g, "").replace(/\*/g, "")
        .replace(/#{1,6}\s+/g, "").replace(/`/g, "")
        .replace(/\n{2,}/g, " ").replace(/\n/g, " ").trim();
    if (clean.length <= 220) return clean;
    const cut = clean.slice(0, 220);
    const last = Math.max(cut.lastIndexOf("."), cut.lastIndexOf("!"), cut.lastIndexOf("?"));
    return (last > 80 ? cut.slice(0, last + 1) : cut) + "…";
}

function _tradeLevels(price, decision, risk) {
    if (!price || !decision || decision === "HOLD") return "";
    const pct  = { LOW: 0.003, MEDIUM: 0.006, HIGH: 0.012 }[risk] || 0.005;
    const dec  = decimals(currentPair);
    const isBuy = decision === "BUY";
    const sl   = (isBuy ? price * (1 - pct)     : price * (1 + pct)).toFixed(dec);
    const tp   = (isBuy ? price * (1 + pct * 2) : price * (1 - pct * 2)).toFixed(dec);
    return `<div class="trade-levels">
        <div class="tl-item"><span class="tl-label">ENTRY</span><span class="tl-val">${price.toFixed(dec)}</span></div>
        <div class="tl-item"><span class="tl-label">STOP</span><span class="tl-val tl-sl">${sl}</span></div>
        <div class="tl-item"><span class="tl-label">TARGET</span><span class="tl-val tl-tp">${tp}</span></div>
    </div>`;
}

function addBossCard(msg) {
    const feed = document.getElementById("discussion-feed");
    if (!feed) return;

    const { thought, pair, decision, confidence, risk_level, price } = msg;
    const livePrice = price || priceCache[pair]?.price || 0;
    const decClass  = decision === "BUY" ? "buy" : decision === "SELL" ? "sell" : "hold";
    const reasoning = _keyReasoning(thought || "");
    const levels    = _tradeLevels(livePrice, decision, risk_level);
    const ts        = _nowTS();

    // Remove any previous boss card so there's always exactly one at top
    const old = document.getElementById("boss-card");
    if (old) old.remove();

    const card = document.createElement("div");
    card.id        = "boss-card";
    card.className = "agent-card orchestrator boss";
    card.innerHTML = `
        <div class="boss-header">
            <div class="agent-name-row">
                <div class="agent-icon" style="background:rgba(56,139,253,0.15)">
                    <i data-lucide="shield" style="color:var(--accent-blue);width:11px;height:11px"></i>
                </div>
                <span class="boss-title">STRATEGIC WAR ROOM</span>
                ${pair ? `<span class="agent-pair-badge">${pair}</span>` : ""}
            </div>
            <span class="card-ts">${ts}</span>
        </div>
        <div class="boss-decision-row">
            <span class="boss-decision ${decClass}">${decision || "—"}</span>
            <span class="boss-conf">${confidence || "?"}% confidence</span>
            <span class="boss-risk risk-${(risk_level||"").toLowerCase()}">${risk_level || ""}</span>
        </div>
        ${levels}
        <div class="boss-reasoning">${reasoning.replace(/\n/g, "<br>")}</div>
        <div class="boss-expand-btn" onclick="
            const r=this.previousElementSibling;
            const full=${JSON.stringify(thought.replace(/`/g,''))};
            if(this.dataset.open){r.innerHTML=this.dataset.short;delete this.dataset.open;this.textContent='Full analysis ▾';}
            else{this.dataset.short=r.innerHTML;r.innerHTML=full.replace(/\\n/g,'<br>');this.dataset.open=1;this.textContent='Show less ▴';}
        ">Full analysis ▾</div>
    `;

    feed.prepend(card);
    lucide.createIcons();
    feed.scrollTop = 0;
}

function getAgentStyle(agent) {
    if (agent.includes("Academic"))     return { cls: "academic",     color: "#7c3aed",          icon: "book-open" };
    if (agent.includes("Geopolitical")) return { cls: "geo",          color: "var(--orange)",    icon: "globe" };
    if (agent.includes("Quantitative")) return { cls: "quantitative", color: "#2962ff",          icon: "calculator" };
    if (agent.includes("User"))         return { cls: "user",         color: "var(--purple)",    icon: "user" };
    if (agent.includes("Orchestrator")) return { cls: "orchestrator", color: "var(--accent-blue)", icon: "shield" };
    if (agent.includes("Market"))       return { cls: "market",       color: "var(--green)",     icon: "activity" };
    return { cls: "", color: "var(--text-secondary)", icon: "message-square" };
}

function addAgentCard(agent, thought, pair, decision, confidence, risk_level) {
    const feed = document.getElementById("discussion-feed");
    if (!feed) return;

    const style   = getAgentStyle(agent);
    const ts      = _nowTS();
    const summary = _keyReasoning(thought || "");

    const decBadge = decision
        ? `<span class="decision-badge ${decision.toLowerCase()}">${decision}</span>` : "";
    const confBar  = confidence
        ? `<div class="confidence-bar">
               <div class="conf-track"><div class="conf-fill" style="width:${confidence}%;background:${style.color}"></div></div>
               <span class="conf-label">${confidence}%</span>
           </div>` : "";

    const card = document.createElement("div");
    card.className = `agent-card ${style.cls}`;
    card.innerHTML = `
        <div class="agent-header">
            <div class="agent-name-row">
                <div class="agent-icon" style="background:${style.color}22">
                    <i data-lucide="${style.icon}" style="color:${style.color};width:10px;height:10px"></i>
                </div>
                <span class="agent-name" style="color:${style.color}">${agent}</span>
                ${pair ? `<span class="agent-pair-badge">${pair}</span>` : ""}
            </div>
            <div style="display:flex;align-items:center;gap:6px">
                ${decBadge}
                <span class="card-ts">${ts}</span>
            </div>
        </div>
        <div class="agent-thought agent-summary">${summary.replace(/\n/g, "<br>")}</div>
        ${confBar}
        <span class="expand-btn" onclick="
            const s=this.previousElementSibling.previousElementSibling;
            const full=${JSON.stringify(thought.replace(/`/g,''))};
            if(this.dataset.open){s.innerHTML=${JSON.stringify(summary.replace(/\n/g,'<br>'))};delete this.dataset.open;this.textContent='Read more ▾';}
            else{s.innerHTML=full.replace(/\\n/g,'<br>');this.dataset.open=1;this.textContent='Show less ▴';}
        ">Read more ▾</span>
    `;

    // Insert after boss card (if present), so boss always stays on top
    const boss = document.getElementById("boss-card");
    if (boss && boss.nextSibling) {
        feed.insertBefore(card, boss.nextSibling);
    } else {
        feed.prepend(card);
    }
    lucide.createIcons();
    feed.scrollTop = 0;

    // Cap at 10 non-boss cards
    const cards = [...feed.querySelectorAll(".agent-card:not(.boss)")];
    if (cards.length > 10) cards.slice(10).forEach(c => c.remove());
}

// ── Refresh Now button ─────────────────────────────────────────────────────────
async function refreshAgents() {
    const btn = document.getElementById("refresh-agents-btn");
    if (btn) { btn.disabled = true; btn.textContent = "Analyzing…"; }
    try {
        const pair = currentPair.replace("/", "_");
        await fetch(`${API_URL}/api/refresh_agents?pair=${encodeURIComponent(currentPair)}`,
                    { method: "POST" });
    } catch (e) {
        console.error("[Refresh] Failed:", e);
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = "Refresh Now"; }
    }
}

// ── Sentiment ──────────────────────────────────────────────────────────────────
function onSentiment(data) {
    if (!data) return;
    const val   = parseInt(data.value);
    const label = (data.classification || "NEUTRAL").toUpperCase();

    const bar    = document.getElementById("sentiment-bar");
    const lbl    = document.getElementById("sentiment-label");
    const valEl  = document.getElementById("sentiment-value");

    if (bar)   bar.style.width = `${val}%`;
    if (lbl)   lbl.textContent = label;
    if (valEl) {
        valEl.textContent = val;
        valEl.style.color = val < 30 ? "var(--red)" : val > 70 ? "var(--green)" : "var(--orange)";
    }
}

// ── System Status (alerts) ────────────────────────────────────────────────────
function onSystemStatus(msg) {
    const container = document.getElementById("alerts-container");
    if (!container) return;

    const el  = document.createElement("div");
    const cls = msg.status === "warning" ? "alert-warning"
              : msg.status === "info"    ? "alert-info"
              : "alert-success";

    el.className = `alert-item ${cls}`;
    el.innerHTML = `<i data-lucide="${msg.status === "warning" ? "alert-triangle" : "info"}" style="width:12px;height:12px;flex-shrink:0"></i>
                    <span>${msg.message || ""}</span>`;
    container.prepend(el);
    lucide.createIcons();
    setTimeout(() => el.remove(), 15000);

    // Cap alerts
    while (container.children.length > 5) container.removeChild(container.lastChild);
}

// ── Portfolio Update ───────────────────────────────────────────────────────────
function onPortfolioUpdate(pf) {
    if (!pf) return;
    portfolio = pf;

    const balEl = document.getElementById("portfolio-value");
    if (balEl) balEl.textContent = `$${pf.balance.toFixed(2)}`;

    const posEl = document.getElementById("positions-count");
    if (posEl) posEl.textContent = (pf.positions || []).length;

    const listEl = document.getElementById("positions-list");
    if (listEl) {
        if (!pf.positions || pf.positions.length === 0) {
            listEl.textContent = "No open positions.";
        } else {
            listEl.innerHTML = pf.positions.map(p => {
                const current = priceCache[p.symbol]?.price || p.entry_price;
                const pnl = ((current - p.entry_price) * p.amount).toFixed(2);
                const cls = pnl >= 0 ? "color:var(--green)" : "color:var(--red)";
                return `<div class="position-row">
                    <span>${p.symbol} ${p.side.toUpperCase()} × ${p.amount}</span>
                    <span style="${cls}">${pnl >= 0 ? "+" : ""}$${pnl}</span>
                </div>`;
            }).join("");
        }
    }
}

// ── News Update (ticker) ───────────────────────────────────────────────────────
function onNewsUpdate(msg) {
    const headlines = msg.headlines || [];
    if (headlines.length === 0) return;
    const tickerEl = document.getElementById("ticker-content");
    if (tickerEl) {
        tickerEl.textContent = headlines
            .filter(h => h)
            .map(h => `📰 ${h}`)
            .join("   •   ");
    }
}

// ── Restore signals from snapshot ─────────────────────────────────────────────
function restoreSignals(signals) {
    if (!signals) return;
    const sigEl = document.getElementById("ind-signal");
    const sig   = signals[currentPair];
    if (sig && sigEl) {
        const cls = sig.decision === "BUY" ? "bullish" : sig.decision === "SELL" ? "bearish" : "neutral";
        sigEl.textContent = `${sig.decision} (${sig.confidence}% confidence)`;
        sigEl.className   = `ind-value ${cls}`;
    }
}

// ── Pair & Timeframe Switching ─────────────────────────────────────────────────
function selectPair(pair, tabEl) {
    if (pair === currentPair) return;
    currentPair = pair;

    // Update pair tabs in header
    document.querySelectorAll(".pair-tab").forEach(t => t.classList.remove("active"));
    if (tabEl) tabEl.classList.add("active");
    else {
        const t = document.querySelector(`.pair-tab[data-pair="${pair}"]`);
        if (t) t.classList.add("active");
    }

    // Update watchlist active state
    document.querySelectorAll(".watch-item").forEach(w => {
        w.classList.toggle("active", w.dataset.pair === pair);
    });

    // Update header price display
    const cached = priceCache[pair];
    const hpEl   = document.getElementById("header-price");
    if (hpEl) hpEl.textContent = cached ? cached.price.toFixed(decimals(pair)) : "–";
    // Reset header change badge for non-WebSocket pairs
    const hChEl = document.getElementById("header-change");
    if (hChEl && !cached) { hChEl.style.display = 'none'; }

    // Update indicator bar from cache
    if (indicatorsCache[pair]) updateIndicatorBar(indicatorsCache[pair], pair);

    // Reload chart
    signalMarkers = [];
    _lastLivePrice = 0; _liveCandleOpen = 0; _liveCandleHigh = 0; _liveCandleLow = 0; _liveCandleBucket = 0; _lastChartUpdateMs = 0;
    loadChartData(pair, currentTimeframe);
}

function setTimeframe(tf, btnEl) {
    currentTimeframe = tf;
    document.querySelectorAll(".tf-btn").forEach(b => b.classList.remove("active"));
    if (btnEl) btnEl.classList.add("active");
    signalMarkers = [];
    _lastLivePrice = 0; _liveCandleOpen = 0; _liveCandleHigh = 0; _liveCandleLow = 0; _liveCandleBucket = 0; _lastChartUpdateMs = 0;
    loadChartData(currentPair, tf);
}

// ── Trade Buttons ──────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
    document.getElementById("buy-btn").addEventListener("click", () => {
        if (!ws || ws.readyState !== WebSocket.OPEN) {
            alert("Not connected to server. Please wait...");
            return;
        }
        const price  = priceCache[currentPair]?.price || 0;
        const amount = parseFloat(document.getElementById("amount-input").value) || 1000;
        ws.send(JSON.stringify({ type: "execute_trade", symbol: currentPair, side: "buy", amount, price }));
        onSystemStatus({ status: "info", message: `BUY order submitted: ${currentPair} × ${amount} @ ${price.toFixed(decimals(currentPair))}` });
    });

    document.getElementById("sell-btn").addEventListener("click", () => {
        if (!ws || ws.readyState !== WebSocket.OPEN) return;
        const price  = priceCache[currentPair]?.price || 0;
        const amount = parseFloat(document.getElementById("amount-input").value) || 1000;
        ws.send(JSON.stringify({ type: "execute_trade", symbol: currentPair, side: "sell", amount, price }));
        onSystemStatus({ status: "warning", message: `SELL order submitted: ${currentPair} × ${amount} @ ${price.toFixed(decimals(currentPair))}` });
    });

    document.getElementById("send-btn").addEventListener("click", () => {
        const input   = document.getElementById("user-input");
        const content = input.value.trim();
        if (!content) return;
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: "user_insight", content }));
            addAgentCard("You", content, currentPair, null, null, null);
            input.value = "";
        } else {
            alert("Not connected. Please wait for backend connection.");
        }
    });

    // Ctrl+Enter to submit insight
    document.getElementById("user-input").addEventListener("keydown", (e) => {
        if (e.key === "Enter" && e.ctrlKey) {
            document.getElementById("send-btn").click();
        }
    });
});

// ── Keyboard Shortcuts ────────────────────────────────────────────────────────
document.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
    if (e.key === 'Escape') {
        setDrawingTool('cursor', document.getElementById('tool-cursor'));
        document.querySelectorAll('.tool-group-flyout').forEach(f => f.classList.remove('open'));
        return;
    }
    if (!e.altKey) return;
    const map = {
        't': () => selectGroupTool('trendline', 'lines', document.getElementById('flyout-trendline')),
        'h': () => selectGroupTool('hline',     'lines', document.getElementById('flyout-hline')),
        'j': () => selectGroupTool('hray',      'lines', document.getElementById('flyout-hray')),
        'v': () => selectGroupTool('vline',      'lines', document.getElementById('flyout-vline')),
        'c': () => selectGroupTool('crossline',  'lines', document.getElementById('flyout-crossline')),
    };
    if (map[e.key.toLowerCase()]) { e.preventDefault(); map[e.key.toLowerCase()](); }
});

// ── Ping to keep WS alive ─────────────────────────────────────────────────────
setInterval(() => {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "ping" }));
    }
}, 30000);

// ── Boot ──────────────────────────────────────────────────────────────────────
window.addEventListener("load", async () => {
    lucide.createIcons();
    initChart();
    connectWS();

    // Set initial BB/Vol toggle state
    const bbBtn = document.getElementById("bb-toggle");
    const volBtn = document.getElementById("vol-toggle");
    if (bbBtn) bbBtn.classList.add("active");
    if (volBtn) volBtn.classList.add("active");

    // Load initial chart data
    await loadChartData(currentPair, currentTimeframe);

    // Initial watchlist price poll
    pollWatchlistPrices();

    // Load initial news
    try {
        const res  = await fetch(`${API_URL}/api/news`);
        const json = await res.json();
        if (json.data && json.data.length > 0) onNewsUpdate({ headlines: json.data.map(n => n.headline) });
    } catch (e) {
        console.warn("[News] Load failed:", e);
    }
});
