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
import re
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

# ─── CMA cross-reference ──────────────────────────────────────────────────────
# Adjusted-comp CMA from the same FMLS sold data (Bridge has no CMA endpoint).
# ponytail: flat rule-of-thumb adjustments; move to a per-market table if BPOs diverge
ADJ_SQFT_FACTOR = 0.5     # sqft gap credited at 50% of the comp's $/sqft
ADJ_PER_BED     = 5000
ADJ_PER_BATH    = 5000
ADJ_PER_GARAGE  = 5000


def cma_estimate(subject, sold):
    """Weighted adjusted-sale CMA. Returns {value, low, high, n} or None."""
    s_sqft = float(subject.get("BuildingAreaTotal") or 0)
    if not s_sqft or not sold:
        return None
    s_beds = int(subject.get("BedroomsTotal") or 0)
    s_bath = (subject.get("BathroomsFull") or 0) + 0.5 * (subject.get("BathroomsHalf") or 0)
    s_gar  = float(subject.get("GarageSpaces") or 0)

    adjusted, weights = [], []
    for c in sold:
        cp, csf = c.get("ClosePrice"), c.get("BuildingAreaTotal")
        if not cp or not csf:
            continue
        cp, csf = float(cp), float(csf)
        adj = cp + (s_sqft - csf) * (cp / csf) * ADJ_SQFT_FACTOR
        if s_beds and c.get("BedroomsTotal"):
            adj += (s_beds - int(c["BedroomsTotal"])) * ADJ_PER_BED
        c_bath = (c.get("BathroomsFull") or 0) + 0.5 * (c.get("BathroomsHalf") or 0)
        if s_bath and c_bath:
            adj += (s_bath - c_bath) * ADJ_PER_BATH
        if c.get("GarageSpaces") is not None:
            adj += (s_gar - float(c["GarageSpaces"])) * ADJ_PER_GARAGE

        months = 6.0
        try:
            months = max(0.5, (TODAY - datetime.fromisoformat(str(c.get("CloseDate"))[:10]).date()).days / 30)
        except (ValueError, TypeError):
            pass
        miles = 1.0
        slat, slon = subject.get("Latitude"), subject.get("Longitude")
        clat, clon = c.get("Latitude"), c.get("Longitude")
        if all(v is not None for v in (slat, slon, clat, clon)):
            miles = max(0.1, _haversine(slat, slon, clat, clon))
        adjusted.append(adj)
        weights.append(1.0 / ((1 + months) * (1 + miles)))  # fresher + closer counts more

    if not adjusted:
        return None
    value = sum(a * w for a, w in zip(adjusted, weights)) / sum(weights)
    return {"value": int(round(value, -3)), "low": int(round(min(adjusted), -3)),
            "high": int(round(max(adjusted), -3)), "n": len(adjusted)}

# ─── HTML template ─────────────────────────────────────────────────────────────
# Layout source of truth: templates/bpo-template.html ($-placeholders, string.Template)

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "templates" / "bpo-template.html"

def _esc(v):
    from html import escape
    return escape(str(v)) if v not in (None, "") else ""


def _cell(v, first=False):
    v = "&nbsp;" if v in (None, "") else v
    h = " height:14px;" if first else ""
    return f'<td style="border:1px solid #000;{h}">{v}</td>'


def _comp_label(i, addr=""):
    return (
        '<td style="border:1px solid #000; text-align:left; padding:2px 3px; '
        f'font-weight:700; font-size:8px;">COMP #{i}: '
        f'<span style="font-weight:400;">{_esc(addr) or "&nbsp;"}</span></td>'
    )


def _comp_meta(c):
    sub = c.get("PropertySubType") or ""
    yr = c.get("YearBuilt") or ""
    _, note = _analyze_condition(c)
    return " | ".join(filter(None, [sub, f"built {yr}" if yr else "", note]))


