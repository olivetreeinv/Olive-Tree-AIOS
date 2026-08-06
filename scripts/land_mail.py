#!/usr/bin/env python3
"""
Olive Tree — Land Mail (/land-mail engine)

Reads the Land Sellers tab and generates one direct-mail offer letter per
parcel, merged from templates/land-mail-offer.md. Output is per-parcel .txt
files + a single merged printable in output/land-mail/<date>-<zip>/.

Nothing is sent automatically. Brian prints, stuffs, and mails.

Usage:
  # Generate all new mail-channel sellers for Cartersville
  python3 scripts/land_mail.py --zip 30120

  # Preview the first 3 letters without writing files
  python3 scripts/land_mail.py --zip 30120 --dry-run --limit 3

  # Include already-generated rows (re-mail or reprint)
  python3 scripts/land_mail.py --zip 30120 --status all
"""

import argparse
import os
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

from land_sheets import get_token, read_rows  # noqa: E402

load_dotenv()

TEMPLATE_PATH     = Path(__file__).parent.parent / "templates" / "land-mail-offer.md"
PSA_TEMPLATE_PATH = Path(__file__).parent.parent / "templates" / "land-psa-template.md"
OUTPUT_DIR        = Path(__file__).parent.parent / "output" / "land-mail"

# Land Sellers column indices (land_setup.TABS["Land Sellers"])
C_PARCEL  =  0   # Parcel ID
C_SITUS   =  1   # Situs Address
C_ZIP     =  2   # Situs Zip (site, used for county lookup)
C_ACRES   =  4   # Acres
C_OWNER   =  5   # Owner Name
C_ADDR    =  6   # Owner Mailing Address
C_CITY    =  7   # Owner City
C_STATE   =  8   # Owner State
C_OFFER   = 11   # Offer Price
C_CHANNEL = 14   # Channel (mail / call)
C_STATUS  = 15   # Call Status
C_OZIP    = 20   # Owner Zip (appended this session)

# Zip → human county name for the letter body
ZIP_COUNTY = {
    "30120": "Bartow County, GA",
    "30121": "Bartow County, GA",
    "30040": "Forsyth County, GA",
    "30041": "Forsyth County, GA",
}

BRIAN_PHONE = os.getenv("BRIAN_PHONE", "[PHONE]")
BRIAN_EMAIL = os.getenv("BRIAN_EMAIL", "brian@olivetreeinv.io")

# PSA (enclosed contract) constants — not on the Land Sellers row. Env-overridable.
BUYER_NAME = os.getenv("BUYER_LEGAL_NAME", "Olive Tree Investments, LLC")
EMD        = os.getenv("LAND_EMD", "$10")
CLOSE_DAYS = int(os.getenv("LAND_CLOSE_DAYS", "30"))

_BOLD = re.compile(r"\*\*(.+?)\*\*")     # strip markdown bold from plain-text output


def _col(row, idx, default=""):
    return (row[idx].strip() if len(row) > idx and row[idx] else default)


def _load_template(path=TEMPLATE_PATH):
    raw = path.read_text()
    # Everything after the first horizontal rule is the body (drops the header /
    # attorney-warning preamble — never goes in the seller-facing document).
    if "\n---\n" in raw:
        body = raw.split("\n---\n", 1)[1].lstrip("\n")
    else:
        body = raw
    return body


def _offer_fmt(row):
    offer_raw = _col(row, C_OFFER)
    try:
        return f"${float(offer_raw):,.0f}"
    except (ValueError, TypeError):
        return offer_raw or "[OFFER]"


def merge(template, row):
    today = date.today().strftime("%B %d, %Y")
    situs_zip = _col(row, C_ZIP)
    county = ZIP_COUNTY.get(situs_zip, "the county")

    mapping = {
        "{{DATE}}":                  today,
        "{{OWNER_NAME}}":            _col(row, C_OWNER) or "[OWNER NAME]",
        "{{OWNER_MAILING_ADDRESS}}": _col(row, C_ADDR)  or "[ADDRESS]",
        "{{OWNER_CITY}}":            _col(row, C_CITY)  or "[CITY]",
        "{{OWNER_STATE}}":           _col(row, C_STATE) or "[STATE]",
        "{{OWNER_ZIP}}":             _col(row, C_OZIP),
        "{{SITUS_ADDRESS}}":         _col(row, C_SITUS) or situs_zip,
        "{{COUNTY}}":                county,
        "{{ACRES}}":                 _col(row, C_ACRES) or "[ACRES]",
        "{{PARCEL_ID}}":             _col(row, C_PARCEL) or "[PARCEL]",
        "{{OFFER}}":                 _offer_fmt(row),
        "{{PHONE}}":                 BRIAN_PHONE,
        "{{EMAIL}}":                 BRIAN_EMAIL,
    }
    result = template
    for k, v in mapping.items():
        result = result.replace(k, str(v))
    # Strip markdown bold markers so printed letters look clean.
    result = _BOLD.sub(r"\1", result)
    return result


