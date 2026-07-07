#!/usr/bin/env python3
"""
Olive Tree Investments — Broker Search
Finds brokers with 2+ active MF listings who aren't in the Google Drive Brokers List.
No buy-box filter — casts wide to build the broker network.

Primary:  Direct platform APIs (Crexi, LoopNet, FMLS) when API keys are set.
Fallback: Gmail alert emails for Crexi + LoopNet when API keys are missing.

Usage:
  python3 scripts/broker_search.py               # Full scan (all platforms)
  python3 scripts/broker_search.py --dry-run     # Print qualifying brokers without writing
  python3 scripts/broker_search.py --source crexi  # One platform only
  python3 scripts/broker_search.py --days 14     # Email fallback lookback window (default 7)

Optional env vars (add to .env for direct platform queries):
  CREXI_API_KEY    — Crexi partner API key
  LOOPNET_API_KEY  — LoopNet/CoStar API key (enterprise)
  FMLS_API_TOKEN   — FMLS (Bridge Data Output) server token
  FMLS_DATASET_ID  — Bridge dataset id (default: fmls)
"""

import argparse
import base64
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
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

CREXI_API_BASE   = "https://api.crexi.com"
CREXI_API_KEY    = os.getenv("CREXI_API_KEY", "")

LOOPNET_API_BASE = "https://api.loopnet.com/api/2"
LOOPNET_API_KEY  = os.getenv("LOOPNET_API_KEY", "")

FMLS_DATASET_ID = os.getenv("FMLS_DATASET_ID", "fmls")
FMLS_API_BASE   = os.getenv(
    "FMLS_API_BASE",
    f"https://api.bridgedataoutput.com/api/v2/OData/{FMLS_DATASET_ID}",
)
FMLS_API_TOKEN  = os.getenv("FMLS_API_TOKEN", "")

MIN_BROKER_LISTINGS = 2
PAGE_SIZE           = 100
# FMLS "Residential Income" includes 2–4 unit duplex/triplex listings handled by
# retail residential agents. Only count listings at/above the deal-analysis floor
# so the qualifying set reflects true multifamily brokers, not SFR/duplex agents.
MIN_MF_UNITS        = 5

EMAIL_QUERIES = {
    "crexi":   'from:crexi.com subject:(listing OR alert OR "new properties" OR "saved search")',
    "loopnet": 'from:loopnet.com subject:(listing OR alert OR "new properties" OR "saved search")',
}

_SCRAPE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
}

KNOWN_BROKERAGES = [
    "Marcus & Millichap", "CBRE", "JLL", "Cushman & Wakefield", "SVN",
    "Bull Realty", "Colliers", "Northmarq", "Walker & Dunlop",
    "Berkshire Hathaway", "BHHS", "Cosgrove", "Mathews", "GREA",
    "Watts Realty", "PWA Properties", "Skyline", "CoStar",
    "Kidder Mathews", "Avison Young", "NAI", "Lee & Associates",
]

# ─────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────

