#!/usr/bin/env python3
"""
Olive Tree — Land Contract (/land-contract engine)

Fills the assignable Vacant Land PSA (seller side) and Assignment Agreement
(builder side) from templates, saves them locally, and uploads both to a
parcel-named folder inside "Olive Tree Investments - Deals / Land Wholesale/"
on Google Drive.

⚠️  Templates require attorney review before sending to any party.

Usage:
  # Draft both contracts for a parcel (looks up seller + builder from sheets)
  python3 scripts/land_contract.py --parcel 0051-0574-005

  # Override builder / offer / spread for the assignment fee
  python3 scripts/land_contract.py --parcel 0051-0574-005 \
      --builder "LGI Homes" --assignment-price 54000

  # Preview filled contracts, no files written
  python3 scripts/land_contract.py --parcel 0051-0574-005 --dry-run
"""

import json
import os
import re
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
from dotenv import load_dotenv

from gws_auth import get_token  # noqa: E402
from land_sheets import read_rows  # noqa: E402

load_dotenv()

# ─── Templates ───────────────────────────────────────────────
PSA_TEMPLATE   = Path(__file__).parent.parent / "templates" / "land-psa-template.md"
ASGN_TEMPLATE  = Path(__file__).parent.parent / "templates" / "land-assignment-template.md"
OUTPUT_DIR     = Path(__file__).parent.parent / "output" / "land-contracts"

# ─── Drive ───────────────────────────────────────────────────
DRIVE_BASE       = "https://www.googleapis.com/drive/v3/files"
UPLOAD_BASE      = "https://www.googleapis.com/upload/drive/v3/files"
FOLDER_MIME      = "application/vnd.google-apps.folder"
DEALS_PARENT_ID  = "1pLWVMaLPy-8Rt1NGQsX2wg2oNDonWC-p"  # Olive Tree Investments - Deals
LAND_FOLDER_NAME = "Land Wholesale"

BUYER_NAME = "Brian Norton"   # Olive Tree Investments

# ─── Land Sellers column indices ─────────────────────────────
C_PARCEL  =  0
C_SITUS   =  1
C_ZIP     =  2
C_ACRES   =  4
C_OWNER   =  5
C_ADDR    =  6
C_CITY    =  7
C_STATE   =  8
C_OFFER   = 11

# ─── Land Builders column indices ────────────────────────────
B_NAME    =  0
B_COMPANY =  1
B_MARKETS =  4
B_PRICE   =  7

ZIP_COUNTY = {
    "30120": "Bartow County", "30121": "Bartow County",
    "30040": "Forsyth County", "30041": "Forsyth County",
}

CLOSE_DAYS    = 21
DEFAULT_EMD   = "$250"
DEFAULT_SPREAD = 0.15


def _col(row, idx, default=""):
    return (row[idx].strip() if len(row) > idx and row[idx] else default)


def _load_template(path):
    raw = path.read_text()
    # Strip the markdown header block (before first horizontal rule)
    if "\n---\n" in raw:
        return raw.split("\n---\n", 1)[1].lstrip("\n")
    return raw


def _fmt_price(val):
    try:
        return f"${float(val):,.0f}"
    except (ValueError, TypeError):
        return str(val) if val else "[PRICE]"


def _find_seller(rows, parcel_id):
    for r in rows[1:]:
        if _col(r, C_PARCEL) == parcel_id:
            return r
    return None


def _find_builder(rows, zip_code):
    """Return the highest-price builder row covering this zip."""
    best, best_price = None, 0
    for r in rows[1:]:
        markets = _col(r, B_MARKETS)
        price_str = _col(r, B_PRICE)
        if zip_code in markets and "/ac" in price_str:
            try:
                p = float(price_str.replace("$", "").replace("/ac", ""))
                if p > best_price:
                    best, best_price = r, p
            except ValueError:
                pass
    return best


def _fill_psa(seller_row, assignment_price, county, close_date):
    tmpl = _load_template(PSA_TEMPLATE)
    zip_code = _col(seller_row, C_ZIP)
    mapping = {
        "{{DATE}}":                     date.today().strftime("%B %d, %Y"),
        "{{BUYER_NAME}}":               BUYER_NAME,
        "{{SELLER_NAME}}":              _col(seller_row, C_OWNER) or "[SELLER NAME]",
        "{{SELLER_MAILING_ADDRESS}}":   (
            _col(seller_row, C_ADDR) + ", " +
            _col(seller_row, C_CITY) + ", " +
            _col(seller_row, C_STATE)
        ).strip(", "),
        "{{PARCEL_ID}}":                _col(seller_row, C_PARCEL),
        "{{SITUS_ADDRESS}}":            _col(seller_row, C_SITUS) or zip_code,
        "{{COUNTY}}":                   county,
        "{{ACRES}}":                    _col(seller_row, C_ACRES),
        "{{PURCHASE_PRICE}}":           _fmt_price(_col(seller_row, C_OFFER)),
        "{{EMD}}":                      DEFAULT_EMD,
        "{{CLOSING_DATE}}":             close_date,
        "{{CLOSE_DAYS}}":               str(CLOSE_DAYS),
    }
    for k, v in mapping.items():
        tmpl = tmpl.replace(k, str(v))
    return tmpl


