#!/usr/bin/env python3
"""
trading_guard.py — Equity anomaly circuit breaker for the Olive Tree Trading Desk.

Motivated by a real incident (2026-07-06/07): the paper account's equity fell
from ~$100k to ~$3.5k overnight with ZERO entries in Alpaca's account
activities log — an account/data glitch, not a trading loss. This breaker
catches "equity moved a lot and the activity log can't explain why" and halts
the desk instead of sizing new trades off a corrupted equity base.

check_equity_anomaly() is pure (no network) — activities for the gap window
are passed in, so it's directly testable. check_and_guard() does the Alpaca
fetch + halt-flag persistence + ntfy push.

Usage:
  python3 scripts/trading_guard.py --test          # assert-based self-check (no network)
  python3 scripts/trading_guard.py --check         # live check against Alpaca; writes halt file if tripped
  python3 scripts/trading_guard.py --clear-halt    # delete the halt flag (resume trading)
"""

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.trading_data import _get as _alpaca_get, _alpaca_headers, _ALPACA_BASE

HALT_FLAG_FILE = Path(__file__).parent.parent / "data" / "trading_halt.json"

ANOMALY_PCT_THRESHOLD      = 0.05  # |equity - last_equity| / last_equity beyond this → investigate
UNEXPLAINED_PCT_THRESHOLD  = 0.05  # unexplained portion of the move, as % of last_equity → HALT
CONSISTENCY_PCT_THRESHOLD  = 0.02  # |equity - (cash + positions mv)| / equity beyond this → HALT
ACTIVITIES_LOOKBACK_DAYS   = 3      # gap window to pull activities for

# Equity-NEUTRAL trade events: asset↔cash conversion at (or near) market, so
# their cash proceeds must not be counted as equity change. Verified against
# real records 2026-07-27: Alpaca logs the share-delivery leg of an assignment
# as OPTRD ("Options Trade") with net_amount = full strike proceeds ($17,850 of
# call-aways), NOT as a FILL — keying on FILL alone re-produced the false halt.
# OPASN/OPEXP/OPEXC are the option-side bookkeeping legs (net_amount 0).
TRADE_ACTIVITY_TYPES = {"FILL", "OPTRD", "OPASN", "OPEXP", "OPEXC"}


def _activity_impact(a: dict) -> float:
    """
    Best-effort $ EQUITY impact of one non-trade Alpaca activity record
    (DIV, CSD, FEE, JNLC, INT, ... carry net_amount/amount directly).
    Only call this for activity types outside TRADE_ACTIVITY_TYPES.
    """
    for key in ("net_amount", "amount"):
        v = a.get(key)
        if v not in (None, ""):
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
    return 0.0


def check_equity_anomaly(equity: float, last_equity: float, activities: list[dict],
                         cash: float = None, positions_value: float = None) -> tuple[bool, str]:
    """
    Pure, no network. Returns (should_halt, reason).

    activities: Alpaca /v2/account/activities records for the gap window.
    cash + positions_value (optional): enables the internal-consistency check —
    equity must ≈ cash + Σ position market value, or the account data itself is
    corrupt (catches valuation glitches even on active trading days).

    The glitch signature this breaker exists for (2026-07-06: $100k → $3.5k
    overnight) is a BIG equity move with ZERO trade activity. A big move WITH
    fills in the window is market/settlement-driven — per the v3 Suna spec
    that's a green light condition, not an anomaly.
    """
    if cash is not None and positions_value is not None and equity > 0:
        recon = cash + positions_value
        drift = abs(equity - recon) / equity
        if drift > CONSISTENCY_PCT_THRESHOLD:
            return True, (
                f"account internally inconsistent: equity ${equity:,.2f} vs cash+positions "
                f"${recon:,.2f} ({drift:.1%} apart, over {CONSISTENCY_PCT_THRESHOLD:.0%}) — "
                f"valuation/data glitch"
            )

    if last_equity <= 0:
        return False, "last_equity <= 0 — no baseline to compare, skipping"

    change = equity - last_equity
    change_pct = abs(change) / last_equity
    if change_pct <= ANOMALY_PCT_THRESHOLD:
        return False, f"equity change {change_pct:+.1%} within {ANOMALY_PCT_THRESHOLD:.0%} band — normal"

    has_trades = any(a.get("activity_type") in TRADE_ACTIVITY_TYPES for a in activities)
    explained = sum(_activity_impact(a) for a in activities
                    if a.get("activity_type") not in TRADE_ACTIVITY_TYPES)
    unexplained = change - explained
    unexplained_pct = abs(unexplained) / last_equity

    if unexplained_pct > UNEXPLAINED_PCT_THRESHOLD:
        if has_trades:
            return False, (
                f"equity moved {change:+,.2f} ({change_pct:+.1%}) with trade/settlement "
                f"activity in the window — market-driven (trades are equity-neutral), not "
                f"halting; glitch signature is a big move with ZERO activity"
            )
        reason = (
            f"equity moved {change:+,.2f} ({change_pct:+.1%}) from last_equity=${last_equity:,.2f} "
            f"with NO trade activity; non-trade flows explain ${explained:+,.2f}; unexplained "
            f"${unexplained:+,.2f} ({unexplained_pct:.1%} of last_equity, over "
            f"{UNEXPLAINED_PCT_THRESHOLD:.0%} threshold) — looks like an account/data glitch"
        )
        return True, reason

    return False, (
        f"equity moved {change:+,.2f} ({change_pct:+.1%}) but non-trade flows explain "
        f"${explained:+,.2f} (unexplained {unexplained_pct:.1%}, within "
        f"{UNEXPLAINED_PCT_THRESHOLD:.0%} band) — looks like legitimate P&L, not halting"
    )


