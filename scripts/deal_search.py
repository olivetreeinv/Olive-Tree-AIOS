#!/usr/bin/env python3
"""
Olive Tree Investments — Deal Search
Scans Crexi + LoopNet alert emails and FMLS API for buy-box listings.
Logs results to the Deal Sourcing spreadsheet.

Usage:
  python3 scripts/deal_search.py                  # Scan last 7 days
  python3 scripts/deal_search.py --days 30        # Scan last 30 days
  python3 scripts/deal_search.py --dry-run        # Parse/print without writing to sheet
  python3 scripts/deal_search.py --source crexi   # One source only (crexi/loopnet/fmls)
"""

import argparse
import base64
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from gws_auth import get_token

load_dotenv()

# ─────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────

SPREADSHEET_ID = "1VxOlof56s8GosrWkSctL-FMm7AoJKJ6YtM3GllMKVH4"
SHEETS_BASE    = "https://sheets.googleapis.com/v4/spreadsheets"
GMAIL_BASE     = "https://gmail.googleapis.com/gmail/v1/users/me"
TODAY          = date.today().strftime("%m/%d/%Y")

FMLS_API_TOKEN  = os.getenv("FMLS_API_TOKEN", "")
FMLS_DATASET_ID = os.getenv("FMLS_DATASET_ID", "fmls")
FMLS_API_BASE   = f"https://api.bridgedataoutput.com/api/v2/OData/{FMLS_DATASET_ID}"

BUY_BOX = {
    "30341": "Chamblee, GA",
    "30080": "Smyrna, GA",
    "30005": "Alpharetta, GA",
    "37207": "North Nashville, TN",
    "37115": "Madison, TN",
    "37408": "Chattanooga Southside, TN",
    "37087": "Lebanon, TN",
    "35801": "Huntsville Core, AL",
    "35205": "Birmingham Urban, AL",
    "35806": "Huntsville Growth, AL",
}

GA_ZIPS = {z for z, m in BUY_BOX.items() if "GA" in m}

AVAILABILITY_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}
SOLD_SIGNALS = [
    "no longer available", "listing has been removed", "listing not found",
    "listing removed", "property is no longer", "expired listing",
    "this listing has expired", "page not found", "listing is no longer",
]

MIN_UNITS = 15
MAX_UNITS = 50
# ponytail: "close to buy box" = unit count near-miss inside a buy-box zip.
# Zip-adjacency (e.g. a submarket bordering Chamblee) needs a geo dataset we
# don't have yet — add if near-zip misses turn out to matter.
NEAR_MIN  = 10
NEAR_MAX  = 65


def classify_units(units):
    """Return 'fit' | 'near' | 'off' | None (unknown) for a unit count."""
    if units is None:
        return None
    if MIN_UNITS <= units <= MAX_UNITS:
        return "fit"
    if NEAR_MIN <= units <= NEAR_MAX:
        return "near"
    return "off"

EMAIL_QUERIES = {
    "crexi":   'from:crexi.com subject:(listing OR alert OR "new properties" OR "saved search")',
    "loopnet": 'from:loopnet.com subject:(listing OR alert OR "new properties" OR "saved search")',
}

# ─────────────────────────────────────────────
# Auth
# ─────────────────────────────────────────────