def _fill_assignment(seller_row, builder_row, assignment_price, county, close_date):
    tmpl = _load_template(ASGN_TEMPLATE)
    contract_price = _col(seller_row, C_OFFER)
    b_name    = _col(builder_row, B_NAME) if builder_row else "[BUILDER NAME]"
    b_company = _col(builder_row, B_COMPANY) if builder_row else "[BUILDER COMPANY]"
    try:
        asgn_fee = float(assignment_price) - float(contract_price)
        asgn_fee_fmt = _fmt_price(asgn_fee)
    except (TypeError, ValueError):
        asgn_fee_fmt = "[ASSIGNMENT FEE]"

    mapping = {
        "{{DATE}}":              date.today().strftime("%B %d, %Y"),
        "{{BUYER_NAME}}":        BUYER_NAME,
        "{{ASSIGNEE_NAME}}":     b_name,
        "{{ASSIGNEE_COMPANY}}":  b_company,
        "{{PSA_DATE}}":          date.today().strftime("%B %d, %Y"),
        "{{PARCEL_ID}}":         _col(seller_row, C_PARCEL),
        "{{SITUS_ADDRESS}}":     _col(seller_row, C_SITUS),
        "{{COUNTY}}":            county,
        "{{ACRES}}":             _col(seller_row, C_ACRES),
        "{{SELLER_NAME}}":       _col(seller_row, C_OWNER),
        "{{CONTRACT_PRICE}}":    _fmt_price(contract_price),
        "{{ASSIGNMENT_FEE}}":    asgn_fee_fmt,
        "{{ASSIGNMENT_PRICE}}":  _fmt_price(assignment_price),
        "{{ASSIGNEE_EMD}}":      DEFAULT_EMD,
        "{{EMD_DAYS}}":          "3",
    }
    for k, v in mapping.items():
        tmpl = tmpl.replace(k, str(v))
    return tmpl


# ─── Drive helpers ───────────────────────────────────────────