def _fetch_activities(days: int = ACTIVITIES_LOOKBACK_DAYS) -> list[dict]:
    """Fetch account activities for the last `days` days from Alpaca."""
    after = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    url = f"{_ALPACA_BASE}/v2/account/activities?after={after}"
    try:
        data = _alpaca_get(url, _alpaca_headers())
        return data if isinstance(data, list) else []
    except Exception as e:
        print(f"  ⚠️  [guard] activities fetch failed: {e}")
        return []


def is_halted() -> bool:
    return HALT_FLAG_FILE.exists()


def _write_halt(reason: str, equity: float, last_equity: float):
    HALT_FLAG_FILE.parent.mkdir(parents=True, exist_ok=True)
    HALT_FLAG_FILE.write_text(json.dumps({
        "reason": reason,
        "equity": equity,
        "last_equity": last_equity,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }, indent=2))


def clear_halt():
    if HALT_FLAG_FILE.exists():
        HALT_FLAG_FILE.unlink()
        print("  [guard] halt flag cleared.")
    else:
        print("  [guard] no halt flag to clear.")


def check_and_guard() -> tuple[bool, str]:
    """
    Call at the start of every trading cycle. Checks the persisted halt flag
    first (halt persists until manually cleared); otherwise fetches fresh
    account + activities and runs check_equity_anomaly(). Writes the halt
    file + fires an ntfy push if it trips. Returns (halted, reason).
    """
    if is_halted():
        try:
            data = json.loads(HALT_FLAG_FILE.read_text())
            return True, f"halt flag already set: {data.get('reason', '(no reason recorded)')}"
        except Exception:
            return True, "halt flag file present (unreadable)"

    # Fail-open, not fail-crash: an Alpaca outage/auth error is a data-availability
    # problem, not evidence of an equity anomaly — the breaker itself must never
    # become the reason the desk goes down.
    try:
        from scripts.trading_data import get_account
        acct = get_account()
        equity, last_equity = acct["equity"], acct["last_equity"]
    except Exception as e:
        return False, f"guard check skipped — account fetch failed ({e}); fail-open, no halt"

    # Consistency inputs are best-effort: the layer just switches off if either
    # fetch fails (fail-open, same rationale as above).
    try:
        cash = float(acct.get("cash"))
    except (TypeError, ValueError):
        cash = None
    positions_value = None
    try:
        pos = _alpaca_get(f"{_ALPACA_BASE}/v2/positions", _alpaca_headers())
        if isinstance(pos, list):
            positions_value = sum(float(p.get("market_value") or 0) for p in pos)
    except Exception:
        pass

    activities = _fetch_activities()
    should_halt, reason = check_equity_anomaly(equity, last_equity, activities,
                                               cash=cash, positions_value=positions_value)

    if should_halt:
        _write_halt(reason, equity, last_equity)
        try:
            from scripts.trading_report import send_alert
            send_alert("Trading Desk — EQUITY ANOMALY HALT", reason)
        except Exception as e:
            print(f"  ⚠️  [guard] alert send failed: {e}")

    return should_halt, reason


