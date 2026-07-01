#!/usr/bin/env python3
"""
trading_insiders.py — smart-money signal feed for the Olive Tree Trading Desk.

Two free sources (no API keys):
  1. House Stock Watcher  — Congress STOCK Act disclosures (~45-day lag)
  2. SEC EDGAR 13F-HR     — Scion Asset Management (Michael Burry), quarterly

Usage:
  python3 scripts/trading_insiders.py              # formatted signal block
  python3 scripts/trading_insiders.py --json       # raw JSON
  python3 scripts/trading_insiders.py --lookback 60  # narrow congress window
"""

import argparse
import io
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pdfplumber
import requests

ROOT = Path(__file__).parent.parent

BURRY_CIK     = "0001649339"  # Scion Asset Management, LLC
BURRY_CACHE   = ROOT / "data" / "insiders_burry_prior.json"
CLERK_BASE    = "https://disclosures-clerk.house.gov"
EDGAR_BASE    = "https://data.sec.gov"
HEADERS       = {"User-Agent": "OliveTreeInvestments brian@olivetreeinv.io"}


# ── Congress (House Clerk PTR PDFs) ──────────────────────────────────────────

def _clerk_ptr_links(last_name: str, years: list[int]) -> list[tuple[str, str]]:
    """Return [(pdf_url, filing_date)] from the House clerk PTR search."""
    links = []
    for year in years:
        try:
            r = requests.post(
                f"{CLERK_BASE}/FinancialDisclosure/ViewMemberSearchResult",
                data={"LastName": last_name, "FilingYear": str(year),
                      "FilingType": "P", "Search": "Search"},
                headers={**HEADERS, "Content-Type": "application/x-www-form-urlencoded"},
                timeout=15,
            )
            r.raise_for_status()
        except Exception:
            continue
        for m in re.finditer(r'href="(public_disc/ptr-pdfs/\d+/(\d+)\.pdf)"', r.text):
            links.append((f"{CLERK_BASE}/{m.group(1)}", f"{year}"))
    return links


def _parse_ptr_pdf(pdf_bytes: bytes, who: str) -> list[dict]:
    """Extract transactions from a House PTR PDF."""
    trades = []
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                # Each transaction block contains a ticker like "(AAPL) [ST]"
                # and a date like "01/16/2026" and amount like "$500,001 - $1,000,000"
                for m in re.finditer(
                    r"\(([A-Z]{1,5})\)\s*\[(?:ST|OP)\].*?"   # ticker + asset type
                    r"\b([PS])\b.*?"                           # transaction type P/S
                    r"(\d{2}/\d{2}/\d{4}).*?"                 # date
                    r"(\$[\d,]+\s*-\s*\$[\d,]+|\$[\d,]+\+?)", # amount
                    text, re.DOTALL,
                ):
                    date_str = m.group(3)
                    try:
                        date_iso = datetime.strptime(date_str, "%m/%d/%Y").date().isoformat()
                    except ValueError:
                        continue
                    trades.append({
                        "who":    who,
                        "ticker": m.group(1),
                        "action": "purchase" if m.group(2) == "P" else "sale",
                        "date":   date_iso,
                        "amount": m.group(4),
                    })
    except Exception as e:
        print(f"  ⚠️  PDF parse error: {e}", file=sys.stderr)
    return trades


