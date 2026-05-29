#!/usr/bin/env python3
"""
Olive Tree Investments — Google Sheets Manager
Restructures and maintains the Deal Sourcing, Brokers List, Prop Mgt, and Reference tabs.

Usage:
  python3 scripts/sheets_update.py rebuild        # Full restructure + migrate existing data
  python3 scripts/sheets_update.py add-broker     # Add a new broker (interactive prompt)
  python3 scripts/sheets_update.py add-pm         # Add a new property manager (interactive)
  python3 scripts/sheets_update.py refresh-token  # Refresh the Google access token
"""

import json
import subprocess
import sys
import requests
from datetime import date

SPREADSHEET_ID = "1VxOlof56s8GosrWkSctL-FMm7AoJKJ6YtM3GllMKVH4"
BASE_URL = "https://sheets.googleapis.com/v4/spreadsheets"
TODAY = date.today().strftime("%m/%d/%Y")

# ─────────────────────────────────────────────
# Auth — pull token from gws CLI keyring
# ─────────────────────────────────────────────

def get_access_token():
    """Get a fresh access token via gws auth export + Google token endpoint."""
    try:
        result = subprocess.run(
            ["gws", "auth", "export", "--unmasked"],
            capture_output=True, text=True, check=True
        )
        creds = json.loads(result.stdout)
    except Exception as e:
        print(f"ERROR: Could not export gws credentials: {e}")
        print("Run: gws auth login -s sheets,drive")
        sys.exit(1)

    resp = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": creds["client_id"],
        "client_secret": creds["client_secret"],
        "refresh_token": creds["refresh_token"],
        "grant_type": "refresh_token",
    })
    resp.raise_for_status()
    return resp.json()["access_token"]


def headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ─────────────────────────────────────────────
# Sheets API helpers
# ─────────────────────────────────────────────

def get_sheet_ids(token):
    """Return {sheet_title: sheet_id} for all tabs."""
    r = requests.get(f"{BASE_URL}/{SPREADSHEET_ID}", headers=headers(token))
    r.raise_for_status()
    return {s["properties"]["title"]: s["properties"]["sheetId"]
            for s in r.json().get("sheets", [])}


def clear_and_write(token, sheet_name, rows):
    """Clear a sheet and write rows starting at A1."""
    # Clear
    requests.post(
        f"{BASE_URL}/{SPREADSHEET_ID}/values/{sheet_name}:clear",
        headers=headers(token)
    )
    # Write
    body = {"values": rows, "majorDimension": "ROWS"}
    r = requests.put(
        f"{BASE_URL}/{SPREADSHEET_ID}/values/{sheet_name}!A1",
        headers=headers(token),
        params={"valueInputOption": "USER_ENTERED"},
        json=body
    )
    r.raise_for_status()
    return r.json()


def append_row(token, sheet_name, row):
    """Append a single row to the bottom of a sheet."""
    body = {"values": [row], "majorDimension": "ROWS"}
    r = requests.post(
        f"{BASE_URL}/{SPREADSHEET_ID}/values/{sheet_name}!A1:append",
        headers=headers(token),
        params={"valueInputOption": "USER_ENTERED", "insertDataOption": "INSERT_ROWS"},
        json=body
    )
    r.raise_for_status()
    return r.json()


def format_sheet(token, sheet_id):
    """Bold + freeze header row, set font to Arial 10."""
    body = {"requests": [
        {
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1},
                "cell": {"userEnteredFormat": {
                    "textFormat": {"bold": True, "fontSize": 10, "fontFamily": "Arial"},
                    "backgroundColor": {"red": 0.18, "green": 0.31, "blue": 0.31},
                    "horizontalAlignment": "LEFT",
                }},
                "fields": "userEnteredFormat(textFormat,backgroundColor,horizontalAlignment)"
            }
        },
        {
            "updateSheetProperties": {
                "properties": {"sheetId": sheet_id, "gridProperties": {"frozenRowCount": 1}},
                "fields": "gridProperties.frozenRowCount"
            }
        },
        {
            "updateDimensionProperties": {
                "range": {"sheetId": sheet_id, "dimension": "ROWS",
                          "startIndex": 0, "endIndex": 1},
                "properties": {"pixelSize": 24},
                "fields": "pixelSize"
            }
        }
    ]}
    r = requests.post(
        f"{BASE_URL}/{SPREADSHEET_ID}:batchUpdate",
        headers=headers(token),
        json=body
    )
    r.raise_for_status()


