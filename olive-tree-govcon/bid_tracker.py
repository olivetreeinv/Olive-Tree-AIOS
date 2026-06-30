import sqlite3
from datetime import datetime
from typing import Optional

TRACKER_DB = "sam_data.db"

STATUSES = [
    "researching",
    "sub_contacted",
    "quoted",
    "submitted",
    "won",
    "lost",
    "skipped",
]

_ALLOWED_UPDATE_FIELDS = frozenset({
    "status", "sub_name", "sub_contact", "sub_quote", "our_bid",
    "past_price_ceiling", "gross_profit", "notes", "proposal_text",
})


def _init():
    with sqlite3.connect(TRACKER_DB) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bids (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                notice_id          TEXT UNIQUE,
                title              TEXT,
                agency             TEXT,
                naics_code         TEXT,
                state              TEXT,
                deadline           TEXT,
                sam_link           TEXT,
                status             TEXT DEFAULT 'researching',
                sub_name           TEXT,
                sub_contact        TEXT,
                sub_quote          REAL,
                our_bid            REAL,
                past_price_ceiling REAL,
                gross_profit       REAL,
                notes              TEXT,
                proposal_text      TEXT,
                created_at         TIMESTAMP,
                updated_at         TIMESTAMP
            )
        """)


_init()


def _row_to_dict(row: tuple, description: list) -> dict:
    return dict(zip([d[0] for d in description], row))


def create_bid(
    notice_id: str,
    title: str,
    agency: str,
    naics_code: str,
    state: str,
    deadline: Optional[str],
    sam_link: Optional[str],
) -> Optional[dict]:
    now = datetime.utcnow().isoformat()
    with sqlite3.connect(TRACKER_DB) as conn:
        conn.execute(
            """INSERT OR IGNORE INTO bids
               (notice_id, title, agency, naics_code, state, deadline, sam_link,
                status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'researching', ?, ?)""",
            (notice_id, title, agency, naics_code, state, deadline, sam_link, now, now),
        )
        cur = conn.execute("SELECT * FROM bids WHERE notice_id = ?", (notice_id,))
        row = cur.fetchone()
        return _row_to_dict(row, cur.description) if row else None


def get_bid(notice_id: str) -> Optional[dict]:
    with sqlite3.connect(TRACKER_DB) as conn:
        cur = conn.execute("SELECT * FROM bids WHERE notice_id = ?", (notice_id,))
        row = cur.fetchone()
        return _row_to_dict(row, cur.description) if row else None


def list_bids(status: Optional[str] = None) -> list[dict]:
    with sqlite3.connect(TRACKER_DB) as conn:
        if status:
            cur = conn.execute(
                "SELECT * FROM bids WHERE status = ? ORDER BY updated_at DESC", (status,)
            )
        else:
            cur = conn.execute("SELECT * FROM bids ORDER BY updated_at DESC")
        desc = cur.description
        return [_row_to_dict(row, desc) for row in cur.fetchall()]


def update_bid(notice_id: str, **fields) -> Optional[dict]:
    updates = {k: v for k, v in fields.items() if k in _ALLOWED_UPDATE_FIELDS}
    if not updates:
        return get_bid(notice_id)

    # Auto-derive gross_profit in SQL — avoids a round-trip SELECT
    if "our_bid" in updates and "gross_profit" not in updates:
        if "sub_quote" in updates:
            updates["gross_profit"] = updates["our_bid"] - updates["sub_quote"]
        else:
            # Use existing sub_quote from DB via COALESCE — single query
            updates["gross_profit"] = None  # placeholder; handled below

    updates["updated_at"] = datetime.utcnow().isoformat()

    with sqlite3.connect(TRACKER_DB) as conn:
        if "our_bid" in updates and updates.get("gross_profit") is None and "sub_quote" not in updates:
            # Compute profit in SQL using stored sub_quote
            del updates["gross_profit"]
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            set_clause += ", gross_profit = ? - COALESCE(sub_quote, 0)"
            values = list(updates.values()) + [updates["our_bid"], notice_id]
            conn.execute(f"UPDATE bids SET {set_clause} WHERE notice_id = ?", values)
        else:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            conn.execute(
                f"UPDATE bids SET {set_clause} WHERE notice_id = ?",
                list(updates.values()) + [notice_id],
            )
        cur = conn.execute("SELECT * FROM bids WHERE notice_id = ?", (notice_id,))
        row = cur.fetchone()
        return _row_to_dict(row, cur.description) if row else None


def pipeline_summary() -> dict:
    with sqlite3.connect(TRACKER_DB) as conn:
        rows = conn.execute("SELECT status, COUNT(*) FROM bids GROUP BY status").fetchall()

    counts = {s: 0 for s in STATUSES}
    for status, count in rows:
        counts[status] = count

    total     = sum(counts.values())
    won       = counts["won"]
    submitted = counts["submitted"] + won + counts["lost"]
    hit_rate  = f"{won / submitted * 100:.0f}%" if submitted else "—"

    return {"counts": counts, "total": total, "hit_rate": hit_rate}
