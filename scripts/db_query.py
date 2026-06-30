#!/usr/bin/env python3
"""
db_query.py — Ad-hoc query tool for olive.db.

Supports raw SQL and a small set of named convenience queries.

Usage
-----
    # Named queries
    python3 scripts/db_query.py markets
    python3 scripts/db_query.py brokers
    python3 scripts/db_query.py brokers --tier A
    python3 scripts/db_query.py brokers --state TN
    python3 scripts/db_query.py deals
    python3 scripts/db_query.py deals --verdict "PURSUE LOI"
    python3 scripts/db_query.py deals --status loi-sent
    python3 scripts/db_query.py meetings
    python3 scripts/db_query.py decisions
    python3 scripts/db_query.py docs --cat deals

    # Raw SQL (quote the whole statement)
    python3 scripts/db_query.py sql "SELECT address, verdict, price_per_unit FROM deals WHERE verdict='PASS'"
    python3 scripts/db_query.py sql "SELECT b.name, b.tier, d.address FROM brokers b JOIN deals d ON d.broker_id=b.id"

    # Counts
    python3 scripts/db_query.py counts
"""

import argparse
import sys
from pathlib import Path
from textwrap import shorten

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from db.connection import engine, init_db
from db.schema import Broker, Deal, Decision, Document, Market, Meeting


def _fmt(v) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:,.2f}"
    return shorten(str(v), width=60, placeholder="…")


def _table(headers: list[str], rows: list[list]) -> str:
    col_w = [len(h) for h in headers]
    str_rows = [[_fmt(c) for c in r] for r in rows]
    for r in str_rows:
        for i, c in enumerate(r):
            col_w[i] = max(col_w[i], len(c))
    sep  = "  ".join("-" * w for w in col_w)
    head = "  ".join(h.ljust(col_w[i]) for i, h in enumerate(headers))
    lines = [head, sep]
    for r in str_rows:
        lines.append("  ".join(c.ljust(col_w[i]) for i, c in enumerate(r)))
    return "\n".join(lines)


# ── Named query handlers ──────────────────────────────────────────────────────

def query_markets(session, args):
    q = session.query(Market)
    rows = q.order_by(Market.state, Market.name).all()
    print(_table(
        ["Zip", "Market", "State", "Strategy", "Price/Unit Low", "Price/Unit High", "Priority"],
        [[m.zip, m.name, m.state, m.strategy, m.price_per_unit_low, m.price_per_unit_high, m.priority]
         for m in rows],
    ))
    print(f"\n{len(rows)} market(s)")


def query_brokers(session, args):
    q = session.query(Broker)
    if getattr(args, "tier", None):
        q = q.filter(Broker.tier == args.tier.upper())
    if getattr(args, "state", None):
        q = q.filter(Broker.markets_covered.contains(args.state))
    rows = q.order_by(Broker.tier, Broker.name).all()
    print(_table(
        ["ID", "Name", "Brokerage", "Email", "Tier", "Markets", "Last Contact", "Status"],
        [[b.id, b.name, b.brokerage, b.email, b.tier, b.markets_covered, b.last_contact, b.status]
         for b in rows],
    ))
    print(f"\n{len(rows)} broker(s)")


def query_deals(session, args):
    q = session.query(Deal)
    if getattr(args, "verdict", None):
        q = q.filter(Deal.verdict == args.verdict)
    if getattr(args, "status", None):
        q = q.filter(Deal.status == args.status)
    rows = q.order_by(Deal.date_found.desc().nullslast()).all()
    print(_table(
        ["ID", "Address", "Zip", "Units", "Asking", "PPU", "Cap%", "IRR%", "Status", "Verdict"],
        [[d.id, d.address, d.zip, d.units, d.asking_price, d.price_per_unit,
          d.cap_rate, d.irr, d.status, d.verdict] for d in rows],
    ))
    print(f"\n{len(rows)} deal(s)")


def query_meetings(session, args):
    rows = session.query(Meeting).order_by(Meeting.date.desc()).all()
    print(_table(
        ["ID", "Date", "Type", "Participants", "Fathom Link"],
        [[m.id, m.date, m.type, m.participants, m.fathom_link] for m in rows],
    ))
    print(f"\n{len(rows)} meeting(s)")


def query_decisions(session, args):
    rows = session.query(Decision).order_by(Decision.date.desc()).all()
    print(_table(
        ["Date", "Title", "Owner"],
        [[d.date, d.title, d.owner] for d in rows],
    ))
    print(f"\n{len(rows)} decision(s)")


def query_docs(session, args):
    q = session.query(Document)
    if getattr(args, "cat", None):
        q = q.filter(Document.category == args.cat)
    rows = q.order_by(Document.category, Document.path).all()
    print(_table(
        ["ID", "Category", "Path", "Last Indexed"],
        [[d.id, d.category, d.path, d.last_indexed] for d in rows],
    ))
    print(f"\n{len(rows)} document(s)")


def query_counts(session, args):
    from db.schema import Investor, InvestorCommitment
    pairs = [
        ("markets",              session.query(Market).count()),
        ("brokers",              session.query(Broker).count()),
        ("deals",                session.query(Deal).count()),
        ("investors",            session.query(Investor).count()),
        ("investor_commitments", session.query(InvestorCommitment).count()),
        ("meetings",             session.query(Meeting).count()),
        ("decisions",            session.query(Decision).count()),
        ("documents (wiki idx)", session.query(Document).count()),
    ]
    for label, n in pairs:
        print(f"  {label:<28} {n:>6}")


def query_sql(session, args):
    sql = " ".join(args.sql)
    with engine.connect() as conn:
        result = conn.execute(text(sql))
        cols   = list(result.keys())
        rows   = result.fetchall()
    if rows:
        print(_table(cols, [list(r) for r in rows]))
    else:
        print("(no rows)")
    print(f"\n{len(rows)} row(s)")


# ── CLI ───────────────────────────────────────────────────────────────────────

HANDLERS = {
    "markets":   query_markets,
    "brokers":   query_brokers,
    "deals":     query_deals,
    "meetings":  query_meetings,
    "decisions": query_decisions,
    "docs":      query_docs,
    "counts":    query_counts,
    "sql":       query_sql,
}


def main():
    parser = argparse.ArgumentParser(
        description="Query olive.db",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  python3 scripts/db_query.py counts
  python3 scripts/db_query.py brokers --tier A
  python3 scripts/db_query.py deals --verdict "PURSUE LOI"
  python3 scripts/db_query.py sql "SELECT * FROM deals WHERE verdict='PASS'"
""",
    )
    parser.add_argument("command", choices=list(HANDLERS.keys()), help="Query to run")
    parser.add_argument("sql", nargs="*", help="(sql command) raw SQL string")
    parser.add_argument("--tier",    help="(brokers) filter by tier: A/B/C")
    parser.add_argument("--state",   help="(brokers) filter by state abbreviation")
    parser.add_argument("--verdict", help="(deals) filter by verdict")
    parser.add_argument("--status",  help="(deals) filter by status")
    parser.add_argument("--cat",     help="(docs) filter by wiki category")
    args = parser.parse_args()

    init_db()

    from db.connection import get_session
    session = get_session()
    try:
        HANDLERS[args.command](session, args)
    finally:
        session.close()


if __name__ == "__main__":
    main()
