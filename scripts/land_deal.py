#!/usr/bin/env python3
"""
Olive Tree — Land Deal (/land-deal cockpit)

Tracks a land deal from contract through close. Computes the spread/profit,
runs the deal-killer checklist, logs status to the Land Deals tab + olive.db,
and fires post-close actions ($1,000 referral + neighbor first-look script).

Usage:
  # Open a new deal (logs the spread; runs deal-killer checklist)
  python3 scripts/land_deal.py --parcel 0051-0574-005 \
      --contract-price 45400 --assignment-price 54000 --builder "LGI Homes"

  # Update status
  python3 scripts/land_deal.py --parcel 0051-0574-005 --status psa-signed
  python3 scripts/land_deal.py --parcel 0051-0574-005 --status assigned
  python3 scripts/land_deal.py --parcel 0051-0574-005 --status closed

  # Log a deal-killer flag
  python3 scripts/land_deal.py --parcel 0051-0574-005 --flag wetlands --severity high
  python3 scripts/land_deal.py --parcel 0051-0574-005 --flag slope --severity low

  # Post-close: trigger referral + neighbor script
  python3 scripts/land_deal.py --parcel 0051-0574-005 --post-close

  # Show all deals in the pipeline
  python3 scripts/land_deal.py --pipeline
"""

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

from land_sheets import get_token, read_rows, upsert_row  # noqa: E402

load_dotenv()

TAB = "Land Deals"

# Land Deals column indices (land_setup.TABS["Land Deals"])
D_PARCEL      =  0   # Parcel ID
D_SITUS       =  1   # Situs Address
D_SELLER      =  2   # Seller (owner name)
D_BUILDER     =  3   # Builder / Assignee
D_CONTRACT    =  4   # Contract Price
D_ASSIGNMENT  =  5   # Assignment Price (builder pays)
D_SPREAD      =  6   # Spread
D_STATUS      =  7   # Status
D_FEASIBILITY =  8   # Feasibility Deadline
D_KILLERS     =  9   # Deal-Killer Check (JSON)
D_TITLE_CO    = 10   # Title Company
D_CLOSE_DATE  = 11   # Close Date
D_PROFIT      = 12   # Profit
D_REFERRAL    = 13   # Referral Sent
D_NEIGHBORS   = 14   # Neighbors Called
D_NOTES       = 15   # Notes

# Land Sellers column indices (for lookup)
S_PARCEL  =  0
S_SITUS   =  1
S_ZIP     =  2
S_OWNER   =  5
S_OFFER   = 11

STATUSES = [
    "new", "psa-sent", "psa-signed", "assigned",
    "in-dd", "title-open", "closed", "terminated",
]

DEAL_KILLERS = [
    ("wetlands",   "Aerial: gray/dead trees = standing water. Severe — can gut value."),
    ("wildlife",   "Call city planning: gopher tortoise, scrub jay, other protected species."),
    ("slope",      "County GIS elevation layer; ask builder's slope tolerance. Big in hilly NW GA."),
    ("utilities",  "County records: are water/sewer/electric at the street? Well-septic ok?"),
    ("flood",      "FEMA / county GIS: flood zone A or AE = lender/buyer risk."),
    ("main-road",  "Check any map: main-road frontage reduces demand from builders and buyers."),
    ("title",      "Title search: open liens, back taxes, heirs/estate issues, break in chain."),
    ("back-taxes", "County tax records: past-due taxes? Cleared at closing, but affects net."),
]

CLOSE_DAYS = 21


def _col(row, idx, default=""):
    return (row[idx].strip() if len(row) > idx and row[idx] else default)


def _fmt(val):
    try:
        return f"${float(val):,.0f}"
    except (ValueError, TypeError):
        return str(val) if val else "—"


def _find_deal(rows, parcel_id):
    for r in rows[1:]:
        if _col(r, D_PARCEL) == parcel_id:
            return list(r)
    return None


def _find_seller(rows, parcel_id):
    for r in rows[1:]:
        if _col(r, S_PARCEL) == parcel_id:
            return r
    return None


def _build_row(parcel_id, situs, seller, builder,
               contract_price, assignment_price, spread,
               status, feasibility, killers, profit):
    today = date.today().isoformat()
    return [
        parcel_id, situs, seller, builder,
        contract_price or "", assignment_price or "", spread or "",
        status, feasibility, killers,
        "", "", profit or "", "N", "N", "",
    ]


