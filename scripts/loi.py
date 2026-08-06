#!/usr/bin/env python3
"""
Olive Tree Investments — LOI Generator

Turns a set of deal values into a finished Letter of Intent: copies the LOI
template Google Doc into the property's deal folder, replaces every placeholder
token, exports a PDF, and uploads the PDF alongside the Doc. The /loi skill
collects terms conversationally, writes them to a values JSON, and calls this.

Single source of truth for fields/defaults/formulas/tokens is
templates/loi-fields.json — this script never hardcodes them.

Reuses the stdlib (urllib) Google infra from loom_sync.py — cloud-ready, no
extra packages. Mirrors the export/upload helpers in loi_sync.py.

Auth: GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / GOOGLE_REFRESH_TOKEN
(read from env or ../.env; falls back to `gws auth export` locally).

Usage:
  python3 scripts/loi.py --values /tmp/loi_values.json
  python3 scripts/loi.py --values /tmp/loi_values.json --folder-id <deal_folder_id>
  python3 scripts/loi.py --values /tmp/loi_values.json --dry-run   # resolve only, no API

values JSON: a flat {KEY: value} object using the keys in loi-fields.json,
e.g. {"OFFER_PRICE": 950000, "UNITS": 24, "BROKER_NAME": "Jane Doe", ...}.
Anything omitted falls back to the field's default; formula fields are computed.
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import loom_sync as G
from loom_sync import _http, _auth, _load_dotenv, get_token, find_or_create_folder

# Reuse the PDF export + upload helpers already written for the archive routine.
from loi_sync import export_doc_pdf, drive_upload_pdf

DOCS_BATCH = "https://docs.googleapis.com/v1/documents/{}:batchUpdate"
FIELDS_PATH = Path(__file__).resolve().parent.parent / "templates" / "loi-fields.json"


# ─────────────────────────────────────────────
# Value resolution
# ─────────────────────────────────────────────

def _num(v):
    """Parse a money/number value that may arrive as '950,000' or '$950000'."""
    if isinstance(v, (int, float)):
        return float(v)
    return float(re.sub(r"[,$\s]", "", str(v)))


def _fmt_money_plain(v):
    return f"{int(round(_num(v))):,}"


def resolve(spec, values):
    """Merge provided values with defaults, compute formulas, apply formatting.

    Returns (resolved, missing) where resolved maps KEY -> display string and
    missing is the list of required keys with no value.
    """
    fields = spec["fields"]
    resolved, missing = {}, []

    # Pass 1 — literal values + defaults (skip formula fields for now).
    for key, meta in fields.items():
        if "formula" in meta:
            continue
        val = values.get(key, meta.get("default"))
        if val is None:
            missing.append(key)
            continue
        if val == "today" and meta.get("type") == "date_mmddyy":
            val = datetime.now().strftime("%m/%d/%y")
        resolved[key] = val

    # Pass 2 — formula fields, evaluated over numeric inputs.
    numeric = {}
    for key, meta in fields.items():
        if "formula" in meta:
            continue
        try:
            numeric[key] = _num(values.get(key, meta.get("default")))
        except (TypeError, ValueError):
            pass
    for key, meta in fields.items():
        if "formula" not in meta:
            continue
        try:
            result = eval(meta["formula"], {"__builtins__": {}}, numeric)  # noqa: S307 — keys/operands are ours
        except (ZeroDivisionError, NameError, TypeError):
            missing.append(key)
            continue
        if meta.get("round"):
            n = meta["round"]
            result = round(result / n) * n
        resolved[key] = result

    # Pass 3 — formatting.
    for key, meta in fields.items():
        if key not in resolved:
            continue
        if meta.get("type") == "money_plain":
            resolved[key] = _fmt_money_plain(resolved[key])
        else:
            resolved[key] = str(resolved[key])

    return resolved, missing


def build_replacements(spec, resolved):
    """doc_token -> value, longest token first so substrings don’t collide
    (e.g. ‘<Purchase Price * .01>’ before ‘<Purchase Price>’). DATE emits both
    straight and smart-apostrophe variants of its token.
    logo_image fields always map to ‘’ — image insertion is handled separately."""
    pairs = []
    for key, meta in spec["fields"].items():
        token = meta.get("doc_token")
        if not token or key not in resolved:
            continue
        value = "" if meta.get("type") == "logo_image" else resolved[key]
        pairs.append((token, value))
        if "'" in token:
            pairs.append((token.replace("'", "’"), value))
    pairs.sort(key=lambda p: len(p[0]), reverse=True)
    return pairs


def _resolve_logo_url(logo_value):
    """Return a direct, publicly-fetchable image URL for the Docs API, or None.

    The Docs API fetches images server-side with NO auth session, so LOGO must be
    a public URL that returns raw image bytes — e.g. the logo hosted on the company
    domain (olivetreeinv.io, served via the GHL CDN). Google Drive share links do
    NOT work: Google serves an HTML wrapper page, not the image bytes (verified). So
    Drive/Google links are rejected here with a hint instead of failing cryptically.
    """
    if not logo_value:
        return None
    v = logo_value.strip()
    if re.search(r"drive\.google\.com|docs\.google\.com|googleusercontent\.com", v):
        print("WARNING: Drive/Google links can't be fetched by the Docs API "
              "(Google serves HTML, not image bytes). Use a direct public image URL "
              "(e.g. the logo hosted on olivetreeinv.io).", file=sys.stderr)
        return None
    if v.startswith(("http://", "https://")):
        return v
    return None


def insert_logo(token, doc_id, image_url, height_in=0.75, max_height_in=1.0):
    """Insert an inline image at position 1 (top of document body).

    Height is set in inches (default 0.75"); width scales proportionally. If the
    requested height exceeds max_height_in (1"), the image is still inserted but a
    warning is printed."""
    if height_in > max_height_in:
        print(f"WARNING: logo height {height_in}\" exceeds the {max_height_in}\" limit "
              "— inserting anyway.", file=sys.stderr)
    request = {"insertInlineImage": {
        "uri": image_url,
        "location": {"index": 1},
        "objectSize": {
            "height": {"magnitude": height_in * 72, "unit": "PT"},
        },
    }}
    _http("POST", DOCS_BATCH.format(doc_id),
          headers={**_auth(token), "Content-Type": "application/json"},
          data=json.dumps({"requests": [request]}).encode(), timeout=60)


# ─────────────────────────────────────────────
# Google Docs / Drive
# ─────────────────────────────────────────────

def copy_template(token, template_id, name, folder_id):
    body = json.dumps({"name": name, "parents": [folder_id]}).encode()
    resp = _http("POST", f"{G.DRIVE_BASE}/files/{template_id}/copy?fields=id",
                 headers={**_auth(token), "Content-Type": "application/json"},
                 data=body, timeout=60)
    return resp["id"]


def replace_tokens(token, doc_id, pairs):
    requests = [{"replaceAllText": {
        "containsText": {"text": old, "matchCase": True},
        "replaceText": new,
    }} for old, new in pairs]
    _http("POST", DOCS_BATCH.format(doc_id),
          headers={**_auth(token), "Content-Type": "application/json"},
          data=json.dumps({"requests": requests}).encode(), timeout=60)


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Generate an Olive Tree LOI Google Doc + PDF.")
    ap.add_argument("--values", required=True, help="Path to {KEY: value} JSON of deal terms.")
    ap.add_argument("--folder-id", help="Deal folder Drive ID. If omitted, resolved/created "
                                        "by PROPERTY_ADDRESS under the Deals root.")
    ap.add_argument("--name", help="Output Doc name. Default: '<property> — LOI — <date>'.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Resolve values and print the plan; make no API calls.")
    args = ap.parse_args()

    spec = json.loads(FIELDS_PATH.read_text())
    values = json.loads(Path(args.values).read_text())

    resolved, missing = resolve(spec, values)
    if missing:
        print(f"ERROR: missing required field(s): {', '.join(sorted(set(missing)))}",
              file=sys.stderr)
        sys.exit(1)

    pairs = build_replacements(spec, resolved)

    # Output name + property short label.
    prop = resolved.get("PROPERTY_ADDRESS", "Property")
    prop_short = prop.split(",")[0].strip()
    date_label = datetime.now().strftime("%Y-%m-%d")
    out_name = args.name or f"{prop_short} — LOI — {date_label}"

    if args.dry_run:
        print("DRY RUN — no API calls made.\n")
        print("Resolved values:")
        for k in spec["fields"]:
            if k in resolved:
                print(f"  {k:18} = {resolved[k]}")
        logo_img_url = _resolve_logo_url(resolved.get("LOGO", ""))
        print(f"\nDoc replacements: {len(pairs)} token(s)")
        print(f"Logo image      : {logo_img_url or 'omitted'}")
        print(f"Output Doc name : {out_name}")
        print(f"Folder          : {args.folder_id or '(resolve by property under Deals root)'}")
        return

    _load_dotenv()
    token = get_token()

    folder_id = args.folder_id or find_or_create_folder(
        token, prop_short, parent_id=spec.get("deals_root_folder_id"))

    doc_id = copy_template(token, spec["template_doc_id"], out_name, folder_id)
    replace_tokens(token, doc_id, pairs)

    logo_img_url = _resolve_logo_url(resolved.get("LOGO", ""))
    logo_inserted = False
    if logo_img_url:
        try:
            insert_logo(token, doc_id, logo_img_url,
                        height_in=spec.get("logo_height_in", 0.75),
                        max_height_in=spec.get("logo_max_height_in", 1.0))
            logo_inserted = True
        except Exception as e:
            print(f"WARNING: logo image insert failed ({e}). "
                  "Paste logo manually into the Doc — all text replacements are complete.",
                  file=sys.stderr)

    pdf_bytes = export_doc_pdf(token, doc_id)
    pdf_link = drive_upload_pdf(token, folder_id, f"{out_name}.pdf", pdf_bytes)

    print(json.dumps({
        "doc_id": doc_id,
        "doc_url": f"https://docs.google.com/document/d/{doc_id}/edit",
        "pdf_link": pdf_link,
        "folder_id": folder_id,
        "replacements": len(pairs),
        "logo_inserted": logo_inserted,
    }, indent=2))


if __name__ == "__main__":
    main()
