#!/usr/bin/env python3
"""
db_migrate_initial.py — One-time backfill to populate olive.db from existing sources.

Steps
-----
1. Create tables (idempotent via CREATE TABLE IF NOT EXISTS).
2. Seed markets from references/buy-box.md (13 markets).
3. Load decisions from decisions/log.md (append-only mirror).
4. Index wiki/ markdown files into documents table (path + frontmatter).
5. Sync brokers / deals / meetings from Google Sheets (calls db_sync).

Safe to re-run — all upserts are keyed on UNIQUE columns; existing rows are updated,
not duplicated.

Usage
-----
    python3 scripts/db_migrate_initial.py [--skip-sheets]

Options
-------
    --skip-sheets   Skip Google Sheets sync (useful offline / for testing steps 1-4)
"""

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.connection import init_db, get_session
from db.schema import Decision, Document, Market

REPO = Path(__file__).parent.parent
BUY_BOX = REPO / "references" / "buy-box.md"
DECISIONS_LOG = REPO / "decisions" / "log.md"
WIKI_ROOT = REPO / "wiki"

WIKI_CATEGORIES = [
    "deals", "brokers", "markets", "mfs-docs", "mfs-videos",
    "govcon-bids", "govcon-subs", "govcon-agencies", "govcon-docs",
    "skills", "meetings",
]

# ── Buy-box parser ────────────────────────────────────────────────────────────

def _parse_price(cell: str) -> tuple[int | None, int | None]:
    """Parse '$90K–$140K' or 'open' into (low, high) integer tuples."""
    cell = cell.strip()
    if not cell or cell.lower() == "open":
        return None, None
    nums = re.findall(r"\$?(\d+(?:\.\d+)?)[Kk]?\+?", cell)
    if not nums:
        return None, None
    vals = []
    for n in nums:
        v = float(n)
        if "K" in cell.upper() or v < 1000:
            v *= 1000
        vals.append(int(v))
    return (vals[0], vals[1]) if len(vals) >= 2 else (vals[0], None)


def _parse_market_profiles(text: str) -> dict[str, dict]:
    """Return {zip: {strategy, vintage_target, red_flags}} from profile sections."""
    profiles: dict[str, dict] = {}
    # Each section starts with ### N — Market Name, ST (zip)
    sections = re.split(r"\n### \d+", text)
    for sec in sections[1:]:
        zip_m = re.search(r"\((\d{5})\)", sec)
        if not zip_m:
            continue
        z = zip_m.group(1)
        strategy_m = re.search(r"\*\*Strategy:\*\*\s*(.+)", sec)
        vintage_m  = re.search(r"\*\*Vintage target:\*\*\s*(.+)", sec)
        red_flags_m = re.search(r"\*\*Red flags:\*\*\s*([\s\S]+?)(?=\n---|\n###|\Z)", sec)
        profiles[z] = {
            "strategy":      strategy_m.group(1).strip() if strategy_m else None,
            "vintage_target": vintage_m.group(1).strip() if vintage_m else None,
            "red_flags":     red_flags_m.group(1).strip() if red_flags_m else None,
        }
    return profiles


def load_markets(session) -> int:
    text = BUY_BOX.read_text()
    profiles = _parse_market_profiles(text)

    # Parse the Quick Reference table rows
    table_rows = re.findall(
        r"\|\s*\d+\s*\|\s*([^|]+)\|\s*(\d{5})\s*\|\s*([A-Z]{2})\s*\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|",
        text,
    )

    today = str(date.today())
    count = 0
    for row in table_rows:
        name, zip_code, state, strategy_cell, price_cell, priority_cell = (
            c.strip() for c in row
        )
        low, high = _parse_price(price_cell)
        profile   = profiles.get(zip_code, {})

        existing = session.get(Market, zip_code)
        if existing:
            m = existing
        else:
            m = Market(zip=zip_code)
            session.add(m)
            count += 1

        m.name               = name
        m.state              = state
        m.strategy           = profile.get("strategy") or strategy_cell.strip()
        m.price_per_unit_low  = low
        m.price_per_unit_high = high
        m.vintage_target     = profile.get("vintage_target")
        m.red_flags          = profile.get("red_flags")
        m.priority           = priority_cell.strip()
        m.last_updated       = today

    session.commit()
    return count


# ── Decisions parser ──────────────────────────────────────────────────────────

