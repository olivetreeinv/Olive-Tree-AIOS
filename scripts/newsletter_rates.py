#!/usr/bin/env python3
"""
newsletter_rates.py — live residential + commercial rate table for the newsletter.

Sources
-------
Residential : mortgagenewsdaily.com/mortgage-rates  (MND daily index, single rates)
Commercial  : commercialloandirect.com/apartment-interest-rates.php  (rate ranges)

`rates_html()` returns an email-safe HTML table matching the old
rate-2026-05.png layout. Each run caches this month's midpoints in
data/newsletter_rates.json so the Monthly Change badges are real
month-over-month moves.

CLI: python3 scripts/newsletter_rates.py [--html out.html]
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

REPO = Path(__file__).parent.parent
CACHE = REPO / "data" / "newsletter_rates.json"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
PCT = re.compile(r"(\d+\.\d+)%")

MND_URL = "https://www.mortgagenewsdaily.com/mortgage-rates"
CLD_URL = "https://www.commercialloandirect.com/apartment-interest-rates.php"

# MND daily-table row label → display label
RESIDENTIAL = [
    ("30 Yr. Fixed", "30-Year Fixed Mortgage"),
    ("15 Yr. Fixed", "15-Year Fixed Mortgage"),
    ("30 Yr. Jumbo", "30-Year Jumbo"),
    ("7/6 SOFR ARM", "7/6 SOFR ARM"),
    ("30 Yr. FHA", "FHA Loans"),
    ("30 Yr. VA", "VA Loans"),
]

# CLD table needle(s) matched against "preceding heading + first row" → display
# label (min/max of all rate %s in the matched tables)
COMMERCIAL = [
    (["FNMA Standard", "Freddie Mac Apartment Loan Rates"], "Agency Debt (Fannie/Freddie)"),
    (["Bridge Loan Rates"], "Bridge Loans (Floating)"),
    (["CMBS"], "CMBS (Conduit)"),
    (["Insurance Loan Rates"], "Life Company Loans"),
    (["FHA Multifamily"], "HUD/FHA Multifamily"),
]


def fetch_residential() -> dict:
    """{display_label: rate_float} from MND's daily table."""
    soup = BeautifulSoup(requests.get(MND_URL, headers=UA, timeout=30).text, "html.parser")
    out = {}
    for table in soup.find_all("table"):
        text = {}
        for tr in table.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
            if len(cells) >= 2:
                # first occurrence wins: MND daily rows precede the Freddie/MBA weekly surveys
                text.setdefault(cells[0], cells[1])
        if "30 Yr. Fixed" in text:
            for src, label in RESIDENTIAL:
                m = PCT.search(text.get(src, ""))
                if m:
                    out[label] = float(m.group(1))
            break
    if len(out) < 4:
        sys.exit(f"MND parse failed — got {out}")
    return out


def fetch_commercial() -> dict:
    """{display_label: (lo, hi)} from Commercial Loan Direct's product tables."""
    soup = BeautifulSoup(requests.get(CLD_URL, headers=UA, timeout=30).text, "html.parser")
    titled = []  # (title, all rate floats in table)
    for table in soup.find_all("table"):
        first = table.find("tr")
        title = first.get_text(" ", strip=True) if first else ""
        heading = table.find_previous(["h1", "h2", "h3", "h4", "strong", "b"])
        title = (heading.get_text(" ", strip=True) + " " if heading else "") + title
        # ponytail: <=20 drops LTV percents (e.g. "83.3% - Investment") — rates never exceed ~13%
        vals = [float(v) for v in PCT.findall(table.get_text(" ", strip=True)) if float(v) <= 20]
        titled.append((title, vals))
    out = {}
    for needles, label in COMMERCIAL:
        vals = [v for title, tv in titled for v in tv
                if any(n.lower() in title.lower() for n in needles)]
        if vals:
            out[label] = (min(vals), max(vals))
    if len(out) < 4:
        sys.exit(f"Commercial Loan Direct parse failed — got {out}")
    return out


def _load_cache() -> dict:
    return json.loads(CACHE.read_text()) if CACHE.exists() else {}