def _auth(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

# ─────────────────────────────────────────────
# Gmail helpers
# ─────────────────────────────────────────────

def search_messages(token, query, days=7):
    after = (datetime.now() - timedelta(days=days)).strftime("%Y/%m/%d")
    r = requests.get(
        f"{GMAIL_BASE}/messages",
        headers=_auth(token),
        params={"q": f"{query} after:{after}", "maxResults": 100},
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get("messages", [])


def get_message(token, msg_id):
    r = requests.get(
        f"{GMAIL_BASE}/messages/{msg_id}",
        headers=_auth(token),
        params={"format": "full"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def extract_body(message):
    parts = message.get("payload", {}).get("parts", [])
    plain, html = "", ""

    def walk(parts_list):
        nonlocal plain, html
        for part in parts_list:
            mime = part.get("mimeType", "")
            data = part.get("body", {}).get("data", "")
            if data:
                decoded = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
                if mime == "text/plain":
                    plain += decoded
                elif mime == "text/html":
                    html += decoded
            if "parts" in part:
                walk(part["parts"])

    payload = message.get("payload", {})
    if not parts:
        data = payload.get("body", {}).get("data", "")
        if data:
            decoded = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
            if payload.get("mimeType") == "text/html":
                html = decoded
            else:
                plain = decoded
    else:
        walk(parts)

    return plain, html


def html_to_text(html):
    return BeautifulSoup(html, "html.parser").get_text(separator=" ", strip=True)

# ─────────────────────────────────────────────
# Availability check
# ─────────────────────────────────────────────

def _find_listing_url(text, source):
    if source == "crexi":
        m = re.search(r'https?://(?:www\.)?crexi\.com/properties/[\w-]+(?:/[\w-]+)?', text)
    else:
        m = re.search(r'https?://(?:www\.)?loopnet\.com/(?:[Ll]isting|listing)/[\w/-]+', text)
    return m.group(0).rstrip("/") if m else ""


def check_availability(url, timeout=8):
    if not url:
        return "unverified"
    try:
        with requests.get(url, headers=AVAILABILITY_HEADERS, timeout=timeout, stream=True) as r:
            if r.status_code == 404:
                return "unavailable"
            if r.status_code not in (200, 301, 302, 303):
                return "unverified"
            content = bytearray()
            for chunk in r.iter_content(chunk_size=1024):
                content += chunk
                if len(content) >= 5000:
                    break
        if any(sig in content.decode("utf-8", errors="replace").lower() for sig in SOLD_SIGNALS):
            return "unavailable"
        return "available"
    except requests.exceptions.Timeout:
        return "unverified"
    except Exception:
        return "unverified"


def check_all_availability(listings, workers=5):
    def _check(listing):
        return listing, check_availability(listing.get("listing_url", ""))

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for listing, status in ex.map(_check, listings):
            listing["availability"] = status

# ─────────────────────────────────────────────
# Email listing parser
# ─────────────────────────────────────────────

def _find_price(text):
    for p in [r'\$[\d,]+(?:\.\d+)?[Mm](?:illion)?', r'\$[\d,]{4,}']:
        m = re.search(p, text)
        if m:
            raw = m.group(0).replace(",", "").replace("$", "")
            if "m" in raw.lower():
                return f"${int(float(re.sub(r'[mM].*', '', raw)) * 1_000_000):,}"
            return f"${int(float(raw)):,}"
    return ""


def _find_units(text):
    for p in [
        r'(\d+)\s*(?:-unit|-Unit|unit|Unit|units|Units)',
        r'(\d+)\s*(?:apartments?|apt)',
        r'[Uu]nits?[:\s]+(\d+)',
        r'(\d+)\s*[Uu]nit\b',
    ]:
        m = re.search(p, text)
        if m:
            return int(m.group(1))
    return None


def _find_zip(text):
    zips = re.findall(r'\b(\d{5})\b', text)
    for z in zips:
        if z in BUY_BOX:
            return z
    return zips[0] if zips else ""


def _find_address(text):
    m = re.search(
        r'\d+\s+[A-Za-z][A-Za-z0-9\s]{3,40}'
        r'(?:St|Ave|Blvd|Dr|Rd|Ln|Way|Ct|Pl|Pkwy|Hwy|Circle|Trail)\b'
        r'[^,\n]*(?:,\s*[A-Za-z\s]+,\s*[A-Z]{2}\s*\d{5})?',
        text,
    )
    return m.group(0).strip() if m else ""


def _find_broker_info(text, source):
    name, email, phone, brokerage = "", "", "", ""

    em = re.search(r'[\w.+-]+@[\w-]+\.\w+', text)
    if em:
        raw = em.group(0)
        if not any(skip in raw for skip in ["crexi.com", "loopnet.com", "noreply", "no-reply"]):
            email = raw

    ph = re.search(r'[\(]?\d{3}[\)\-.\s]?\d{3}[\-.\s]\d{4}', text)
    if ph:
        phone = ph.group(0).strip()

    for p in [
        r'[Ll]isted\s+[Bb]y[:\s]+([A-Z][a-z]+(?:\s[A-Z][a-z]+)+)',
        r'[Cc]ontact[:\s]+([A-Z][a-z]+(?:\s[A-Z][a-z]+)+)',
        r'[Aa]gent[:\s]+([A-Z][a-z]+(?:\s[A-Z][a-z]+)+)',
        r'[Bb]roker[:\s]+([A-Z][a-z]+(?:\s[A-Z][a-z]+)+)',
        r'[Rr]ep(?:resented by)?[:\s]+([A-Z][a-z]+(?:\s[A-Z][a-z]+)+)',
    ]:
        m = re.search(p, text)
        if m:
            name = m.group(1).strip()
            break

    known_brokerages = [
        "Marcus & Millichap", "CBRE", "JLL", "Cushman & Wakefield", "SVN",
        "Bull Realty", "Colliers", "Northmarq", "Walker & Dunlop",
        "Berkshire Hathaway", "BHHS", "Cosgrove", "Mathews", "GREA",
        "Watts Realty", "PWA Properties", "Skyline", "Crexi", "CoStar",
        "Kidder Mathews", "Avison Young", "NAI", "Lee & Associates",
    ]
    tl = text.lower()
    for b in known_brokerages:
        if b.lower() in tl:
            brokerage = b
            break
    if not brokerage:
        bm = re.search(r'(?:[Bb]rokerage|[Ff]irm|[Cc]ompany)[:\s]+([A-Z][A-Za-z\s&,\.]+?)(?:\n|<|\|)', text)
        if bm:
            brokerage = bm.group(1).strip()

    return name, email, phone, brokerage


def parse_email_listings(text, source):
    listings = []
    blocks = re.split(
        r'(?:View Listing|View Property|See More|See Details|Learn More)\s*\n',
        text, flags=re.IGNORECASE,
    )
    if len(blocks) < 2:
        blocks = [text]

    for block in blocks:
        if len(block.strip()) < 50:
            continue

        units    = _find_units(block)
        price    = _find_price(block)
        address  = _find_address(block)
        zip_code = _find_zip(block)
        broker_name, broker_email, broker_phone, brokerage = _find_broker_info(block, source)

        if not address and not zip_code:
            continue

        prop_name = ""
        lines = [l.strip() for l in block.split("\n") if l.strip()]
        if lines:
            first = lines[0]
            if len(first) < 80 and not first.startswith("$") and not re.match(r'^\d', first):
                prop_name = first

        listings.append({
            "source":        source,
            "property_name": prop_name,
            "address":       address,
            "zip":           zip_code,
            "market":        BUY_BOX.get(zip_code, ""),
            "units":         units,
            "price":         price,
            "brokerage":     brokerage,
            "broker_name":   broker_name,
            "broker_email":  broker_email,
            "broker_phone":  broker_phone,
            "in_buy_box":    zip_code in BUY_BOX,
            "unit_fit":      classify_units(units),
            "listing_url":   _find_listing_url(block, source),
            "availability":  "unverified",
        })

    return listings

# ─────────────────────────────────────────────
# FMLS API source
# ─────────────────────────────────────────────

def fetch_fmls_listings():
    if not FMLS_API_TOKEN:
        print("FMLS: FMLS_API_TOKEN not set — skipping. Add to .env to enable.")
        return []

    headers = {"Authorization": f"Bearer {FMLS_API_TOKEN}"}
    zip_list = ",".join(f"'{z}'" for z in sorted(GA_ZIPS))
    params = {
        "$filter": (
            f"PropertyType eq 'Residential Income'"
            f" and StandardStatus eq 'Active'"
            f" and PostalCode in ({zip_list})"
        ),
        "$select": ",".join([
            "ListingKey", "UnparsedAddress", "PostalCode", "ListPrice",
            "NumberOfUnitsTotal", "YearBuilt", "ListAgentFullName", "ListAgentEmail",
            "ListAgentDirectPhone", "ListOfficeName", "VirtualTourURLUnbranded",
            "MajorChangeTimestamp",
        ]),
        "$orderby": "MajorChangeTimestamp desc",
        "$top": 200,
    }
    try:
        r = requests.get(
            f"{FMLS_API_BASE}/Property",
            headers=headers,
            params=params,
            timeout=30,
        )
        if r.status_code == 401:
            print("FMLS: Unauthorized — check FMLS_API_TOKEN in .env")
            return []
        r.raise_for_status()
        props = r.json().get("value", [])
        listings = [l for p in props if (l := _fmls_to_listing(p))]
        print(f"  FMLS: {len(props)} active listing(s) in GA buy-box zips, {len(listings)} in unit range")
        return listings
    except requests.exceptions.RequestException as e:
        print(f"  FMLS: error — {e}")
        return []


def _fmls_to_listing(prop):
    raw_units = prop.get("NumberOfUnitsTotal")
    if not raw_units:
        return None
    units    = int(raw_units)
    price    = prop.get("ListPrice", 0)
    zip_code = str(prop.get("PostalCode", "")).split("-")[0]  # strip +4

    return {
        "source":        "fmls",
        "property_name": prop.get("UnparsedAddress", "")[:60],
        "address":       prop.get("UnparsedAddress", ""),
        "zip":           zip_code,
        "market":        BUY_BOX.get(zip_code, ""),
        "units":         units,
        "price":         f"${int(price):,}" if price else "",
        "brokerage":     prop.get("ListOfficeName", ""),
        "broker_name":   prop.get("ListAgentFullName", ""),
        "broker_email":  prop.get("ListAgentEmail", ""),
        "broker_phone":  prop.get("ListAgentDirectPhone", ""),
        "in_buy_box":    zip_code in BUY_BOX,
        "unit_fit":      classify_units(units),
        "listing_url":   prop.get("VirtualTourURLUnbranded", ""),
        "availability":  "available",  # FMLS Active = available
    }

# ─────────────────────────────────────────────
# Sheets helpers
# ─────────────────────────────────────────────

def _read_sheet(token, sheet_name, range_="A1:Z500"):
    r = requests.get(
        f"{SHEETS_BASE}/{SPREADSHEET_ID}/values/{sheet_name}!{range_}",
        headers=_auth(token),
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get("values", [])


def _append_rows(token, sheet_name, rows):
    if not rows:
        return
    r = requests.post(
        f"{SHEETS_BASE}/{SPREADSHEET_ID}/values/{sheet_name}!A1:append",
        headers=_auth(token),
        params={"valueInputOption": "USER_ENTERED", "insertDataOption": "INSERT_ROWS"},
        json={"values": rows, "majorDimension": "ROWS"},
        timeout=30,
    )
    r.raise_for_status()


def get_existing_deals(token):
    rows = _read_sheet(token, "Deal Sourcing")
    existing = set()
    for row in rows[1:]:
        addr  = row[3].strip().lower() if len(row) > 3 else ""
        pname = row[2].strip().lower() if len(row) > 2 else ""
        if addr:  existing.add(addr)
        if pname: existing.add(pname)
    return existing


def is_duplicate(listing, existing):
    return (
        listing["address"].lower() in existing
        or (listing["property_name"] and listing["property_name"].lower() in existing)
    )


def build_deal_row(listing):
    price_per_unit = ""
    if listing["units"] and listing["price"]:
        try:
            raw = int(listing["price"].replace("$", "").replace(",", ""))
            price_per_unit = f"${raw // listing['units']:,}"
        except (ValueError, TypeError, ZeroDivisionError):
            pass

    notes = []
    if not listing["in_buy_box"]:
        notes.append(f"⚠️ Outside buy box (zip {listing['zip']})")
    if listing["unit_fit"] == "near":
        notes.append(f"🔶 Unit count {listing['units']} near 15–50 range — worth a broker call")
    elif listing["unit_fit"] == "off":
        notes.append(f"⚠️ Unit count {listing['units']} outside 15–50 range")
    if listing.get("availability") == "unverified":
        notes.append("❓ Availability unverified")

    if listing["in_buy_box"] and listing["unit_fit"] in ("fit", None):
        stage = "New"
    elif listing["in_buy_box"] and listing["unit_fit"] == "near":
        stage = "Near — Review"
    else:
        stage = "Pass"

    return [
        listing["market"] or listing["zip"],
        listing["zip"],
        listing["property_name"],
        listing["address"],
        str(listing["units"]) if listing["units"] else "",
        listing["price"],
        "",           # Offer Price
        price_per_unit,
        "",           # Vintage
        "",           # Cap Rate
        "",           # Gross Rent (Annual)
        "",           # NOI
        listing["source"].upper(),
        listing["brokerage"],
        listing["broker_name"],
        listing["broker_email"],
        listing["broker_phone"],
        stage,
        TODAY,        # Date Found
        TODAY,        # Last Updated
        " | ".join(notes),
    ]

# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def run(days=7, dry_run=False, source=None):
    prefix = "[DRY RUN] " if dry_run else ""
    sources = [source] if source else ["crexi", "loopnet", "fmls"]
    print(f"{prefix}Deal Search — {TODAY}")
    print(f"Sources: {', '.join(sources).upper()}  |  Email window: {days} days\n")

    all_listings = []

    # Email sources (Crexi + LoopNet)
    email_sources = [s for s in sources if s in ("crexi", "loopnet")]
    if email_sources:
        token = get_token()
        print("Loading existing deals for deduplication...")
        existing_deals = get_existing_deals(token)
        print(f"  {len(existing_deals)} existing deal(s) on record\n")

        for src in email_sources:
            query = EMAIL_QUERIES[src]
            messages = search_messages(token, query, days=days)
            print(f"{src.upper()}: {len(messages)} alert email(s) found")

            def fetch_and_parse(msg_meta, _src=src):
                msg = get_message(token, msg_meta["id"])
                plain, html = extract_body(msg)
                text = html_to_text(html) if html else plain
                return _src, parse_email_listings(text, _src)

            with ThreadPoolExecutor(max_workers=5) as ex:
                futures = {ex.submit(fetch_and_parse, m): m for m in messages}
                for future in as_completed(futures):
                    try:
                        _src, listings = future.result()
                        print(f"  → {len(listings)} listing(s) parsed")
                        all_listings.extend(listings)
                    except Exception as e:
                        print(f"  ⚠️  Skipped one email (parse error): {e}")
    else:
        token = get_token()
        existing_deals = get_existing_deals(token)

    # FMLS API
    if "fmls" in sources:
        print("\nFMLS: querying active MF listings in GA buy-box zips...")
        fmls_listings = fetch_fmls_listings()
        print(f"  {len(fmls_listings)} FMLS listing(s) retrieved")
        all_listings.extend(fmls_listings)

    if not all_listings:
        print("\nNo listings found.")
        if "crexi" in sources or "loopnet" in sources:
            print("Tip: verify saved searches are set up on Crexi/LoopNet and alerts are arriving in Gmail.")
        return

    print(f"\nTotal listings: {len(all_listings)}")

    # Availability check (email sources only — FMLS Active = available)
    email_listings = [l for l in all_listings if l["source"] in ("crexi", "loopnet")]
    has_urls = sum(1 for l in email_listings if l.get("listing_url"))
    if has_urls:
        print(f"\nChecking availability ({has_urls}/{len(email_listings)} have URLs)...")
        check_all_availability(email_listings)
        unavailable = [l for l in email_listings if l["availability"] == "unavailable"]
        for l in unavailable:
            print(f"  ❌ Unavailable — skipping: {l['property_name'] or l['address']}")
        all_listings = [l for l in all_listings if l["availability"] != "unavailable"]

    # Deduplicate + categorize
    new_deals, skipped = [], []
    for listing in all_listings:
        if is_duplicate(listing, existing_deals):
            skipped.append(listing)
        else:
            new_deals.append(listing)

    inbox  = [l for l in new_deals if l["in_buy_box"] and l["unit_fit"] in ("fit", None)]
    near   = [l for l in new_deals if l["in_buy_box"] and l["unit_fit"] == "near"]
    outbox = [l for l in new_deals if not l["in_buy_box"] or l["unit_fit"] == "off"]

    print(f"\n{'='*50}")
    print(f"IN BUY BOX:    {len(inbox)}")
    print(f"NEAR BUY BOX:  {len(near)} (units {NEAR_MIN}-{NEAR_MAX}, logged as Near — Review — broker worth a call)")
    print(f"OUT OF BOX:    {len(outbox)} (logged as Pass)")
    print(f"DUPLICATES:    {len(skipped)} (skipped)")

    deal_rows = []
    for listing in new_deals:
        deal_rows.append(build_deal_row(listing))
        if listing["in_buy_box"] and listing["unit_fit"] in ("fit", None):
            flag = "✅"
        elif listing["in_buy_box"] and listing["unit_fit"] == "near":
            flag = "🔶"
        else:
            flag = "⚠️ "
        print(f"  {flag} {listing['property_name'] or listing['address']} "
              f"({listing['zip']}) — {listing['units'] or '?'} units — {listing['price']} "
              f"[{listing['source'].upper()}]")

    if not dry_run and deal_rows:
        _append_rows(token, "Deal Sourcing", deal_rows)

    print(f"\n{'='*50}")
    if dry_run:
        print("[DRY RUN] No changes written.")
    else:
        print(f"✅ Done — {len(deal_rows)} deal(s) logged to Deal Sourcing.")
        print(f"   https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Olive Tree deal search")
    parser.add_argument("--days",    type=int, default=7,  help="Email lookback window in days (default 7)")
    parser.add_argument("--dry-run", action="store_true",  help="Parse/print without writing to sheet")
    parser.add_argument("--source",  choices=["crexi", "loopnet", "fmls"],
                        help="Scan one source only")
    args = parser.parse_args()
    run(days=args.days, dry_run=args.dry_run, source=args.source)
