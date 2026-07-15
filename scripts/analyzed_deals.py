#!/usr/bin/env python3
"""
Olive Tree Investments — Analyzed-Deals Cross-Check

Shared helper: reads the "Olive Tree Investments - Deals" Drive folder (one
subfolder per property we've already worked up) and matches candidate listings
against it, so deal screens don't re-surface deals we've already analyzed.

Deal folders are named "<address>, <city>, <ST> <zip>" (commas inconsistent);
broker/Crexi listings are named "<property name>, <city>, <ST>". We can't rely
on address, so we match on (city, state) and flag for human confirmation.

    from analyzed_deals import load_analyzed, match_analyzed
    analyzed = load_analyzed(token)          # list of dicts
    hit = match_analyzed("Chattanooga, TN", "Windgate Apartments", analyzed)
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from deal_index import DEALS_FOLDER_ID, list_subfolders

_SKIP = ("olive tree investments -", "- test", "test)")
STATES = {"GA", "TN", "AL", "SC", "NC", "FL", "KY"}


def street_key(text):
    """'542 Ashe Ave, ...' -> '542 ashe'. '' if no leading street number."""
    m = re.match(r"\s*(\d{2,6})\s+([A-Za-z]+)", text or "")
    return f"{m.group(1)} {m.group(2).lower()}" if m else ""


def parse_location(folder_name):
    """'542 Ashe Ave, New Johnsonville, TN 37134' -> ('new johnsonville','TN','37134')."""
    zip_m = re.search(r"\b(\d{5})\b", folder_name)
    zip_code = zip_m.group(1) if zip_m else ""
    # the state is the LAST known-state token (skips "SE"/"SW"/"St" false hits)
    st_m = None
    for m in re.finditer(r"\b([A-Z]{2})\b", folder_name):
        if m.group(1) in STATES:
            st_m = m
    state = st_m.group(1) if st_m else ""
    city = ""
    if state:
        # text just before the state token, last comma-or-space chunk
        pre = folder_name[:st_m.start()].rstrip(" ,")
        parts = [p.strip() for p in pre.split(",") if p.strip()]
        if len(parts) >= 2:
            city = parts[-1]
        elif parts:  # no comma before state, e.g. "550 Harding Place Nashville"
            city = parts[-1].split()[-1]
    return city.lower(), state, zip_code


def load_analyzed(token):
    out = []
    for f in list_subfolders(token, DEALS_FOLDER_ID):
        name = f.get("name", "")
        if any(s in name.lower() for s in _SKIP):
            continue
        city, state, zip_code = parse_location(name)
        out.append({"folder": name, "id": f.get("id"), "city": city,
                    "state": state, "zip": zip_code, "street": street_key(name)})
    return out


def match_analyzed(listing_city_state, listing_name, analyzed, listing_zip=""):
    """Match a candidate listing against analyzed deals.

    Returns (deal_dict, strength):
      'address' — same street number+name (strong: it IS the analyzed deal)
      'city'    — same city+state only (weak: verify; a zip holds many properties)
    or (None, None). Address match wins over city; a same-city hit is only a
    'verify' nudge, never an assertion — one zip can hold many properties.
    """
    m = re.match(r"\s*([A-Za-z .'-]+),\s*([A-Z]{2})", listing_city_state or "")
    if not m:
        return None, None
    city, state = m.group(1).strip().lower(), m.group(2)
    lstreet = street_key(listing_name)
    city_hit = None
    for a in analyzed:
        if a["state"] != state:
            continue
        if lstreet and a["street"] and lstreet == a["street"]:
            return a, "address"
        if a["city"] and a["city"] == city:
            city_hit = a
    return (city_hit, "city") if city_hit else (None, None)


if __name__ == "__main__":
    from gws_auth import get_token
    deals = load_analyzed(get_token())
    print(f"{len(deals)} analyzed deal folders:")
    for d in deals:
        print(f"  {d['city']}, {d['state']} {d['zip']}  ←  {d['folder']}")
