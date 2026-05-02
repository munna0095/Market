"""
Database Service — central SQLite manager for the trading system.
All tables: signals_history, agent_performance, market_patterns.
Also owns: backtest_results, token_usage (created elsewhere, accessed here).
"""
import os
import sqlite3
from datetime import datetime, timedelta
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "trading_signals.db")


@contextmanager
def _conn():
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        yield conn


# ── Schema ────────────────────────────────────────────────────────────────────

def init_db() -> None:
    """Create all tables if not exists. Safe to call on every startup."""
    with _conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS signals_history (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                pair             TEXT    NOT NULL,
                datetime         TEXT    NOT NULL,
                decision         TEXT    NOT NULL,
                confidence       INTEGER,
                price_at_signal  REAL,
                rsi              REAL,
                macd             REAL,
                adx              REAL,
                regime           TEXT,
                provider         TEXT,
                source           TEXT,
                outcome          TEXT    DEFAULT 'PENDING',
                price_after_1h   REAL    DEFAULT NULL,
                price_after_4h   REAL    DEFAULT NULL,
                price_after_1d   REAL    DEFAULT NULL,
                outcome_checked  INTEGER DEFAULT 0,
                stop_loss        REAL    DEFAULT NULL,
                target           REAL    DEFAULT NULL
            );

            CREATE TABLE IF NOT EXISTS agent_performance (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_name      TEXT    NOT NULL,
                pair            TEXT    NOT NULL,
                date            TEXT    NOT NULL,
                total_signals   INTEGER DEFAULT 0,
                correct_signals INTEGER DEFAULT 0,
                win_rate        REAL    DEFAULT 0.0,
                provider_used   TEXT
            );

            CREATE TABLE IF NOT EXISTS market_patterns (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern_name    TEXT    NOT NULL,
                pair            TEXT    NOT NULL,
                first_seen      TEXT,
                last_seen       TEXT,
                occurrences     INTEGER DEFAULT 0,
                wins            INTEGER DEFAULT 0,
                win_rate        REAL    DEFAULT 0.0,
                avg_confidence  REAL    DEFAULT 0.0,
                description     TEXT
            );
        """)
    # Migrate existing DB — ignore if columns already exist
    with _conn() as conn:
        for col_sql in [
            "ALTER TABLE signals_history ADD COLUMN stop_loss REAL DEFAULT NULL",
            "ALTER TABLE signals_history ADD COLUMN target    REAL DEFAULT NULL",
        ]:
            try:
                conn.execute(col_sql)
            except Exception:
                pass
    print("[DB] Tables initialised.")


# ── Write operations ──────────────────────────────────────────────────────────

def save_signal(
    pair: str,
    decision: str,
    confidence: int,
    price: float,
    rsi: float | None,
    macd: float | None,
    adx: float | None,
    regime: str | None,
    provider: str | None,
    source: str,
    stop_loss: float | None = None,
    target: float | None = None,
) -> int:
    """Insert a new signal into signals_history. Returns the new row id."""
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    with _conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO signals_history
                (pair, datetime, decision, confidence, price_at_signal,
                 rsi, macd, adx, regime, provider, source, stop_loss, target)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (pair, now, decision, confidence, price,
             rsi, macd, adx, regime, provider, source, stop_loss, target),
        )
        return cur.lastrowid


def update_outcome(
    signal_id: int,
    outcome: str,
    price_1h:  float | None = None,
    price_4h:  float | None = None,
    price_1d:  float | None = None,
) -> None:
    """Set WIN/LOSS/NEUTRAL outcome and future prices on a signal row."""
    with _conn() as conn:
        conn.execute(
            """
            UPDATE signals_history
               SET outcome         = ?,
                   price_after_1h  = COALESCE(?, price_after_1h),
                   price_after_4h  = COALESCE(?, price_after_4h),
                   price_after_1d  = COALESCE(?, price_after_1d),
                   outcome_checked = 1
             WHERE id = ?
            """,
            (outcome, price_1h, price_4h, price_1d, signal_id),
        )


# ── Read operations ───────────────────────────────────────────────────────────

def get_pending_outcomes() -> list[dict]:
    """
    Return signals that are still PENDING, not yet checked, and fired
    at least 1 hour ago — ready for outcome resolution.
    """
    cutoff = (datetime.utcnow() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT * FROM signals_history
             WHERE outcome         = 'PENDING'
               AND outcome_checked = 0
               AND decision        != 'HOLD'
               AND datetime        <= ?
             ORDER BY datetime ASC
            """,
            (cutoff,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_signal_history(pair: str | None = None, limit: int = 50) -> list[dict]:
    """Return recent signals, newest first, optionally filtered by pair."""
    with _conn() as conn:
        if pair:
            rows = conn.execute(
                """
                SELECT * FROM signals_history
                 WHERE pair = ?
                 ORDER BY datetime DESC
                 LIMIT ?
                """,
                (pair, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM signals_history
                 ORDER BY datetime DESC
                 LIMIT ?
                """,
                (limit,),
            ).fetchall()
    return [dict(r) for r in rows]


def get_agent_performance(pair: str | None = None) -> list[dict]:
    """Return agent win-rate rows, optionally filtered by pair."""
    with _conn() as conn:
        if pair:
            rows = conn.execute(
                """
                SELECT * FROM agent_performance
                 WHERE pair = ?
                 ORDER BY date DESC
                """,
                (pair,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM agent_performance ORDER BY date DESC"
            ).fetchall()
    return [dict(r) for r in rows]


def get_win_rate_by_pair() -> dict:
    """
    Aggregate win/total from signals_history for every pair.
    Returns: { "NIFTY": {"win_rate": 0.62, "total": 48, "wins": 30}, ... }
    """
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT pair,
                   COUNT(*)                                        AS total,
                   SUM(CASE WHEN outcome = 'WIN'  THEN 1 ELSE 0 END) AS wins,
                   SUM(CASE WHEN outcome = 'LOSS' THEN 1 ELSE 0 END) AS losses
              FROM signals_history
             WHERE outcome_checked = 1
               AND decision       != 'HOLD'
             GROUP BY pair
            """
        ).fetchall()

    result = {}
    for r in rows:
        total = r["total"] or 0
        wins  = r["wins"]  or 0
        result[r["pair"]] = {
            "win_rate": round(wins / total, 4) if total else 0.0,
            "total":    total,
            "wins":     wins,
            "losses":   r["losses"] or 0,
        }
    return result
