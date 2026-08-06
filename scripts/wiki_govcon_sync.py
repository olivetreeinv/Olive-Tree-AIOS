#!/usr/bin/env python3
"""
wiki_govcon_sync.py — Sync the GovCon bid tracker into the LLM Wiki.

Reads from olive-tree-govcon/sam_data.db (bids table) and writes/updates
wiki pages for each bid, its agency, and any recorded subcontractors.

Usage:
    python scripts/wiki_govcon_sync.py              # sync all bids
    python scripts/wiki_govcon_sync.py --overwrite  # regenerate all pages
    python scripts/wiki_govcon_sync.py --dry-run    # print what would be written
"""

import argparse
import datetime
import re
import sqlite3
import sys
from pathlib import Path

import anthropic

REPO_ROOT = Path(__file__).parent.parent
DB_PATH = REPO_ROOT / "olive-tree-govcon" / "sam_data.db"
WIKI_ROOT = REPO_ROOT / "wiki"
LOG = WIKI_ROOT / "_log.md"
SCHEMA = WIKI_ROOT / "SCHEMA.md"

GENERATE_MODEL = "claude-sonnet-4-6"

NAICS_LABELS: dict[str, str] = {
    "561720": "Janitorial & Cleaning",
    "561730": "Landscaping",
    "561710": "Pest Control",
    "561740": "Carpet & Upholstery Cleaning",
    "561790": "Other Building Services",
    "238320": "Painting & Wall Covering",
    "238110": "Poured Concrete",
    "238130": "Framing",
    "238140": "Masonry",
    "238160": "Roofing",
    "238170": "Siding",
    "238190": "Exterior Trades (Other)",
    "238210": "Electrical",
    "238220": "Plumbing & HVAC",
    "238290": "Other Building Equipment",
    "238310": "Drywall & Insulation",
    "238330": "Flooring",
    "238340": "Tile & Terrazzo",
    "238350": "Finish Carpentry",
    "238390": "Other Finishing Trades",
    "238990": "Specialty Trades (Other)",
    "236118": "Residential Remodelers",
    "236220": "Commercial Building Construction",
    "238910": "Site Prep & Excavation",
    "531311": "Residential Property Management",
}

client = anthropic.Anthropic()


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower().strip()).strip("-")


def load_bids() -> list[dict]:
    if not DB_PATH.exists():
        print(f"Database not found: {DB_PATH}")
        sys.exit(1)
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM bids ORDER BY created_at").fetchall()
    return [dict(r) for r in rows]


def agency_slug(agency: str) -> str:
    return slugify(agency)


def fmt_money(val) -> str:
    if val is None:
        return "—"
    try:
        return f"${float(val):,.2f}"
    except (TypeError, ValueError):
        return str(val)


def fmt(val) -> str:
    return str(val) if val is not None else "—"


# ---------------------------------------------------------------------------
# Page builders (no AI needed — data is already structured)
# ---------------------------------------------------------------------------

def build_bid_page(bid: dict) -> str:
    naics = bid.get("naics_code") or "—"
    naics_label = NAICS_LABELS.get(naics, "—")
    agency = bid.get("agency") or "—"
    agency_link = f"[[govcon-agencies/{agency_slug(agency)}]]" if agency != "—" else "—"
    sub_name = bid.get("sub_name")
    sub_link = f"[[govcon-subs/{slugify(sub_name)}]]" if sub_name else "—"

    margin = "—"
    if bid.get("our_bid") and bid.get("sub_quote"):
        try:
            margin = f"{(float(bid['our_bid']) - float(bid['sub_quote'])) / float(bid['our_bid']) * 100:.1f}%"
        except (TypeError, ValueError, ZeroDivisionError):
            pass

    return f"""\
---
type: govcon-bid
title: {bid.get('title', '—')}
notice_id: {bid.get('notice_id', '—')}
agency: "{agency_link}"
naics_code: "{naics}"
naics_label: {naics_label}
state: {fmt(bid.get('state'))}
deadline: {fmt(bid.get('deadline'))}
sam_link: {fmt(bid.get('sam_link'))}
status: {bid.get('status', 'researching')}
sub_name: {fmt(sub_name)}
sub_contact: {fmt(bid.get('sub_contact'))}
sub_quote: {fmt_money(bid.get('sub_quote'))}
our_bid: {fmt_money(bid.get('our_bid'))}
past_price_ceiling: {fmt_money(bid.get('past_price_ceiling'))}
gross_profit: {fmt_money(bid.get('gross_profit'))}
last_updated: {datetime.date.today()}
---

## Status
**{bid.get('status', 'researching').upper()}** — {_status_note(bid)}

## Subcontractor
- **Name:** {sub_link}
- **Quote:** {fmt_money(bid.get('sub_quote'))}
- **Contact:** {fmt(bid.get('sub_contact'))}

## Pricing
| Item | Amount |
|---|---|
| Sub quote | {fmt_money(bid.get('sub_quote'))} |
| Our bid | {fmt_money(bid.get('our_bid'))} |
| Past price ceiling | {fmt_money(bid.get('past_price_ceiling'))} |
| Gross profit | {fmt_money(bid.get('gross_profit'))} |
| Margin | {margin} |

## Proposal
{bid.get('proposal_text') or '—'}

## Notes
{bid.get('notes') or ''}
"""


