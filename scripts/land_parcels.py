#!/usr/bin/env python3
"""
Olive Tree Investments — Land Parcels (County GIS client)

The automation core of the land-wholesaling vertical. Queries county
tax-assessor parcel layers (published on ArcGIS Online) and returns
normalized parcel records: situs address, acreage, land use, owner name,
owner MAILING address, owner state (out-of-state flag), and land value.

This replaces Zillow/portal scraping (which the sandbox blocks) with the
authoritative, free, JSON-queryable source the data actually comes from.

Per-county config lives in COUNTIES below. Each county has its own ArcGIS
org id + service + layer + field names, so adding a county = one registry
entry. Two counties are wired and validated:
  • bartow-ga  — launch market (Cartersville/White/Emerson); situs zip, 57.5K parcels
  • forsyth-ga — first validated county (bbox-only; no situs zip), 131.8K parcels

Used by:  land_markets.py (/land-scout), land_sellers.py (/land-sellers)

Usage:
  # Count vacant, out-of-state-owned lots in Cartersville
  python3 scripts/land_parcels.py --county bartow-ga --zip 30120 \
      --vacant --out-of-state --count

  # Pull a seller list (vacant, 0.1–3 ac, out-of-state), print JSON
  python3 scripts/land_parcels.py --county bartow-ga --zip 30120 \
      --vacant --out-of-state --min-acres 0.1 --max-acres 3 --limit 25 --json

  # Cookie-cutter test (acreage uniformity) for a zip
  python3 scripts/land_parcels.py --county bartow-ga --zip 30120 --vacant --stats

Notes:
  • Field types differ by county (Bartow numeric, Forsyth string), so numeric/
    blank filtering is also enforced in Python after fetch as a safety net.
  • "Vacant" = no structure: blank building field OR building value/area == 0.
  • Location filter: situs-zip WHERE when the county exposes one (Bartow), else a
    spatial bbox from ZIP_BBOX (Forsyth). Pass --bbox to override.
"""

import argparse
import json
import os
import statistics
import sys
import time

import requests

# ─────────────────────────────────────────────
# Per-county registry
# ─────────────────────────────────────────────
# field_map: canonical key -> source field name, OR a list of source fields to
# join with spaces (blanks dropped). Canonical keys are stable across counties.
# Optional keys per county:
#   zip_field    — situs-zip field for direct WHERE filtering (skip bbox)
#   vacant_where — server-side SQL for "no structure" (speeds the query)

COUNTIES = {
    "bartow-ga": {
        "name":  "Bartow County, GA",
        "state": "GA",
        "url": ("https://services.arcgis.com/0tQ9yX5b2VG5RHei/arcgis/rest/"
                "services/ParcelInfo/FeatureServer/11"),
        "zip_field": "Property_Zip",
        "vacant_where": "BuildingValue=0",
        "field_map": {
            "parcel_id":    "PARCELID",
            "site_address": ["HOUSE_NO", "STREET_NAM"],
            "site_zip":     "Property_Zip",
            "subdivision":  "Subdivision_Name",
            "acres":        "TOTALACRES",       # Double
            "bldg_area":    "BuildingValue",    # Double; 0 => vacant
            "owner_name":   ["Owner1", "Owner2"],
            "owner_addr":   ["Mailing_Address_1", "Mailing_Address_2"],
            "owner_city":   "Mailing_City",
            "owner_state":  "Mailing_State",
            "owner_zip":    "Mailing_Zip",
            "land_value":   "LandValue",        # Double (offer anchor)
        },
    },
    "forsyth-ga": {
        "name":  "Forsyth County, GA",
        "state": "GA",
        "url": ("https://services2.arcgis.com/StQaZGYzUARPnrpL/arcgis/rest/"
                "services/TylerParcels/FeatureServer/90"),
        # No situs zip in this layer -> location filter is a bbox (see ZIP_BBOX).
        "vacant_where": "BLDGAREA IS NULL OR BLDGAREA='' OR BLDGAREA=' '",
        "field_map": {
            "parcel_id":    "Name",
            "site_address": "SITEADDRES",
            "acres":        "L_ACRES",          # String
            "land_use":     "P_LUC",
            "zoning":       "P_ZONING",
            "bldg_area":    "BLDGAREA",         # String; blank => vacant
            "owner_name":   "O_OWN1",
            "owner_addr":   "O_ADDR1",
            "owner_city":   "O_CITYNAME",
            "owner_state":  "O_STATECOD",
            "owner_zip":    "O_ZIP1",
            "land_value":   "A_APRLAND",
        },
    },
    # To add a county: copy a block, point url at its ArcGIS-Online parcel layer,
    # map the canonical keys, and set zip_field/vacant_where if available.
    # Only ArcGIS-Online (services*.arcgis.com) orgs are reachable here; on-prem
    # county servers (maps.<county>.gov) are not.
}