def cmd_open(args, token):
    """Log a new deal or update price/builder on an existing one."""
    seller_rows = read_rows(token, "Land Sellers")
    seller_row  = _find_seller(seller_rows, args.parcel)
    if seller_row is None:
        sys.exit(f"Parcel '{args.parcel}' not found in Land Sellers tab.")

    situs  = _col(seller_row, S_SITUS)
    seller = _col(seller_row, S_OWNER)
    offer  = args.contract_price or _col(seller_row, S_OFFER)

    asgn = args.assignment_price
    if not asgn:
        # Default heuristic: offer / (1 - spread) ≈ builder's buy-box price.
        # This is a rough estimate — always verify with your builder before
        # sending the assignment. Pass --assignment-price to set it exactly.
        try:
            asgn = round(float(offer) / (1 - DEFAULT_SPREAD) / 100) * 100
        except (TypeError, ValueError, ZeroDivisionError):
            asgn = None

    spread = None
    profit = None
    try:
        spread = float(asgn) - float(offer)
        profit = spread   # simplified: no costs in this model
    except (TypeError, ValueError):
        pass

    feasibility = (date.today() + timedelta(days=CLOSE_DAYS)).isoformat()

    # Check for existing deal row
    deal_rows = read_rows(token, TAB)
    existing = _find_deal(deal_rows, args.parcel)
    killers = _col(existing, D_KILLERS) if existing else "{}"

    row = _build_row(
        args.parcel, situs, seller, args.builder or (
            _col(existing, D_BUILDER) if existing else ""),
        offer, asgn, spread, "new" if not existing else _col(existing, D_STATUS),
        feasibility, killers, profit,
    )
    upsert_row(token, TAB, D_PARCEL, args.parcel, row)

    print(f"\n  Land Deal opened: {args.parcel}")
    print(f"  Seller:           {seller}")
    print(f"  Situs:            {situs}")
    print(f"  Contract price:   {_fmt(offer)}")
    print(f"  Assignment price: {_fmt(asgn)}")
    print(f"  Your spread:      {_fmt(spread)}")
    print(f"  Feasibility by:   {feasibility}\n")
    print(f"  Deal-killer checklist (run each; flag anything material):")
    for key, desc in DEAL_KILLERS:
        print(f"    • {key:12} — {desc}")
    print(f"\n  Flag issues:")
    print(f"    python3 scripts/land_deal.py --parcel {args.parcel} --flag wetlands --severity high")
    print(f"\n  When clear: update status to psa-sent or assigned.")
    print(f"    python3 scripts/land_deal.py --parcel {args.parcel} --status psa-sent")


def cmd_status(args, token):
    if args.status not in STATUSES:
        sys.exit(f"--status must be one of: {', '.join(STATUSES)}")

    deal_rows = read_rows(token, TAB)
    row = _find_deal(deal_rows, args.parcel)
    if row is None:
        sys.exit(f"Deal '{args.parcel}' not in Land Deals tab. Open it with --contract-price first.")

    while len(row) < 16:
        row.append("")

    row[D_STATUS] = args.status
    if args.status == "closed":
        row[D_CLOSE_DATE] = date.today().isoformat()

    upsert_row(token, TAB, D_PARCEL, args.parcel, row)
    print(f"  {args.parcel} → status: {args.status}")

    if args.status == "closed":
        print("\n  Deal closed! Run --post-close to fire referral + neighbor actions.")


def cmd_flag(args, token):
    if not args.severity:
        args.severity = "medium"

    deal_rows = read_rows(token, TAB)
    row = _find_deal(deal_rows, args.parcel)
    if row is None:
        sys.exit(f"Deal '{args.parcel}' not in Land Deals tab. Open it first.")

    while len(row) < 16:
        row.append("")

    try:
        killers = json.loads(row[D_KILLERS] or "{}")
    except json.JSONDecodeError:
        killers = {}

    killers[args.flag] = args.severity
    row[D_KILLERS] = json.dumps(killers)
    upsert_row(token, TAB, D_PARCEL, args.parcel, row)

    sev = args.severity.upper()
    print(f"  Flagged {args.flag} [{sev}] on {args.parcel}.")

    if args.severity == "high":
        print(f"\n  ⚠️  HIGH severity. Consider terminating (feasibility clause — no penalty).")
        print(f"  To terminate: update status to terminated and email the seller.")
    elif args.severity == "medium":
        print(f"\n  Medium severity. Confirm with your builder — they may accept or want a price cut.")


