#!/usr/bin/env python3
"""Apply Olive Tree brand formatting to a Google Doc.

Usage:
  python3 scripts/format_gdoc.py --doc-id <docId>

Applies:
  - Arial font throughout
  - Bold headings (H1 / H2 / H3)
  - Borderless tables
"""

import argparse
import json
import sys
from pathlib import Path

import requests as http

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.gws_auth import get_token

DOCS_BASE = "https://docs.googleapis.com/v1/documents"

NO_BORDER = {
    "width": {"magnitude": 0, "unit": "PT"},
    "dashStyle": "SOLID",
    "color": {"color": {"rgbColor": {}}},
}

HEADING_SIZES = {
    "HEADING_1": 18,
    "HEADING_2": 14,
    "HEADING_3": 12,
}


def _api(method, url, token, body=None):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    resp = http.request(method, url, headers=headers, json=body, timeout=20)
    resp.raise_for_status()
    return resp.json()


def _end_index(body_content):
    idx = 1
    for elem in body_content:
        idx = max(idx, elem.get("endIndex", 1))
    return idx


def _build_requests(doc):
    reqs = []
    content = doc.get("body", {}).get("content", [])

    # 1. Arial across the full document body
    end = _end_index(content)
    if end > 2:
        reqs.append({
            "updateTextStyle": {
                "range": {"startIndex": 1, "endIndex": end - 1},
                "textStyle": {"weightedFontFamily": {"fontFamily": "Arial"}},
                "fields": "weightedFontFamily",
            }
        })

    # 2. Bold headings (also re-assert Arial + size)
    for elem in content:
        para = elem.get("paragraph")
        if not para:
            continue
        named = para.get("paragraphStyle", {}).get("namedStyleType", "")
        if named not in HEADING_SIZES:
            continue
        start = elem.get("startIndex", 0) + 1
        end_p = elem.get("endIndex", 0) - 1
        if end_p <= start:
            continue
        reqs.append({
            "updateTextStyle": {
                "range": {"startIndex": start, "endIndex": end_p},
                "textStyle": {
                    "bold": True,
                    "weightedFontFamily": {"fontFamily": "Arial"},
                    "fontSize": {"magnitude": HEADING_SIZES[named], "unit": "PT"},
                },
                "fields": "bold,weightedFontFamily,fontSize",
            }
        })

    # 3. Remove borders from all top-level tables
    for elem in content:
        if "table" not in elem:
            continue
        table = elem["table"]
        table_start = elem.get("startIndex", 0)
        for row_idx, row in enumerate(table.get("tableRows", [])):
            for col_idx in range(len(row.get("tableCells", []))):
                reqs.append({
                    "updateTableCellStyle": {
                        "tableStartLocation": {"index": table_start},
                        "rowIndex": row_idx,
                        "columnIndex": col_idx,
                        "tableCellStyle": {
                            "borderLeft": NO_BORDER,
                            "borderRight": NO_BORDER,
                            "borderTop": NO_BORDER,
                            "borderBottom": NO_BORDER,
                        },
                        "fields": "borderLeft,borderRight,borderTop,borderBottom",
                    }
                })

    return reqs


def format_doc(doc_id: str, verbose: bool = True) -> None:
    token = get_token()

    if verbose:
        print(f"Fetching doc {doc_id}...")
    doc = _api("GET", f"{DOCS_BASE}/{doc_id}", token)
    if verbose:
        print(f"  Title: {doc.get('title', 'Untitled')}")

    reqs = _build_requests(doc)
    if not reqs:
        if verbose:
            print("  No formatting requests generated.")
        return

    if verbose:
        print(f"  Applying {len(reqs)} formatting requests...")
    _api("POST", f"{DOCS_BASE}/{doc_id}:batchUpdate", token, {"requests": reqs})
    if verbose:
        print("  Done — Arial font, bold headings, borderless tables applied.")


def main():
    parser = argparse.ArgumentParser(
        description="Apply Olive Tree brand formatting to a Google Doc"
    )
    parser.add_argument("--doc-id", required=True, help="Google Doc document ID")
    parser.add_argument("--quiet", action="store_true", help="Suppress output")
    args = parser.parse_args()
    format_doc(args.doc_id, verbose=not args.quiet)


if __name__ == "__main__":
    main()
