#!/usr/bin/env python3
"""
db_sync.py — Mirror Google Sheets tabs into olive.db.

Pulls three tabs:
  • Brokers List  (SPREADSHEET_ID 1VxOlof...  Brokers List!A:M)
  • Deal Sourcing (SPREADSHEET_ID 1VxOlof...  Deal Sourcing!A:T)
  • Meetings      (SHEET_ID       1PyPmgC...   first tab)

Each upsert is keyed on a UNIQUE column so re-running is safe and produces zero
duplicate rows. Only changed fields are updated.

Usage
-----
    python3 scripts/db_sync.py               # full sync
    python3 scripts/db_sync.py --table brokers   # one table
    python3 scripts/db_sync.py --table deals
    python3 scripts/db_sync.py --table meetings
"""

import argparse
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))

load_dotenv()

from db.connection import get_session, init_db
from db.schema import Broker, Deal, LandBuilder, LandDeal, LandMarket, LandSeller, Meeting

SPREADSHEET_ID    = "1VxOlof56s8GosrWkSctL-FMm7AoJKJ6YtM3GllMKVH4"
MEETINGS_SHEET_ID = "1PyPmgCAB92aPjPSAYqbDbC6iVKQ9gi3Ti9m3xXOqoYo"
LAND_SHEET_ID     = os.getenv("LAND_SHEET_ID", "")
SHEETS_BASE       = "https://sheets.googleapis.com/v4/spreadsheets"


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _read_tab(token: str, spreadsheet_id: str, tab_range: str) -> list[list[str]]:
    r = requests.get(
        f"{SHEETS_BASE}/{spreadsheet_id}/values/{tab_range}",
        headers=_auth_header(token),
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get("values", [])


def _cell(row: list, idx: int) -> str:
    return row[idx].strip() if len(row) > idx else ""


def _parse_float(v: str) -> float | None:
    if not v:
        return None
    try:
        return float(v.replace("$", "").replace(",", "").replace("%", "").strip())
    except ValueError:
        return None


def _parse_int(v: str) -> int | None:
    try:
        return int(_parse_float(v) or 0) or None
    except (TypeError, ValueError):
        return None


# ── Brokers ───────────────────────────────────────────────────────────────────
# Columns A:M (0-indexed):
# 0:brokerage 1:name 2:email 3:phone 4:markets 5:specialty 6:tier
# 7:buy_box_sent 8:deals_sent 9:last_contact 10:next_followup 11:status 12:notes

def sync_brokers(token: str, session) -> tuple[int, int]:
    rows = _read_tab(token, SPREADSHEET_ID, "Brokers List!A1:M2000")
    if not rows:
        return 0, 0
    inserted = updated = 0
    for row in rows[1:]:       # skip header
        email = _cell(row, 2).lower()
        name  = _cell(row, 1)
        if not email and not name:
            continue

        existing = (
            session.query(Broker).filter_by(email=email).first()
            if email else
            session.query(Broker).filter_by(name=name).first()
        )
        is_new = existing is None
        b = existing or Broker()

        b.brokerage     = _cell(row, 0)
        b.name          = name
        b.email         = email or None
        b.phone         = _cell(row, 3)
        b.markets_covered = _cell(row, 4)
        b.specialty     = _cell(row, 5)
        b.tier          = _cell(row, 6)
        b.buy_box_sent  = _cell(row, 7)
        b.deals_sent    = _parse_int(_cell(row, 8)) or 0
        b.last_contact  = _cell(row, 9)
        b.next_followup = _cell(row, 10)
        b.status        = _cell(row, 11)
        b.notes         = _cell(row, 12)

        if is_new:
            session.add(b)
            inserted += 1
        else:
            updated += 1

    session.commit()
    return inserted, updated


# ── Deals ────────────────────────────────────────────────────────────────────
# Columns A:T (0-indexed) as written by deal_search.py build_deal_row():
# 0:market 1:zip 2:property_name 3:address 4:units 5:asking_price
# 6:offer_price 7:price_per_unit 8:vintage 9:cap_rate 10:gpr 11:noi
# 12:platform 13:brokerage 14:broker_name 15:broker_email 16:broker_phone
# 17:status 18:date_found 19:last_updated 20:notes

def _find_broker(session, email: str, name: str, brokerage: str) -> Broker | None:
    if email:
        b = session.query(Broker).filter_by(email=email.lower()).first()
        if b:
            return b
    if name:
        b = session.query(Broker).filter_by(name=name).first()
        if b:
            return b
    if email or name:
        b = Broker(email=email.lower() or None, name=name, brokerage=brokerage)
        session.add(b)
        session.flush()
        return b
    return None


def sync_deals(token: str, session) -> tuple[int, int]:
    rows = _read_tab(token, SPREADSHEET_ID, "Deal Sourcing!A1:U2000")
    if not rows:
        return 0, 0
    inserted = updated = 0
    for row in rows[1:]:
        address = _cell(row, 3)
        if not address:
            continue

        broker = _find_broker(
            session,
            _cell(row, 15),
            _cell(row, 14),
            _cell(row, 13),
        )

        existing = session.query(Deal).filter_by(address=address).first()
        is_new   = existing is None
        d = existing or Deal(address=address)

        d.name           = _cell(row, 2)
        d.zip            = _cell(row, 1) or None
        d.broker_id      = broker.id if broker else None
        d.units          = _parse_int(_cell(row, 4))
        d.asking_price   = _parse_float(_cell(row, 5))
        d.offer_price    = _parse_float(_cell(row, 6))
        d.price_per_unit = _parse_float(_cell(row, 7))
        d.vintage        = _parse_int(_cell(row, 8))
        d.cap_rate       = _parse_float(_cell(row, 9))
        d.gpr            = _parse_float(_cell(row, 10))
        d.noi            = _parse_float(_cell(row, 11))
        d.status         = _cell(row, 17)
        d.date_found     = _cell(row, 18)
        d.last_updated   = _cell(row, 19)
        d.risks          = _cell(row, 20)

        if is_new:
            session.add(d)
            inserted += 1
        else:
            updated += 1

    session.commit()
    return inserted, updated


# ── Meetings ─────────────────────────────────────────────────────────────────
# Columns as written by fathom_sync.py parse_meeting_row():
# 0:date 1:type/title 2:participants 3:summary 4:action_items 5:""(unused)
# 6:source 7:fathom_link

def sync_meetings(token: str, session) -> tuple[int, int]:
    rows = _read_tab(token, MEETINGS_SHEET_ID, "A1:H2000")
    if not rows:
        return 0, 0
    inserted = updated = 0
    for row in rows[1:]:
        fathom_link = _cell(row, 7)
        if not fathom_link:
            continue

        existing = session.query(Meeting).filter_by(fathom_link=fathom_link).first()
        is_new   = existing is None
        m = existing or Meeting(fathom_link=fathom_link)

        m.date         = _cell(row, 0)
        m.type         = _cell(row, 1)
        m.participants = _cell(row, 2)
        m.summary      = _cell(row, 3)
        m.action_items = _cell(row, 4)

        if is_new:
            session.add(m)
            inserted += 1
        else:
            updated += 1

    session.commit()
    return inserted, updated


# ── Land Markets ─────────────────────────────────────────────────────────────
# Land Markets tab columns (0-indexed, per land_setup.TABS):
# 0:County 1:Zip 2:City 3:State 4:Total Parcels 5:Vacant Lots 6:Vacant OOS
# 7:Uniformity 8:Median Acres 9:Avg Land Value 10:Builders Active
# 11:Go/No-Go 12:Score 13:Notes 14:Date

def sync_land_markets(token: str, session) -> tuple[int, int]:
    if not LAND_SHEET_ID:
        print("  (land_markets skipped — LAND_SHEET_ID not set)")
        return 0, 0
    rows = _read_tab(token, LAND_SHEET_ID, "Land Markets!A1:O2000")
    if not rows:
        return 0, 0
    inserted = updated = 0
    for row in rows[1:]:
        county = _cell(row, 0)
        zip_   = _cell(row, 1)
        if not county or not zip_:
            continue
        existing = session.query(LandMarket).filter_by(county=county, zip=zip_).first()
        is_new = existing is None
        m = existing or LandMarket(county=county, zip=zip_)
        m.city           = _cell(row, 2)
        m.state          = _cell(row, 3)
        m.total_parcels  = _parse_int(_cell(row, 4))
        m.vacant_lots    = _parse_int(_cell(row, 5))
        m.vacant_oos     = _parse_int(_cell(row, 6))
        m.uniformity     = _parse_float(_cell(row, 7))
        m.median_acres   = _parse_float(_cell(row, 8))
        m.avg_land_value = _parse_float(_cell(row, 9))
        m.builders_active = _cell(row, 10)
        m.go_nogo        = _cell(row, 11)
        m.score          = _parse_float(_cell(row, 12))
        m.notes          = _cell(row, 13)
        m.date           = _cell(row, 14)
        if is_new:
            session.add(m)
            inserted += 1
        else:
            updated += 1
    session.commit()
    return inserted, updated


# ── Land Builders ─────────────────────────────────────────────────────────────
# Land Builders tab columns (0-indexed):
# 0:Name 1:Company 2:Phone 3:Email 4:Markets/Zips 5:Lot Size Min 6:Lot Size Max
# 7:Price Per Lot 8:Volume/Mo 9:Conditions 10:Close Timeline 11:Tier
# 12:Deals Done 13:Last Contact 14:Notes

def sync_land_builders(token: str, session) -> tuple[int, int]:
    if not LAND_SHEET_ID:
        print("  (land_builders skipped — LAND_SHEET_ID not set)")
        return 0, 0
    rows = _read_tab(token, LAND_SHEET_ID, "Land Builders!A1:O2000")
    if not rows:
        return 0, 0
    inserted = updated = 0
    for row in rows[1:]:
        name = _cell(row, 0)
        if not name:
            continue
        existing = (session.query(LandBuilder)
                    .filter(LandBuilder.name == name).first())
        is_new = existing is None
        b = existing or LandBuilder(name=name)
        b.company       = _cell(row, 1)
        b.phone         = _cell(row, 2)
        b.email         = _cell(row, 3) or None
        b.markets       = _cell(row, 4)
        b.lot_size_min  = _parse_float(_cell(row, 5))
        b.lot_size_max  = _parse_float(_cell(row, 6))
        price_str = _cell(row, 7)
        b.price_per_lot = _parse_float(price_str.replace("/ac", "")) if price_str else None
        b.volume_per_mo = _parse_int(_cell(row, 8))
        b.conditions    = _cell(row, 9)
        b.close_timeline = _cell(row, 10)
        b.tier          = _cell(row, 11)
        b.deals_done    = _parse_int(_cell(row, 12)) or 0
        b.last_contact  = _cell(row, 13)
        b.notes         = _cell(row, 14)
        if is_new:
            session.add(b)
            inserted += 1
        else:
            updated += 1
    session.commit()
    return inserted, updated


# ── Land Sellers ──────────────────────────────────────────────────────────────
# Land Sellers tab columns (0-indexed):
# 0:Parcel ID 1:Situs Address 2:Zip 3:Subdivision 4:Acres 5:Owner Name
# 6:Owner Mailing Address 7:Owner City 8:Owner State 9:Out-of-State
# 10:Est Land Value 11:Offer Price 12:Owner Phone 13:Builder Target
# 14:Channel 15:Call Status 16:Last Call 17:Callback Date 18:Outcome 19:Notes
# 20:Owner Zip

def sync_land_sellers(token: str, session) -> tuple[int, int]:
    if not LAND_SHEET_ID:
        print("  (land_sellers skipped — LAND_SHEET_ID not set)")
        return 0, 0
    rows = _read_tab(token, LAND_SHEET_ID, "Land Sellers!A1:U2000")
    if not rows:
        return 0, 0
    inserted = updated = 0
    for row in rows[1:]:
        parcel_id = _cell(row, 0)
        if not parcel_id:
            continue
        existing = session.query(LandSeller).filter_by(parcel_id=parcel_id).first()
        is_new = existing is None
        s = existing or LandSeller(parcel_id=parcel_id)
        s.situs_address  = _cell(row, 1)
        s.zip            = _cell(row, 2)
        s.subdivision    = _cell(row, 3)
        s.acres          = _parse_float(_cell(row, 4))
        s.owner_name     = _cell(row, 5)
        s.owner_addr     = _cell(row, 6)
        s.owner_city     = _cell(row, 7)
        s.owner_state    = _cell(row, 8)
        s.out_of_state   = _cell(row, 9).upper() == "Y"
        s.est_land_value = _parse_float(_cell(row, 10))
        s.offer_price    = _parse_float(_cell(row, 11))
        s.owner_phone    = _cell(row, 12)
        s.builder_target = _cell(row, 13)
        s.channel        = _cell(row, 14)
        s.call_status    = _cell(row, 15)
        s.last_call      = _cell(row, 16)
        s.callback_date  = _cell(row, 17)
        s.outcome        = _cell(row, 18)
        s.notes          = _cell(row, 19)
        s.owner_zip      = _cell(row, 20)
        if is_new:
            session.add(s)
            inserted += 1
        else:
            updated += 1
    session.commit()
    return inserted, updated


# ── Land Deals ────────────────────────────────────────────────────────────────
# Land Deals tab columns (0-indexed):
# 0:Parcel ID 1:Situs Address 2:Seller 3:Builder 4:Contract Price
# 5:Assignment Price 6:Spread 7:Status 8:Feasibility Deadline
# 9:Deal-Killer Check 10:Title Company 11:Close Date 12:Profit
# 13:Referral Sent 14:Neighbors Called 15:Notes

def sync_land_deals(token: str, session) -> tuple[int, int]:
    if not LAND_SHEET_ID:
        print("  (land_deals skipped — LAND_SHEET_ID not set)")
        return 0, 0
    rows = _read_tab(token, LAND_SHEET_ID, "Land Deals!A1:P2000")
    if not rows:
        return 0, 0
    inserted = updated = 0
    for row in rows[1:]:
        parcel_id = _cell(row, 0)
        if not parcel_id:
            continue
        existing = session.query(LandDeal).filter_by(parcel_id=parcel_id).first()
        is_new = existing is None
        d = existing or LandDeal(parcel_id=parcel_id)
        d.situs_address    = _cell(row, 1)
        d.contract_price   = _parse_float(_cell(row, 4))
        d.assignment_price = _parse_float(_cell(row, 5))
        d.spread           = _parse_float(_cell(row, 6))
        d.status           = _cell(row, 7)
        d.feasibility_deadline = _cell(row, 8)
        d.deal_killer_check = _cell(row, 9)
        d.title_company    = _cell(row, 10)
        d.close_date       = _cell(row, 11)
        d.profit           = _parse_float(_cell(row, 12))
        d.referral_sent    = _cell(row, 13).upper() == "Y"
        d.neighbors_called = _cell(row, 14).upper() in ("Y", "PENDING")
        d.notes            = _cell(row, 15)
        # FK: resolve seller by parcel_id
        seller = session.query(LandSeller).filter_by(parcel_id=parcel_id).first()
        if seller:
            d.seller_id = seller.id
        # FK: resolve builder by name (col 3)
        builder_name = _cell(row, 3)
        if builder_name:
            builder = session.query(LandBuilder).filter_by(name=builder_name).first()
            if builder:
                d.builder_id = builder.id
        if is_new:
            session.add(d)
            inserted += 1
        else:
            updated += 1
    session.commit()
    return inserted, updated


# ── Main ──────────────────────────────────────────────────────────────────────

SYNC_FUNCS = {
    "brokers":       sync_brokers,
    "deals":         sync_deals,
    "meetings":      sync_meetings,
    "land_markets":  sync_land_markets,
    "land_builders": sync_land_builders,
    "land_sellers":  sync_land_sellers,
    "land_deals":    sync_land_deals,
}


def run(session=None):
    from gws_auth import get_token
    token = get_token()
    own_session = session is None
    if own_session:
        session = get_session()
    try:
        for name, fn in SYNC_FUNCS.items():
            i, u = fn(token, session)
            print(f"    {name:16} {i} inserted, {u} updated")
    finally:
        if own_session:
            session.close()


def main():
    parser = argparse.ArgumentParser(description="Sync Google Sheets → olive.db")
    parser.add_argument("--table", choices=sorted(SYNC_FUNCS),
                        help="Sync only one table")
    args = parser.parse_args()

    init_db()

    from gws_auth import get_token
    token   = get_token()
    session = get_session()

    try:
        tables = [args.table] if args.table else list(SYNC_FUNCS)
        for tbl in tables:
            i, u = SYNC_FUNCS[tbl](token, session)
            print(f"  {tbl}: {i} inserted, {u} updated")
    finally:
        session.close()

    print("Sync complete.")


if __name__ == "__main__":
    main()
