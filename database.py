"""
database.py – SQLite persistence layer.

Tables
------
tickets
    Stores every generated accumulator ticket.
legs
    Stores each individual leg belonging to a ticket.
results
    Stores the win/loss result manually supplied via /track.
"""

import sqlite3
import logging
from datetime import date
from typing import Optional

import config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

def init_db() -> None:
    """Create tables if they do not yet exist."""
    with _connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS tickets (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                date          TEXT    NOT NULL UNIQUE,
                total_odds    REAL    NOT NULL,
                bookmaker     TEXT,
                created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS legs (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id     INTEGER NOT NULL REFERENCES tickets(id),
                leg_type      TEXT    NOT NULL,  -- 'foundation' | 'booster'
                match_name    TEXT    NOT NULL,
                market        TEXT    NOT NULL,
                odds          REAL    NOT NULL,
                league        TEXT
            );

            CREATE TABLE IF NOT EXISTS results (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id     INTEGER NOT NULL UNIQUE REFERENCES tickets(id),
                outcome       TEXT    NOT NULL,  -- 'win' | 'loss'
                stake_usd     REAL    NOT NULL,
                pnl_usd       REAL    NOT NULL,
                recorded_at   TEXT    NOT NULL DEFAULT (datetime('now'))
            );
        """)
    logger.info("Database initialised at %s", config.DATABASE_PATH)


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Ticket persistence
# ---------------------------------------------------------------------------

def save_ticket(
    ticket_date: date,
    total_odds: float,
    bookmaker: str,
    legs: list[dict],
) -> int:
    """
    Persist a ticket and its legs.  Returns the new ticket id.

    ``legs`` is a list of dicts with keys:
        leg_type, match_name, market, odds, league
    """
    with _connect() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO tickets (date, total_odds, bookmaker) VALUES (?, ?, ?)",
                (ticket_date.isoformat(), round(total_odds, 4), bookmaker),
            )
            ticket_id = cur.lastrowid
        except sqlite3.IntegrityError:
            # A ticket already exists for today – fetch its id
            row = conn.execute(
                "SELECT id FROM tickets WHERE date = ?",
                (ticket_date.isoformat(),),
            ).fetchone()
            ticket_id = row["id"]
            # Delete old legs so we can replace them
            conn.execute("DELETE FROM legs WHERE ticket_id = ?", (ticket_id,))
            conn.execute(
                "UPDATE tickets SET total_odds=?, bookmaker=? WHERE id=?",
                (round(total_odds, 4), bookmaker, ticket_id),
            )

        conn.executemany(
            """INSERT INTO legs (ticket_id, leg_type, match_name, market, odds, league)
               VALUES (:ticket_id, :leg_type, :match_name, :market, :odds, :league)""",
            [
                {
                    "ticket_id": ticket_id,
                    "leg_type": leg["leg_type"],
                    "match_name": leg["match_name"],
                    "market": leg["market"],
                    "odds": round(leg["odds"], 4),
                    "league": leg.get("league", ""),
                }
                for leg in legs
            ],
        )

    logger.info("Saved ticket id=%s date=%s odds=%.2f", ticket_id, ticket_date, total_odds)
    return ticket_id


def get_ticket_by_date(ticket_date: date) -> Optional[dict]:
    """Return ticket + legs for a given date, or None."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM tickets WHERE date = ?",
            (ticket_date.isoformat(),),
        ).fetchone()
        if row is None:
            return None
        ticket = dict(row)
        legs = conn.execute(
            "SELECT * FROM legs WHERE ticket_id = ? ORDER BY id",
            (ticket["id"],),
        ).fetchall()
        ticket["legs"] = [dict(leg) for leg in legs]
    return ticket


def get_latest_ticket() -> Optional[dict]:
    """Return the most-recently created ticket + legs."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM tickets ORDER BY date DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        ticket = dict(row)
        legs = conn.execute(
            "SELECT * FROM legs WHERE ticket_id = ? ORDER BY id",
            (ticket["id"],),
        ).fetchall()
        ticket["legs"] = [dict(leg) for leg in legs]
    return ticket


# ---------------------------------------------------------------------------
# Result tracking
# ---------------------------------------------------------------------------

def record_result(outcome: str) -> Optional[dict]:
    """
    Mark the *latest* ticket as 'win' or 'loss'.
    Returns a summary dict or None if no ticket exists.
    """
    outcome = outcome.lower()
    if outcome not in ("win", "loss"):
        raise ValueError("outcome must be 'win' or 'loss'")

    ticket = get_latest_ticket()
    if ticket is None:
        return None

    stake = config.DAILY_STAKE_USD
    if outcome == "win":
        pnl = round(stake * ticket["total_odds"] - stake, 2)
    else:
        pnl = -stake

    with _connect() as conn:
        try:
            conn.execute(
                """INSERT INTO results (ticket_id, outcome, stake_usd, pnl_usd)
                   VALUES (?, ?, ?, ?)""",
                (ticket["id"], outcome, stake, pnl),
            )
        except sqlite3.IntegrityError:
            # Already recorded – overwrite
            conn.execute(
                """UPDATE results SET outcome=?, pnl_usd=?, recorded_at=datetime('now')
                   WHERE ticket_id=?""",
                (outcome, pnl, ticket["id"]),
            )

    logger.info("Recorded result ticket_id=%s outcome=%s pnl=%.2f", ticket["id"], outcome, pnl)
    return {"ticket_id": ticket["id"], "outcome": outcome, "pnl_usd": pnl}


def get_stats() -> dict:
    """Return aggregated all-time stats."""
    with _connect() as conn:
        totals = conn.execute(
            """SELECT
                COUNT(*)                        AS total_tickets,
                SUM(CASE WHEN outcome='win'  THEN 1 ELSE 0 END) AS wins,
                SUM(CASE WHEN outcome='loss' THEN 1 ELSE 0 END) AS losses,
                SUM(pnl_usd)                    AS net_pnl,
                SUM(stake_usd)                  AS total_staked
               FROM results"""
        ).fetchone()

    total = totals["total_tickets"] or 0
    wins = totals["wins"] or 0
    losses = totals["losses"] or 0
    net_pnl = totals["net_pnl"] or 0.0
    total_staked = totals["total_staked"] or 0.0
    hit_rate = (wins / total * 100) if total > 0 else 0.0
    roi = (net_pnl / total_staked * 100) if total_staked > 0 else 0.0

    return {
        "total_tickets": total,
        "wins": wins,
        "losses": losses,
        "hit_rate": round(hit_rate, 1),
        "net_pnl": round(net_pnl, 2),
        "roi": round(roi, 1),
        "total_staked": round(total_staked, 2),
    }