# ZIP → [west, south, east, north] bbox (WGS84) for counties without a situs zip.
ZIP_BBOX = {
    "30040": [-84.20, 34.18, -84.10, 34.27],  # Cumming / Forsyth
    "30041": [-84.16, 34.18, -84.02, 34.27],
}

ARCGIS_PAGE = 1000  # max records per ArcGIS query page


# ─────────────────────────────────────────────
# ReportAllUSA parcel API — multi-state source (6-state Southeast expansion)
# ─────────────────────────────────────────────
# STUB, inert until REPORTALL_API_KEY is set (trial keys pending — see decisions/log
# 2026-06-29). One nationwide API replaces per-county ArcGIS scrapers for GA/AL/NC/SC/
# TN/KY, where most counties run qPublic/Schneider (unreachable) or geometry-only AGO
# layers. Output is the SAME canonical record as query_parcels(), so the whole downstream
# pipeline (apply_filters / acre_stats / is_vacant / is_out_of_state) works unchanged.
#
# Field names verified against ReportAll's standard API data dictionary (2026-06-30):
# https://reportallusa.com/product-docs/api/api-standard-data-dictionary
# Standard schema includes owner mailing (incl. state) — no premium tier. The only
# trial-time confirm left is the query-param syntax for server-side filtering (below).
REPORTALL_API = "https://reportallusa.com/api/parcels"
REPORTALL_VERSION = 9
REPORTALL_RPP = 1000  # rows per page (API max)

# MapServer endpoint — supports real WHERE clause; bills only rows returned (not total scanned).
# Use this path for seller pulls (vacant + out-of-state server-side) to avoid paying for houses.
# ponytail: key embedded in URL per ReportAll's own pattern (no separate auth header)
REPORTALL_MAPSERVER = "https://reportallusa.com/api/rest_services/client={key}/Parcels/MapServer/0/query"

# FIPS county_id values required by the MapServer WHERE clause for SE expansion markets.
# county_id = 5-digit FIPS (leading zeros dropped by the API).
REPORTALL_FIPS = {
    "bartow-ga":    (13015, "GA"),
    "forsyth-ga":   (13117, "GA"),
    "hall-ga":      (13139, "GA"),
    "jackson-ga":   (13157, "GA"),
    "paulding-ga":  (13223, "GA"),
    "maury-tn":     (47119, "TN"),
    "limestone-al": (1083,  "AL"),
    "johnston-nc":  (37101, "NC"),
    "york-sc":      (45091, "SC"),
    "lee-fl":       (12071, "FL"),
    "horry-sc":     (45051, "SC"),
}

REPORTALL_FIELD_MAP = {
    "parcel_id":    "parcel_id",
    "site_address": "address",        # assembled situs address
    "site_zip":     "addr_zip",
    "acres":        "acreage_calc",   # GIS-calc acres; deeded ("acreage") fallback in fetch
    "land_use":     "land_use_code",
    "bldg_area":    "mkt_val_bldg",   # improvement value; 0/blank => vacant land
    "owner_name":   "owner",
    "owner_addr":   "mail_address1",
    "owner_city":   "mail_placename",
    "owner_state":  "mail_statename", # absentee filter keys on this — verified
    "owner_zip":    "mail_zipcode",
    "land_value":   "mkt_val_land",   # offer anchor
}