def merge_psa(template, row):
    """Fill the enclosed Purchase & Sale Agreement for one parcel (the sign-and-
    return contract). Closing is relative to the Effective Date (seller signs on
    their own timeline), EMD is due at closing, and the buyer carries '/and Assigns'."""
    situs_zip = _col(row, C_ZIP)
    county = ZIP_COUNTY.get(situs_zip, "the county")
    county_short = county.replace(", GA", "").replace(", Georgia", "")  # template appends ", Georgia"
    seller_line = f"{_col(row, C_CITY)}, {_col(row, C_STATE)} {_col(row, C_OZIP)}".strip(", ")
    seller_addr = ", ".join(p for p in (_col(row, C_ADDR), seller_line) if p.strip(", "))

    mapping = {
        "{{DATE}}":                    date.today().strftime("%B %d, %Y"),
        "{{BUYER_NAME}}":              BUYER_NAME,
        "{{SELLER_NAME}}":             _col(row, C_OWNER) or "[SELLER NAME]",
        "{{SELLER_MAILING_ADDRESS}}":  seller_addr or "[SELLER ADDRESS]",
        "{{PARCEL_ID}}":               _col(row, C_PARCEL) or "[PARCEL]",
        "{{SITUS_ADDRESS}}":           _col(row, C_SITUS) or situs_zip,
        "{{COUNTY}}":                  county_short,
        "{{ACRES}}":                   _col(row, C_ACRES) or "[ACRES]",
        "{{PURCHASE_PRICE}}":          _offer_fmt(row),
        "{{EMD}}":                     EMD,
        "{{CLOSING_DATE}}":            f"{CLOSE_DAYS} days after the Effective Date",
        "{{CLOSE_DAYS}}":              str(CLOSE_DAYS),
    }
    result = template
    for k, v in mapping.items():
        result = result.replace(k, str(v))
    return _BOLD.sub(r"\1", result)


