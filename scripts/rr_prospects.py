#!/usr/bin/env python3
"""
Olive Tree — Rank & Rent Prospects (the /rr_prospects engine)

Pulls local operator leads (tree service, towing, concrete, etc.) via Google
Places Text Search — the same call-sheet targets you'll cold-call to rent a
ranked site to. Mirrors the land_builders.py --discover-builders pattern.

Usage:
  # Pull operators for a niche + city into olive.db
  python3 scripts/rr_prospects.py --pull "tree service" "Cartersville, GA"

  # Call sheet, best-first, with a pitch script up top
  python3 scripts/rr_prospects.py --list
  python3 scripts/rr_prospects.py --list --niche "tree service" --city "Cartersville, GA"

  # Log an outcome
  python3 scripts/rr_prospects.py --status 3 called --note "left voicemail"
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from sqlalchemy import text

from db.connection import engine  # noqa: E402

load_dotenv()

STATUSES = {"new", "called", "interested", "no", "callback", "signed"}

PITCH = """I own {niche} websites in {city} that generate exclusive phone
leads. Not a directory -- the calls go only to you. First 10 calls free so
you can judge quality, then flat $500/mo or per-call. Want me to point it
at your phone this week?"""

_DDL = """
CREATE TABLE IF NOT EXISTS rr_prospects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    niche TEXT NOT NULL,
    city TEXT NOT NULL,
    name TEXT NOT NULL,
    phone TEXT,
    website TEXT,
    rating REAL,
    review_count INTEGER,
    status TEXT NOT NULL DEFAULT 'new',
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(name, city)
)
"""


def _ensure_table():
    with engine.begin() as conn:
        conn.execute(text(_DDL))


def _places_search(query, key):
    """Google Places (New) Text Search — same pattern as land_builders.py."""
    import requests
    resp = requests.post(
        "https://places.googleapis.com/v1/places:searchText",
        headers={
            "X-Goog-Api-Key": key,
            "X-Goog-FieldMask": ("places.displayName,places.nationalPhoneNumber,"
                                 "places.websiteUri,places.rating,places.userRatingCount"),
        },
        json={"textQuery": query},
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json().get("places", [])


def cmd_pull(a):
    niche, city = a.pull
    key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not key:
        sys.exit("Set GOOGLE_MAPS_API_KEY in .env (Places API New).")
    _ensure_table()

    places = _places_search(f"{niche} in {city}", key)
    if not places:
        print(f"No results for '{niche}' in {city}.")
        return

    now = datetime.now().isoformat(timespec="seconds")
    added = updated = 0
    with engine.begin() as conn:
        for p in places:
            name = (p.get("displayName") or {}).get("text", "")
            if not name:
                continue
            existing = conn.execute(
                text("SELECT id FROM rr_prospects WHERE name=:n AND city=:c"),
                {"n": name, "c": city},
            ).first()
            row = {
                "niche": niche, "city": city, "name": name,
                "phone": p.get("nationalPhoneNumber", ""),
                "website": p.get("websiteUri", ""),
                "rating": p.get("rating"),
                "review_count": p.get("userRatingCount"),
                "now": now,
            }
            if existing:
                conn.execute(text("""
                    UPDATE rr_prospects SET phone=:phone, website=:website,
                        rating=:rating, review_count=:review_count, updated_at=:now
                    WHERE id=:id
                """), {**row, "id": existing.id})
                updated += 1
            else:
                conn.execute(text("""
                    INSERT INTO rr_prospects
                        (niche, city, name, phone, website, rating, review_count,
                         status, notes, created_at, updated_at)
                    VALUES (:niche, :city, :name, :phone, :website, :rating,
                            :review_count, 'new', '', :now, :now)
                """), row)
                added += 1
    print(f"'{niche}' in {city}: {added} added, {updated} updated ({len(places)} pulled).")


def _score(row):
    """Best-first heuristic: has a phone, rating 3.5-4.7, <150 reviews.
    Big established shops (500+ reviews, near-5.0) need leads less than
    hungry mid-tier operators -- they're the easier sell and the better renter."""
    has_phone = bool(row.phone)
    rating = row.rating or 0
    reviews = row.review_count or 0
    sweet_spot = has_phone and 3.5 <= rating <= 4.7 and reviews < 150
    return (not has_phone, not sweet_spot, -(rating or 0))


def cmd_list(a):
    _ensure_table()
    with engine.begin() as conn:
        q = "SELECT * FROM rr_prospects WHERE 1=1"
        params = {}
        if a.niche:
            q += " AND niche=:niche"
            params["niche"] = a.niche
        if a.city:
            q += " AND city=:city"
            params["city"] = a.city
        rows = conn.execute(text(q), params).all()

    if not rows:
        print("No prospects yet. Run --pull \"<niche>\" \"<city>\" first.")
        return

    rows = sorted(rows, key=_score)
    niche = a.niche or rows[0].niche
    city = a.city or rows[0].city
    print(f"\n  PITCH SCRIPT (personalize per call):")
    print(f"  " + PITCH.format(niche=niche, city=city).replace("\n", "\n  "))
    print(f"\n  Call sheet — {niche} — {city} — {len(rows)} prospect(s), best-first\n")
    print(f"  {'ID':<4} {'Name':<32} {'Phone':<16} {'Rating':<8} {'Reviews':<8} {'Status':<12} Notes")
    print("  " + "-" * 100)
    for r in rows:
        rating = f"{r.rating:.1f}" if r.rating else "-"
        print(f"  {r.id:<4} {r.name[:32]:<32} {(r.phone or '-'):<16} "
              f"{rating:<8} {(r.review_count or '-'):<8} {r.status:<12} {r.notes or ''}")


def cmd_status(a):
    if a.status not in STATUSES:
        sys.exit(f"status must be one of: {', '.join(sorted(STATUSES))}")
    _ensure_table()
    now = datetime.now().isoformat(timespec="seconds")
    with engine.begin() as conn:
        existing = conn.execute(text("SELECT id, notes FROM rr_prospects WHERE id=:id"),
                                 {"id": a.status_id}).first()
        if not existing:
            sys.exit(f"No prospect with id={a.status_id}")
        notes = existing.notes or ""
        if a.note:
            notes = (notes + " | " + a.note).strip(" |")
        conn.execute(text("UPDATE rr_prospects SET status=:s, notes=:n, updated_at=:now WHERE id=:id"),
                     {"s": a.status, "n": notes, "now": now, "id": a.status_id})
    print(f"  id={a.status_id} -> {a.status}")


def main():
    ap = argparse.ArgumentParser(description="Rank & Rent operator prospect list.")
    ap.add_argument("--pull", nargs=2, metavar=("NICHE", "CITY"),
                    help='e.g. --pull "tree service" "Cartersville, GA"')
    ap.add_argument("--list", action="store_true", help="Print the call sheet")
    ap.add_argument("--niche", help="Filter --list to a niche")
    ap.add_argument("--city", help="Filter --list to a city")
    ap.add_argument("--status", dest="status_id", type=int, metavar="ID",
                    help="Prospect id to update")
    ap.add_argument("outcome", nargs="?", help=argparse.SUPPRESS)  # positional status value
    ap.add_argument("--note", help="Note to append (use with --status)")
    a = ap.parse_args()
    a.status = a.outcome  # `--status <id> <outcome>` -> outcome is positional

    if a.pull:
        cmd_pull(a)
    elif a.status_id:
        cmd_status(a)
    elif a.list:
        cmd_list(a)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