# ─────────────────────────────────────────────
# Field assembly
# ─────────────────────────────────────────────

def _to_float(val):
    """Parse a possibly-blank string/number field to float, else None."""
    if isinstance(val, (int, float)):
        return float(val)
    try:
        s = (val or "").strip()
        return float(s) if s else None
    except (TypeError, ValueError):
        return None


def _join(attrs, src):
    """Resolve a field_map value (single field or list to join) to a string."""
    if isinstance(src, list):
        parts = [str(attrs.get(f) or "").strip() for f in src]
        return " ".join(p for p in parts if p)
    v = attrs.get(src)
    return v.strip() if isinstance(v, str) else v


def _raw_bldg(attrs, field_map):
    src = field_map["bldg_area"]
    return attrs.get(src[0] if isinstance(src, list) else src)


def _normalize(attrs, field_map):
    """Map a raw ArcGIS attribute dict to the canonical record."""
    rec = {canon: _join(attrs, src) for canon, src in field_map.items()}
    rec["acres"] = _to_float(rec.get("acres"))
    rec["land_value"] = _to_float(rec.get("land_value"))
    rec["bldg_area_raw"] = _raw_bldg(attrs, field_map)
    return rec


# ─────────────────────────────────────────────
# Core query
# ─────────────────────────────────────────────

def _combine_where(*clauses):
    parts = [c for c in clauses if c and c != "1=1"]
    return " AND ".join(f"({c})" for c in parts) if parts else "1=1"


def _get_json(url, params, timeout=30, retries=3):
    """GET with retry/backoff — public county GIS servers throw transient 5xx."""
    last = None
    for attempt in range(retries):
        try:
            resp = requests.get(url, params=params, timeout=timeout)
            if resp.status_code in (429, 500, 502, 503, 504):
                last = requests.HTTPError(f"{resp.status_code} {resp.reason}")
                time.sleep(2 ** attempt)
                continue
            resp.raise_for_status()
            data = resp.json()
            if "error" in data:
                raise RuntimeError(f"ArcGIS error: {data['error']}")
            return data
        except (requests.Timeout, requests.ConnectionError) as e:
            last = e
            time.sleep(2 ** attempt)
    raise RuntimeError(f"GIS request failed after {retries} tries: {last}")


def query_parcels(county, where="1=1", bbox=None, zip_code=None,
                  vacant_only=False, max_records=None, timeout=30):
    """
    Query a county parcel layer; return a list of normalized records.

    where:        extra ArcGIS SQL (county-native fields).
    bbox:         [w,s,e,n] WGS84 spatial filter.
    zip_code:     situs zip; uses the county's zip_field WHERE when available.
    vacant_only:  add the county's server-side vacant_where when available.
    """
    cfg = COUNTIES[county]
    out_fields = sorted({f for v in cfg["field_map"].values()
                         for f in ([v] if isinstance(v, str) else v)})

    clauses = [where]
    if zip_code and cfg.get("zip_field"):
        clauses.append(f"{cfg['zip_field']}='{zip_code}'")
    if vacant_only and cfg.get("vacant_where"):
        clauses.append(cfg["vacant_where"])

    params = {
        "where": _combine_where(*clauses),
        "outFields": ",".join(out_fields),
        "returnGeometry": "false",
        "outSR": "4326",
        "f": "json",
        "resultRecordCount": ARCGIS_PAGE,
    }
    if bbox:
        params.update({
            "geometry": ",".join(str(c) for c in bbox),
            "geometryType": "esriGeometryEnvelope",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
        })

    records, offset = [], 0
    while True:
        params["resultOffset"] = offset
        data = _get_json(cfg["url"] + "/query", params, timeout=timeout)
        feats = data.get("features", [])
        if not feats:
            break
        for ft in feats:
            records.append(_normalize(ft["attributes"], cfg["field_map"]))
            if max_records and len(records) >= max_records:
                return records
        if not data.get("exceededTransferLimit"):
            break
        offset += len(feats)
    return records