def _status_note(bid: dict) -> str:
    status = bid.get("status", "researching")
    notes = {
        "researching":   "Reviewing opportunity. Next: find and contact a sub.",
        "sub_contacted": "Sub outreach sent. Next: follow up for quote.",
        "quoted":        "Sub quote received. Next: build pricing and submit.",
        "submitted":     "Proposal submitted. Awaiting award decision.",
        "won":           "Contract awarded.",
        "lost":          "Not awarded.",
        "skipped":       "Passed on this opportunity.",
    }
    return notes.get(status, "")


def build_agency_page(agency: str, bids: list[dict]) -> str:
    naics_set = sorted({b.get("naics_code") for b in bids if b.get("naics_code")})
    bid_links = "\n".join(
        f"- [[govcon-bids/{slugify(b['title'])}]] — {b.get('state')} — {b.get('status')}"
        for b in bids
    )
    return f"""\
---
type: govcon-agency
name: {agency}
abbreviation: {_abbreviate(agency)}
typical_naics:
{chr(10).join(f'  - "{n}"' for n in naics_set)}
---

## Overview
Federal agency. Contracts observed: {len(bids)}.

## Active Bids
{bid_links or '—'}

## Past Awards (from USASpending)
| Title | Amount | State | Year |
|---|---|---|---|

## Notes
"""


def _abbreviate(agency: str) -> str:
    words = agency.upper().split()
    stops = {"OF", "THE", "AND", "FOR", "IN", "A"}
    return "".join(w[0] for w in words if w not in stops) or agency[:6].upper()


def build_sub_page(bid: dict) -> str:
    """Build a stub sub page from bid data."""
    name = bid.get("sub_name") or "Unknown"
    naics = bid.get("naics_code") or "—"
    state = bid.get("state") or "—"
    return f"""\
---
type: govcon-sub
name: {name}
contact: {fmt(bid.get('sub_contact'))}
naics_codes:
  - "{naics}"
states:
  - {state}
last_contact: {datetime.date.today()}
reliability: —
---

## Quote History
| Bid | NAICS | State | Quote | Outcome | Date |
|---|---|---|---|---|---|
| [[govcon-bids/{slugify(bid.get('title', ''))}]] | {naics} | {state} | {fmt_money(bid.get('sub_quote'))} | {fmt(bid.get('status'))} | {fmt(bid.get('updated_at', '')[:10])} |

## Notes
"""


# ---------------------------------------------------------------------------
# Sync logic
# ---------------------------------------------------------------------------

def append_log(entry: str):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    with LOG.open("a") as f:
        f.write(f"\n## {timestamp}\n{entry}\n")


def write_page(path: Path, content: str, overwrite: bool, dry_run: bool) -> bool:
    if path.exists() and not overwrite:
        return False
    if not dry_run:
        path.write_text(content)
    action = "[dry] " if dry_run else ("updated" if path.exists() else "wrote")
    print(f"  {action}: {path.relative_to(WIKI_ROOT)}")
    return True


def sync(overwrite: bool = False, dry_run: bool = False):
    bids = load_bids()
    print(f"Syncing {len(bids)} bid(s) from {DB_PATH.name}...")

    written: list[str] = []

    # Group bids by agency for agency pages
    by_agency: dict[str, list[dict]] = {}
    for bid in bids:
        agency = bid.get("agency") or "Unknown"
        by_agency.setdefault(agency, []).append(bid)

    # Write bid pages
    for bid in bids:
        title = bid.get("title") or bid.get("notice_id") or "unknown"
        slug = slugify(title)
        dest = WIKI_ROOT / "govcon-bids" / f"{slug}.md"
        page = build_bid_page(bid)
        if write_page(dest, page, overwrite, dry_run):
            written.append(f"govcon-bids/{slug}.md")

    # Write agency pages
    for agency, agency_bids in by_agency.items():
        slug = agency_slug(agency)
        dest = WIKI_ROOT / "govcon-agencies" / f"{slug}.md"
        page = build_agency_page(agency, agency_bids)
        if write_page(dest, page, overwrite, dry_run):
            written.append(f"govcon-agencies/{slug}.md")

    # Write sub stub pages for any bids with a recorded sub
    for bid in bids:
        if bid.get("sub_name"):
            slug = slugify(bid["sub_name"])
            dest = WIKI_ROOT / "govcon-subs" / f"{slug}.md"
            page = build_sub_page(bid)
            if write_page(dest, page, overwrite, dry_run):
                written.append(f"govcon-subs/{slug}.md")

    if written and not dry_run:
        append_log(
            f"**govcon sync** — {len(bids)} bids  \n"
            f"**Pages written/updated:** {len(written)}  \n"
            f"**Pages:** {', '.join(f'`{p}`' for p in written)}"
        )

    print(f"\nDone. {len(written)} page(s) written.")
    if not written:
        print("  (all pages already up to date — use --overwrite to regenerate)")


def main():
    parser = argparse.ArgumentParser(description="Sync GovCon bids to the LLM Wiki")
    parser.add_argument("--overwrite", action="store_true", help="Regenerate existing pages")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be written — write nothing")
    args = parser.parse_args()
    sync(overwrite=args.overwrite, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
