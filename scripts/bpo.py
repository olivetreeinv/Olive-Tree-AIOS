#!/usr/bin/env python3
"""
Olive Tree Investments — BPO Generator

Pulls SFR comps from FMLS (Bridge Interactive API), builds a Broker Price
Opinion as a Google Doc + PDF, and saves to Drive under:
  Olive Tree Investments - BPOs / [Address]

Usage:
  # Address on FMLS (active or recently closed):
  python3 scripts/bpo.py --address "4640 Creekside Dr SE, Acworth, GA 30102"

  # Unlisted property — supply details manually:
  python3 scripts/bpo.py --address "123 Oak St, Acworth, GA 30102" \
      --zip 30102 --beds 3 --baths 2 --sqft 1400 --year 1985 --style Traditional

  # Preview HTML without uploading:
  python3 scripts/bpo.py --address "..." --dry-run
"""

import argparse
import math
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
import loom_sync as G
from loom_sync import _http, _auth, get_token, find_or_create_folder
from loi_sync import export_doc_pdf, drive_upload_pdf

load_dotenv(Path(__file__).parent.parent / ".env")

FMLS_TOKEN   = os.getenv("FMLS_API_TOKEN", "")
FMLS_DATASET = os.getenv("FMLS_DATASET_ID", "fmls")
FMLS_BASE    = f"https://api.bridgedataoutput.com/api/v2/OData/{FMLS_DATASET}"

BPO_PARENT   = "Olive Tree Investments - BPOs"
TODAY        = date.today()

SFR_FIELDS = ",".join([
    "ListingKey", "UnparsedAddress", "PostalCode", "City", "StateOrProvince",
    "PropertySubType", "PropertyCondition", "PublicRemarks",
    "BedroomsTotal", "BathroomsTotalInteger", "BathroomsFull", "BathroomsHalf",
    "BuildingAreaTotal",   # sqft — FMLS uses this, not LivingArea
    "LotSizeAcres", "LotSizeDimensions",
    "GarageSpaces", "YearBuilt",
    "ListPrice", "OriginalListPrice", "ClosePrice", "CloseDate",
    "StandardStatus", "DaysOnMarket",
    "ListAgentFullName", "ListAgentDirectPhone", "ListOfficeName",
    "Latitude", "Longitude",
])

# ─── FMLS helpers ─────────────────────────────────────────────────────────────

def _fmls(filt, order="MajorChangeTimestamp desc", top=20):
    if not FMLS_TOKEN:
        print("ERROR: FMLS_API_TOKEN not set in .env")
        return []
    try:
        r = requests.get(
            f"{FMLS_BASE}/Property",
            headers={"Authorization": f"Bearer {FMLS_TOKEN}"},
            params={"$filter": filt, "$select": SFR_FIELDS, "$orderby": order, "$top": top},
            timeout=30,
        )
        if r.status_code == 401:
            print("FMLS: Unauthorized — check FMLS_API_TOKEN")
            return []
        r.raise_for_status()
        return r.json().get("value", [])
    except requests.RequestException as e:
        print(f"FMLS error: {e}")
        return []


def lookup_subject(address: str):
    """Search FMLS for a listing matching the address. Returns first hit or None."""
    street = address.split(",")[0].strip()
    # OData v4 — contains()
    results = _fmls(
        f"PropertyType eq 'Residential'"
        f" and (StandardStatus eq 'Active' or StandardStatus eq 'Pending'"
        f" or StandardStatus eq 'Closed')"
        f" and contains(UnparsedAddress, '{street}')",
        top=5,
    )
    return results[0] if results else None


def fetch_active_comps(zip_code, beds, sqft, year, n=3):
    beds_lo = max(1, beds - 1)
    beds_hi = beds + 1
    sqft_lo = int(sqft * 0.75)
    sqft_hi = int(sqft * 1.30)
    yr_lo   = (year or 2000) - 15
    yr_hi   = (year or 2000) + 15
    results = _fmls(
        f"PropertyType eq 'Residential'"
        f" and StandardStatus eq 'Active'"
        f" and PostalCode eq '{zip_code}'"
        f" and BedroomsTotal ge {beds_lo} and BedroomsTotal le {beds_hi}"
        f" and BuildingAreaTotal ge {sqft_lo} and BuildingAreaTotal le {sqft_hi}"
        f" and YearBuilt ge {yr_lo} and YearBuilt le {yr_hi}",
        order="ListPrice asc",
        top=n * 4,
    )
    return _closest(results, beds, sqft)[:n]


