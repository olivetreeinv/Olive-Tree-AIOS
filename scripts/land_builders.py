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

  # Discover builder leads for a zip via Google Places (unverified rows to call)
  python3 scripts/land_builders.py --discover-builders 30120
"""

import argparse
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from land_sheets import get_token, read_rows, upsert_row  # noqa: E402

TAB = "Land Builders"
# Land Builders header order (land_setup.TABS):
# Name|Company|State|City|Phone|Email|Markets/Zips|Avg $/Acre (Comp)|Lot Size Min|
# Lot Size Max|Price Per Lot|Volume/Mo|Conditions|Close Timeline|Tier|Deals Done|
# Last Contact|Notes|Intake Portal


def _row(a):
    # Price Per Lot column carries either a flat price or "$/acre <n>" note.
    price = f"${a.price_per_acre:g}/ac" if a.price_per_acre else (a.price_per_lot or "")
    return [
        a.name or "", a.company or "", a.state or "", a.city or "",
        a.phone or "", a.email or "",
        a.markets or "", a.avg_acre or "", a.min_acres or "", a.max_acres or "", price,
        a.volume or "", a.conditions or "", a.timeline or "", a.tier or "B",
        0, date.today().isoformat(), a.notes or "", a.intake_portal or "",
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
        if a.market and a.market not in (r[6] if len(r) > 6 else ""):
            continue
        name = r[0] if r else ""
        company = r[1] if len(r) > 1 else ""
        loc = "/".join(p for p in [(r[2] if len(r) > 2 else ""),
                                   (r[3] if len(r) > 3 else "")] if p)
        markets = r[6] if len(r) > 6 else ""
        price = r[10] if len(r) > 10 else ""
        print(f"  {name:24} {company:22} {loc:18} {markets:16} {price}")


def cmd_price_for(a):
    """Highest builder price/acre covering a market — the offer anchor."""
    token = get_token()
    rows = read_rows(token, TAB)
    best = None
    for r in rows[1:]:
        markets = r[6] if len(r) > 6 else ""
        price = r[10] if len(r) > 10 else ""
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


def _city_state(formatted_address):
    """'123 Main St, Cartersville, GA 30120, USA' -> ('Cartersville', 'GA').
    Anchors on the 'ST 12345' part, so it works with or without a country suffix."""
    import re
    parts = [p.strip() for p in (formatted_address or "").split(",")]
    for i, p in enumerate(parts):
        m = re.match(r"^([A-Z]{2})\s+\d{5}", p)
        if m and i >= 1:
            return parts[i - 1], m.group(1)
    return "", ""


def _places_search(query, key):
    """Google Places (New) Text Search — returns list of builder dicts."""
    import requests
    resp = requests.post(
        "https://places.googleapis.com/v1/places:searchText",
        headers={
            "X-Goog-Api-Key": key,
            "X-Goog-FieldMask": ("places.displayName,places.nationalPhoneNumber,"
                                 "places.websiteUri,places.formattedAddress"),
        },
        json={"textQuery": query},
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json().get("places", [])


def cmd_discover(a):
    zip_code = a.discover_builders
    key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not key:
        sys.exit("Set GOOGLE_MAPS_API_KEY in .env (Places API New). ~$0/mo at this volume.")
    seen, leads = set(), []
    for q in (f"home builders in {zip_code}", f"land developers in {zip_code}"):
        for p in _places_search(q, key):
            company = (p.get("displayName") or {}).get("text", "")
            phone = p.get("nationalPhoneNumber", "")
            # No phone = a subdivision/POI, not a callable builder. Dedup builders
            # by phone so one builder isn't listed once per community they sell.
            if not company or not phone or phone in seen:
                continue
            seen.add(phone)
            city, state = _city_state(p.get("formattedAddress", ""))
            leads.append({
                "company": company, "phone": p.get("nationalPhoneNumber", ""),
                "city": city, "state": state, "site": p.get("websiteUri", ""),
            })
    if not leads:
        print(f"No builder leads found for {zip_code}.")
        return
    token = get_token()
    for L in leads:
        # header: Name|Company|State|City|Phone|Email|Markets|Avg$|Min|Max|Price|
        #         Vol|Conditions|Timeline|Tier|Deals|LastContact|Notes|IntakePortal
        row = ["", L["company"], L["state"], L["city"], L["phone"], "", zip_code,
               "", "", "", "", "", "", "", "unverified", 0,
               date.today().isoformat(),
               f"discovered via Google Places {date.today().isoformat()}", L["site"]]
        upsert_row(token, TAB, 1, L["company"], row)  # dedup on Company
        print(f"  {L['company']:32} {L['phone']:16} {L['city']}, {L['state']}")
    print(f"\n{len(leads)} unverified leads in Land Builders for {zip_code}. "
          f"Call to capture buy box, then --add to verify.")


def _demo():
    assert _city_state("123 Main St, Cartersville, GA 30120, USA") == ("Cartersville", "GA")
    assert _city_state("Acme Homes, 5 Oak Dr, Atlanta, GA 30301") == ("Atlanta", "GA")
    assert _city_state("no commas here") == ("", "")
    print("ok")


def main():
    ap = argparse.ArgumentParser(description="Capture/look up land builder buy boxes.")
    ap.add_argument("--add", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--price-for", help="Show offer-anchor $/acre for a market zip")
    ap.add_argument("--discover-builders", metavar="ZIP",
                    help="Find builder leads for a zip via Google Places")
    ap.add_argument("--demo", action="store_true", help="Run self-check")
    ap.add_argument("--market", help="Filter --list to a market zip")
    # buy-box fields
    ap.add_argument("--name"); ap.add_argument("--company")
    ap.add_argument("--state"); ap.add_argument("--city")
    ap.add_argument("--phone")
    ap.add_argument("--email"); ap.add_argument("--markets", help="comma-separated zips")
    ap.add_argument("--avg-acre", help="Avg comp $/acre in the builder's zip(s)")
    ap.add_argument("--price-per-acre", type=float)
    ap.add_argument("--price-per-lot")
    ap.add_argument("--min-acres", type=float); ap.add_argument("--max-acres", type=float)
    ap.add_argument("--volume", type=int, help="lots/month")
    ap.add_argument("--conditions"); ap.add_argument("--timeline"); ap.add_argument("--tier")
    ap.add_argument("--notes")
    ap.add_argument("--intake-portal", help="Land/lot submission URL")
    a = ap.parse_args()

    if a.demo:
        _demo()
    elif a.add:
        cmd_add(a)
    elif a.discover_builders:
        cmd_discover(a)
    elif a.price_for:
        cmd_price_for(a)
    elif a.list:
        cmd_list(a)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
