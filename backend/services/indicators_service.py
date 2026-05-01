"""
Advanced Technical Indicators — pure Python, zero external TA libraries.

Provides:
  - Supertrend          (period=10, multiplier=3)
  - ADX + DI+ / DI-     (period=14)
  - EMA 200
  - Stochastic RSI      (rsi=14, k=3, d=3)
  - OBV (On-Balance Volume)
  - VWAP
  - Volume Analysis     (vs 20-bar average)
"""


# ── Shared maths ─────────────────────────────────────────────────────────────

def _ema(data: list, period: int) -> float:
    if len(data) < period:
        return data[-1] if data else 0.0
    k = 2 / (period + 1)
    val = sum(data[:period]) / period
    for p in data[period:]:
        val = p * k + val * (1 - k)
    return round(val, 6)


def _sma(data: list, period: int) -> list:
    return [sum(data[i:i + period]) / period for i in range(len(data) - period + 1)]


def _wilder(data: list, period: int) -> list:
    """Wilder's smoothing (used in ATR, ADX)."""
    if len(data) < period:
        return []
    result = [sum(data[:period]) / period]
    for v in data[period:]:
        result.append((result[-1] * (period - 1) + v) / period)
    return result


def _rsi_series(closes: list, period: int = 14) -> list:
    """Returns a list of RSI values aligned with closes[period:]."""
    vals = []
    for i in range(period, len(closes)):
        window = closes[i - period: i + 1]
        gains  = [max(window[j] - window[j - 1], 0) for j in range(1, len(window))]
        losses = [max(window[j - 1] - window[j], 0) for j in range(1, len(window))]
        ag = sum(gains)  / period
        al = sum(losses) / period
        vals.append(100.0 if al == 0 else round(100 - 100 / (1 + ag / al), 2))
    return vals


# ── Indicator functions ───────────────────────────────────────────────────────

def compute_supertrend(candles: list, period: int = 10, multiplier: float = 3.0) -> dict:
    """ATR-based Supertrend. Returns direction (UP/DOWN), level, signal."""
    if len(candles) < period + 2:
        return {"direction": "UNKNOWN", "value": None, "signal": "UNKNOWN", "above": False}

    # True Range
    trs = [candles[0]["high"] - candles[0]["low"]]
    for i in range(1, len(candles)):
        h, l, pc = candles[i]["high"], candles[i]["low"], candles[i - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))

    atr_vals = _wilder(trs, period)   # length = len(candles) - period + 1
    offset   = period - 1             # candle index of first valid ATR

    fu = [0.0] * len(atr_vals)        # final upper bands
    fl = [0.0] * len(atr_vals)        # final lower bands
    st = [0.0] * len(atr_vals)        # supertrend values
    dr = [0]   * len(atr_vals)        # direction: +1 UP, -1 DOWN

    for i, atr in enumerate(atr_vals):
        ci  = offset + i
        hl2 = (candles[ci]["high"] + candles[ci]["low"]) / 2
        bu  = hl2 + multiplier * atr
        bl  = hl2 - multiplier * atr

        if i == 0:
            fu[i], fl[i], st[i], dr[i] = bu, bl, bu, -1
            continue

        pc = candles[ci - 1]["close"]
        fu[i] = bu if bu < fu[i - 1] or pc > fu[i - 1] else fu[i - 1]
        fl[i] = bl if bl > fl[i - 1] or pc < fl[i - 1] else fl[i - 1]

        close = candles[ci]["close"]
        if st[i - 1] == fu[i - 1]:          # was bearish
            st[i], dr[i] = (fl[i], 1) if close > fu[i] else (fu[i], -1)
        else:                                # was bullish
            st[i], dr[i] = (fu[i], -1) if close < fl[i] else (fl[i], 1)

    up = dr[-1] == 1
    return {
        "direction": "UP" if up else "DOWN",
        "value":     round(st[-1], 6),
        "signal":    "BULLISH" if up else "BEARISH",
        "above":     candles[-1]["close"] > st[-1],
    }


