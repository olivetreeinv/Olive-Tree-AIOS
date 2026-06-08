#!/usr/bin/env python3
"""
Olive Tree Investments — Broker Search via Email Alerts
Parses Crexi and LoopNet listing alert emails from Gmail, filters against the buy box,
and logs new deals + qualifying brokers to the Deal Sourcing spreadsheet.

Usage:
  python3 scripts/broker_search.py              # Run full scan (last 7 days)
  python3 scripts/broker_search.py --days 30    # Scan last 30 days
  python3 scripts/broker_search.py --dry-run    # Parse and print — don't write to sheet
"""

import argparse
import base64
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta

import requests
from bs4 import BeautifulSoup
from gws_auth import get_token

# ─────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────

SPREADSHEET_ID = "1VxOlof56s8GosrWkSctL-FMm7AoJKJ6YtM3GllMKVH4"
SHEETS_BASE = "https://sheets.googleapis.com/v4/spreadsheets"
GMAIL_BASE  = "https://gmail.googleapis.com/gmail/v1/users/me"
TODAY = date.today().strftime("%m/%d/%Y")

# Buy box: 10 active zips → market labels
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

# Availability check config
AVAILABILITY_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}
SOLD_SIGNALS = [
    "no longer available", "listing has been removed", "listing not found",
    "listing removed", "property is no longer", "expired listing",
    "this listing has expired", "page not found", "listing is no longer",
]

MIN_UNITS = 15
MAX_UNITS = 50
MIN_BROKER_LISTINGS = 2  # broker must have this many listings to be added

# Gmail search queries for each platform
EMAIL_QUERIES = {
    "crexi":   'from:crexi.com subject:(listing OR alert OR "new properties" OR "saved search")',
    "loopnet": 'from:loopnet.com subject:(listing OR alert OR "new properties" OR "saved search")',
}

# ─────────────────────────────────────────────
# Auth
# ─────────────────────────────────────────────

def auth(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

# ─────────────────────────────────────────────
# Gmail helpers
# ─────────────────────────────────────────────

def search_messages(token, query, days=7):
    after = (datetime.now() - timedelta(days=days)).strftime("%Y/%m/%d")
    full_query = f"{query} after:{after}"
    r = requests.get(f"{GMAIL_BASE}/messages",
                     headers=auth(token),
                     params={"q": full_query, "maxResults": 100},
                     timeout=30)
    r.raise_for_status()
    return r.json().get("messages", [])


def get_message(token, msg_id):
    r = requests.get(f"{GMAIL_BASE}/messages/{msg_id}",
                     headers=auth(token),
                     params={"format": "full"},
                     timeout=30)
    r.raise_for_status()
    return r.json()


def extract_body(message):
    """Return decoded plain text + HTML from a Gmail message."""
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
            # Recurse into nested parts
            if "parts" in part:
                walk(part["parts"])

    # Handle simple (non-multipart) messages
    payload = message.get("payload", {})
    if not parts:
        data = payload.get("body", {}).get("data", "")
        if data:
            decoded = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
            mime = payload.get("mimeType", "")
            if mime == "text/html":
                html = decoded
            else:
                plain = decoded
    else:
        walk(parts)

    return plain, html


def html_to_text(html):
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text(separator=" ", strip=True)

# ─────────────────────────────────────────────
# Availability checking
# ─────────────────────────────────────────────

def find_listing_url(text, source):
    """Extract the first Crexi or LoopNet listing URL from email text."""
    if source == "crexi":
        m = re.search(r'https?://(?:www\.)?crexi\.com/properties/[\w-]+(?:/[\w-]+)?', text)
    else:
        m = re.search(r'https?://(?:www\.)?loopnet\.com/(?:[Ll]isting|listing)/[\w/-]+', text)
    return m.group(0).rstrip("/") if m else ""


def check_availability(url, timeout=8):
    """Returns: 'available', 'unavailable', or 'unverified'."""
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
        text_lower = content.decode("utf-8", errors="replace").lower()
        if any(sig in text_lower for sig in SOLD_SIGNALS):
            return "unavailable"
        return "available"
    except requests.exceptions.Timeout:
        return "unverified"
    except Exception:
        return "unverified"


def check_all_availability(listings, timeout=8, workers=5):
    """Check availability for all listings in parallel. Updates listing dicts in-place."""
    def check_one(listing):
        return listing, check_availability(listing.get("listing_url", ""), timeout=timeout)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(check_one, l): l for l in listings}
        for future in as_completed(futures):
            listing, status = future.result()
            listing["availability"] = status