def ensure_sheet_exists(token, title):
    """Create a new sheet tab if it doesn't exist. Returns sheet_id."""
    sheet_ids = get_sheet_ids(token)
    if title in sheet_ids:
        return sheet_ids[title]
    body = {"requests": [{"addSheet": {"properties": {"title": title}}}]}
    r = requests.post(f"{BASE_URL}/{SPREADSHEET_ID}:batchUpdate",
                      headers=headers(token), json=body)
    r.raise_for_status()
    return get_sheet_ids(token)[title]


# ─────────────────────────────────────────────
# Schema definitions
# ─────────────────────────────────────────────

DEAL_HEADERS = [
    "Market", "Zip Code", "Property Name", "Address", "Doors",
    "Asking Price", "Offer Price", "Price/Unit", "Vintage",
    "Cap Rate", "Gross Rent (Annual)", "NOI",
    "Platform", "Brokerage", "Broker Name", "Broker Email", "Broker Phone",
    "Stage", "Date Found", "Last Updated", "Notes"
]

BROKER_HEADERS = [
    "Brokerage", "Broker Name", "Email", "Phone",
    "Markets / Zips Covered", "Specialty",
    "Tier (A/B/C)", "Buy Box Sent", "# Deals Sent",
    "Last Contact", "Next Follow-Up", "Status", "Notes"
]

PM_HEADERS = [
    "Company", "Contact Name", "Email", "Phone",
    "Markets Covered", "Mgmt Fee %", "Units Under Mgmt",
    "Value-Add Experience", "Monthly Reporting",
    "Last Contact", "Status", "Notes"
]

# ─────────────────────────────────────────────
# Migrated data
# ─────────────────────────────────────────────

DEAL_DATA = [
    # Market | Zip | Name | Address | Doors | Asking | Offer | Price/Unit | Vintage | Cap Rate | Gross Rent | NOI | Platform | Brokerage | Broker | Email | Phone | Stage | Date Found | Last Updated | Notes
    ["Knoxville, TN", "37912", "Upchurch Rd Apartments", "", "14", "$1,550,000", "", "=IF(E2<>\"\",F2/E2,\"\")", "", "", "", "", "Crexi", "SVN", "Jon Roosen", "jon.roosen@svn.com", "865-202-6767", "Pass", "", TODAY, "Already renovated — not value add. Outside buy box (37912)."],
    ["Knoxville, TN", "37912", "Elyria Apartments", "", "16", "", "", "=IF(E3<>\"\",F3/E3,\"\")", "", "", "", "", "Crexi", "SVN", "Jon Roosen", "jon.roosen@svn.com", "865-202-6767", "Pass", "", TODAY, "Already renovated — not value add. Outside buy box (37912)."],
    ["Smyrna, GA", "30080", "", "641 Powder Springs St, Smyrna, GA 30080", "14", "$1,500,000", "$1,100,000", "=IF(E4<>\"\",F4/E4,\"\")", "", "", "", "", "Off-Market", "Bull Realty", "Andy Lundsberg", "", "", "In Progress", "", TODAY, "Value add on 10 of 14 units."],
    ["Carrollton, GA", "", "Harmony Oaks Apartments", "", "60", "$4,500,000", "$3,800,000", "=IF(E5<>\"\",F5/E5,\"\")", "", "", "", "", "Marcus & Millichap", "Marcus & Millichap", "Scott Spaulding", "", "678-776-5720", "In Progress", "", TODAY, "Value add on all units. Outside buy box (60 units, Carrollton)."],
]

