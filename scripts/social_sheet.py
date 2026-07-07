#!/usr/bin/env python3
"""
social_sheet.py — log one Instagram post to the tracking sheet
"Olive Tree Investments - Instagram Posts". Mirrors the Looms sheet pattern.

Columns: Date | Title | Type | Topic / Angle | Caption | Slides (Drive) | Metricool Link | Status

CLI:
    python3 scripts/social_sheet.py --date 2026-07-03 --title "..." --type "MF Carousel" \
        --topic "..." --caption "..." --slides "<drive folder url>" \
        --metricool "<planner url>" --status Draft
"""
from __future__ import annotations
import argparse, sys
from pathlib import Path
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gws_auth import get_token

SHEETS = "https://sheets.googleapis.com/v4/spreadsheets"
SHEET_ID = "1wSdYytgnEZrLGiwVarA-OIN2OfJ1WOlB7MOYBMdRKrQ"


def append_post(date, title, ptype, topic, caption, slides_url, metricool_url, status="Draft"):
    tok = get_token()
    row = [date, title, ptype, topic, caption, slides_url, metricool_url, status]
    r = requests.post(
        f"{SHEETS}/{SHEET_ID}/values/A1:H1:append",
        headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
        params={"valueInputOption": "RAW", "insertDataOption": "INSERT_ROWS"},
        json={"values": [row]}, timeout=30,
    )
    r.raise_for_status()
    return r.json().get("updates", {}).get("updatedRange")


def main():
    ap = argparse.ArgumentParser()
    for f in ("date", "title", "type", "topic", "caption", "slides", "metricool"):
        ap.add_argument(f"--{f}", required=(f in ("date", "title")), default="")
    ap.add_argument("--status", default="Draft")
    a = ap.parse_args()
    print(append_post(a.date, a.title, a.type, a.topic, a.caption, a.slides, a.metricool, a.status))


if __name__ == "__main__":
    main()
