"""
entity_db.py — SQLite schema, search helpers, and stats for SAM bulk-data tables.

Tables
------
entities   — from SAM_PUBLIC_MONTHLY_V2 extract (monthly refresh)
exclusions — from SAM_Exclusions_Public_Extract (daily refresh)
extract_log — audit trail for every import run
"""

import sqlite3
from typing import Optional

SAM_DB = "sam_data.db"

# ── Schema ─────────────────────────────────────────────────────────────────────

_SCHEMA = """
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS entities (
    uei          TEXT PRIMARY KEY,
    cage_code    TEXT,
    legal_name   TEXT,
    dba_name     TEXT,
    addr_line1   TEXT,
    city         TEXT,
    state        TEXT,
    zip          TEXT,
    country      TEXT,
    reg_status   TEXT,
    expiry_date  TEXT,
    entity_type  TEXT,
    imported_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_ent_cage   ON entities(cage_code);
CREATE INDEX IF NOT EXISTS idx_ent_name   ON entities(legal_name COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_ent_status ON entities(reg_status);

CREATE TABLE IF NOT EXISTS exclusions (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    exclusion_name    TEXT,
    uei               TEXT,
    cage_code         TEXT,
    exclusion_type    TEXT,
    exclusion_program TEXT,
    excluding_agency  TEXT,
    exclusion_date    TEXT,
    termination_date  TEXT,
    ct_code           TEXT,
    imported_at       TEXT
);
CREATE INDEX IF NOT EXISTS idx_excl_uei  ON exclusions(uei);
CREATE INDEX IF NOT EXISTS idx_excl_cage ON exclusions(cage_code);

CREATE TABLE IF NOT EXISTS extract_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    extract     TEXT NOT NULL,
    filename    TEXT NOT NULL,
    row_count   INTEGER,
    finished_at TEXT
);
"""


def init_db(db_path: str = SAM_DB) -> sqlite3.Connection:
    """Create tables + indexes; return an open connection."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


# ── Search ─────────────────────────────────────────────────────────────────────

def search_entities(db_path: str, q: str, limit: int = 25) -> list[dict]:
    """
    Search entities by UEI (exact), CAGE code (exact), or legal name (LIKE).
    Each result is annotated with any matching exclusion records.
    """
    q = q.strip()
    if not q:
        return []

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT * FROM entities
            WHERE  uei = ?1
                OR cage_code = ?1
                OR legal_name LIKE ?2
            ORDER BY
                CASE WHEN uei = ?1 OR cage_code = ?1 THEN 0 ELSE 1 END,
                legal_name COLLATE NOCASE
            LIMIT ?3
            """,
            (q.upper(), f"%{q}%", limit),
        ).fetchall()
        conn.close()
    except sqlite3.OperationalError:
        # DB not initialised yet
        return []

    results = []
    for row in rows:
        ent = dict(row)
        ent["exclusions"] = get_exclusions(db_path, ent.get("uei"), ent.get("cage_code"))
        ent["excluded"] = len(ent["exclusions"]) > 0
        results.append(ent)
    return results


def get_exclusions(
    db_path: str,
    uei: Optional[str],
    cage: Optional[str],
) -> list[dict]:
    """Return all exclusion records for a given UEI and/or CAGE code."""
    if not uei and not cage:
        return []
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT * FROM exclusions
            WHERE  (?1 IS NOT NULL AND uei       = ?1)
                OR (?2 IS NOT NULL AND cage_code = ?2)
            ORDER BY exclusion_date DESC
            """,
            (uei or None, cage or None),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []


# ── Audit log ──────────────────────────────────────────────────────────────────

def log_extract(db_path: str, extract: str, filename: str, row_count: int):
    from datetime import datetime, timezone
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO extract_log (extract, filename, row_count, finished_at) VALUES (?,?,?,?)",
        (extract, filename, row_count, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()


# ── Stats ──────────────────────────────────────────────────────────────────────

def db_stats(db_path: str = SAM_DB) -> dict:
    """Return counts and last-import metadata. Safe to call before first import."""
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        entity_count = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
        excl_count   = conn.execute("SELECT COUNT(*) FROM exclusions").fetchone()[0]

        last_ent = conn.execute(
            "SELECT filename, finished_at, row_count FROM extract_log "
            "WHERE extract='entities' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        last_exc = conn.execute(
            "SELECT filename, finished_at, row_count FROM extract_log "
            "WHERE extract='exclusions' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()

        return {
            "entity_count":           entity_count,
            "exclusion_count":        excl_count,
            "last_entity_import":     dict(last_ent) if last_ent else None,
            "last_exclusion_import":  dict(last_exc) if last_exc else None,
            "ready":                  entity_count > 0,
        }
    except sqlite3.OperationalError:
        return {
            "entity_count": 0, "exclusion_count": 0,
            "last_entity_import": None, "last_exclusion_import": None,
            "ready": False,
        }