def compute_adx(candles: list, period: int = 14) -> dict:
    """ADX with DI+ and DI-. Returns adx, di_plus, di_minus, strength."""
    if len(candles) < period * 2 + 2:
        return {"adx": None, "di_plus": None, "di_minus": None,
                "strength": "UNKNOWN", "trending": False, "bullish": False}

    tr_l, dp_l, dm_l = [], [], []
    for i in range(1, len(candles)):
        h, l  = candles[i]["high"], candles[i]["low"]
        ph, pl, pc = candles[i-1]["high"], candles[i-1]["low"], candles[i-1]["close"]
        tr = max(h - l, abs(h - pc), abs(l - pc))
        dp = max(h - ph, 0)
        dm = max(pl - l, 0)
        if dp > dm:   dm = 0
        elif dm > dp: dp = 0
        else:         dp = dm = 0
        tr_l.append(tr); dp_l.append(dp); dm_l.append(dm)

    str_ = _wilder(tr_l, period)
    sdp  = _wilder(dp_l, period)
    sdm  = _wilder(dm_l, period)

    di_p, di_m, dx_l = [], [], []
    for s, p, m in zip(str_, sdp, sdm):
        dip = 100 * p / s if s else 0.0
        dim = 100 * m / s if s else 0.0
        di_p.append(dip); di_m.append(dim)
        tot = dip + dim
        dx_l.append(100 * abs(dip - dim) / tot if tot else 0.0)

    adx_l = _wilder(dx_l, period)
    if not adx_l:
        return {"adx": None, "di_plus": None, "di_minus": None,
                "strength": "UNKNOWN", "trending": False, "bullish": False}

    adx = round(adx_l[-1], 2)
    dip = round(di_p[-1], 2)
    dim = round(di_m[-1], 2)
    return {
        "adx":      adx,
        "di_plus":  dip,
        "di_minus": dim,
        "strength": "STRONG" if adx > 25 else "WEAK" if adx < 20 else "MODERATE",
        "trending": adx > 25,
        "bullish":  dip > dim,
    }


def compute_ema200(candles: list) -> dict:
    """EMA-200. Requires ~200+ candles for accuracy."""
    if not candles:
        return {"value": None, "price_above": False, "signal": "UNKNOWN"}
    closes = [c["close"] for c in candles]
    val    = _ema(closes, 200)
    above  = closes[-1] > val
    return {
        "value":       round(val, 6),
        "price_above": above,
        "signal":      "BULLISH" if above else "BEARISH",
    }


def compute_stoch_rsi(candles: list, rsi_period: int = 14,
                       k_period: int = 3, d_period: int = 3) -> dict:
    """Stochastic RSI. Returns k, d, signal (OVERBOUGHT/OVERSOLD/NEUTRAL)."""
    closes = [c["close"] for c in candles]
    rsi_v  = _rsi_series(closes, rsi_period)

    if len(rsi_v) < k_period + d_period:
        return {"k": None, "d": None, "signal": "UNKNOWN", "bullish": False}

    # Raw stochastic on RSI values
    raw_k = []
    for i in range(k_period - 1, len(rsi_v)):
        w  = rsi_v[i - k_period + 1: i + 1]
        lo, hi = min(w), max(w)
        raw_k.append(50.0 if hi == lo else (rsi_v[i] - lo) / (hi - lo) * 100)

    k_sm = _sma(raw_k, k_period) if len(raw_k) >= k_period else raw_k
    d_sm = _sma(k_sm,  d_period) if len(k_sm)  >= d_period else k_sm

    if not k_sm or not d_sm:
        return {"k": None, "d": None, "signal": "UNKNOWN", "bullish": False}

    k = round(k_sm[-1], 2)
    d = round(d_sm[-1], 2)
    sig = "OVERBOUGHT" if k > 80 else "OVERSOLD" if k < 20 else "NEUTRAL"
    return {
        "k":       k,
        "d":       d,
        "signal":  sig,
        "bullish": k > 50 and k > d,
        "bearish": k < 50 and k < d,
    }