def cmd_post_close(args, token):
    deal_rows = read_rows(token, TAB)
    row = _find_deal(deal_rows, args.parcel)
    if row is None:
        sys.exit(f"Deal '{args.parcel}' not in Land Deals tab.")

    while len(row) < 16:
        row.append("")

    situs  = _col(row, D_SITUS)
    seller = _col(row, D_SELLER)
    profit = _col(row, D_PROFIT)

    print(f"\n  Post-close actions — {args.parcel}")
    print(f"  Situs:   {situs}")
    print(f"  Seller:  {seller}")
    print(f"  Profit:  {_fmt(profit)}\n")

    print(f"  1. REFERRAL LETTER (mail within 48 hrs):")
    print(f"     —————————————————————————————————————")
    print(f"     {seller}")
    print(f"     Dear {seller.split()[0] if seller else '[Name]'},")
    print(f"     Thank you for working with us on {situs}. It was a pleasure")
    print(f"     and I hope it was the cleanest transaction you've ever done.")
    print(f"     If you refer a friend or family member whose land I end up")
    print(f"     buying, I'll send you $1,000 cash at closing. No strings.")
    print(f"     My number: call or text any time.")
    print(f"     - Brian Norton, Olive Tree Investments")
    print(f"     —————————————————————————————————————\n")

    print(f"  2. NEIGHBOR FIRST-LOOK (call adjacent owners before builder re-lists):")
    print(f"     From the Land Sellers tab, find owners with lots adjacent to {situs}.")
    print(f"     Script: 'Hi [name] — courtesy call. I'm about to sell the vacant lot")
    print(f"     next to you at {situs} to a builder. Before it goes, I wanted")
    print(f"     to give you first look — any interest in extending your yard or")
    print(f"     picking it up yourself?'")
    print(f"     (Neighbors often pay above market — the lot has unique value to them.)\n")

    print(f"  3. SAME-OWNER CHECK:")
    print(f"     Run: python3 scripts/land_sellers.py --zip [zip] --dry-run")
    print(f"     Look for other parcels under '{seller}' — they may own adjacent lots.\n")

    row[D_REFERRAL]  = "Y"
    row[D_NEIGHBORS] = "pending"
    upsert_row(token, TAB, D_PARCEL, args.parcel, row)
    print(f"  Referral marked sent. Neighbors column → 'pending'.")


def cmd_pipeline(token):
    deal_rows = read_rows(token, TAB)
    if len(deal_rows) <= 1:
        print("  No deals in the pipeline yet. Open one with --contract-price.")
        return
    print(f"\n  Land Deal Pipeline — {date.today().isoformat()}")
    print(f"  {'Parcel':20} {'Situs':26} {'Status':12} {'Spread':>10} {'Killers'}")
    print(f"  {'─'*80}")
    for r in deal_rows[1:]:
        p = _col(r, D_PARCEL)
        s = _col(r, D_SITUS)[:25]
        st = _col(r, D_STATUS)
        sp = _col(r, D_SPREAD)
        ki = _col(r, D_KILLERS)
        try:
            flags = list(json.loads(ki or "{}").keys())
        except json.JSONDecodeError:
            flags = []
        flag_str = ", ".join(flags) if flags else "—"
        print(f"  {p:20} {s:26} {st:12} {_fmt(sp):>10} {flag_str}")
    print()


def main():
    ap = argparse.ArgumentParser(description="Land deal cockpit — track from contract to close.")
    ap.add_argument("--parcel", help="Parcel ID (required for all non-pipeline commands)")

    # Open / edit
    ap.add_argument("--contract-price", type=float,
                    help="Price you're paying the seller")
    ap.add_argument("--assignment-price", type=float,
                    help="Price the builder pays you (contract price + spread)")
    ap.add_argument("--builder", help="Builder/Assignee name")

    # Status
    ap.add_argument("--status", choices=STATUSES,
                    help=f"Update status ({', '.join(STATUSES)})")

    # Deal-killers
    ap.add_argument("--flag", choices=[k for k, _ in DEAL_KILLERS],
                    help="Flag a deal-killer issue")
    ap.add_argument("--severity", choices=["low", "medium", "high"],
                    help="Severity of the flagged issue")

    # Post-close
    ap.add_argument("--post-close", action="store_true",
                    help="Generate referral + neighbor scripts after closing")

    # Pipeline view
    ap.add_argument("--pipeline", action="store_true",
                    help="Show all deals in the pipeline")

    args = ap.parse_args()

    token = get_token()

    if args.pipeline:
        cmd_pipeline(token)
        return

    if not args.parcel:
        ap.print_help()
        return

    if args.post_close:
        cmd_post_close(args, token)
    elif args.status:
        cmd_status(args, token)
    elif args.flag:
        cmd_flag(args, token)
    else:
        cmd_open(args, token)


if __name__ == "__main__":
    main()