def _drive_get(token, **params):
    r = requests.get(DRIVE_BASE, headers={"Authorization": f"Bearer {token}"},
                     params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def _find_or_create_folder(token, name, parent_id=None):
    safe = name.replace("'", "\\'")
    q = f"name = '{safe}' and mimeType = '{FOLDER_MIME}' and trashed = false"
    if parent_id:
        q += f" and '{parent_id}' in parents"
    files = _drive_get(token, q=q, fields="files(id)", pageSize=5).get("files", [])
    if files:
        return files[0]["id"]
    body = {"name": name, "mimeType": FOLDER_MIME}
    if parent_id:
        body["parents"] = [parent_id]
    r = requests.post(DRIVE_BASE, headers={"Authorization": f"Bearer {token}"},
                      json=body, timeout=30)
    r.raise_for_status()
    print(f"  [Drive] Created folder: {name}")
    return r.json()["id"]


def _upload_text(token, name, content, folder_id):
    """Upload a .txt file. Skip if already there (idempotent)."""
    safe = name.replace("'", "\\'")
    existing = _drive_get(token,
                          q=f"name='{safe}' and '{folder_id}' in parents and trashed=false",
                          fields="files(id)", pageSize=1).get("files", [])
    if existing:
        fid = existing[0]["id"]
        print(f"  [Drive] Already exists: {name} → https://drive.google.com/file/d/{fid}")
        return fid
    content_bytes = content.encode("utf-8")
    boundary = "olive_land_boundary"
    meta = json.dumps({"name": name, "parents": [folder_id]})
    body = (
        f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
        f"{meta}\r\n"
        f"--{boundary}\r\nContent-Type: text/plain; charset=UTF-8\r\n\r\n"
    ).encode() + content_bytes + f"\r\n--{boundary}--".encode()
    r = requests.post(
        f"{UPLOAD_BASE}?uploadType=multipart",
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": f"multipart/related; boundary={boundary}"},
        data=body, timeout=60,
    )
    r.raise_for_status()
    fid = r.json()["id"]
    print(f"  [Drive] Uploaded: {name} → https://drive.google.com/file/d/{fid}")
    return fid


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Draft land contracts for a parcel.")
    ap.add_argument("--parcel", required=True, help="Parcel ID from Land Sellers tab")
    ap.add_argument("--builder", help="Builder name override (else auto-selected by zip)")
    ap.add_argument("--assignment-price", type=float,
                    help="Total price Assignee pays (contract price + spread); "
                         "default: offer × (1 + 0.20)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print filled contracts; don't write files or upload")
    args = ap.parse_args()

    token = get_token()

    # ── Load seller row ──────────────────────────────────────
    seller_rows = read_rows(token, "Land Sellers")
    seller = _find_seller(seller_rows, args.parcel)
    if seller is None:
        sys.exit(f"Parcel '{args.parcel}' not found in Land Sellers tab. "
                 f"Run /land-sellers first.")

    zip_code = _col(seller, C_ZIP)
    county   = ZIP_COUNTY.get(zip_code, "the county")
    offer    = _col(seller, C_OFFER)

    # ── Assignment price ─────────────────────────────────────
    # Anchor to builder's price/acre × acres (their buy-box ceiling).
    # Never use offer × markup — offer is already discounted from the builder's
    # price, so re-marking up overshoots what the builder will pay.
    asgn_price = args.assignment_price
    if not asgn_price:
        # First try to compute from builder's $/acre × acres.
        # Fall back to offer × (1+spread) only if builder lookup fails.
        computed = False
        if not args.builder:           # auto-select builder by zip to get price
            builder_rows_pre = read_rows(token, "Land Builders")
            _b = _find_builder(builder_rows_pre, zip_code)
        else:
            _b = None
        for _row in [_b]:
            if _row is None:
                break
            try:
                price_str = _col(_row, B_PRICE)       # "$8000/ac"
                price_per_ac = float(
                    price_str.replace("$", "").replace("/ac", "").strip())
                acres_val = float(_col(seller, C_ACRES))
                asgn_price = round(price_per_ac * acres_val / 100) * 100
                computed = True
            except (ValueError, TypeError):
                pass
        if not computed:
            try:
                asgn_price = round(float(offer) * (1 + DEFAULT_SPREAD) / 100) * 100
            except (TypeError, ValueError):
                asgn_price = None

    # ── Builder row ──────────────────────────────────────────
    builder_rows = read_rows(token, "Land Builders")
    builder = None
    if args.builder:
        for r in builder_rows[1:]:
            if args.builder.lower() in _col(r, B_NAME).lower():
                builder = r
                break
        if not builder:
            print(f"  [warn] Builder '{args.builder}' not found — assignment names left blank.")
    else:
        builder = _find_builder(builder_rows, zip_code)

    close_date = (date.today() + timedelta(days=CLOSE_DAYS)).strftime("%B %d, %Y")

    # ── Fill templates ───────────────────────────────────────
    psa_text  = _fill_psa(seller, asgn_price, county, close_date)
    asgn_text = _fill_assignment(seller, builder, asgn_price, county, close_date)

    parcel_safe = re.sub(r"[^A-Za-z0-9_-]", "-", args.parcel)
    psa_name  = f"PSA_{parcel_safe}.txt"
    asgn_name = f"Assignment_{parcel_safe}.txt"

    # ── Summary ──────────────────────────────────────────────
    print(f"\n  Land Contracts — {args.parcel}")
    print(f"  Seller:        {_col(seller, C_OWNER)}")
    print(f"  Situs:         {_col(seller, C_SITUS)}, {county}")
    print(f"  Acres:         {_col(seller, C_ACRES)}")
    print(f"  Contract price (offer to seller): {_fmt_price(offer)}")
    print(f"  Assignment price (builder pays):  {_fmt_price(asgn_price)}")
    if asgn_price and offer:
        try:
            spread = float(asgn_price) - float(offer)
            print(f"  Your spread:   {_fmt_price(spread)}")
        except (TypeError, ValueError):
            pass
    b_display = (_col(builder, B_NAME) if builder else "— (add a builder first)")
    print(f"  Builder:       {b_display}")
    print(f"  Closing target: {close_date}")
    print(f"\n  ⚠️  ATTORNEY REVIEW REQUIRED before sending either document.")

    if args.dry_run:
        print(f"\n{'='*62}\n{psa_name}\n{'='*62}")
        print(psa_text[:1200])
        if len(psa_text) > 1200:
            print("  … (truncated)")
        print(f"\n{'='*62}\n{asgn_name}\n{'='*62}")
        print(asgn_text[:800])
        if len(asgn_text) > 800:
            print("  … (truncated)")
        print("\n  (dry-run — nothing written)")
        return

    # ── Save locally ─────────────────────────────────────────
    stamp   = date.today().isoformat()
    out_dir = OUTPUT_DIR / f"{stamp}-{parcel_safe}"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / psa_name).write_text(psa_text, encoding="utf-8")
    (out_dir / asgn_name).write_text(asgn_text, encoding="utf-8")
    print(f"\n  Saved locally:\n  {out_dir}/")

    # ── Upload to Drive ──────────────────────────────────────
    try:
        land_folder_id   = _find_or_create_folder(token, LAND_FOLDER_NAME, DEALS_PARENT_ID)
        parcel_folder_id = _find_or_create_folder(token, args.parcel, land_folder_id)
        _upload_text(token, psa_name,  psa_text,  parcel_folder_id)
        _upload_text(token, asgn_name, asgn_text, parcel_folder_id)
        print(f"\n  Drive: Olive Tree Investments - Deals / {LAND_FOLDER_NAME} / {args.parcel}/")
    except requests.RequestException as e:
        print(f"\n  [warn] Drive upload failed ({e}). Documents saved locally.")

    print(f"\n  Next steps:")
    print(f"  1. Have attorney review both docs before sending.")
    print(f"  2. Send PSA to seller (email/overnight mail/DocuSign).")
    print(f"  3. Once seller signs, send Assignment to builder + collect EMD.")
    print(f"  4. Run /land-deal to track status, deal-killers, and the spread.")


if __name__ == "__main__":
    main()