BROKER_DATA = [
    # Brokerage | Name | Email | Phone | Markets/Zips | Specialty | Tier | Buy Box Sent | # Deals Sent | Last Contact | Next Follow-Up | Status | Notes
    ["SVN", "Jon Roosen", "jon.roosen@svn.com", "865-202-6767", "TN / GA — 37912", "Multifamily", "B", "No", "2", "05/12/2026", "", "Active", ""],
    ["Bull Realty", "Andy Lundsberg", "andy@bullrealty.com", "404-509-8533", "GA — 30080", "Multifamily", "A", "No", "1", "05/12/2026", "", "Active", "Value add on 10 of 14 units deal"],
    ["Marcus & Millichap", "Scott Spaulding", "Scott.Spalding@marcusmillichap.com", "678-776-5720", "GA", "Multifamily", "A", "No", "1", "05/12/2026", "", "Active", "Same team as Harold Shepard"],
    ["Marcus & Millichap", "Harold Shepard", "harold.shepard@marcusmillichap.com", "(503) 953-0085", "GA", "Multifamily", "A", "No", "0", "05/12/2026", "", "Active", "Same team as Scott Spaulding"],
    ["Marcus & Millichap", "Harrison Johnson", "Harrison.Johnson@marcusmillichap.com", "(615) 579-2147", "TN", "Multifamily", "B", "No", "0", "05/12/2026", "", "Active", ""],
    ["Cosgrove Group", "Patrick Cosgrove", "", "", "TN", "Multifamily", "B", "No", "0", "05/12/2026", "", "Active", ""],
    ["Mathews", "Connor Kerns", "", "", "Atlanta, GA", "Multifamily", "B", "No", "0", "05/12/2026", "", "Active", ""],
    ["Berkshire Hathaway Home Services", "Willie Acree", "willie.acree@bhhsgeorgia.com", "(404) 954-2430", "GA", "Multifamily", "B", "Yes", "0", "05/12/2026", "", "Active", "Sent buy box"],
    ["Skyline Realty Group", "Karen Stephens", "", "", "GA", "Multifamily", "C", "No", "0", "", "", "Emailed", ""],
    ["GREA", "", "mack.leath@grea.com", "404-909-5171", "GA", "Multifamily", "C", "No", "0", "", "", "Emailed", "50+ units only — outside buy box"],
    ["PWA Properties", "Kevin Tipton", "kevin@pwa-properties.com", "865-210-0228", "TN", "Multifamily", "B", "No", "0", "05/12/2026", "", "Active", ""],
    ["Watts Realty", "Chip Watts", "chip@wattsrealty.com", "(205) 966-1908", "AL", "Multifamily", "B", "No", "0", "05/12/2026", "", "Active", "Also: jcmorris@wattsrealty.com"],
    ["Atlanta Leasing & Investment", "Stephan Dickie", "stephan@atlantaleasing.com", "470-983-9993", "GA", "Multifamily", "B", "No", "0", "05/12/2026", "", "Active", ""],
]

PM_DATA = [
    # Company | Contact | Email | Phone | Markets | Fee% | Units | Value-Add | Monthly Reporting | Last Contact | Status | Notes
    ["PMI Terminus", "Trizzia", "", "770-618-9225", "Smyrna, GA", "", "", "", "", "", "Active", ""],
    ["KeyRenter Marietta", "Andy", "", "404-800-1818", "Marietta, GA", "", "", "", "", "", "Active", ""],
]