def query_parcels_reportall(region=None, zip_code=None, county_id=None,
                            vacant_only=False, min_acres=None, max_acres=None,
                            max_records=None, api_key=None, timeout=30):
    """
    Query ReportAllUSA for a region -> canonical records (same shape as query_parcels).

    Geography (one required, the "region clause"):
      region    — "County, ST" or "ST" (e.g. "Lancaster, SC")
      zip_code  — postal code
      county_id — numeric FIPS55

    Server-side attribute filters (the API requires ≥1, and you're only charged
    for parcels RETURNED — so filter hard to conserve credits):
      vacant_only        -> mkt_val_bldg_max=0
      min_acres/max_acres -> acreage_min/acreage_max

    Out-of-state ownership has NO server param — apply it Python-side via
    apply_filters(out_of_state=...) after the pull.

    Verified live 2026-06-30 (Lancaster SC). Two data wrinkles:
      • The deeded `acreage` field carries placeholder 1.0000 values on data-poor
        subdivision slivers; we map acres to `acreage_calc` (reliable) and the
        server band filters deeded acreage — so refine on acreage_calc with
        apply_filters(min_acres/max_acres) after the pull.
      • Some counties (e.g. Lancaster SC) return mkt_val_land=0; the offer anchor
        comes from the builder price, so a 0 land value is non-fatal.
    """
    api_key = api_key or os.environ.get("REPORTALL_API_KEY")
    if not api_key:
        raise RuntimeError("REPORTALL_API_KEY not set — add it to .env.")
    if not (region or zip_code or county_id):
        raise ValueError("Need a region clause: region, zip_code, or county_id.")

    geo = {}
    if region:    geo["region"] = region
    if zip_code:  geo["zip_code"] = zip_code
    if county_id: geo["county_id"] = county_id

    attrs_q = {}
    if vacant_only:        attrs_q["mkt_val_bldg_max"] = 0
    if min_acres is not None: attrs_q["acreage_min"] = min_acres
    if max_acres is not None: attrs_q["acreage_max"] = max_acres
    if not attrs_q:        # API demands ≥1 attribute clause alongside the region
        attrs_q["acreage_min"] = 0.01

    # Credit safety: you're billed per parcel RETURNED, so never request more per
    # page than max_records — otherwise a 1000-row page bills 1000 even if we stop
    # reading at 12.
    rpp = min(REPORTALL_RPP, max_records) if max_records else REPORTALL_RPP

    records, page = [], 1
    while True:
        params = {"client": api_key, "v": REPORTALL_VERSION,
                  "rpp": rpp, "page": page, **geo, **attrs_q}
        data = _get_json(REPORTALL_API, params, timeout=timeout)
        if data.get("status") not in (None, "OK"):
            raise RuntimeError(f"ReportAll error: {data.get('message', data)}")
        rows = data.get("results", [])
        if not rows:
            break
        for a in rows:
            rec = _normalize(a, REPORTALL_FIELD_MAP)
            if rec["acres"] is None:                       # acreage_calc blank
                rec["acres"] = _to_float(a.get("acreage"))  # deeded fallback
            records.append(rec)
            if max_records and len(records) >= max_records:
                return records
        if len(rows) < REPORTALL_RPP:                      # last page
            break
        page += 1
    return records