def main():
    ap = argparse.ArgumentParser(description="Generate land offer letters from Land Sellers tab.")
    ap.add_argument("--zip", dest="zip_code", required=True,
                    help="Situs zip to pull sellers for (e.g. 30120)")
    ap.add_argument("--status", default="new",
                    help="call_status filter: 'new', 'mail', or 'all' (default: new)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Preview up to 3 letters; don't write files")
    ap.add_argument("--limit", type=int,
                    help="Cap the number of letters generated")
    ap.add_argument("--with-contract", action="store_true",
                    help="Also enclose a pre-filled signable PSA per parcel (source-of-truth "
                         "mail-back method). Requires GA attorney sign-off on the PSA template.")
    args = ap.parse_args()

    if not TEMPLATE_PATH.exists():
        sys.exit(f"Template not found: {TEMPLATE_PATH}")

    template = _load_template()
    token    = get_token()
    rows     = read_rows(token, "Land Sellers")

    if len(rows) <= 1:
        sys.exit("Land Sellers tab is empty — run /land-sellers first.")

    data = rows[1:]

    # Filter: zip + channel=mail + status
    filtered = []
    skipped_no_addr = 0
    for r in data:
        if _col(r, C_ZIP) != args.zip_code:
            continue
        if _col(r, C_CHANNEL) != "mail":
            continue
        if args.status != "all" and _col(r, C_STATUS) not in ("new", args.status):
            continue
        if not _col(r, C_ADDR):
            skipped_no_addr += 1
            continue
        filtered.append(r)

    if args.limit:
        filtered = filtered[:args.limit]

    print(f"\n  Land Mail — zip {args.zip_code}")
    print(f"  {len(filtered)} letters to generate "
          f"(channel=mail, status={args.status})"
          + (f" — {skipped_no_addr} skipped (no mailing address)" if skipped_no_addr else ""))

    if not filtered:
        print("\n  Nothing to merge.")
        print("  If /land-sellers ran successfully, check that rows have channel='mail'.")
        return

    letters = [(r, merge(template, r)) for r in filtered]

    contracts = None
    if args.with_contract:
        if not PSA_TEMPLATE_PATH.exists():
            sys.exit(f"PSA template not found: {PSA_TEMPLATE_PATH}")
        # A binding contract must never go out with a placeholder price — hard-stop
        # and name the bad parcels so the Offer column gets fixed in /land-sellers.
        no_price = [_col(r, C_PARCEL) or "(no id)" for r in filtered
                    if _offer_fmt(r).startswith("[")]
        if no_price:
            sys.exit(f"Refusing to generate contracts: {len(no_price)} parcel(s) have no "
                     f"numeric Offer (e.g. {no_price[:3]}). Fix the Offer column in Land Sellers first.")
        psa = _load_template(PSA_TEMPLATE_PATH)
        contracts = [merge_psa(psa, r) for r in filtered]
        print("\n  " + "!" * 60)
        print("  --with-contract: enclosing a SIGNABLE Purchase & Sale Agreement")
        print("  per parcel. A seller's signature forms a BINDING contract.")
        print("  GA ATTORNEY REVIEW of templates/land-psa-template.md is REQUIRED")
        print("  before mailing any of these. Nothing sends automatically.")
        print("  " + "!" * 60)

    if args.dry_run:
        sep = "=" * 62
        for i, (r, letter) in enumerate(letters[:3], 1):
            print(f"\n{sep}\nLETTER {i}: {_col(r, C_OWNER)} — {_col(r, C_SITUS)}\n{sep}")
            print(letter[:700])
            if len(letter) > 700:
                print("  … (letter continues)")
            if contracts:
                print(f"\n{sep}\nENCLOSED CONTRACT {i} (PSA)\n{sep}")
                print(contracts[i - 1][:700])
                print("  … (contract continues)")
        if len(letters) > 3:
            print(f"\n  … and {len(letters) - 3} more. Use --limit to see fewer.")
        print(f"\n  (dry-run — no files written)")
        return

    # Write output
    stamp   = date.today().isoformat()
    out_dir = OUTPUT_DIR / f"{stamp}-{args.zip_code}"
    out_dir.mkdir(parents=True, exist_ok=True)

    page_break = "\n" + ("=" * 62) + "\n\n"
    all_pages, all_contracts = [], []

    for i, (r, letter) in enumerate(letters, 1):
        parcel_safe = re.sub(r"[^A-Za-z0-9_-]", "-", _col(r, C_PARCEL))
        (out_dir / f"{i:03d}-{parcel_safe}.txt").write_text(letter, encoding="utf-8")
        all_pages.append(letter)
        if contracts:
            doc = contracts[i - 1]
            (out_dir / f"{i:03d}-{parcel_safe}-CONTRACT.txt").write_text(doc, encoding="utf-8")
            all_contracts.append(doc)
        print(f"  [{i:3d}] {_col(r, C_OWNER):32} ${_col(r, C_OFFER):>8} → {parcel_safe}"
              + ("  +contract" if contracts else ""))

    (out_dir / "_all_letters.txt").write_text(page_break.join(all_pages), encoding="utf-8")
    if all_contracts:
        (out_dir / "_all_contracts.txt").write_text(page_break.join(all_contracts), encoding="utf-8")

    print(f"\n  {len(letters)} letter(s) written to:")
    print(f"  {out_dir}/")
    print(f"\n  Print _all_letters.txt for the full batch (use Page Breaks between letters).")
    if all_contracts:
        print(f"  Print _all_contracts.txt too — stuff ONE letter + ONE contract per envelope,")
        print(f"  matched by the NNN- parcel prefix. ⚠️  Attorney sign-off required first.")
    print(f"  Track responses: update Outcome column in Land Sellers tab after calls come in.")
    if skipped_no_addr:
        print(f"\n  Note: {skipped_no_addr} row(s) skipped — no mailing address. "
              f"Verify parcel data or skip-trace for those owners.")


if __name__ == "__main__":
    main()