def _parse_decisions(text: str) -> list[dict]:
    """Parse append-only decisions/log.md into a list of dicts."""
    entries = []
    # Split on level-2 headers: ## YYYY-MM-DD — Title
    blocks = re.split(r"\n## ", text)
    for block in blocks[1:]:
        lines = block.strip().splitlines()
        header = lines[0].strip()
        date_m = re.match(r"(\d{4}-\d{2}-\d{2})\s+[—–-]+\s+(.+)", header)
        if not date_m:
            continue
        entry_date, title = date_m.group(1), date_m.group(2).strip()
        body = "\n".join(lines[1:])
        decision_m   = re.search(r"\*\*Decision:\*\*\s*([\s\S]+?)(?=\*\*Why|\Z)", body)
        why_m        = re.search(r"\*\*Why:\*\*\s*([\s\S]+?)(?=\*\*Alternatives|\Z)", body)
        alts_m       = re.search(r"\*\*Alternatives considered:\*\*\s*([\s\S]+?)(?=\*\*Owner|\Z)", body)
        owner_m      = re.search(r"\*\*Owner:\*\*\s*(.+)", body)
        entries.append({
            "date":          entry_date,
            "title":         title,
            "decision_text": decision_m.group(1).strip() if decision_m else None,
            "why":           why_m.group(1).strip() if why_m else None,
            "alternatives":  alts_m.group(1).strip() if alts_m else None,
            "owner":         owner_m.group(1).strip() if owner_m else None,
        })
    return entries


def load_decisions(session) -> int:
    text    = DECISIONS_LOG.read_text()
    entries = _parse_decisions(text)
    count   = 0
    existing_titles = {(d.date, d.title) for d in session.query(Decision).all()}
    for e in entries:
        key = (e["date"], e["title"])
        if key in existing_titles:
            continue
        session.add(Decision(**e))
        count += 1
    session.commit()
    return count


# ── Wiki indexer ──────────────────────────────────────────────────────────────

def _parse_frontmatter(text: str) -> dict:
    """Extract YAML frontmatter from a markdown file into a plain dict."""
    m = re.match(r"^---\s*\n([\s\S]+?)\n---", text)
    if not m:
        return {}
    fm: dict = {}
    for line in m.group(1).splitlines():
        kv = re.match(r"^(\w[\w_-]*):\s*(.*)", line.strip())
        if kv:
            fm[kv.group(1)] = kv.group(2).strip().strip('"').strip("'")
    return fm


def index_wiki(session) -> int:
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    count = 0
    for cat in WIKI_CATEGORIES:
        cat_dir = WIKI_ROOT / cat
        if not cat_dir.exists():
            continue
        for md in sorted(cat_dir.glob("*.md")):
            rel_path = str(md.relative_to(REPO))
            fm = _parse_frontmatter(md.read_text())
            existing = session.query(Document).filter_by(path=rel_path).first()
            if existing:
                existing.frontmatter  = json.dumps(fm)
                existing.last_indexed = now
            else:
                session.add(Document(
                    path         = rel_path,
                    category     = cat,
                    frontmatter  = json.dumps(fm),
                    last_indexed = now,
                ))
                count += 1
    session.commit()
    return count


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Populate olive.db from existing sources")
    parser.add_argument("--skip-sheets", action="store_true", help="Skip Google Sheets sync")
    args = parser.parse_args()

    print("olive.db — initial migration\n")

    print("  Creating tables …")
    init_db()
    print("  Tables ready.\n")

    session = get_session()

    print("  Seeding markets from buy-box.md …")
    n = load_markets(session)
    total = session.query(Market).count()
    print(f"  {n} new, {total} total markets.\n")

    print("  Loading decisions from decisions/log.md …")
    n = load_decisions(session)
    total = session.query(Decision).count()
    print(f"  {n} new, {total} total decisions.\n")

    print("  Indexing wiki/ markdown files …")
    n = index_wiki(session)
    total = session.query(Document).count()
    print(f"  {n} new, {total} total documents indexed.\n")

    if not args.skip_sheets:
        print("  Syncing from Google Sheets …")
        try:
            import db_sync
            db_sync.run(session)
        except Exception as exc:
            print(f"  Sheets sync failed: {exc}")
            print("  (Re-run later with: python3 scripts/db_sync.py)\n")
    else:
        print("  Skipping Sheets sync (--skip-sheets).\n")

    session.close()
    print("Migration complete.")


if __name__ == "__main__":
    main()