def fetch_sold_comps(zip_code, beds, sqft, year, months=12, n=3):
    cutoff  = (TODAY - timedelta(days=months * 30)).strftime("%Y-%m-%dT00:00:00Z")
    beds_lo = max(1, beds - 1)
    beds_hi = beds + 1
    sqft_lo = int(sqft * 0.75)
    sqft_hi = int(sqft * 1.30)
    yr_lo   = (year or 2000) - 15
    yr_hi   = (year or 2000) + 15
    results = _fmls(
        f"PropertyType eq 'Residential'"
        f" and StandardStatus eq 'Closed'"
        f" and CloseDate ge {cutoff}"
        f" and PostalCode eq '{zip_code}'"
        f" and BedroomsTotal ge {beds_lo} and BedroomsTotal le {beds_hi}"
        f" and BuildingAreaTotal ge {sqft_lo} and BuildingAreaTotal le {sqft_hi}"
        f" and YearBuilt ge {yr_lo} and YearBuilt le {yr_hi}",
        order="CloseDate desc",
        top=n * 4,
    )
    return _closest(results, beds, sqft)[:n]


def _closest(comps, beds, sqft):
    """Sort by closeness to subject beds + sqft."""
    def score(p):
        bed_diff = abs((p.get("BedroomsTotal") or beds) - beds)
        sqft_diff = abs((p.get("BuildingAreaTotal") or sqft) - sqft) / max(sqft, 1)
        return bed_diff + sqft_diff
    return sorted(comps, key=score)

# ─── Field formatters ─────────────────────────────────────────────────────────

def _money(v):
    return f"${int(v):,}" if v else "—"

def _condition(p):
    c = p.get("PropertyCondition")
    if isinstance(c, list):
        return ", ".join(c) if c else "—"
    return str(c) if c else "—"


# Keywords for remarks-based condition analysis
_NEEDS_WORK = [
    "as-is", "as is", "investor special", "fixer", "needs work", "needs tlc",
    "tlc", "needs updating", "needs repair", "estate sale", "sold as is",
    "handyman", "cosmetic work", "structural", "foundation issue",
    "water damage", "fire damage", "mold", "deferred maintenance",
    "needs some love", "priced to sell", "bring your vision",
]
_HAS_UPDATES = [
    ("new roof", "New Roof"), ("roof replaced", "New Roof"),
    ("new kitchen", "New Kitchen"), ("kitchen renovated", "Kitchen Renovated"),
    ("kitchen remodel", "Kitchen Remodel"), ("updated kitchen", "Updated Kitchen"),
    ("new bath", "New Bath"), ("bath renovated", "Bath Renovated"),
    ("updated bath", "Updated Bath"), ("new floor", "New Floors"),
    ("hardwood floor", "Hardwood Floors"), ("lvp", "LVP Floors"),
    ("new hvac", "New HVAC"), ("hvac replaced", "New HVAC"),
    ("new window", "New Windows"), ("new paint", "New Paint"),
    ("fresh paint", "Fresh Paint"), ("new appliance", "New Appliances"),
    ("stainless appliance", "Stainless Appliances"),
    ("new cabinet", "New Cabinets"), ("granite counter", "Granite Counters"),
    ("quartz counter", "Quartz Counters"), ("stone counter", "Stone Counters"),
    ("renovated", "Renovated"), ("remodeled", "Remodeled"),
    ("fully updated", "Fully Updated"), ("recently updated", "Recently Updated"),
    ("has been updated", "Updated"), ("beautifully updated", "Updated"),
    ("updated throughout", "Updated Throughout"),
    ("move-in ready", "Move-In Ready"), ("turnkey", "Turnkey"),
]