def compute_obv(candles: list) -> dict:
    """On-Balance Volume. Returns value, direction (UP/DOWN), rising."""
    if len(candles) < 2:
        return {"value": 0, "direction": "FLAT", "rising": False}
    obv = [0]
    for i in range(1, len(candles)):
        vol = candles[i].get("volume", 0) or 0
        c, pc = candles[i]["close"], candles[i - 1]["close"]
        obv.append(obv[-1] + vol if c > pc else obv[-1] - vol if c < pc else obv[-1])

    window = min(10, len(obv) // 2)
    if window >= 2:
        rising = sum(obv[-window:]) / window > sum(obv[-window * 2:-window]) / window
    else:
        rising = obv[-1] > obv[0]

    return {
        "value":     obv[-1],
        "direction": "UP" if rising else "DOWN",
        "rising":    rising,
    }


def compute_vwap(candles: list) -> dict:
    """VWAP over all available candles. Returns value, price_above, signal."""
    if not candles:
        return {"value": None, "price_above": False, "signal": "UNKNOWN"}
    total_tp_v = total_v = 0.0
    for c in candles:
        tp  = (c["high"] + c["low"] + c["close"]) / 3
        vol = c.get("volume", 1) or 1
        total_tp_v += tp * vol
        total_v    += vol
    if total_v == 0:
        return {"value": None, "price_above": False, "signal": "UNKNOWN"}
    val   = round(total_tp_v / total_v, 6)
    above = candles[-1]["close"] > val
    return {
        "value":       val,
        "price_above": above,
        "signal":      "BULLISH" if above else "BEARISH",
    }


def compute_volume_analysis(candles: list, avg_period: int = 20) -> dict:
    """Compare current bar volume vs 20-bar average. Flags spikes and confirmation."""
    if len(candles) < avg_period + 1:
        return {"ratio": 1.0, "confirmed": False, "spike": False,
                "signal": "NORMAL", "current": 0, "average": 0}
    vols    = [c.get("volume", 0) or 0 for c in candles]
    current = vols[-1]
    avg     = sum(vols[-avg_period - 1:-1]) / avg_period
    ratio   = round(current / avg, 2) if avg else 1.0
    sig     = ("SPIKE" if ratio >= 2.0 else
               "CONFIRMED" if ratio >= 1.5 else
               "BELOW_AVG" if ratio < 0.8 else "NORMAL")
    return {
        "current":   current,
        "average":   round(avg, 0),
        "ratio":     ratio,
        "confirmed": ratio >= 1.5,
        "spike":     ratio >= 2.0,
        "signal":    sig,
    }


# ── Divergence & chart patterns (used by academic agent) ─────────────────────

def detect_rsi_divergence(candles: list, lookback: int = 10) -> str | None:
    """
    Bullish: price makes lower low but RSI makes higher low  → potential reversal up.
    Bearish: price makes higher high but RSI makes lower high → potential reversal down.
    Returns 'BULLISH_DIVERGENCE', 'BEARISH_DIVERGENCE', or None.
    """
    if len(candles) < lookback + 14:
        return None
    closes = [c["close"] for c in candles]
    rsi_v  = _rsi_series(closes, 14)

    # Align: rsi_v[i] corresponds to closes[i + 14]
    rsi_offset = 14
    n = min(lookback, len(rsi_v))
    rc = closes[-(n + rsi_offset):-rsi_offset] if rsi_offset else closes[-n:]
    rv = rsi_v[-n:]

    # Find local lows and highs in price
    p_lows, p_highs = [], []
    for i in range(1, len(rc) - 1):
        if rc[i] < rc[i - 1] and rc[i] < rc[i + 1]:
            p_lows.append((i, rc[i], rv[i]))
        if rc[i] > rc[i - 1] and rc[i] > rc[i + 1]:
            p_highs.append((i, rc[i], rv[i]))

    if len(p_lows) >= 2:
        a, b = p_lows[-2], p_lows[-1]
        if b[1] < a[1] and b[2] > a[2]:        # lower price low + higher RSI low
            return "BULLISH_DIVERGENCE"

    if len(p_highs) >= 2:
        a, b = p_highs[-2], p_highs[-1]
        if b[1] > a[1] and b[2] < a[2]:        # higher price high + lower RSI high
            return "BEARISH_DIVERGENCE"

    return None


def detect_chart_patterns(candles: list, lookback: int = 50) -> list:
    """
    Detect chart patterns from the last `lookback` candles.
    Returns a list of pattern description strings.
    """
    recent = candles[-lookback:] if len(candles) >= lookback else candles
    if len(recent) < 20:
        return []

    highs = [c["high"]  for c in recent]
    lows  = [c["low"]   for c in recent]
    n     = len(recent)
    patterns = []

    # Swing pivots (2-bar rule)
    sh = [(i, highs[i]) for i in range(1, n - 1)
          if highs[i] > highs[i - 1] and highs[i] > highs[i + 1]]
    sl = [(i, lows[i])  for i in range(1, n - 1)
          if lows[i]  < lows[i - 1]  and lows[i]  < lows[i + 1]]

    # Double Top
    if len(sh) >= 2:
        h1, h2 = sh[-2][1], sh[-1][1]
        if abs(h1 - h2) / max(h1, h2) < 0.005:
            patterns.append("DOUBLE TOP — Bearish reversal at resistance")

    # Double Bottom
    if len(sl) >= 2:
        l1, l2 = sl[-2][1], sl[-1][1]
        if abs(l1 - l2) / max(l1, l2) < 0.005:
            patterns.append("DOUBLE BOTTOM — Bullish reversal at support")

    if len(sh) >= 3 and len(sl) >= 3:
        t_h = [x[1] for x in sh[-3:]]
        t_l = [x[1] for x in sl[-3:]]
        lh  = t_h[0] > t_h[1] > t_h[2]
        hl  = t_l[0] < t_l[1] < t_l[2]
        ll  = t_l[0] > t_l[1] > t_l[2]
        flat_top = (max(t_h) - min(t_h)) / max(t_h) < 0.003

        # Ascending Triangle
        if flat_top and hl:
            patterns.append("ASCENDING TRIANGLE — Bullish breakout pattern forming")
        # Symmetrical Triangle
        elif lh and hl:
            patterns.append("SYMMETRICAL TRIANGLE — Breakout imminent, direction unclear")
        # Descending Channel
        elif lh and ll:
            patterns.append("DESCENDING CHANNEL — Bearish (lower highs + lower lows)")

    # Flag & Pole: one large candle (pole) followed by tight consolidation (flag)
    if n >= 10:
        avg_range = sum(c["high"] - c["low"] for c in recent[-20:]) / min(20, n)
        pole_size = recent[-10]["high"] - recent[-10]["low"]
        flag_tight = all((c["high"] - c["low"]) < 0.6 * avg_range
                         for c in recent[-9:-4])
        if pole_size > 2 * avg_range and flag_tight:
            bias = "BULLISH" if recent[-10]["close"] > recent[-10]["open"] else "BEARISH"
            patterns.append(f"FLAG AND POLE — {bias} continuation setup")

    return patterns


# ── Convenience aggregator ────────────────────────────────────────────────────

def compute_all(candles: list) -> dict:
    """
    Compute all advanced indicators from a candle list.
    Returns a dict ready to merge into the main indicators response.
    """
    return {
        "supertrend":      compute_supertrend(candles),
        "adx":             compute_adx(candles),
        "ema_200":         compute_ema200(candles),
        "stoch_rsi":       compute_stoch_rsi(candles),
        "obv":             compute_obv(candles),
        "vwap":            compute_vwap(candles),
        "volume_analysis": compute_volume_analysis(candles),
    }
