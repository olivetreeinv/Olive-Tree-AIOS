#!/usr/bin/env python3
"""
trading_orchestrator.py — Main loop for the Olive Tree Trading Desk.

Agent pipeline per cycle:
  1. Research agent  — Claude theses (JSON)
  2. Quant agent     — walk-forward backtest gate
  3. Risk agent      — sizing + veto
  4. Execution agent — Alpaca paper orders
  5. Report          — equity snapshot + iMessage alerts

Usage:
  # Single cycle (test before scheduling):
  python3 scripts/trading_orchestrator.py --once

  # Dry run — no orders, no API costs beyond data:
  python3 scripts/trading_orchestrator.py --once --dry-run

  # Backtest only — no orders, just print quant gate results:
  python3 scripts/trading_orchestrator.py --backtest-only

  # Continuous loop (wrap with caffeinate to keep Mac awake):
  caffeinate -i python3 scripts/trading_orchestrator.py --loop --interval 3600

  # Show today's P&L:
  python3 scripts/trading_orchestrator.py --report
"""

import argparse
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.trading_data   import get_account, is_market_open, get_top_movers, EQUITY_UNIVERSE, CRYPTO_UNIVERSE
from scripts.trading_research import run_research
from scripts.trading_quant  import run_walk_forward
from scripts.trading_risk   import evaluate as risk_evaluate, is_daily_halted
from scripts.trading_execution import submit_order, sync_fills
from scripts.trading_report import snapshot_equity, print_performance, send_alert
from db.connection import Session
from db.schema import TradingSignal