def _monthly_change(cache: dict, month: str, label: str, mid: float):
    """Signed delta vs the most recent cached month before `month`, or None."""
    prior = sorted(m for m in cache if m < month)
    for m in reversed(prior):
        if label in cache[m]:
            return round(mid - cache[m][label], 2)
    return None


def _badge(delta) -> str:
    if delta is None:
        style, txt = ("#FBF3D5", "#8A6D1A"), "&#8594; New"
    elif abs(delta) < 0.05:
        style, txt = ("#FBF3D5", "#8A6D1A"), "&#8594; Stable"
    elif delta > 0:
        style, txt = ("#F6DDDD", "#A33333"), f"&#8593; {delta:+.2f}%"
    else:
        style, txt = ("#DDEEDD", "#2A6E2A"), f"&#8595; {delta:.2f}%"
    return (f'<span style="display:inline-block;padding:3px 10px;border-radius:6px;'
            f'background:{style[0]};color:{style[1]};font-weight:bold;font-size:11px;">{txt}</span>')


def rates_html() -> str:
    """Fetch both sources, update the monthly cache, return the email table."""
    res = fetch_residential()
    com = fetch_commercial()
    month = datetime.now().strftime("%Y-%m")
    cache = _load_cache()

    mids = {**res, **{k: round((lo + hi) / 2, 2) for k, (lo, hi) in com.items()}}
    changes = {k: _monthly_change(cache, month, k, v) for k, v in mids.items()}
    cache[month] = mids
    CACHE.write_text(json.dumps(cache, indent=1))

    cell = "padding:10px 12px;font-family:arial,helvetica,sans-serif;font-size:12px;color:#26281C;"
    rows = []

    def row(label, rate, key, shade):
        rows.append(
            f'<tr style="background:{shade};">'
            f'<td style="{cell}">{label}</td>'
            f'<td style="{cell}font-weight:bold;color:#1B1E08;white-space:nowrap;">{rate}</td>'
            f'<td style="{cell}white-space:nowrap;">{_badge(changes.get(key))}</td></tr>'
        )

    for i, (_, label) in enumerate(RESIDENTIAL):
        if label in res:
            row(label, f"{res[label]:.2f}%", label, "#F7F8FA" if i % 2 == 0 else "#FFFFFF")

    rows.append(
        '<tr style="background:#F7F8FA;border-top:2px solid #505A19;">'
        f'<td colspan="3" style="{cell}color:#505A19;">Multifamily &amp; Commercial</td></tr>'
    )
    for i, (_, label) in enumerate(COMMERCIAL):
        if label in com:
            lo, hi = com[label]
            row(label, f"{lo:.2f}% - {hi:.2f}%", label, "#FFFFFF" if i % 2 == 0 else "#F7F8FA")

    head = "padding:12px;font-family:arial,helvetica,sans-serif;font-size:12px;color:#FFFFFF;text-align:left;letter-spacing:1px;"
    today = datetime.now().strftime("%B %-d, %Y")
    return (
        '<table width="100%" cellpadding="0" cellspacing="0" border="0" '
        'style="border:1px solid #E4DFCF;border-radius:16px;border-collapse:separate;overflow:hidden;margin:0 0 8px;">'
        '<tr style="background:#1B1E08;">'
        f'<th style="{head}">LOAN TYPE</th><th style="{head}">CURRENT RATE RANGE</th><th style="{head}">MONTHLY CHANGE</th></tr>'
        + "".join(rows)
        + "</table>"
        '<p style="margin:0 0 16px;font-size:11px;color:#8A8770;font-family:arial,helvetica,sans-serif;">'
        f"Sources: Mortgage News Daily (residential) &middot; Commercial Loan Direct (multifamily) &mdash; pulled {today}.</p>"
    )


if __name__ == "__main__":
    html = rates_html()
    if len(sys.argv) > 2 and sys.argv[1] == "--html":
        Path(sys.argv[2]).write_text(html)
        print(f"Wrote {sys.argv[2]}")
    else:
        for m, vals in sorted(_load_cache().items()):
            print(m, json.dumps(vals))