def _self_check():
    print("── Equity anomaly guard self-check ─────────────────────────────\n")

    h, r = check_equity_anomaly(101_000, 100_000, [])
    assert not h, r
    print(f"  ✅ Small move (1%): {r}")

    h, r = check_equity_anomaly(94_000, 100_000, [{"net_amount": -6000}])
    assert not h, r
    print(f"  ✅ Big move, fully explained by activity: {r}")

    # The real incident: $100k → $3.5k, zero activity → HALT
    h, r = check_equity_anomaly(3_500, 100_000, [])
    assert h, r
    print(f"  ✅ Unexplained catastrophic drop: HALT — {r[:90]}...")

    h, r = check_equity_anomaly(80_000, 100_000, [{"amount": -1_000}])
    assert h, r
    print(f"  ✅ Partially explained, still over threshold: HALT — {r[:90]}...")

    h, r = check_equity_anomaly(80_000, 100_000, [{"amount": -19_000}])
    assert not h, r
    print(f"  ✅ Partially explained, within threshold: {r}")

    h, r = check_equity_anomaly(5_000, 0, [])
    assert not h, r
    print(f"  ✅ Zero/negative baseline skipped (no false halt): {r}")

    # Big move WITH trade/settlement activity → market-driven, never a halt.
    # Real records from the 2026-07-27 false halts (both rounds): Alpaca logs
    # assignment share-delivery as OPTRD with net_amount = strike proceeds
    # (NOT as FILL — round two keyed on FILL and still false-halted), plus
    # OPASN/OPEXP bookkeeping legs and FEE records.
    h, r = check_equity_anomaly(50_176, 53_354, [
        {"activity_type": "OPTRD", "net_amount": "5650", "qty": "-100", "price": "56.5", "symbol": "XLE"},
        {"activity_type": "OPTRD", "net_amount": "8600", "qty": "-400", "price": "21.5", "symbol": "T"},
        {"activity_type": "OPTRD", "net_amount": "3600", "qty": "-100", "price": "36", "symbol": "IBIT"},
        {"activity_type": "OPASN", "net_amount": "0", "qty": "1", "symbol": "XLE260724C00056500"},
        {"activity_type": "OPEXP", "net_amount": "0", "qty": "1", "symbol": "F260724P00013000"},
        {"activity_type": "FEE", "net_amount": "-0.17"},
    ])
    assert not h, r
    print(f"  ✅ Assignment weekend (real OPTRD/OPASN/FEE records): no halt — {r[:70]}...")

    # Internal consistency: equity far from cash + positions mv → data glitch, HALT
    # even with fills in the window.
    h, r = check_equity_anomaly(50_000, 50_000, [{"activity_type": "FILL", "qty": "1", "price": "1", "side": "buy"}],
                                cash=20_000, positions_value=10_000)
    assert h, r
    print(f"  ✅ Internally inconsistent account: HALT — {r[:90]}...")

    h, r = check_equity_anomaly(50_000, 50_000, [], cash=32_750, positions_value=17_425)
    assert not h, r
    print(f"  ✅ Internally consistent account: {r}")

    print("\n  All equity guard self-checks passed. ✅")


def main():
    ap = argparse.ArgumentParser(description="Equity anomaly circuit breaker")
    ap.add_argument("--test",       action="store_true", help="Assert-based self-check (no network)")
    ap.add_argument("--check",      action="store_true", help="Live check against Alpaca")
    ap.add_argument("--clear-halt", action="store_true", help="Delete the halt flag file")
    args = ap.parse_args()

    if args.test:
        _self_check()
        return
    if args.clear_halt:
        clear_halt()
        return
    if args.check:
        halted, reason = check_and_guard()
        print(f"  {'🛑 HALT' if halted else '✅ OK'} — {reason}")
        return
    ap.print_help()


if __name__ == "__main__":
    main()
