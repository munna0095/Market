"""
Backtesting Service
Rule-based signal simulation on 15M candles (59 days), with accuracy measurement.
Regime detection (ADX), Break-of-Structure, volume confirmation, 5-candle lookahead.
NSE session filter for NIFTY/SENSEX.
"""
import sqlite3
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf


YF_SYMBOLS = {
    "EUR/USD": "EURUSD=X",
    "USD/JPY": "JPY=X",
    "BTC/USD": "BTC-USD",
    "NIFTY":   "^NSEI",
    "SENSEX":  "^BSESN",
}

DB_PATH = "trading_signals.db"
_WARMUP = 100   # need 100 bars for vol_percentile + ADX warmup


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS backtest_results (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            pair       TEXT    NOT NULL,
            datetime   TEXT    NOT NULL,
            signal     TEXT    NOT NULL,
            correct    INTEGER,
            rsi        REAL,
            ema9       REAL,
            ema21      REAL,
            confidence INTEGER DEFAULT 50
        )
    """)
    conn.commit()


def _fetch_candles(symbol: str) -> pd.DataFrame:
    end   = datetime.utcnow()
    start = end - timedelta(days=59)   # yfinance 15m max = 60 days
    df = yf.download(
        symbol,
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        interval="15m",
        progress=False,
        auto_adjust=False,
    )
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0] for col in df.columns]
    return df.dropna(subset=["Close"])


def _add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    c = df["Close"]

    # ── RSI(14) Wilder ────────────────────────────────────────────────────────
    delta    = c.diff()
    gain     = delta.clip(lower=0)
    loss     = (-delta).clip(lower=0)
    avg_gain = gain.ewm(com=13, adjust=False).mean()
    avg_loss = loss.ewm(com=13, adjust=False).mean()
    rs       = avg_gain / avg_loss.replace(0, float("nan"))
    df["rsi"] = (100 - 100 / (1 + rs)).round(2)

    # ── EMA(9) and EMA(21) ────────────────────────────────────────────────────
    df["ema9"]  = c.ewm(span=9,  adjust=False).mean().round(6)
    df["ema21"] = c.ewm(span=21, adjust=False).mean().round(6)

    # ── MACD(12, 26, 9) ───────────────────────────────────────────────────────
    ema12           = c.ewm(span=12, adjust=False).mean()
    ema26           = c.ewm(span=26, adjust=False).mean()
    df["macd"]      = (ema12 - ema26).round(6)
    df["macd_sig"]  = df["macd"].ewm(span=9, adjust=False).mean().round(6)
    df["macd_hist"] = (df["macd"] - df["macd_sig"]).round(6)

    # ── ADX(14) — Wilder smoothing ────────────────────────────────────────────
    high  = df["High"]
    low   = df["Low"]
    prev_close = c.shift(1)
    prev_high  = high.shift(1)
    prev_low   = low.shift(1)

    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)

    plus_dm  = (high - prev_high).clip(lower=0)
    minus_dm = (prev_low - low).clip(lower=0)
    # Zero out whichever DM is smaller
    mask_plus  = plus_dm >= minus_dm
    mask_minus = minus_dm > plus_dm
    plus_dm  = plus_dm.where(mask_plus,  0.0)
    minus_dm = minus_dm.where(mask_minus, 0.0)

    period = 14
    atr14   = tr.ewm(com=period - 1, adjust=False).mean()
    pdm14   = plus_dm.ewm(com=period - 1, adjust=False).mean()
    mdm14   = minus_dm.ewm(com=period - 1, adjust=False).mean()

    di_plus  = 100 * pdm14 / atr14.replace(0, float("nan"))
    di_minus = 100 * mdm14 / atr14.replace(0, float("nan"))
    dx       = 100 * (di_plus - di_minus).abs() / (di_plus + di_minus).replace(0, float("nan"))
    df["adx"] = dx.ewm(com=period - 1, adjust=False).mean().round(2)

    # ── Break-of-Structure (8-bar swing = 2hr structure on 15M) ─────────────────
    df["swing_high"] = high.rolling(8).max().shift(1)
    df["swing_low"]  = low.rolling(8).min().shift(1)
    df["bos_bull"]   = c > df["swing_high"]
    df["bos_bear"]   = c < df["swing_low"]

    # ── Volume percentile (rolling rank over 100 bars) ────────────────────────
    vol = df["Volume"].astype(float).fillna(0)
    if vol.sum() == 0:
        df["vol_pct"] = 1.0   # forex/index — no real volume, treat as always valid
    else:
        df["vol_pct"] = vol.rolling(100).rank(pct=True).round(4)

    return df


def _signal(rsi: float, macd: float, macd_sig: float,
            bos_bull: bool, bos_bear: bool,
            volume_ok: bool, vol_percentile: float, adx: float) -> tuple[str, int]:
    """Returns (signal, confidence) using regime-aware rules."""
    if pd.isna(rsi) or pd.isna(adx) or pd.isna(macd):
        return "HOLD", 0

    regime = "TRENDING" if adx > 20 else "RANGING"

    if regime == "TRENDING":
        if bos_bull and volume_ok and macd > macd_sig and rsi < 60:
            confidence = 55
            if vol_percentile > 0.80: confidence += 10
            if rsi < 50:              confidence += 5
            return "BUY", confidence

        if bos_bear and volume_ok and macd < macd_sig and rsi > 40:
            confidence = 55
            if vol_percentile > 0.80: confidence += 10
            if rsi > 50:              confidence += 5
            return "SELL", confidence

    else:  # RANGING
        if rsi < 30 and volume_ok:
            return "BUY", 60
        if rsi > 70 and volume_ok:
            return "SELL", 60

    return "HOLD", 0


def _is_correct(signal: str, cur_idx: int, df: pd.DataFrame,
                threshold: float = 0.002) -> bool | None:
    """5-candle lookahead: correct if price moves `threshold` in signal direction."""
    if signal == "HOLD":
        return None
    cur       = float(df.iloc[cur_idx]["Close"])
    lookahead = min(5, len(df) - cur_idx - 1)
    if lookahead == 0:
        return None
    for j in range(1, lookahead + 1):
        nxt = float(df.iloc[cur_idx + j]["Close"])
        pct = (nxt - cur) / cur
        if signal == "BUY"  and pct >  threshold: return True
        if signal == "SELL" and pct < -threshold: return True
    return False


_NSE_PAIRS = {"NIFTY", "SENSEX"}


def _is_nse_valid_session(dt) -> bool:
    """Only 9:30-11:30 and 13:30-15:00 IST are high-quality 15M sessions."""
    try:
        # If timestamp is tz-aware, convert to IST first
        if getattr(dt, "tzinfo", None) is not None:
            import pytz
            dt = dt.astimezone(pytz.timezone("Asia/Kolkata"))
            ist_min = dt.hour * 60 + dt.minute
        else:
            # Assume UTC, add 330 min offset
            ist_min = (dt.hour * 60 + dt.minute + 330) % 1440
        return (570 <= ist_min <= 690) or (810 <= ist_min <= 900)
    except Exception:
        return True


_THRESHOLDS = {
    "EUR/USD": 0.0008,
    "USD/JPY": 0.0008,
    "BTC/USD": 0.002,
    "NIFTY":   0.0015,
    "SENSEX":  0.0015,
}


def run_backtest(pair: str) -> dict:
    symbol = YF_SYMBOLS.get(pair)
    if not symbol:
        raise ValueError(f"Unsupported pair '{pair}'. Valid: {list(YF_SYMBOLS)}")

    threshold = _THRESHOLDS.get(pair, 0.002)

    df = _fetch_candles(symbol)
    if len(df) < _WARMUP + 10:
        raise ValueError(f"Too few candles for {pair} ({len(df)} rows)")

    df = _add_indicators(df)
    df = df.reset_index(drop=False)   # keep datetime as a regular column

    # ── NSE session filter ────────────────────────────────────────────────────
    dt_col = df.columns[0]   # first col after reset_index is the datetime index
    if pair in _NSE_PAIRS:
        df["session_ok"] = df[dt_col].apply(
            lambda x: _is_nse_valid_session(x) if hasattr(x, "hour") else True
        )
    else:
        df["session_ok"] = True

    buy_n = sell_n = hold_n = correct_n = tradeable_n = 0
    results_by_day: list[dict] = []
    db_rows: list[tuple] = []

    end_idx = len(df) - 5   # reserve 5 candles for lookahead

    for i in range(_WARMUP, end_idx):
        row = df.iloc[i]

        if not row["session_ok"]:
            hold_n += 1
            continue

        rsi          = float(row["rsi"])
        macd         = float(row["macd"])
        macd_sig_val = float(row["macd_sig"])
        adx          = float(row["adx"])
        vol_pct      = float(row["vol_pct"]) if not pd.isna(row["vol_pct"]) else 0.0
        bos_bull     = bool(row["bos_bull"])
        bos_bear     = bool(row["bos_bear"])
        volume_ok    = vol_pct > 0.60
        ema9         = float(row["ema9"])
        ema21        = float(row["ema21"])

        sig, confidence = _signal(
            rsi, macd, macd_sig_val,
            bos_bull, bos_bear, volume_ok, vol_pct, adx,
        )
        correct = _is_correct(sig, i, df, threshold)

        if   sig == "BUY":  buy_n  += 1
        elif sig == "SELL": sell_n += 1
        else:               hold_n += 1

        if correct is not None:
            tradeable_n += 1
            if correct:
                correct_n += 1

        idx_val = row.get("index", row.get("Datetime", row.get("Date", "")))
        dt_str  = idx_val.strftime("%Y-%m-%d %H:%M") if hasattr(idx_val, "strftime") else str(idx_val)

        results_by_day.append({
            "datetime":   dt_str,
            "signal":     sig,
            "correct":    correct,
            "confidence": confidence,
            "rsi":        round(rsi,  2),
            "ema9":       round(ema9, 4),
            "ema21":      round(ema21, 4),
        })
        db_rows.append((
            pair, dt_str, sig,
            (1 if correct else 0) if correct is not None else None,
            round(rsi, 2), round(ema9, 4), round(ema21, 4), confidence,
        ))

    win_rate = round(correct_n / tradeable_n, 4) if tradeable_n else 0.0

    try:
        with sqlite3.connect(DB_PATH) as conn:
            _ensure_table(conn)
            conn.executemany(
                "INSERT INTO backtest_results "
                "(pair, datetime, signal, correct, rsi, ema9, ema21, confidence) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                db_rows,
            )
    except Exception as e:
        print(f"[Backtest] DB write error: {e}")

    return {
        "pair":            pair,
        "total_signals":   buy_n + sell_n + hold_n,
        "buy_signals":     buy_n,
        "sell_signals":    sell_n,
        "hold_signals":    hold_n,
        "correct_signals": correct_n,
        "win_rate":        win_rate,
        "results_by_day":  results_by_day,
    }