def _save_signal(thesis_id: int | None, result: dict) -> int | None:
    if not result.get("oos"):
        return None
    s = Session()
    try:
        oos = result["oos"]
        row = TradingSignal(
            thesis_id=thesis_id,
            symbol=result["symbol"],
            run_id=result.get("run_at", ""),
            sharpe=oos.get("sharpe"),
            max_drawdown=oos.get("max_drawdown"),
            cagr=oos.get("cagr"),
            win_rate=oos.get("win_rate"),
            oos_sharpe=oos.get("sharpe"),
            passed_gate=result.get("passed_gate", False),
            strategy_params=str(result.get("params", {})),
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        s.add(row)
        s.commit()
        return row.id
    finally:
        s.close()


def run_cycle(dry_run: bool = False, market_session: str = "equities"):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n{'='*60}")
    print(f"  Trading Desk Cycle — {now}  [{market_session}]")
    print(f"{'='*60}")

    # ── Account check + day-open snapshot ─────────────────────────
    acct = get_account()
    equity = acct["equity"]
    print(f"\n  💰 Equity: ${equity:,.2f}   Cash: ${acct['cash']:,.2f}")

    # Write snapshot now so is_daily_halted() has a day-open baseline
    if not dry_run:
        snapshot_equity()

    if is_daily_halted(equity):
        msg = f"Daily halt active — portfolio down ≥2% today. No new trades."
        print(f"  🛑 {msg}")
        send_alert("Trading Desk — HALT", msg)
        return

    # ── Step 1: Research ───────────────────────────────────────────
    # For equities: narrow to top 8 movers to stay within Polygon rate limits.
    # For crypto: use full universe (only 2 symbols).
    if market_session == "crypto":
        symbols = CRYPTO_UNIVERSE
    else:
        symbols = get_top_movers(EQUITY_UNIVERSE, n=8)
        print(f"  Top movers selected: {symbols}")
    print(f"\n  [1/4] Research agent ({len(symbols)} symbols)...")
    run_id = datetime.now(timezone.utc).isoformat()
    theses = run_research(symbols, market_session=market_session, dry_run=dry_run, run_id=run_id)

    if not theses:
        print("  No theses returned. Nothing to trade.")
        return

    # ── Steps 2–4: Quant → Risk → Execute per thesis ──────────────
    approved_count = 0
    for t in theses:
        symbol    = t.get("symbol", "")
        direction = t.get("direction", "LONG").lower()  # long / short
        conviction = t.get("conviction", 0)

        print(f"\n  ── {symbol} {direction.upper()} (conviction={conviction}) ──")

        # Alpaca does not support shorting crypto — skip short crypto theses
        is_crypto = "/" in symbol
        if is_crypto and direction == "short":
            print(f"        ⏭  Skipping SHORT {symbol} — Alpaca doesn't support crypto shorts")
            continue

        # Step 2: Quant gate (direction-aware)
        print(f"  [2/4] Quant gate...")
        quant_result = run_walk_forward(symbol, days=365, direction=direction)
        passed = quant_result.get("passed_gate", False)
        if passed:
            oos = quant_result["oos"]
            print(f"        ✅ PASS  Sharpe={oos['sharpe']:.2f}  DD={oos['max_drawdown']:.1%}  WinRate={oos['win_rate']:.0%}")
        else:
            reason = quant_result.get("error", "below gate thresholds")
            print(f"        ❌ FAIL  {reason}")

        # Look up the thesis ID saved by the research agent this run
        thesis_db_id = None
        s_lookup = Session()
        try:
            from db.schema import TradingThesis
            th = s_lookup.query(TradingThesis).filter_by(
                run_id=run_id, symbol=symbol
            ).order_by(TradingThesis.id.desc()).first()
            thesis_db_id = th.id if th else None
        finally:
            s_lookup.close()

        # Save signal regardless of pass/fail
        signal_id = _save_signal(thesis_db_id, quant_result)

        # Step 3: Risk gate
        print(f"  [3/4] Risk agent...")
        try:
            quote_data = __import__("scripts.trading_data", fromlist=["get_quote"]).get_quote(symbol)
            entry_price = quote_data.get("ask", 0) or quote_data.get("last", 0)
        except Exception:
            entry_price = 0

        decision = risk_evaluate(
            symbol=symbol,
            side=direction,
            entry_price=entry_price,
            quant_passed=passed,
            portfolio_equity=equity,
        )

        if decision.approved:
            print(f"        ✅ APPROVED  qty={decision.qty:.4f}  pos=${decision.position_usd:,.2f}  stop=${decision.stop_price:.2f}")
        else:
            print(f"        ❌ VETOED   {decision.veto_reason}")
            continue

        # Step 4: Execute
        print(f"  [4/4] Execution...")
        if dry_run:
            print(f"        [DRY RUN] Would submit {symbol} {direction.upper()} qty={decision.qty:.4f}")
        else:
            result = submit_order(decision, signal_id=signal_id)
            if result.get("submitted"):
                approved_count += 1
                send_alert(
                    f"📈 {symbol} {direction.upper()} — Paper",
                    f"qty={decision.qty:.4f}  notional=${decision.position_usd:,.2f}  stop=${decision.stop_price:.2f}",
                )

    # ── Reconcile fills ────────────────────────────────────────────
    if not dry_run:
        sync_fills()

    # ── Equity snapshot (end-of-cycle update) ─────────────────────
    print(f"\n  [5/5] Equity snapshot...")
    if not dry_run:
        snapshot_equity()  # overwrites the start-of-cycle row with final equity
    else:
        print(f"        [DRY RUN] Skipped snapshot.")

    print(f"\n  Cycle complete. {approved_count} order(s) submitted.")


def main():
    ap = argparse.ArgumentParser(description="Olive Tree Trading Desk orchestrator")
    ap.add_argument("--once",          action="store_true", help="Run one cycle and exit")
    ap.add_argument("--loop",          action="store_true", help="Run continuously (use with caffeinate -i)")
    ap.add_argument("--interval",      type=int, default=3600, help="Seconds between cycles (default 3600)")
    ap.add_argument("--dry-run",       action="store_true", help="No orders, no equity snapshot")
    ap.add_argument("--backtest-only", action="store_true", help="Run quant gate on all symbols and exit")
    ap.add_argument("--report",        action="store_true", help="Print P&L table and exit")
    ap.add_argument("--market-session", default="auto", choices=["auto", "equities", "crypto"],
                    help="Force session type (default auto-detects by time)")
    args = ap.parse_args()

    if args.report:
        print_performance()
        return

    if args.backtest_only:
        from scripts.trading_quant import main as quant_main
        import sys
        sys.argv = ["trading_quant.py", "--backtest-all", "--days", "365"]
        quant_main()
        return

    def _session() -> str:
        if args.market_session != "auto":
            return args.market_session
        return "equities" if is_market_open() else "crypto"

    if args.once:
        run_cycle(dry_run=args.dry_run, market_session=_session())
        return

    if args.loop:
        print(f"  Starting loop (interval={args.interval}s). Wrap with 'caffeinate -i' to keep Mac awake.")
        while True:
            try:
                run_cycle(dry_run=args.dry_run, market_session=_session())
            except KeyboardInterrupt:
                print("\n  Loop stopped by user.")
                break
            except Exception as e:
                msg = f"Cycle error: {e}"
                print(f"  ⚠️  {msg}")
                traceback.print_exc()
                send_alert("Trading Desk — ERROR", msg)
            time.sleep(args.interval)
        return

    ap.print_help()


if __name__ == "__main__":
    main()