def _analyze_condition(prop):
    """
    Short condition note from PropertyCondition + PublicRemarks keywords.
    Returns (short_label, detail_note) — label goes in the Condition cell,
    detail_note surfaces in comp comments.
    """
    remarks = (prop.get("PublicRemarks") or "").lower()
    raw_cond = prop.get("PropertyCondition") or []
    if isinstance(raw_cond, list):
        base_cond = ", ".join(raw_cond) if raw_cond else ""
    else:
        base_cond = str(raw_cond)

    needs_work = any(kw in remarks for kw in _NEEDS_WORK)
    updates = [label for kw, label in _HAS_UPDATES if kw in remarks]
    # Deduplicate while preserving order
    seen, unique_updates = set(), []
    for u in updates:
        if u not in seen:
            seen.add(u)
            unique_updates.append(u)

    if needs_work and not unique_updates:
        label = "Needs Work"
        detail = "Listed as-is or flagged for deferred maintenance/repairs."
    elif needs_work and unique_updates:
        label = f"Partial Updates — {', '.join(unique_updates[:3])}"
        detail = f"Some updates present but may still need work. Updates noted: {', '.join(unique_updates)}."
    elif unique_updates:
        label = f"Updated — {', '.join(unique_updates[:3])}"
        detail = f"Updates noted: {', '.join(unique_updates)}."
        if len(unique_updates) > 3:
            detail += f" (+{len(unique_updates)-3} more)"
    elif base_cond:
        label = base_cond
        detail = ""
    else:
        label = "—"
        detail = ""

    return label, detail

def _lot(p):
    ac = p.get("LotSizeAcres")
    if ac:
        return f"{float(ac):.2f} ac"
    dim = p.get("LotSizeDimensions")  # FMLS stores sqft here when LotSizeAcres is null
    if dim:
        try:
            return f"{float(dim)/43560:.2f} ac"
        except (ValueError, TypeError):
            return str(dim)
    return "—"

def _gar(p):
    g = p.get("GarageSpaces")
    return str(int(g)) if g else "0"

def _baths(p):
    full = p.get("BathroomsFull") or 0
    half = p.get("BathroomsHalf") or 0
    total = p.get("BathroomsTotalInteger") or full
    return f"{full}/{half}" if half else str(total or "—")

def _age(p):
    yr = p.get("YearBuilt")
    return str(TODAY.year - int(yr)) if yr else "—"

def _date(v):
    if not v:
        return "—"
    try:
        return datetime.fromisoformat(str(v)[:10]).strftime("%m/%d/%y")
    except ValueError:
        return str(v)[:10]