def query_sellers_mapserver(county, zip_code, home_state, min_acres, max_acres,
                            api_key=None, max_records=None, timeout=30):
    """Pull ONLY vacant + out-of-state sellers via the ReportAll MapServer WHERE clause.

    Costs credits = rows returned (sellers only, not all parcels). Use instead of
    query_parcels_reportall for any county in REPORTALL_FIPS — ~12x more efficient
    because houses are excluded server-side.

    Returns canonical records (same shape as query_parcels / query_parcels_reportall).
    """
    api_key = api_key or os.environ.get("REPORTALL_API_KEY")
    if not api_key:
        raise RuntimeError("REPORTALL_API_KEY not set — add it to .env.")
    if county not in REPORTALL_FIPS:
        raise ValueError(f"No FIPS entry for '{county}'. Add it to REPORTALL_FIPS.")

    cid, _ = REPORTALL_FIPS[county]
    where = (
        f"county_id={cid} AND addr_zip='{zip_code}'"
        f" AND acreage_calc>={min_acres} AND acreage_calc<={max_acres}"
        f" AND (buildings=0 OR buildings IS NULL)"
        f" AND mail_statename<>'{home_state}' AND mail_statename IS NOT NULL"
    )
    url = REPORTALL_MAPSERVER.format(key=api_key)
    out_fields = ",".join(REPORTALL_FIELD_MAP.values()) + ",buildings"

    records, offset = [], 0
    while True:
        params = {"where": where, "f": "json", "returnGeometry": "false",
                  "outFields": out_fields, "resultOffset": offset,
                  "resultRecordCount": 1000}
        data = _get_json(url, params, timeout=timeout)
        feats = data.get("features", [])
        for ft in feats:
            a = ft["attributes"]
            rec = _normalize(a, REPORTALL_FIELD_MAP)
            if rec["acres"] is None:
                rec["acres"] = _to_float(a.get("acreage"))
            records.append(rec)
            if max_records and len(records) >= max_records:
                return records
        if not data.get("exceededTransferLimit"):
            break
        offset += len(feats)
    return records


def _owner_state_field(cfg):
    """Return the owner-state field name if it's a single column (for SQL filtering)."""
    f = cfg["field_map"].get("owner_state")
    return f if isinstance(f, str) else None


def count_parcels(county, where="1=1", bbox=None, zip_code=None,
                  vacant_only=False, out_of_state=False, timeout=30):
    """Fast server-side count without pulling records."""
    cfg = COUNTIES[county]
    if vacant_only and not cfg.get("vacant_where"):
        raise RuntimeError(
            f"{county} has no vacant_where; cannot count vacancy server-side. "
            f"Add one to its COUNTIES config.")
    clauses = [where]
    if zip_code and cfg.get("zip_field"):
        clauses.append(f"{cfg['zip_field']}='{zip_code}'")
    if vacant_only and cfg.get("vacant_where"):
        clauses.append(f"({cfg['vacant_where']})")
    if out_of_state and _owner_state_field(cfg):
        f = _owner_state_field(cfg)
        clauses.append(f"{f}<>'{cfg['state']}' AND {f}<>''")
    params = {"where": _combine_where(*clauses), "returnCountOnly": "true", "f": "json"}
    if bbox:
        params.update({
            "geometry": ",".join(str(c) for c in bbox),
            "geometryType": "esriGeometryEnvelope",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
        })
    return _get_json(cfg["url"] + "/query", params, timeout=timeout).get("count", 0)


# ─────────────────────────────────────────────
# Filters & stats (Python-side safety net)
# ─────────────────────────────────────────────

def is_vacant(rec):
    """True if the parcel has no structure: blank building field or value/area 0."""
    raw = rec.get("bldg_area_raw")
    if raw is None:
        return True
    if isinstance(raw, str):
        s = raw.strip()
        return s == "" or _to_float(s) == 0
    return _to_float(raw) == 0


def is_out_of_state(rec, home_state="GA"):
    st = (rec.get("owner_state") or "").strip().upper()
    return bool(st) and st != home_state.upper()


def apply_filters(records, vacant=False, out_of_state=False, home_state="GA",
                  min_acres=None, max_acres=None, land_use=None):
    """Apply the filters the source layer can't reliably express in SQL."""
    out = []
    luc = {c.strip() for c in land_use.split(",")} if land_use else None
    for r in records:
        if vacant and not is_vacant(r):
            continue
        if out_of_state and not is_out_of_state(r, home_state):
            continue
        if min_acres is not None and (r["acres"] is None or r["acres"] < min_acres):
            continue
        if max_acres is not None and (r["acres"] is None or r["acres"] > max_acres):
            continue
        if luc and (r.get("land_use") or "").strip() not in luc:
            continue
        out.append(r)
    return out


