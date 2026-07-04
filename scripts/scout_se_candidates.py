#!/usr/bin/env python3
"""Scout the 12 SE land-flip candidates via ReportAll, log to Land Markets, print a table.

One button for the whole SE expansion list (decisions/log.md 2026-07-01). Blocked
until the ReportAll quota clears (client in09INjjWJ hit its 1000-req all-time cap).
Run: python3 scripts/scout_se_candidates.py
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

import land_markets as lm
from land_sheets import get_token, upsert_row
_token = get_token()

# (zip, county-label, state, strategy, band)
TARGETS = [
    ("30506", "hall-ga",      "GA", "A", (1.0, 10.0)),
    ("38401", "maury-tn",     "TN", "A", (1.0, 10.0)),
    ("30549", "jackson-ga",   "GA", "A", (1.0, 10.0)),
    ("35611", "limestone-al", "AL", "A", (1.0, 10.0)),
    ("27520", "johnston-nc",  "NC", "A", (1.0, 10.0)),
    ("30157", "paulding-ga",  "GA", "A", (1.0, 10.0)),
    ("29730", "york-sc",      "SC", "A", (1.0, 10.0)),
    ("34472", "marion-fl",    "FL", "B", (0.2, 0.5)),
    ("33972", "lee-fl",       "FL", "B", (0.2, 0.5)),
    ("33948", "charlotte-fl", "FL", "B", (0.2, 0.5)),
    ("34434", "citrus-fl",    "FL", "B", (0.2, 0.5)),
    ("29526", "horry-sc",     "SC", "B", (0.2, 0.5)),
]

CAP = 500
results = []
for zc, county, state, strat, band in TARGETS:
    try:
        m = lm.screen_zip_reportall(county, zc, state, band, cap=CAP)
        # log to the sheet (best-effort), keyed on zip like main()
        try:
            upsert_row(_token, "Land Markets", 1, m["zip"], lm._row(m))
        except Exception as e:
            print(f"  (sheet log skipped for {zc}: {e})", flush=True)
        results.append((zc, county, strat, m))
        print(f"OK  {county:14} {zc}  strat-{strat}  verdict={m['go_nogo']:6} "
              f"vac_oos={m['vacant_oos']:>4}  band_lots={m['band_lots']:>4}  "
              f"unif={m['uniformity']}  med_ac={m['median_acres']}  "
              f"score={m['score']}  capped={m.get('capped')}", flush=True)
    except Exception as e:
        print(f"ERR {county:14} {zc}  {type(e).__name__}: {e}", flush=True)
        results.append((zc, county, strat, None))

print("\nDONE", flush=True)