REFERENCE_DATA = [
    ["OLIVE TREE INVESTMENTS — REFERENCE DATA", "", "", ""],
    ["", "", "", ""],
    ["ACTIVE BUY BOX MARKETS", "", "", ""],
    ["Tier", "Market", "Zip", "Strategy"],
    ["Primary", "Chamblee, GA", "30341", "Value-add — BEST upside"],
    ["Primary", "Smyrna, GA", "30080", "Stabilized w/ upside — BEST balance"],
    ["Primary", "Alpharetta, GA", "30005", "Long-term hold — BEST quality"],
    ["Secondary", "North Nashville, TN", "37207", "Value-add / Emerging"],
    ["Secondary", "Madison, TN", "37115", "Stable workforce / Cash flow"],
    ["Secondary", "Chattanooga Southside, TN", "37408", "Selective / Off-market only"],
    ["Secondary", "Huntsville Core, AL", "35801", "Quality + operational upside"],
    ["Secondary", "Birmingham Urban, AL", "35205", "Value-add / Transitional"],
    ["Secondary", "Huntsville Growth Corridor, AL", "35806", "Growth corridor / Light value-add"],
    ["", "", "", ""],
    ["EXPENSE RATIO BENCHMARKS (when no financials provided)", "", "", ""],
    ["Vintage", "Expense Ratio Range", "", ""],
    ["< 1980", "45–52%", "", ""],
    ["1980–2000", "38–45%", "", ""],
    [">= 2000", "25–38%", "", ""],
    ["", "", "", ""],
    ["EXPENSE RATIO ADJUSTMENT FACTORS", "", "", ""],
    ["Factor", "Direction", "", ""],
    ["Deferred maintenance", "Push ratio UP", "", ""],
    ["Fully renovated", "Bring ratio DOWN", "", ""],
    ["Owner pays water/sewer/trash", "Push ratio UP", "", ""],
    ["RUBS in place", "Bring ratio DOWN", "", ""],
    ["Under-assessed property taxes (will reset at purchase)", "Push ratio UP", "", ""],
    ["PM fee missing from T12", "Push ratio UP (add 3–5%)", "", ""],
    ["Asset mgmt fee missing", "Push ratio UP (add 1–2%)", "", ""],
    ["", "", "", ""],
    ["DEAL STAGE DEFINITIONS", "", "", ""],
    ["Stage", "Meaning", "", ""],
    ["New", "Just came in — not yet reviewed", "", ""],
    ["Reviewing", "OM / financials in hand — underwriting in progress", "", ""],
    ["Offer Made", "LOI or verbal offer submitted", "", ""],
    ["In Progress", "Active back-and-forth with seller/broker", "", ""],
    ["Under Contract", "PSA signed", "", ""],
    ["Pass", "Reviewed and passed — reason noted in Notes column", "", ""],
    ["", "", "", ""],
    ["BROKER TIER DEFINITIONS", "", "", ""],
    ["Tier", "Meaning", "", ""],
    ["A", "Active relationship — sending deals, responding quickly", "", ""],
    ["B", "Contacted, responded — not yet sending consistent deal flow", "", ""],
    ["C", "Cold — emailed once, no response or outside focus", "", ""],
    ["", "", "", ""],
    ["UNIVERSAL DEAL FILTER", "", "", ""],
    ["Criterion", "Requirement", "", ""],
    ["Unit count", "15–50 units", "", ""],
    ["Property type", "Multifamily only", "", ""],
    ["Strategy", "Value-add or stabilized with operational upside", "", ""],
    ["Hold period", "4–6 years", "", ""],
    ["Return target", "18.21% annual ROI / 2.09x equity multiple", "", ""],
    ["Preferred return", "6% pref, then 70/30 LP/GP", "", ""],
    ["Min investment", "$25K per LP", "", ""],
]


# ─────────────────────────────────────────────
# Commands
# ─────────────────────────────────────────────