def build_html(subject, sold, active, address, as_is="", repaired="", cma_note=""):
    cond, cond_detail = _analyze_condition(subject)
    subj_remarks = _esc((subject.get("PublicRemarks") or "").strip())

    subject_row = "<tr>" + "".join([
        _cell(subject.get("PropertySubType") or "—", first=True),
        _cell(cond),
        _cell(subject.get("BuildingAreaTotal") or "—"),
        _cell("—"),  # living rooms — not in FMLS feed
        _cell(subject.get("BedroomsTotal") or "—"),
        _cell(_baths(subject)),
        _cell(_gar(subject)),
        _cell(_lot(subject)),
        _cell(_age(subject)),
        _cell(subject.get("DaysOnMarket") if subject.get("DaysOnMarket") is not None else "—"),
        _cell(_money(subject.get("OriginalListPrice"))),
        _cell(_money(subject.get("ListPrice"))),
    ]) + "</tr>"

    sold_rows = ""
    for i, c in enumerate(sold, 1):
        sold_rows += "<tr>" + _comp_label(i, c.get("UnparsedAddress", "")) + "".join([
            _cell(c.get("BuildingAreaTotal", "—"), first=True),
            _cell("—"), _cell(c.get("BedroomsTotal", "—")), _cell(_baths(c)),
            _cell(_gar(c)), _cell(_lot(c)), _cell(_age(c)), _cell(c.get("DaysOnMarket", "—")),
            _cell(_money(c.get("ListPrice"))),
            _cell(f"<b>{_money(c.get('ClosePrice'))}</b>"),
            _cell(_date(c.get("CloseDate"))), _cell(_prox(subject, c)),
        ]) + "</tr>\n"
    for i in range(len(sold) + 1, 4):
        sold_rows += "<tr>" + _comp_label(i) + _cell("", first=True) + _cell("") * 11 + "</tr>\n"

    active_rows = ""
    for i, c in enumerate(active, 1):
        active_rows += "<tr>" + _comp_label(i, c.get("UnparsedAddress", "")) + "".join([
            _cell(c.get("BuildingAreaTotal", "—"), first=True),
            _cell("—"), _cell(c.get("BedroomsTotal", "—")), _cell(_baths(c)),
            _cell(_gar(c)), _cell(_lot(c)), _cell(_age(c)), _cell(c.get("DaysOnMarket", "—")),
            _cell(f"<b>{_money(c.get('ListPrice'))}</b>"), _cell(_prox(subject, c)),
        ]) + "</tr>\n"
    for i in range(len(active) + 1, 4):
        active_rows += "<tr>" + _comp_label(i) + _cell("", first=True) + _cell("") * 9 + "</tr>\n"

    # avg $/sqft of sold comps for the sold-comments line
    psf = [round(int(c["ClosePrice"]) / int(c["BuildingAreaTotal"]))
           for c in sold
           if c.get("ClosePrice") and c.get("BuildingAreaTotal") and int(c["BuildingAreaTotal"]) > 0]
    sold_notes = "; ".join(f"#{i} {_comp_meta(c)}" for i, c in enumerate(sold, 1) if _comp_meta(c))
    if psf:
        avg = round(sum(psf) / len(psf))
        sold_notes = f"Avg ${avg}/sqft over {len(psf)} sale(s). " + sold_notes
    if cma_note:
        sold_notes = cma_note + " " + sold_notes
    active_notes = "; ".join(f"#{i} {_comp_meta(c)}" for i, c in enumerate(active, 1) if _comp_meta(c))

    subj_comments = (cond_detail + " " if cond_detail else "") + (
        subj_remarks[:300] + ("…" if len(subj_remarks) > 300 else "") if subj_remarks else "")

    lbl = 'style="border:1px solid #000; padding:2px 6px; text-align:left; font-weight:700;"'
    value_rows = (
        f'<tr><td {lbl}>As Is Value</td>{_cell("", first=True)}{_cell(as_is)}{_cell("")}</tr>\n'
        f'<tr><td {lbl}>Repaired Value</td>{_cell("", first=True)}{_cell(repaired)}{_cell("")}</tr>'
    )

    city = subject.get("City")
    city_st_zip = (f'{city}, {subject.get("StateOrProvince", "")} {subject.get("PostalCode", "")}'
                   if city else subject.get("PostalCode") or "&nbsp;")

    listed = bool(subject.get("ListPrice"))
    from string import Template
    html = Template(TEMPLATE_PATH.read_text(encoding="utf-8")).safe_substitute(
        address=_esc(address),
        agent=_esc(subject.get("ListAgentFullName")) or "&nbsp;",
        city_st_zip=city_st_zip,
        subject_row=subject_row,
        cb_listed_yes="☑" if listed else "☐",
        cb_listed_no="☐" if listed else "☑",
        office=_esc(subject.get("ListOfficeName")) or "&nbsp;",
        phone=_esc(subject.get("ListAgentDirectPhone")) or "&nbsp;",
        subject_comments=subj_comments or "&nbsp;",
        sold_rows=sold_rows,
        sold_comments=sold_notes or "&nbsp;",
        active_rows=active_rows,
        active_comments=active_notes or "&nbsp;",
        value_rows=value_rows,
    )
    missing = [t for t in ("$subject_row", "$sold_rows", "$active_rows", "$value_rows") if t in html]
    if missing:
        raise RuntimeError(f"bpo-template.html placeholders not filled: {missing}")
    return html

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
    sold_all = fetch_sold_comps(zip_code, beds, sqft, year, n=8)  # extra depth for the CMA
    sold = sold_all[:3]
    print(f"  {len(sold_all)} sold comp(s) — top 3 shown on BPO")

    # 3. CMA cross-reference (computed from the full sold pool)
    as_is, cma_note = a.as_is, ""
    cma = cma_estimate(subject, sold_all)
    if cma:
        print(f"CMA estimate: ${cma['value']:,} (range ${cma['low']:,}–${cma['high']:,}, {cma['n']} adjusted sales)")
        cma_note = (f"CMA cross-ref: adjusted-sale value ${cma['value']:,} "
                    f"(range ${cma['low']:,}–${cma['high']:,}, n={cma['n']}).")
        stated = int(re.sub(r"[^\d]", "", as_is) or 0) if as_is else 0
        if stated:
            pct = (stated - cma["value"]) / cma["value"] * 100
            if abs(pct) > 10:
                print(f"  ⚠ Stated as-is ${stated:,} is {pct:+.0f}% vs CMA — double-check before sending")
                cma_note += f" Stated as-is diverges {pct:+.0f}% from CMA."
        else:
            as_is = f"${cma['value']:,} (CMA est.)"
    else:
        print("CMA estimate: skipped (no usable sold comps or subject sqft)")

    # 4. Build HTML
    html = build_html(subject, sold, active, a.address, as_is, a.repaired, cma_note)

    if a.dry_run:
        out = Path("/tmp/bpo_preview.html")
        out.write_text(html, encoding="utf-8")
        print(f"\nDry run — HTML saved to {out}")
        print(f"  {len(sold)} sold comps, {len(active)} active comps")
        return

    # 5. Drive folder
    token = get_token()
    print("\nCreating Drive folder...")
    parent_id = find_or_create_folder(token, BPO_PARENT)
    folder_id = find_or_create_folder(token, a.address, parent_id)
    print(f"  https://drive.google.com/drive/folders/{folder_id}")

    # 6. Google Doc
    title = f"BPO - {a.address}"
    print("Creating BPO Google Doc...")
    doc_id, doc_link = create_gdoc_from_html(token, title, html, folder_id)
    print(f"  {doc_link}")

    # 7. PDF
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