def fetch_congress(lookback_days: int = 90) -> list[dict]:
    """Fetch recent Pelosi trades from House clerk PTR PDFs."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).date().isoformat()
    current_year = datetime.now().year
    years = list({current_year, current_year - 1})

    links = _clerk_ptr_links("Pelosi", years)
    out = []
    for pdf_url, _year in links:
        try:
            r = requests.get(pdf_url, headers=HEADERS, timeout=20)
            r.raise_for_status()
            trades = _parse_ptr_pdf(r.content, "Nancy Pelosi")
            out.extend(t for t in trades if t["date"] >= cutoff)
        except Exception as e:
            print(f"  ⚠️  PTR fetch failed {pdf_url}: {e}", file=sys.stderr)

    # Deduplicate (same ticker+date can appear across PDFs)
    seen = set()
    deduped = []
    for t in out:
        key = (t["ticker"], t["date"], t["action"])
        if key not in seen:
            seen.add(key)
            deduped.append(t)

    return sorted(deduped, key=lambda x: x["date"], reverse=True)


# ── Burry 13F ─────────────────────────────────────────────────────────────────

def fetch_burry_13f() -> dict:
    """Fetch Scion's most recent 13F-HR from EDGAR; diff vs cached prior filing."""
    try:
        sub = requests.get(f"{EDGAR_BASE}/submissions/CIK{BURRY_CIK}.json",
                           headers=HEADERS, timeout=15)
        sub.raise_for_status()
        sub = sub.json()
    except Exception as e:
        return {"error": str(e), "holdings": [], "new": [], "exited": [], "as_of": ""}

    filings    = sub.get("filings", {}).get("recent", {})
    forms      = filings.get("form", [])
    accessions = filings.get("accessionNumber", [])
    dates      = filings.get("filingDate", [])

    idx = next((i for i, f in enumerate(forms) if f == "13F-HR"), None)
    if idx is None:
        return {"error": "No 13F-HR found", "holdings": [], "new": [], "exited": [], "as_of": ""}

    accession   = accessions[idx]
    filing_date = dates[idx]
    acc_clean   = accession.replace("-", "")
    cik_int     = int(BURRY_CIK)

    # Parse HTML filing index to locate infotable.xml
    htm_url = (f"https://www.sec.gov/Archives/edgar/data/{cik_int}"
               f"/{acc_clean}/{accession}-index.htm")
    try:
        r = requests.get(htm_url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        # Find infotable.xml link (avoid the xslForm13F_ prefixed version)
        links = re.findall(r'href="(/Archives/[^"]+infotable\.xml)"', r.text, re.IGNORECASE)
        # Prefer the plain path (no xsl prefix)
        infotable_path = next((l for l in links if "xslForm" not in l), links[0] if links else None)
    except Exception as e:
        return {"error": f"Index fetch failed: {e}", "holdings": [], "new": [], "exited": [], "as_of": filing_date}

    if not infotable_path:
        return {"error": "infotable.xml not found in index", "holdings": [], "new": [], "exited": [], "as_of": filing_date}

    try:
        xr = requests.get(f"https://www.sec.gov{infotable_path}", headers=HEADERS, timeout=15)
        xr.raise_for_status()
        xml = xr.text
    except Exception as e:
        return {"error": str(e), "holdings": [], "new": [], "exited": [], "as_of": filing_date}

    holdings = _parse_13f_xml(xml)
    return _diff_burry(holdings, filing_date)


def _parse_13f_xml(xml: str) -> list[tuple[str, int]]:
    entries  = re.findall(r"<infoTable>(.*?)</infoTable>", xml, re.DOTALL)
    holdings = []
    for entry in entries:
        name_m = re.search(r"<nameOfIssuer>(.*?)</nameOfIssuer>", entry)
        val_m  = re.search(r"<value>(.*?)</value>", entry)
        if name_m and val_m:
            try:
                val = int(val_m.group(1).strip()) * 1000  # filed in thousands
            except ValueError:
                val = 0
            holdings.append((name_m.group(1).strip().upper(), val))
    return sorted(holdings, key=lambda x: x[1], reverse=True)


def _diff_burry(current: list[tuple[str, int]], as_of: str) -> dict:
    prior: dict[str, int] = {}
    if BURRY_CACHE.exists():
        try:
            prior = {t: v for t, v in json.loads(BURRY_CACHE.read_text())}
        except Exception:
            pass

    try:
        BURRY_CACHE.write_text(json.dumps(current))
    except Exception as e:
        print(f"  ⚠️  Failed to write Burry cache: {e}", file=sys.stderr)

    current_set = {t for t, _ in current}
    total       = sum(v for _, v in current) or 1
    top10       = [(t, round(v / total * 100, 1)) for t, v in current[:10]]

    return {
        "holdings": top10,
        "new":      sorted(current_set - set(prior)),
        "exited":   sorted(set(prior) - current_set),
        "as_of":    as_of,
    }


# ── public API ───────────────────────────────────────────────────────────────

def get_insider_signal(lookback_days: int = 90) -> dict:
    return {
        "congress": fetch_congress(lookback_days),
        "burry":    fetch_burry_13f(),
        "as_of":    datetime.now(timezone.utc).date().isoformat(),
    }


def format_signal_block(signal: dict) -> str:
    """Prompt-ready text block. Injected into trading_research.py build_prompt()."""
    lines = [
        "## Insider / Smart-Money Signals",
        "⚠️  Congress trades lag ~45 days. Burry 13F is quarterly. Use to confirm, not initiate.",
    ]

    congress = signal.get("congress", [])
    if congress:
        lines.append("\n### Congressional Trades (Pelosi)")
        for tx in congress[:10]:
            lines.append(f"  [{tx['date']}] {tx['who']} — {tx['action'].upper()} {tx['ticker']} ({tx['amount']})")
    else:
        lines.append("\n### Congressional Trades — none in lookback window")

    burry = signal.get("burry", {})
    if burry.get("error"):
        lines.append(f"\n### Burry 13F — fetch error: {burry['error']}")
    else:
        lines.append(f"\n### Burry / Scion 13F (as of {burry.get('as_of', 'unknown')})")
        if burry.get("new"):
            lines.append(f"  New positions: {', '.join(burry['new'])}")
        if burry.get("exited"):
            lines.append(f"  Exited: {', '.join(burry['exited'])}")
        if burry.get("holdings"):
            top5 = ", ".join(f"{t} {p}%" for t, p in burry["holdings"][:5])
            lines.append(f"  Top 5 by portfolio weight: {top5}")

    return "\n".join(lines)


# ── Ticker extraction for orchestrator ───────────────────────────────────────

# 13F company-name → ticker (Burry's known holdings; extend as needed)
_NAME_TO_TICKER: dict[str, str] = {
    "NVIDIA CORPORATION":        "NVDA",
    "PALANTIR TECHNOLOGIES INC": "PLTR",
    "PFIZER INC":                "PFE",
    "HALLIBURTON CO":            "HAL",
    "MOLINA HEALTHCARE INC":     "MOH",
    "BRUKER CORP":               "BRKR",
    "SLM CORP":                  "SLM",
    "LULULEMON ATHLETICA INC":   "LULU",
    "APPLE INC":                 "AAPL",
    "MICROSOFT CORPORATION":     "MSFT",
    "ALPHABET INC":              "GOOGL",
    "AMAZON.COM INC":            "AMZN",
    "META PLATFORMS INC":        "META",
    "TESLA INC":                 "TSLA",
    "JPMORGAN CHASE & CO":       "JPM",
}


def get_insider_tickers(signal: dict) -> tuple[set[str], set[str]]:
    """
    Extract (long_tickers, short_tickers) from an insider signal dict.

    Congress: PURCHASE → long, SALE → short.
    Burry new positions → long (he's entering), exited → short signal.
    Holdings without diff (first run, no prior cache) → long for top-10.
    """
    long_tickers:  set[str] = set()
    short_tickers: set[str] = set()

    # Congress trades
    for tx in signal.get("congress", []):
        ticker = tx.get("ticker", "").strip().upper()
        if not ticker:
            continue
        if "purchase" in tx.get("action", "").lower():
            long_tickers.add(ticker)
        elif "sale" in tx.get("action", "").lower():
            short_tickers.add(ticker)

    # Burry 13F diff
    burry = signal.get("burry", {})
    for name in burry.get("new", []):
        t = _NAME_TO_TICKER.get(name.upper())
        if t:
            long_tickers.add(t)
    for name in burry.get("exited", []):
        t = _NAME_TO_TICKER.get(name.upper())
        if t:
            short_tickers.add(t)

    # If no diff available (first run), treat top-5 holdings as long signals
    if not burry.get("new") and not burry.get("exited"):
        for name, _ in burry.get("holdings", [])[:5]:
            t = _NAME_TO_TICKER.get(name.upper())
            if t:
                long_tickers.add(t)

    # A ticker can't be both — congress trade direction wins over Burry if conflict
    overlap = long_tickers & short_tickers
    for t in overlap:
        congress_dirs = [
            tx.get("action", "") for tx in signal.get("congress", [])
            if tx.get("ticker") == t
        ]
        if any("sale" in d.lower() for d in congress_dirs):
            long_tickers.discard(t)
        else:
            short_tickers.discard(t)

    return long_tickers, short_tickers


# ── CLI smoke test ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Insider signal feed")
    ap.add_argument("--json",     action="store_true", help="Raw JSON output")
    ap.add_argument("--lookback", type=int, default=90, help="Congress lookback in days")
    args = ap.parse_args()

    print("Fetching Congress trades...", file=sys.stderr)
    congress = fetch_congress(args.lookback)
    print(f"  {len(congress)} trade(s) found", file=sys.stderr)

    print("Fetching Burry 13F from EDGAR...", file=sys.stderr)
    burry = fetch_burry_13f()
    if burry.get("error"):
        print(f"  ⚠️  {burry['error']}", file=sys.stderr)
    else:
        print(f"  {len(burry['holdings'])} positions, filed {burry.get('as_of')}", file=sys.stderr)

    signal = {"congress": congress, "burry": burry, "as_of": __import__("datetime").date.today().isoformat()}
    if args.json:
        print(json.dumps(signal, indent=2))
    else:
        print(format_signal_block(signal))