def cmd_rebuild():
    print("Getting access token...")
    token = get_access_token()

    print("Reading sheet IDs...")
    sheet_ids = get_sheet_ids(token)

    # Ensure Reference tab exists
    ref_id = ensure_sheet_exists(token, "Reference")
    sheet_ids = get_sheet_ids(token)

    sheets = {
        "Deal Sourcing": (DEAL_HEADERS, DEAL_DATA),
        "Brokers List":  (BROKER_HEADERS, BROKER_DATA),
        "Prop Mgt":      (PM_HEADERS, PM_DATA),
        "Reference":     ([], REFERENCE_DATA),
    }

    for sheet_name, (headers_row, data_rows) in sheets.items():
        print(f"Rebuilding: {sheet_name}...")
        rows = ([headers_row] + data_rows) if headers_row else data_rows
        clear_and_write(token, sheet_name, rows)
        sid = sheet_ids.get(sheet_name)
        if sid is not None and headers_row:
            format_sheet(token, sid)

    print("\n✅ Done. All 4 tabs rebuilt:")
    print("   • Deal Sourcing  — 4 deals migrated, new schema applied")
    print("   • Brokers List   — 13 brokers migrated, new schema applied")
    print("   • Prop Mgt       — 2 PMs migrated, new schema applied")
    print("   • Reference      — market data, expense ratios, stage + tier defs")
    print("\nNote: Price/Unit column uses a formula (=Asking/Doors) — fill in Doors + Asking Price to see it calculate.")


def cmd_add_broker():
    print("\n── Add New Broker ──────────────────────────")
    fields = [
        ("Brokerage", ""),
        ("Broker Name", ""),
        ("Email", ""),
        ("Phone", ""),
        ("Markets / Zips Covered", "e.g. GA — 30341, 30080"),
        ("Specialty", "Multifamily / Mixed / SF"),
        ("Tier (A/B/C)", "B"),
        ("Buy Box Sent", "No"),
        ("# Deals Sent", "0"),
        ("Status", "Active"),
        ("Notes", ""),
    ]
    row = []
    for label, placeholder in fields:
        val = input(f"  {label}{' (' + placeholder + ')' if placeholder else ''}: ").strip()
        row.append(val if val else placeholder)

    # Insert today's date for Last Contact, leave Next Follow-Up blank
    row.insert(9, TODAY)   # Last Contact
    row.insert(10, "")     # Next Follow-Up

    token = get_access_token()
    append_row(token, "Brokers List", row)
    print(f"\n✅ {row[1]} ({row[0]}) added to Brokers List.")


def cmd_add_pm():
    print("\n── Add New Property Manager ────────────────")
    fields = [
        ("Company", ""),
        ("Contact Name", ""),
        ("Email", ""),
        ("Phone", ""),
        ("Markets Covered", "e.g. Smyrna, GA / Huntsville, AL"),
        ("Mgmt Fee %", "e.g. 8%"),
        ("Units Under Mgmt", ""),
        ("Value-Add Experience", "Yes / No / Unknown"),
        ("Monthly Reporting", "Yes / No / Unknown"),
        ("Status", "Active"),
        ("Notes", ""),
    ]
    row = []
    for label, placeholder in fields:
        val = input(f"  {label}{' (' + placeholder + ')' if placeholder else ''}: ").strip()
        row.append(val if val else placeholder)

    row.insert(9, TODAY)  # Last Contact

    token = get_access_token()
    append_row(token, "Prop Mgt", row)
    print(f"\n✅ {row[0]} added to Prop Mgt.")


def cmd_refresh_token():
    token = get_access_token()
    print(f"✅ Token refreshed successfully. (first 20 chars: {token[:20]}...)")


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────

COMMANDS = {
    "rebuild":       cmd_rebuild,
    "add-broker":    cmd_add_broker,
    "add-pm":        cmd_add_pm,
    "refresh-token": cmd_refresh_token,
}

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "rebuild"
    if cmd not in COMMANDS:
        print(f"Unknown command: {cmd}")
        print(f"Available: {', '.join(COMMANDS)}")
        sys.exit(1)
    COMMANDS[cmd]()
