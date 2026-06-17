#!/usr/bin/env python3
"""
Olive Tree — Land Builders (the /land-builders engine)

Captures the buy box of spec builders / land buyers you call, into the Land
Builders tab + olive.db. Buy-box capture is a phone call (inherently manual);
this script is the structured place to record and look up what they told you,
and it sets the price that /land-sellers uses to compute offers.

Usage:
  # Add / update a builder's buy box
  python3 scripts/land_builders.py --add \
      --name "Jane Doe" --company "Acme Homes" --phone 770-555-0100 \
      --markets 30120,30121 --price-per-acre 8000 --min-acres 1 --max-acres 10 \
      --volume 3 --conditions "no wetlands; <10% slope; needs road frontage" \
      --timeline "30 days" --tier A

  # List builders (optionally for a zip)
  python3 scripts/land_builders.py --list
  python3 scripts/land_builders.py --list --market 30120

  # Show the price/acre to use for a market (max across builders covering it)
  python3 scripts/land_builders.py --price-for 30120
"""

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from land_sheets import get_token, read_rows, upsert_row  # noqa: E402

TAB = "Land Builders"
# Land Builders header order (land_setup.TABS):
# Name|Company|Phone|Email|Markets/Zips|Lot Size Min|Lot Size Max|Price Per Lot|
# Volume/Mo|Conditions|Close Timeline|Tier|Deals Done|Last Contact|Notes


def _row(a):
    # Price Per Lot column carries either a flat price or "$/acre <n>" note.
    price = f"${a.price_per_acre:g}/ac" if a.price_per_acre else (a.price_per_lot or "")
    return [
        a.name or "", a.company or "", a.phone or "", a.email or "",
        a.markets or "", a.min_acres or "", a.max_acres or "", price,
        a.volume or "", a.conditions or "", a.timeline or "", a.tier or "B",
        0, date.today().isoformat(), a.notes or "",
    ]


def _db_upsert(a):
    try:
        from db.connection import get_session
        from db.schema import LandBuilder
        s = get_session()
        key = a.email or a.name
        existing = (s.query(LandBuilder)
                    .filter((LandBuilder.email == a.email) | (LandBuilder.name == a.name))
                    .first()) if key else None
        obj = existing or LandBuilder()
        obj.name, obj.company, obj.phone, obj.email = a.name, a.company, a.phone, a.email
        obj.markets = a.markets
        obj.lot_size_min = a.min_acres
        obj.lot_size_max = a.max_acres
        obj.price_per_lot = a.price_per_acre or a.price_per_lot
        obj.volume_per_mo = a.volume
        obj.conditions = a.conditions
        obj.close_timeline = a.timeline
        obj.tier = a.tier or "B"
        obj.last_contact = date.today().isoformat()
        obj.notes = a.notes
        if not existing:
            s.add(obj)
        s.commit()
        s.close()
    except Exception as e:
        print(f"  (DB mirror skipped: {e})")


def cmd_add(a):
    if not a.name:
        sys.exit("--name is required to add a builder")
    token = get_token()
    # Dedup the sheet on builder name (col 0).
    status = upsert_row(token, TAB, 0, a.name, _row(a))
    _db_upsert(a)
    print(f"Builder '{a.name}' {status} in Land Builders.")


def cmd_list(a):
    token = get_token()
    rows = read_rows(token, TAB)
    if len(rows) <= 1:
        print("No builders yet. Add one with --add.")
        return
    header, data = rows[0], rows[1:]
    for r in data:
        if a.market and a.market not in (r[4] if len(r) > 4 else ""):
            continue
        name = r[0] if r else ""
        company = r[1] if len(r) > 1 else ""
        markets = r[4] if len(r) > 4 else ""
        price = r[7] if len(r) > 7 else ""
        print(f"  {name:24} {company:22} {markets:16} {price}")


def cmd_price_for(a):
    """Highest builder price/acre covering a market — the offer anchor."""
    token = get_token()
    rows = read_rows(token, TAB)
    best = None
    for r in rows[1:]:
        markets = r[4] if len(r) > 4 else ""
        price = r[7] if len(r) > 7 else ""
        if a.price_for in markets and "/ac" in price:
            try:
                v = float(price.replace("$", "").replace("/ac", ""))
                best = max(best or 0, v)
            except ValueError:
                pass
    if best:
        print(f"{a.price_for}: use ${best:.0f}/acre (max builder price on file)")
    else:
        print(f"{a.price_for}: no per-acre builder price on file yet. "
              f"Call a builder and --add one.")


def main():
    ap = argparse.ArgumentParser(description="Capture/look up land builder buy boxes.")
    ap.add_argument("--add", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--price-for", help="Show offer-anchor $/acre for a market zip")
    ap.add_argument("--market", help="Filter --list to a market zip")
    # buy-box fields
    ap.add_argument("--name"); ap.add_argument("--company"); ap.add_argument("--phone")
    ap.add_argument("--email"); ap.add_argument("--markets", help="comma-separated zips")
    ap.add_argument("--price-per-acre", type=float)
    ap.add_argument("--price-per-lot")
    ap.add_argument("--min-acres", type=float); ap.add_argument("--max-acres", type=float)
    ap.add_argument("--volume", type=int, help="lots/month")
    ap.add_argument("--conditions"); ap.add_argument("--timeline"); ap.add_argument("--tier")
    ap.add_argument("--notes")
    a = ap.parse_args()

    if a.add:
        cmd_add(a)
    elif a.price_for:
        cmd_price_for(a)
    elif a.list:
        cmd_list(a)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