def _gws_auth(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _broker_key(email, name):
    """Canonical dedup key: email preferred, else lowercased name."""
    return (email or "").lower().strip() or (name or "").lower().strip()


def _merge_broker(store, key, name, email, phone, brokerage, zip_code, platform):
    """Upsert broker entry into store dict."""
    if key not in store:
        store[key] = {
            "name":      name,
            "email":     email,
            "phone":     phone,
            "brokerage": brokerage,
            "zips":      set(),
            "platforms": set(),
            "count":     0,
        }
    entry = store[key]
    if not entry["name"]      and name:      entry["name"]      = name
    if not entry["email"]     and email:     entry["email"]     = email
    if not entry["phone"]     and phone:     entry["phone"]     = phone
    if not entry["brokerage"] and brokerage: entry["brokerage"] = brokerage
    if zip_code:  entry["zips"].add(str(zip_code))
    if platform:  entry["platforms"].add(platform)
    entry["count"] += 1

# ─────────────────────────────────────────────
# Gmail helpers (email fallback)
# ─────────────────────────────────────────────

def _search_messages(token, query, days):
    after = (datetime.now() - timedelta(days=days)).strftime("%Y/%m/%d")
    r = requests.get(
        f"{GMAIL_BASE}/messages",
        headers=_gws_auth(token),
        params={"q": f"{query} after:{after}", "maxResults": 200},
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get("messages", [])


def _get_message(token, msg_id):
    r = requests.get(
        f"{GMAIL_BASE}/messages/{msg_id}",
        headers=_gws_auth(token),
        params={"format": "full"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def _extract_body(message):
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


def _html_to_text(html):
    return BeautifulSoup(html, "html.parser").get_text(separator=" ", strip=True)


def _extract_broker_from_block(block, source):
    """Pull (name, email, phone, brokerage, zip) from one listing block."""
    name, email, phone, brokerage, zip_code = "", "", "", "", ""

    em = re.search(r'[\w.+-]+@[\w-]+\.\w+', block)
    if em:
        raw = em.group(0)
        if not any(skip in raw for skip in
                   ["crexi.com", "loopnet.com", "costar.com", "noreply", "no-reply"]):
            email = raw

    ph = re.search(r'[\(]?\d{3}[\)\-.\s]?\d{3}[\-.\s]\d{4}', block)
    if ph:
        phone = ph.group(0).strip()

    for p in [
        r'[Ll]isted\s+[Bb]y[:\s]+([A-Z][a-z]+(?:\s[A-Z][a-z]+)+)',
        r'[Cc]ontact[:\s]+([A-Z][a-z]+(?:\s[A-Z][a-z]+)+)',
        r'[Aa]gent[:\s]+([A-Z][a-z]+(?:\s[A-Z][a-z]+)+)',
        r'[Bb]roker[:\s]+([A-Z][a-z]+(?:\s[A-Z][a-z]+)+)',
    ]:
        m = re.search(p, block)
        if m:
            name = m.group(1).strip()
            break

    tl = block.lower()
    for b in KNOWN_BROKERAGES:
        if b.lower() in tl:
            brokerage = b
            break
    if not brokerage:
        bm = re.search(
            r'(?:[Bb]rokerage|[Ff]irm|[Cc]ompany)[:\s]+([A-Z][A-Za-z\s&,\.]+?)(?:\n|<|\|)',
            block,
        )
        if bm:
            brokerage = bm.group(1).strip()

    zips = re.findall(r'\b(\d{5})\b', block)
    zip_code = zips[0] if zips else ""

    return name, email, phone, brokerage, zip_code


def fetch_email_brokers(broker_store, token, source, days=7):
    """
    Fallback: parse Crexi/LoopNet alert emails and aggregate ALL broker info.
    No buy-box filter — every broker with a listing gets counted.
    """
    query    = EMAIL_QUERIES[source]
    messages = _search_messages(token, query, days=days)
    print(f"  {source.upper()} (email fallback): {len(messages)} alert email(s) found")

    parsed, skipped = 0, 0

    def _fetch(m):
        try:
            return _get_message(token, m["id"])
        except Exception as e:
            return e

    # Fetch in parallel; parse/merge stay on the main thread (shared broker_store).
    with ThreadPoolExecutor(max_workers=8) as pool:
        fetched = list(pool.map(_fetch, messages))
    for msg_meta, msg in zip(messages, fetched):
        if isinstance(msg, Exception):
            print(f"    ⚠️ skipped {msg_meta['id']}: {msg}")
            skipped += 1
            continue
        try:
            plain, html = _extract_body(msg)
            text = _html_to_text(html) if html else plain

            # Split on listing-block delimiters
            blocks = re.split(
                r'(?:View Listing|View Property|See More|See Details|Learn More)\s*\n',
                text, flags=re.IGNORECASE,
            )
            if len(blocks) < 2:
                blocks = [text]

            for block in blocks:
                if len(block.strip()) < 50:
                    continue
                name, email, phone, brokerage, zip_code = _extract_broker_from_block(block, source)
                key = _broker_key(email, name)
                if key:
                    _merge_broker(broker_store, key, name, email, phone,
                                  brokerage, zip_code, source.title())
                    parsed += 1
        except Exception as e:
            skipped += 1

    print(f"  {source.upper()} (email fallback): {parsed} broker record(s) extracted"
          + (f", {skipped} email(s) skipped" if skipped else ""))

# ─────────────────────────────────────────────
# Crexi — API or email fallback
# ─────────────────────────────────────────────

def fetch_crexi_brokers(broker_store, token=None, days=7):
    if not CREXI_API_KEY:
        if token:
            print("Crexi: no API key — falling back to email alerts...")
            fetch_email_brokers(broker_store, token, "crexi", days)
        else:
            print("Crexi: no API key and no token — skipping.")
        return

    headers = {**_SCRAPE_HEADERS, "x-api-key": CREXI_API_KEY}
    page, total, errors = 0, 0, 0

    print("Crexi: querying active MF listings via API...")
    while True:
        params = {
            "types": "multifamily", "statuses": "active", "saleType": "for-sale",
            "size": PAGE_SIZE, "from": page * PAGE_SIZE,
        }
        try:
            r = requests.get(f"{CREXI_API_BASE}/assets", headers=headers,
                             params=params, timeout=30)
            if r.status_code == 401:
                print("  Crexi: 401 Unauthorized — check CREXI_API_KEY.")
                return
            if r.status_code == 429:
                time.sleep(10)
                continue
            r.raise_for_status()
        except requests.exceptions.RequestException as e:
            errors += 1
            if errors >= 3:
                print(f"  Crexi: too many errors ({e}), stopping.")
                return
            time.sleep(2)
            continue

        data   = r.json()
        assets = data.get("assets", data.get("data", data.get("results", [])))
        for asset in assets:
            agent     = asset.get("agent", asset.get("contact", {}))
            name      = agent.get("name", agent.get("fullName", ""))
            email     = agent.get("email", "")
            phone     = agent.get("phone", agent.get("phoneNumber", ""))
            brokerage = (asset.get("brokerage", {}).get("name", "")
                         or asset.get("brokerageName", "")
                         or agent.get("company", ""))
            zip_code  = (asset.get("address", {}).get("zip", "") or asset.get("zip", ""))
            key = _broker_key(email, name)
            if key:
                _merge_broker(broker_store, key, name, email, phone, brokerage, zip_code, "Crexi")

        total += len(assets)
        print(f"  Crexi: page {page + 1} — {len(assets)} listings ({total} total)")
        if len(assets) < PAGE_SIZE:
            break
        page += 1

    print(f"  Crexi: done — {total} listing(s) scanned\n")

# ─────────────────────────────────────────────
# LoopNet — API or email fallback
# ─────────────────────────────────────────────

def fetch_loopnet_brokers(broker_store, token=None, days=7):
    if not LOOPNET_API_KEY:
        if token:
            print("LoopNet: no API key — falling back to email alerts...")
            fetch_email_brokers(broker_store, token, "loopnet", days)
        else:
            print("LoopNet: no API key and no token — skipping.")
        return

    headers = {**_SCRAPE_HEADERS, "Authorization": f"Bearer {LOOPNET_API_KEY}"}
    page, total = 1, 0

    print("LoopNet: querying active MF listings via API...")
    while True:
        params = {
            "PropertyType": "Multifamily", "ListingType": "For Sale",
            "ActiveStatus": "Active", "pageSize": PAGE_SIZE, "page": page,
        }
        try:
            r = requests.get(f"{LOOPNET_API_BASE}/property/search", headers=headers,
                             params=params, timeout=30)
            if r.status_code == 401:
                print("  LoopNet: 401 Unauthorized — check LOOPNET_API_KEY.")
                return
            if r.status_code == 429:
                time.sleep(10)
                continue
            r.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"  LoopNet: error — {e}")
            return

        data     = r.json()
        listings = data.get("Properties", data.get("results", data.get("listings", [])))
        for prop in listings:
            agent     = prop.get("ListingAgent", prop.get("Agent", prop.get("Contact", {})))
            name      = agent.get("Name", agent.get("name", ""))
            email     = agent.get("Email", agent.get("email", ""))
            phone     = agent.get("Phone", agent.get("phone", ""))
            brokerage = (prop.get("Company", {}).get("Name", "")
                         or prop.get("BrokerageName", "")
                         or agent.get("Company", ""))
            address  = prop.get("Address", {})
            zip_code = address.get("PostalCode", address.get("Zip", ""))
            key = _broker_key(email, name)
            if key:
                _merge_broker(broker_store, key, name, email, phone, brokerage, zip_code, "LoopNet")

        total += len(listings)
        print(f"  LoopNet: page {page} — {len(listings)} listings ({total} total)")
        if len(listings) < PAGE_SIZE:
            break
        page += 1

    print(f"  LoopNet: done — {total} listing(s) scanned\n")

# ─────────────────────────────────────────────
# FMLS — API only (no email fallback)
# ─────────────────────────────────────────────

def fetch_fmls_brokers(broker_store):
    if not FMLS_API_TOKEN:
        print("FMLS: FMLS_API_TOKEN not set — skipping.")
        print("      Add FMLS_API_TOKEN (Bridge Data Output) to .env to enable.")
        return

    headers = {"Authorization": f"Bearer {FMLS_API_TOKEN}"}
    params = {
        "$filter": (
            "PropertyType eq 'Residential Income'"
            " and StandardStatus eq 'Active'"
        ),
        "$select": ",".join([
            "ListingKey", "PostalCode", "NumberOfUnitsTotal",
            "ListAgentFullName", "ListAgentEmail", "ListAgentDirectPhone", "ListOfficeName",
        ]),
        "$top": 200,
    }
    url, total, pages = f"{FMLS_API_BASE}/Property", 0, 0
    MAX_PAGES = 50  # safety cap: 50 × 200 = 10k listings

    print("FMLS: querying active income properties...")
    while url and pages < MAX_PAGES:
        pages += 1
        try:
            r = requests.get(url, headers=headers, params=params, timeout=30)
            if r.status_code == 401:
                print("  FMLS: 401 Unauthorized — check FMLS_API_TOKEN.")
                return
            r.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"  FMLS: error — {e}")
            return

        data  = r.json()
        props = data.get("value", [])
        for prop in props:
            units = prop.get("NumberOfUnitsTotal") or 0
            try:
                units = int(units)
            except (TypeError, ValueError):
                units = 0
            if units < MIN_MF_UNITS:
                continue  # skip SFR/duplex/triplex "income" listings
            name      = prop.get("ListAgentFullName", "")
            email     = prop.get("ListAgentEmail", "")
            phone     = prop.get("ListAgentDirectPhone", "")
            brokerage = prop.get("ListOfficeName", "")
            zip_code  = str(prop.get("PostalCode", "")).split("-")[0]
            key = _broker_key(email, name)
            if key:
                _merge_broker(broker_store, key, name, email, phone, brokerage, zip_code, "FMLS")

        total += len(props)
        print(f"  FMLS: {total} listing(s) scanned")
        # Bridge OData paginates via @odata.nextLink (already carries params).
        url, params = data.get("@odata.nextLink"), None

    print(f"  FMLS: done — {total} listing(s) scanned\n")

# ─────────────────────────────────────────────
# Google Drive Brokers List cross-ref
# ─────────────────────────────────────────────

def get_existing_brokers(token):
    r = requests.get(
        f"{SHEETS_BASE}/{SPREADSHEET_ID}/values/Brokers List!A1:Z2000",
        headers=_gws_auth(token),
        timeout=30,
    )
    r.raise_for_status()
    rows = r.json().get("values", [])
    emails, names = set(), set()
    for row in rows[1:]:
        email = row[2].strip().lower() if len(row) > 2 else ""
        name  = row[1].strip().lower() if len(row) > 1 else ""
        if email: emails.add(email)
        if name:  names.add(name)
    return emails, names


def is_existing_broker(entry, existing_emails, existing_names):
    if entry["email"] and entry["email"].lower() in existing_emails:
        return True
    if entry["name"] and entry["name"].lower() in existing_names:
        return True
    return False


def build_broker_row(entry):
    platforms = ", ".join(sorted(entry["platforms"]))
    return [
        entry["brokerage"],
        entry["name"],
        entry["email"],
        entry["phone"],
        ", ".join(sorted(entry["zips"])),
        "Multifamily",
        "B",                   # Tier — no relationship yet
        "No",                  # Buy Box Sent
        str(entry["count"]),   # # Deals Sent (listing count at discovery)
        TODAY,                 # Last Contact
        "",                    # Next Follow-Up
        "New — Found via Platform Scan",
        f"Auto-added: {entry['count']} listing(s) found on {platforms}",
    ]


def append_rows(token, rows):
    if not rows:
        return
    r = requests.post(
        f"{SHEETS_BASE}/{SPREADSHEET_ID}/values/Brokers List!A1:append",
        headers=_gws_auth(token),
        params={"valueInputOption": "USER_ENTERED", "insertDataOption": "INSERT_ROWS"},
        json={"values": rows, "majorDimension": "ROWS"},
        timeout=30,
    )
    r.raise_for_status()

# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def run(dry_run=False, source=None, days=7):
    prefix  = "[DRY RUN] " if dry_run else ""
    sources = [source] if source else ["crexi", "loopnet", "fmls"]
    print(f"{prefix}Broker Search — {TODAY}")
    print(f"Sources: {', '.join(sources).upper()}  |  Threshold: {MIN_BROKER_LISTINGS}+ listings  |  Email window: {days}d\n")

    # Get token upfront — needed for email fallback AND for the Sheets cross-ref
    token = get_token()

    broker_store = {}

    if "crexi"   in sources: fetch_crexi_brokers(broker_store, token=token, days=days)
    if "loopnet" in sources: fetch_loopnet_brokers(broker_store, token=token, days=days)
    if "fmls"    in sources: fetch_fmls_brokers(broker_store)

    if not broker_store:
        print("\nNo broker data retrieved.")
        print("If email alerts are set up on Crexi/LoopNet, try extending the window: --days 30")
        return

    total_brokers = len(broker_store)
    print(f"\n{'='*50}")
    print(f"Unique brokers found: {total_brokers}\n")

    print("Cross-referencing Google Drive Brokers List...")
    existing_emails, existing_names = get_existing_brokers(token)
    print(f"  {len(existing_emails)} broker(s) already on record\n")

    qualifying, single, already_in = [], [], []
    for key, entry in broker_store.items():
        if entry["count"] < MIN_BROKER_LISTINGS:
            single.append(entry)
        elif is_existing_broker(entry, existing_emails, existing_names):
            already_in.append(entry)
        else:
            qualifying.append(entry)

    print(f"{'='*50}")
    print(f"NEW BROKERS QUALIFYING ({len(qualifying)}):")
    broker_rows = []
    for entry in sorted(qualifying, key=lambda e: -e["count"]):
        platforms = ", ".join(sorted(entry["platforms"]))
        zips_str  = ", ".join(sorted(entry["zips"])) or "zip unknown"
        print(f"  ✅ {entry['name'] or entry['email']} — {entry['brokerage'] or 'no brokerage'} "
              f"| {entry['count']} listing(s) on {platforms} | zips: {zips_str}")
        broker_rows.append(build_broker_row(entry))

    print(f"\nALREADY IN LIST ({len(already_in)} skipped):")
    for entry in already_in:
        print(f"  ↩️  {entry['name'] or entry['email']}")

    print(f"\nSINGLE-LISTING BROKERS ({len(single)} — not yet qualifying):")
    for entry in single[:10]:
        print(f"  —  {entry['name'] or entry['email']} | {', '.join(sorted(entry['platforms']))}")
    if len(single) > 10:
        print(f"  ... and {len(single) - 10} more")

    print(f"\n{'='*50}")
    if dry_run:
        print("[DRY RUN] No changes written.")
    elif broker_rows:
        append_rows(token, broker_rows)
        print(f"✅ {len(broker_rows)} new broker(s) added to Brokers List.")
        print(f"   https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}")
    else:
        print("No new brokers to add.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Olive Tree broker discovery")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print qualifying brokers without writing to sheet")
    parser.add_argument("--source", choices=["crexi", "loopnet", "fmls"],
                        help="Scan one platform only")
    parser.add_argument("--days", type=int, default=7,
                        help="Email alert lookback window in days (default 7)")
    args = parser.parse_args()
    run(dry_run=args.dry_run, source=args.source, days=args.days)