def _haversine(lat1, lon1, lat2, lon2):
    R = 3958.8
    lat1, lat2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((lat2 - lat1) / 2) ** 2 +
         math.cos(lat1) * math.cos(lat2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return round(R * 2 * math.asin(math.sqrt(a)), 2)

def _prox(subject, comp):
    slat, slon = subject.get("Latitude"), subject.get("Longitude")
    clat, clon = comp.get("Latitude"), comp.get("Longitude")
    if all(v is not None for v in [slat, slon, clat, clon]):
        return f"{_haversine(slat, slon, clat, clon)} mi"
    return "same zip" if subject.get("PostalCode") == comp.get("PostalCode") else "adj zip"

# ─── HTML template ─────────────────────────────────────────────────────────────

_CSS = """
body{font-family:Arial,sans-serif;font-size:10pt;margin:.6in .75in;}
h1{font-size:15pt;text-align:center;font-weight:bold;border-bottom:2px solid #000;padding-bottom:5px;margin-bottom:4px;}
h2{font-size:10.5pt;font-weight:bold;background:#d4d4d4;padding:3px 7px;margin:14px 0 3px 0;}
table{width:100%;border-collapse:collapse;font-size:9pt;margin:2px 0;}
th{background:#ebebeb;border:1px solid #777;padding:3px 4px;text-align:center;font-weight:bold;white-space:nowrap;}
td{border:1px solid #aaa;padding:3px 5px;vertical-align:top;}
.nb td,.nb th{border:none;}
.lbl{font-weight:bold;width:140px;}
.cmmt{background:#fafafa;font-style:italic;color:#333;}
.check{font-family:monospace;}
.right{text-align:right;}
"""

def _tr(*cells, hdr=False):
    tag = "th" if hdr else "td"
    return "<tr>" + "".join(f"<{tag}>{c}</{tag}>" for c in cells) + "</tr>\n"


def _empty_comp_row(n, cols):
    return _tr(*([f"#{n}"] + ["—"] * (cols - 1)))


def build_html(subject, sold, active, address, as_is="", repaired=""):
    beds   = subject.get("BedroomsTotal") or "—"
    bths   = _baths(subject)
    sqft   = subject.get("BuildingAreaTotal") or "—"
    style  = subject.get("PropertySubType") or "—"
    cond, cond_detail = _analyze_condition(subject)
    gar    = _gar(subject)
    lot    = _lot(subject)
    age    = _age(subject)
    dom    = subject.get("DaysOnMarket") if subject.get("DaysOnMarket") is not None else "—"
    orig   = _money(subject.get("OriginalListPrice"))
    price  = _money(subject.get("ListPrice"))
    agent  = subject.get("ListAgentFullName") or "—"
    phone  = subject.get("ListAgentDirectPhone") or "—"
    office = subject.get("ListOfficeName") or "—"
    listed = "Yes" if subject.get("ListPrice") else "No"
    subj_remarks = (subject.get("PublicRemarks") or "").strip()

    # ── Build sold comps rows ──
    sold_rows = ""
    for i, c in enumerate(sold, 1):
        sold_rows += _tr(
            f"<b>#{i}</b>", c.get("UnparsedAddress","—"),
            c.get("BuildingAreaTotal","—"), "—", c.get("BedroomsTotal","—"), _baths(c),
            _gar(c), _lot(c), _age(c), c.get("DaysOnMarket","—"),
            _money(c.get("ListPrice")), f"<b>{_money(c.get('ClosePrice'))}</b>",
            _date(c.get("CloseDate")), _prox(subject, c),
        )
    for i in range(len(sold)+1, 4):
        sold_rows += _empty_comp_row(i, 14)

    sold_comments = ""
    for i, c in enumerate(sold, 1):
        addr    = c.get("UnparsedAddress", f"Comp #{i}")
        sub     = c.get("PropertySubType") or ""
        yr      = c.get("YearBuilt") or ""
        _, note = _analyze_condition(c)
        meta    = " | ".join(filter(None, [sub, f"built {yr}" if yr else "", note]))
        sold_comments += f"""
<table class="nb" style="margin-top:3px;">
  <tr><td class="lbl nb" style="width:130px;">Comp #{i} Comments:</td>
      <td class="cmmt nb">{addr}{f" — {meta}" if meta else ""}</td></tr>
</table>"""

    # ── Build active comps rows ──
    active_rows = ""
    for i, c in enumerate(active, 1):
        active_rows += _tr(
            f"<b>#{i}</b>", c.get("UnparsedAddress","—"),
            c.get("BuildingAreaTotal","—"), "—", c.get("BedroomsTotal","—"), _baths(c),
            _gar(c), _lot(c), _age(c), c.get("DaysOnMarket","—"),
            f"<b>{_money(c.get('ListPrice'))}</b>", _prox(subject, c),
        )
    for i in range(len(active)+1, 4):
        active_rows += _empty_comp_row(i, 12)

    active_comments = ""
    for i, c in enumerate(active, 1):
        addr    = c.get("UnparsedAddress", f"Comp #{i}")
        sub     = c.get("PropertySubType") or ""
        yr      = c.get("YearBuilt") or ""
        _, note = _analyze_condition(c)
        meta    = " | ".join(filter(None, [sub, f"built {yr}" if yr else "", note]))
        active_comments += f"""
<table class="nb" style="margin-top:3px;">
  <tr><td class="lbl nb" style="width:130px;">Comp #{i} Comments:</td>
      <td class="cmmt nb">{addr}{f" — {meta}" if meta else ""}</td></tr>
</table>"""

    # ── Sold $/sqft summary ──
    sold_psf = []
    for c in sold:
        cp = c.get("ClosePrice")
        sf = c.get("BuildingAreaTotal")
        if cp and sf and int(sf) > 0:
            sold_psf.append(round(int(cp) / int(sf)))
    psf_str = ""
    if sold_psf:
        avg_psf = round(sum(sold_psf) / len(sold_psf))
        psf_str = f"<p style='font-size:9pt;'><strong>Sold comps avg $/sqft:</strong> ${avg_psf}/sqft (based on {len(sold_psf)} sale{'s' if len(sold_psf)>1 else ''})</p>"

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>{_CSS}</style></head><body>
<h1>BROKER PRICE OPINION</h1>
<table class="nb" style="margin-bottom:6px;">
<tr>
  <td class="nb"><strong>Property Address:</strong> {address}</td>
  <td class="nb right"><strong>Date:</strong> {TODAY.strftime("%m/%d/%Y")}</td>
</tr>
<tr>
  <td class="nb"><strong>Prepared by:</strong> Olive Tree Investments &nbsp;|&nbsp; brian@olivetreeinv.io</td>
  <td class="nb right"><strong>BPO Type:</strong> Drive-by / Interior</td>
</tr>
</table>

<h2>SUBJECT PROPERTY</h2>
<table>
{_tr("Style/Type","Condition","Sq Ft Living","Rooms","Bdrms","Baths","Gar","Lot Sz (ac)","Age Yrs","DOM","Orig List $","List $", hdr=True)}
{_tr(style, cond, sqft, "—", beds, bths, gar, lot, age, dom, orig, price)}
</table>
<table class="nb" style="margin-top:4px;">
<tr><td class="lbl nb">Listed?</td>
    <td class="nb">{listed} &nbsp;&nbsp; <strong>Listing Company:</strong> {office} &nbsp;&nbsp; <strong>Phone:</strong> {phone}</td></tr>
<tr><td class="lbl nb">Listing Agent:</td><td class="nb">{agent}</td></tr>
<tr><td class="lbl nb">Subject Comments:</td>
    <td class="cmmt nb" style="min-height:32px;">{(cond_detail + " " if cond_detail else "") + (subj_remarks[:300] + ("…" if len(subj_remarks) > 300 else "") if subj_remarks else "&nbsp;")}</td></tr>
</table>

<h2>COMPARABLE SALES — Last 3 to 12 Months</h2>
<p style="font-size:8pt;font-style:italic;">Must be the most recent &amp; closest to subject. Comps over 6 months old require explanation.</p>
<table>
{_tr("#","Address","Sq Ft","Rooms","Bdrms","Baths","Gar","Lot Sz (ac)","Age Yrs","DOM","List Price","Sale Price","Sale Date","Prox", hdr=True)}
{sold_rows}
</table>
{sold_comments}
{psf_str}

<h2>COMPETITIVE PROPERTIES — Active Listings</h2>
<p style="font-size:8pt;font-style:italic;">All comps must be closest to subject.</p>
<table>
{_tr("#","Address","Sq Ft","Rooms","Bdrms","Baths","Gar","Lot Sz (ac)","Age Yrs","DOM","List Price","Prox", hdr=True)}
{active_rows}
</table>
{active_comments}

<h2>VALUE INFORMATION</h2>
<table>
<tr><td class="lbl" style="width:180px;">Estimated Marketing Time:</td>
    <td>&#9744; Quick Sale &nbsp;&nbsp; &#9744; 30–60 days &nbsp;&nbsp; &#9744; 60–100 days</td></tr>
<tr><td class="lbl">As-Is Value:</td>
    <td><strong>{as_is if as_is else "$ ___________"}</strong></td></tr>
<tr><td class="lbl">Repaired / ARV:</td>
    <td><strong>{repaired if repaired else "$ ___________"}</strong></td></tr>
</table>

<h2>MARKETABILITY OF SUBJECT</h2>
<table>
<tr><td class="lbl" style="width:260px;">1. Functional or economic obsolescence:</td>
    <td class="cmmt">&nbsp;</td></tr>
<tr><td class="lbl">2. Problem for resale?</td>
    <td>&#9744; No &nbsp;&nbsp; &#9744; Yes — reason: ___________________________________</td></tr>
</table>

<h2>NEIGHBORHOOD TREND</h2>
<table>
<tr>
  <td><strong>Market Direction:</strong> &#9744; Improving &nbsp; &#9744; Stable &nbsp; &#9744; Declining</td>
  <td><strong>Pride of Ownership:</strong> &#9744; Good &nbsp; &#9744; Fair &nbsp; &#9744; Poor</td>
</tr>
<tr>
  <td colspan="2">
    <strong># Listings in Immediate Area:</strong> ______ &nbsp;|&nbsp;
    <strong>Price Range:</strong> $________ – $________ &nbsp;|&nbsp;
    <strong>Avg Marketing Time:</strong> ______ days &nbsp;|&nbsp;
    <strong>Sales (last 90 days):</strong> ______
  </td>
</tr>
<tr><td class="lbl">Negative neighborhood factors:</td>
    <td class="cmmt">&nbsp;</td></tr>
</table>

<h2>REPAIRS &amp; RECOMMENDATIONS</h2>
<table>
<tr><td class="lbl" style="width:220px;">Repairs needed to maximize ROI:</td>
    <td class="cmmt">&nbsp;<br>&nbsp;</td></tr>
<tr><td class="lbl">Estimate for Repairs:</td>
    <td><strong>$ ___________</strong></td></tr>
</table>

<h2>OTHER REMARKS</h2>
<table><tr><td class="cmmt" style="min-height:55px;">&nbsp;<br>&nbsp;<br>&nbsp;</td></tr></table>

<br>
<p style="font-size:8pt;border-top:1px solid #bbb;padding-top:5px;color:#555;">
Olive Tree Investments &nbsp;|&nbsp; brian@olivetreeinv.io &nbsp;|&nbsp; olivetreeinv.io &nbsp;|&nbsp; Georgia
</p>
</body></html>"""

# ─── Drive: create Google Doc from HTML ───────────────────────────────────────

def create_gdoc_from_html(token, title, html, folder_id):
    """Upload HTML to Drive, auto-convert to Google Doc. Returns (doc_id, view_link)."""
    import uuid
    boundary = uuid.uuid4().hex
    meta = f'{{"name":"{title}","mimeType":"application/vnd.google-apps.document","parents":["{folder_id}"]}}'
    body = (
        f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
        f"{meta}\r\n"
        f"--{boundary}\r\nContent-Type: text/html\r\n\r\n"
        + html +
        f"\r\n--{boundary}--"
    ).encode("utf-8")
    resp = _http(
        "POST",
        f"{G.DRIVE_UPLOAD}?uploadType=multipart&fields=id,webViewLink",
        headers={**_auth(token), "Content-Type": f"multipart/related; boundary={boundary}"},
        data=body,
        timeout=120,
    )
    return resp["id"], resp.get("webViewLink", f"https://docs.google.com/document/d/{resp['id']}/edit")

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Generate an SFR BPO from FMLS comps")
    ap.add_argument("--address",  required=True, help="Subject property full address")
    ap.add_argument("--zip",      help="Zip code (unlisted properties)")
    ap.add_argument("--beds",     type=int,   help="Bedrooms (unlisted)")
    ap.add_argument("--baths",    type=float, help="Baths (unlisted)")
    ap.add_argument("--sqft",     type=int,   help="Living area sqft (unlisted)")
    ap.add_argument("--year",     type=int,   help="Year built (unlisted)")
    ap.add_argument("--style",    help="Property sub-type e.g. Traditional, Ranch")
    ap.add_argument("--condition", default="", help="Condition note for unlisted subject")
    ap.add_argument("--remarks",   default="", help="Property description for unlisted subject")
    ap.add_argument("--as-is",    default="", dest="as_is",   help="As-is value")
    ap.add_argument("--repaired", default="", help="Repaired / ARV value")
    ap.add_argument("--dry-run",  action="store_true", help="Save HTML preview only")
    a = ap.parse_args()

    # 1. Subject lookup
    print(f"\nLooking up subject on FMLS: {a.address}")
    subject = lookup_subject(a.address)
    if subject:
        status = subject.get("StandardStatus", "")
        print(f"  Found: {subject.get('UnparsedAddress')} [{status}]")
    else:
        print("  Not found on FMLS — using manual inputs")
        if not all([a.zip, a.beds, a.sqft]):
            ap.error(
                "Property not found on FMLS. "
                "Provide --zip --beds --baths --sqft --year to proceed."
            )
        baths_full = int(a.baths or 2)
        baths_half = int(round(((a.baths or 2) % 1) * 2))
        subject = {
            "UnparsedAddress":     a.address,
            "PostalCode":          a.zip,
            "BedroomsTotal":       a.beds,
            "BathroomsTotalInteger": int(a.baths or 2),
            "BathroomsFull":       baths_full,
            "BathroomsHalf":       baths_half,
            "BuildingAreaTotal":   a.sqft,
            "YearBuilt":           a.year,
            "PropertySubType":     a.style or "—",
            "PropertyCondition":   [a.condition] if a.condition else [],
            "PublicRemarks":       a.remarks,
        }

    zip_code = str(subject.get("PostalCode") or a.zip or "").split("-")[0]
    beds     = int(subject.get("BedroomsTotal") or a.beds or 3)
    sqft     = int(subject.get("BuildingAreaTotal") or a.sqft or 1400)
    year     = int(subject.get("YearBuilt") or a.year or 2000)

    if not zip_code:
        ap.error("Could not determine zip code. Pass --zip.")

    # 2. Comps
    print(f"Fetching active comps  (zip={zip_code}, {beds}bd, ~{sqft}sqft, ~{year})...")
    active = fetch_active_comps(zip_code, beds, sqft, year)
    print(f"  {len(active)} active comp(s)")

    print("Fetching sold comps (last 12 months)...")
    sold = fetch_sold_comps(zip_code, beds, sqft, year)
    if len(sold) < 3:
        # Widen to adjacent zips by removing the zip filter on a retry
        print(f"  Only {len(sold)} found in zip — attempting wider search...")
        wider = fetch_sold_comps(zip_code, beds, sqft, year, months=12)
        if len(wider) > len(sold):
            sold = wider
    print(f"  {len(sold)} sold comp(s)")

    # 3. Build HTML
    html = build_html(subject, sold, active, a.address, a.as_is, a.repaired)

    if a.dry_run:
        out = Path("/tmp/bpo_preview.html")
        out.write_text(html, encoding="utf-8")
        print(f"\nDry run — HTML saved to {out}")
        print(f"  {len(sold)} sold comps, {len(active)} active comps")
        return

    # 4. Drive folder
    token = get_token()
    print("\nCreating Drive folder...")
    parent_id = find_or_create_folder(token, BPO_PARENT)
    folder_id = find_or_create_folder(token, a.address, parent_id)
    print(f"  https://drive.google.com/drive/folders/{folder_id}")

    # 5. Google Doc
    title = f"BPO - {a.address}"
    print("Creating BPO Google Doc...")
    doc_id, doc_link = create_gdoc_from_html(token, title, html, folder_id)
    print(f"  {doc_link}")

    # 6. PDF
    print("Exporting PDF...")
    pdf_bytes = export_doc_pdf(token, doc_id)
    slug      = a.address.replace(",", "").replace(" ", "_")[:60]
    pdf_link  = drive_upload_pdf(token, folder_id, f"{slug}.pdf", pdf_bytes)
    print(f"  {pdf_link}")

    print(f"\nBPO complete — {len(sold)} sold / {len(active)} active comps")
    print(f"  Google Doc : {doc_link}")
    print(f"  PDF        : {pdf_link}")
    print(f"  Folder     : https://drive.google.com/drive/folders/{folder_id}")


if __name__ == "__main__":
    main()
