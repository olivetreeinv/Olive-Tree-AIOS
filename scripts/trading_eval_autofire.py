#!/usr/bin/env python3
"""Auto-start the clean Aug 1–31 trading-desk eval the moment the Alpaca paper account
is reset to $50k (Brian does that reset in the dashboard — there's no API for it).

`maybe_fire_eval()` is called once per desk cycle by trading_orchestrator. It no-ops until the
LIVE account equity reads ~$50k, then ONCE:
  1. archives all July tracking rows (equity curve / orders / CC positions / signals) and clears them
     so the DB matches the fresh account,
  2. seeds the Aug-1 $50k baseline row,
  3. flips _DESK_START -> 2026-08-01 in trading_report.py (SPY-alpha + annualization anchor),
  4. kickstarts the desk so the loop reloads the new anchor,
  5. ntfy-pushes Brian and drops a sentinel so it never fires twice.

Guarded + sentinel-gated: cannot fire before the reset and cannot fire twice. Run standalone
(`python3 scripts/trading_eval_autofire.py`) to check status / fire manually.
"""
import json
import sqlite3
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts.trading_data import get_account, get_open_position_count  # loads .env on import

DB = ROOT / "data" / "olive.db"
SENTINEL = ROOT / "data" / ".eval_autofire_done"
ARCH = ROOT / "archives" / "trading-eval-2026-08"
REPORT_PY = ROOT / "scripts" / "trading_report.py"
NOTIFY = ROOT / "scripts" / "notify.sh"

BASELINE_DATE = "2026-08-01"
BASELINE_EQ = 50_000.0
TABLES = ["trading_equity_curve", "trading_orders", "trading_cc_positions", "trading_signals"]
DESK_LABEL = "com.olivetree.trading-desk"
UID = "501"
OLD_ANCHOR = '_DESK_START = "2026-07-07"'
NEW_ANCHOR = '_DESK_START = "2026-08-01"'


def _fire():
    # 1–2. archive July tracking, clear, seed the $50k baseline
    con = sqlite3.connect(DB)
    try:
        con.row_factory = sqlite3.Row
        ARCH.mkdir(parents=True, exist_ok=True)
        for t in TABLES:
            rows = [dict(r) for r in con.execute(f"SELECT * FROM {t}")]
            (ARCH / f"{t}.json").write_text(json.dumps(rows, indent=2, default=str))
            con.execute(f"DELETE FROM {t}")
            print(f"  archived {len(rows):>3} rows -> {t}.json (cleared)")
        con.execute(
            "INSERT INTO trading_equity_curve "
            "(date, portfolio_equity, cash, port_return_pct, sharpe_running, max_drawdown, open_positions, daily_halted) "
            "VALUES (?,?,?,0,0,0,0,0)",
            (BASELINE_DATE, BASELINE_EQ, BASELINE_EQ),
        )
        con.commit()
    finally:
        con.close()
    print(f"  seeded baseline {BASELINE_DATE} @ ${BASELINE_EQ:,.0f}")

    # 3. flip the report anchor to Aug 1
    src = REPORT_PY.read_text()
    if OLD_ANCHOR in src:
        REPORT_PY.write_text(src.replace(OLD_ANCHOR, NEW_ANCHOR, 1))
        print("  flipped _DESK_START -> 2026-08-01")
    else:
        print("  WARN: _DESK_START anchor not found (already flipped?) — leaving as-is")

    # 4. sentinel + push BEFORE the kickstart (kickstart -k kills this process)
    SENTINEL.write_text(f"fired: baseline {BASELINE_DATE} $50k\n")
    subprocess.run([str(NOTIFY), "Trading eval LIVE",
                    "Account reset to $50k. Aug 1-31 clean eval started: baseline seeded, "
                    "July data archived, desk reloading."], check=False)
    # 5. kickstart the desk so the loop reloads the new anchor (this restarts us; work is already done)
    print("  kicking desk to reload anchor")
    subprocess.run(["launchctl", "kickstart", "-k", f"gui/{UID}/{DESK_LABEL}"], check=False)


def maybe_fire_eval() -> bool:
    """Fire the eval start once the account is at $50k. Safe to call every cycle; returns True on fire."""
    if SENTINEL.exists() or date.today().isoformat() < BASELINE_DATE:
        return False
    try:
        eq = float(get_account()["equity"])
        pos_count = get_open_position_count()
        if pos_count is None:
            print("  eval-autofire: position count unknown (Alpaca fetch failed) — will retry next cycle")
            return False
        # Equity alone is NOT a reset signal — July equity drifting back through the
        # $49.5–50.5k band would wipe live tracking data mid-eval. A reset account is
        # also FLAT; the wheel desk is not. Require both.
        if abs(eq - BASELINE_EQ) > 500 or pos_count > 0:
            return False
    except Exception as e:
        print(f"  eval-autofire: account check failed ({e}) — will retry next cycle")
        return False
    print(f"  eval-autofire: account at ${eq:,.2f}, flat — starting Aug 1–31 eval")
    _fire()
    return True


if __name__ == "__main__":
    if SENTINEL.exists():
        print("already fired (sentinel present) — no-op")
    elif not maybe_fire_eval():
        print(f"waiting: account not at ~$50k yet (reset it in the Alpaca dashboard)")