def acre_stats(records):
    """
    Cookie-cutter test: how uniform are the lot sizes?
    Returns count, min/median/max/mean acres, coefficient of variation, and a
    uniformity score in [0,1] (1 = perfectly uniform): 1 - clamp(stdev/mean).
    """
    acres = [r["acres"] for r in records if r["acres"] is not None]
    if not acres:
        return {"count": 0, "uniformity": None}
    mean = statistics.mean(acres)
    stdev = statistics.pstdev(acres) if len(acres) > 1 else 0.0
    cv = (stdev / mean) if mean else 0.0
    return {
        "count": len(acres),
        "min": round(min(acres), 3),
        "median": round(statistics.median(acres), 3),
        "max": round(max(acres), 3),
        "mean": round(mean, 3),
        "cv": round(cv, 3),
        "uniformity": round(max(0.0, 1.0 - min(cv, 1.0)), 3),
    }


def resolve_bbox(county, zip_code=None, bbox=None):
    """Resolve a bbox only when the county lacks a situs-zip field."""
    if bbox:
        parts = [float(x) for x in bbox.split(",")]
        if len(parts) != 4:
            raise ValueError("--bbox must be 'west,south,east,north'")
        return parts
    if zip_code and not COUNTIES[county].get("zip_field"):
        if zip_code not in ZIP_BBOX:
            raise ValueError(
                f"{county} has no situs zip and no bbox for {zip_code}. "
                f"Add it to ZIP_BBOX or pass --bbox.")
        return ZIP_BBOX[zip_code]
    return None


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Query county parcel data (land wholesaling).")
    ap.add_argument("--county", default="bartow-ga", choices=sorted(COUNTIES),
                    help="County config to query (default: bartow-ga)")
    ap.add_argument("--zip", dest="zip_code", help="Situs zip filter")
    ap.add_argument("--bbox", help="Spatial filter 'west,south,east,north' (overrides zip)")
    ap.add_argument("--where", default="1=1", help="Extra ArcGIS WHERE clause")
    ap.add_argument("--vacant", action="store_true", help="Only parcels with no building")
    ap.add_argument("--out-of-state", action="store_true", help="Only out-of-state owners")
    ap.add_argument("--min-acres", type=float, help="Minimum lot size")
    ap.add_argument("--max-acres", type=float, help="Maximum lot size")
    ap.add_argument("--land-use", help="Comma-separated land-use codes to keep")
    ap.add_argument("--limit", type=int, help="Cap records fetched")
    ap.add_argument("--count", action="store_true", help="Print count only (server-side)")
    ap.add_argument("--stats", action="store_true", help="Print acreage uniformity stats")
    ap.add_argument("--json", action="store_true", help="Print records as JSON")
    args = ap.parse_args()

    cfg = COUNTIES[args.county]
    try:
        bbox = resolve_bbox(args.county, args.zip_code, args.bbox)
    except ValueError as e:
        ap.error(str(e))

    # Fast server-side count when no Python-only filters are needed.
    py_filters = args.out_of_state or args.min_acres or args.max_acres or args.land_use
    if args.count and not py_filters:
        print(count_parcels(args.county, args.where, bbox,
                            zip_code=args.zip_code, vacant_only=args.vacant))
        return

    records = query_parcels(args.county, args.where, bbox, zip_code=args.zip_code,
                            vacant_only=args.vacant, max_records=args.limit)
    records = apply_filters(
        records, vacant=args.vacant, out_of_state=args.out_of_state,
        home_state=cfg["state"], min_acres=args.min_acres,
        max_acres=args.max_acres, land_use=args.land_use,
    )

    if args.count:
        print(len(records))
        return
    if args.stats:
        print(json.dumps(acre_stats(records), indent=2))
        return
    if args.json:
        json.dump(records, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return

    print(f"{cfg['name']} — {len(records)} parcels")
    for r in records[:50]:
        addr = (r.get("site_address") or "").strip() or "(no situs)"
        ac = r["acres"] if r["acres"] is not None else "?"
        val = f"${int(r['land_value']):,}" if r.get("land_value") else "$?"
        print(f"  {str(r.get('parcel_id','')):16} {addr:26} {ac:>7} ac  {val:>11}  "
              f"{r.get('owner_name','')} [{r.get('owner_state','')}]")
    if len(records) > 50:
        print(f"  … and {len(records) - 50} more (use --json for all)")


if __name__ == "__main__":
    main()