# ─────────────────────────────────────────────
# Listing parser
# ─────────────────────────────────────────────

# Regex helpers
def find_price(text):
    patterns = [
        r'\$[\d,]+(?:\.\d+)?[Mm](?:illion)?',   # $1.5M
        r'\$[\d,]{4,}',                           # $1,500,000
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            raw = m.group(0).replace(",", "").replace("$", "")
            if "m" in raw.lower():
                val = float(re.sub(r'[mM].*', '', raw)) * 1_000_000
                return f"${int(val):,}"
            return f"${int(raw):,}"
    return ""


def find_units(text):
    patterns = [
        r'(\d+)\s*(?:-unit|-Unit|unit|Unit|units|Units)',
        r'(\d+)\s*(?:apartments?|apt)',
        r'[Uu]nits?[:\s]+(\d+)',
        r'(\d+)\s*[Uu]nit\b',
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            return int(m.group(1))
    return None


def find_zip(text):
    zips = re.findall(r'\b(\d{5})\b', text)
    for z in zips:
        if z in BUY_BOX:
            return z
    # Return any zip found (for out-of-box flagging)
    return zips[0] if zips else ""


def find_address(text):
    # Street address pattern: number + street name
    m = re.search(r'\d+\s+[A-Za-z][A-Za-z0-9\s]{3,40}(?:St|Ave|Blvd|Dr|Rd|Ln|Way|Ct|Pl|Pkwy|Hwy|Circle|Trail)\b[^,\n]*(?:,\s*[A-Za-z\s]+,\s*[A-Z]{2}\s*\d{5})?', text)
    return m.group(0).strip() if m else ""


def find_broker_info(text, source):
    """Extract (name, email, phone, brokerage) from listing text."""
    name, email, phone, brokerage = "", "", "", ""

    # Email
    em = re.search(r'[\w.+-]+@[\w-]+\.\w+', text)
    if em:
        raw = em.group(0)
        if not any(skip in raw for skip in ["crexi.com", "loopnet.com", "noreply", "no-reply"]):
            email = raw

    # Phone
    ph = re.search(r'[\(]?\d{3}[\)\-.\s]?\d{3}[\-.\s]\d{4}', text)
    if ph:
        phone = ph.group(0).strip()

    # Broker name patterns
    name_patterns = [
        r'[Ll]isted\s+[Bb]y[:\s]+([A-Z][a-z]+(?:\s[A-Z][a-z]+)+)',
        r'[Cc]ontact[:\s]+([A-Z][a-z]+(?:\s[A-Z][a-z]+)+)',
        r'[Aa]gent[:\s]+([A-Z][a-z]+(?:\s[A-Z][a-z]+)+)',
        r'[Bb]roker[:\s]+([A-Z][a-z]+(?:\s[A-Z][a-z]+)+)',
        r'[Rr]ep(?:resented by)?[:\s]+([A-Z][a-z]+(?:\s[A-Z][a-z]+)+)',
    ]
    for p in name_patterns:
        m = re.search(p, text)
        if m:
            name = m.group(1).strip()
            break

    # Brokerage patterns
    known_brokerages = [
        "Marcus & Millichap", "CBRE", "JLL", "Cushman & Wakefield",
        "SVN", "Bull Realty", "Colliers", "Northmarq", "Walker & Dunlop",
        "Berkshire Hathaway", "BHHS", "Cosgrove", "Mathews", "GREA",
        "Watts Realty", "PWA Properties", "Skyline", "Crexi", "CoStar",
        "Kidder Mathews", "Avison Young", "NAI", "Lee & Associates",
    ]
    text_lower = text.lower()
    for b in known_brokerages:
        if b.lower() in text_lower:
            brokerage = b
            break

    # Try brokerage from structured patterns
    if not brokerage:
        bm = re.search(r'(?:[Bb]rokerage|[Ff]irm|[Cc]ompany)[:\s]+([A-Z][A-Za-z\s&,\.]+?)(?:\n|<|\|)', text)
        if bm:
            brokerage = bm.group(1).strip()

    return name, email, phone, brokerage


def parse_listing_from_email(text, source):
    """Parse one or more listings from email body text. Returns list of dicts."""
    listings = []

    # Crexi emails typically repeat a block per property
    # LoopNet alerts list multiple properties in sequence
    # Split on common delimiters
    blocks = re.split(r'(?:View Listing|View Property|See More|See Details|Learn More)\s*\n', text, flags=re.IGNORECASE)
    if len(blocks) < 2:
        blocks = [text]  # treat whole email as one block

    for block in blocks:
        if len(block.strip()) < 50:
            continue

        units = find_units(block)
        price = find_price(block)
        address = find_address(block)
        zip_code = find_zip(block)
        broker_name, broker_email, broker_phone, brokerage = find_broker_info(block, source)

        # Require at least address or zip to be useful
        if not address and not zip_code:
            continue

        # Try to get property name (first line or heading-like text)
        prop_name = ""
        lines = [l.strip() for l in block.split("\n") if l.strip()]
        if lines:
            first = lines[0]
            if len(first) < 80 and not first.startswith("$") and not re.match(r'^\d', first):
                prop_name = first

        listing = {
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
            "unit_fit":      MIN_UNITS <= units <= MAX_UNITS if units else None,
            "listing_url":   find_listing_url(block, source),
            "availability":  "unverified",  # filled by check_all_availability()
        }
        listings.append(listing)

    return listings

# ─────────────────────────────────────────────
# Sheets helpers
# ─────────────────────────────────────────────

def read_sheet(token, sheet_name, range_="A1:Z500"):
    r = requests.get(
        f"{SHEETS_BASE}/{SPREADSHEET_ID}/values/{sheet_name}!{range_}",
        headers=auth(token),
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get("values", [])


def append_rows(token, sheet_name, rows):
    """Append one or more rows to a sheet in a single API call."""
    if not rows:
        return
    body = {"values": rows, "majorDimension": "ROWS"}
    r = requests.post(
        f"{SHEETS_BASE}/{SPREADSHEET_ID}/values/{sheet_name}!A1:append",
        headers=auth(token),
        params={"valueInputOption": "USER_ENTERED", "insertDataOption": "INSERT_ROWS"},
        json=body,
        timeout=30,
    )
    r.raise_for_status()


def get_existing_deals(token):
    """Return set of (address_lower, property_name_lower) tuples from Deal Sourcing."""
    rows = read_sheet(token, "Deal Sourcing")
    existing = set()
    for row in rows[1:]:  # skip header
        addr  = row[3].strip().lower() if len(row) > 3 else ""
        pname = row[2].strip().lower() if len(row) > 2 else ""
        if addr:  existing.add(addr)
        if pname: existing.add(pname)
    return existing


def get_existing_brokers(token):
    """Return set of (email_lower, name_lower) from Brokers List."""
    rows = read_sheet(token, "Brokers List")
    emails, names = set(), set()
    for row in rows[1:]:
        email = row[2].strip().lower() if len(row) > 2 else ""
        name  = row[1].strip().lower() if len(row) > 1 else ""
        if email: emails.add(email)
        if name:  names.add(name)
    return emails, names


def is_duplicate_deal(listing, existing_deals):
    addr  = listing["address"].lower()
    pname = listing["property_name"].lower()
    return addr in existing_deals or (pname and pname in existing_deals)


def is_duplicate_broker(broker_email, broker_name, existing_emails, existing_names):
    if broker_email and broker_email.lower() in existing_emails:
        return True
    if broker_name and broker_name.lower() in existing_names:
        return True
    return False

# ─────────────────────────────────────────────
# Logging to sheets
# ─────────────────────────────────────────────

def build_deal_row(listing):
    units_str = str(listing["units"]) if listing["units"] else ""
    price_str = listing["price"]
    price_per_unit = ""
    if listing["units"] and listing["price"]:
        try:
            raw = int(listing["price"].replace("$","").replace(",",""))
            price_per_unit = f"${raw // listing['units']:,}"
        except (ValueError, TypeError, ZeroDivisionError):
            pass

    # Notes: flag buy box, unit range, and availability
    notes = []
    if not listing["in_buy_box"]:
        notes.append(f"⚠️ Outside buy box (zip {listing['zip']})")
    if listing["unit_fit"] is False:
        notes.append(f"⚠️ Unit count {listing['units']} outside 15–50 range")
    if listing.get("availability") == "unverified":
        notes.append("❓ Availability unverified")
    notes_str = " | ".join(notes) if notes else ""

    # Stage: flag out-of-box as Pass, otherwise New
    stage = "Pass" if (not listing["in_buy_box"] or listing["unit_fit"] is False) else "New"

    row = [
        listing["market"] or listing["zip"],  # Market
        listing["zip"],                         # Zip Code
        listing["property_name"],               # Property Name
        listing["address"],                     # Address
        units_str,                              # Doors
        price_str,                              # Asking Price
        "",                                     # Offer Price
        price_per_unit,                         # Price/Unit
        "",                                     # Vintage
        "",                                     # Cap Rate
        "",                                     # Gross Rent (Annual)
        "",                                     # NOI
        listing["source"].title(),              # Platform
        listing["brokerage"],                   # Brokerage
        listing["broker_name"],                 # Broker Name
        listing["broker_email"],                # Broker Email
        listing["broker_phone"],                # Broker Phone
        stage,                                  # Stage
        TODAY,                                  # Date Found
        TODAY,                                  # Last Updated
        notes_str,                              # Notes
    ]
    return row


def build_broker_row(broker_name, broker_email, broker_phone, brokerage,
                     markets, listing_count):
    row = [
        brokerage,                        # Brokerage
        broker_name,                      # Broker Name
        broker_email,                     # Email
        broker_phone,                     # Phone
        ", ".join(sorted(markets)),       # Markets / Zips Covered
        "Multifamily",                    # Specialty
        "B",                              # Tier (start at B — no relationship yet)
        "No",                             # Buy Box Sent
        str(listing_count),               # # Deals Sent
        TODAY,                            # Last Contact
        "",                               # Next Follow-Up
        "New — Found via Alert",          # Status
        f"Auto-added: {listing_count} listings found via {brokerage or 'email alert'}",
    ]
    return row

# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def run(days=7, dry_run=False):
    print(f"{'[DRY RUN] ' if dry_run else ''}Scanning last {days} days of listing alert emails...\n")

    token = get_token()

    # Load existing data for deduplication
    print("Loading existing sheet data...")
    existing_deals = get_existing_deals(token)
    existing_emails, existing_names = get_existing_brokers(token)
    print(f"  Existing deals:   {len(existing_deals)}")
    print(f"  Existing brokers: {len(existing_emails)}\n")

    all_listings = []

    # Scan Gmail for alert emails from each platform
    for source, query in EMAIL_QUERIES.items():
        messages = search_messages(token, query, days=days)
        print(f"{source.upper()}: {len(messages)} alert email(s) found")

        def fetch_and_parse(msg_meta, _source=source):
            msg = get_message(token, msg_meta["id"])
            plain, html = extract_body(msg)
            text = html_to_text(html) if html else plain
            return _source, msg_meta["id"], parse_listing_from_email(text, _source)

        with ThreadPoolExecutor(max_workers=5) as executor:
            for _source, msg_id, listings in executor.map(fetch_and_parse, messages):
                print(f"  → Parsed {len(listings)} listing(s) from message {msg_id[:8]}...")
                all_listings.extend(listings)

    if not all_listings:
        print("\nNo listings parsed from emails.")
        print("If you haven't set up saved searches yet, see the broker-search skill setup instructions.")
        return

    print(f"\nTotal listings parsed: {len(all_listings)}")

    # Availability check — parallel, before anything else
    has_urls = sum(1 for l in all_listings if l.get("listing_url"))
    print(f"\nChecking availability ({has_urls}/{len(all_listings)} have URLs)...")
    check_all_availability(all_listings)
    unavailable = [l for l in all_listings if l["availability"] == "unavailable"]
    for l in unavailable:
        print(f"  ❌ Unavailable — skipping: {l['property_name'] or l['address']}")

    # Drop unavailable before any further processing
    all_listings = [l for l in all_listings if l["availability"] != "unavailable"]

    # Filter and deduplicate
    new_deals = []
    skipped = []
    for listing in all_listings:
        if is_duplicate_deal(listing, existing_deals):
            skipped.append(("duplicate", listing))
        else:
            new_deals.append(listing)

    # Broker counting — count all listings per broker (email or name as key)
    broker_listings = defaultdict(list)  # key → list of listings
    for listing in new_deals:
        key = listing["broker_email"].lower() if listing["broker_email"] \
              else listing["broker_name"].lower()
        if key:
            broker_listings[key].append(listing)

    # Separate in-box vs out-of-box deals
    inbox_deals  = [l for l in new_deals if l["in_buy_box"] and l["unit_fit"] is not False]
    outbox_deals = [l for l in new_deals if not l["in_buy_box"] or l["unit_fit"] is False]

    print(f"\n{'='*50}")
    print(f"UNAVAILABLE (filtered out):  {len(unavailable)}")
    print(f"NEW DEALS — IN BUY BOX:     {len(inbox_deals)}")
    print(f"NEW DEALS — OUT OF BUY BOX: {len(outbox_deals)} (will be logged as Pass)")
    print(f"SKIPPED (duplicates):        {len(skipped)}")

    # Collect all new deal rows, then append in a single batched call
    deal_rows = []
    for listing in new_deals:
        deal_rows.append(build_deal_row(listing))
        flag = "✅" if listing["in_buy_box"] else "⚠️ "
        print(f"  {flag} Deal: {listing['property_name'] or listing['address']} "
              f"({listing['zip']}) — {listing['units'] or '?'} units — {listing['price']}")
    if not dry_run:
        append_rows(token, "Deal Sourcing", deal_rows)
    logged_deals = len(deal_rows)

    # Evaluate brokers — only add if 2+ listings AND not already in sheet
    print(f"\n{'='*50}")
    print(f"BROKER EVALUATION (threshold: {MIN_BROKER_LISTINGS}+ listings)")
    broker_rows = []
    for key, listings in broker_listings.items():
        # Get broker info from the first listing with a non-empty email/name
        sample = listings[0]
        b_name  = sample["broker_name"]
        b_email = sample["broker_email"]
        b_phone = sample["broker_phone"]
        brokerage = sample["brokerage"]
        markets = {l["zip"] for l in listings if l["zip"]}
        count = len(listings)

        already_in = is_duplicate_broker(b_email, b_name, existing_emails, existing_names)

        if count < MIN_BROKER_LISTINGS:
            print(f"  ⏭  {b_name or b_email} — only {count} listing(s), need {MIN_BROKER_LISTINGS}+. Skipped.")
            continue

        if already_in:
            print(f"  ↩️  {b_name or b_email} — already in Brokers List. Skipped.")
            continue

        broker_rows.append(build_broker_row(b_name, b_email, b_phone, brokerage,
                                            markets, count))
        print(f"  ✅ Added broker: {b_name or b_email} ({brokerage}) — {count} listings in {', '.join(sorted(markets))}")
    if not dry_run:
        append_rows(token, "Brokers List", broker_rows)
    new_brokers = len(broker_rows)

    print(f"\n{'='*50}")
    if dry_run:
        print("[DRY RUN] No changes written to spreadsheet.")
    else:
        print(f"✅ Done.")
        print(f"   Deals logged:   {logged_deals}")
        print(f"   Brokers added:  {new_brokers}")
        print(f"\n   Spreadsheet: https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}")


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Olive Tree broker search via email alerts")
    parser.add_argument("--days",    type=int, default=7,       help="Scan this many days back (default 7)")
    parser.add_argument("--dry-run", action="store_true",       help="Parse and print without writing to sheet")
    args = parser.parse_args()
    run(days=args.days, dry_run=args.dry_run)
