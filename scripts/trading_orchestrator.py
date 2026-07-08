#!/usr/bin/env python3
"""
trading_orchestrator.py — Main loop for the Olive Tree Trading Desk (Premium Desk v2).

Default cycle (CC/wheel-primary):
  0. Equity anomaly guard — halts the whole cycle on an unexplained equity jump
  1. CC/wheel cycle  — scripts/trading_covered_calls.py (screener → CSP-first entries,
     21-DTE management, cover, wheel)
  2. Report          — equity snapshot + alerts

The original momentum pipeline (Claude research → quant walk-forward gate →
risk veto → Alpaca paper execution) and the SPY core sweep are RETIRED as the
default path — the walk-forward gate was passing small-sample noise. Both are
still fully wired and opt back in behind --momentum for anyone who wants to
resume/compare them; they are not deleted.

Usage:
  # Single cycle (test before scheduling):
  python3 scripts/trading_orchestrator.py --once

  # Dry run — no orders, no API costs beyond data:
  python3 scripts/trading_orchestrator.py --once --dry-run

  # Also run the retired momentum pipeline + SPY core sweep this cycle:
  python3 scripts/trading_orchestrator.py --once --momentum

  # Backtest only — no orders, just print quant gate results (momentum pipeline):
  python3 scripts/trading_orchestrator.py --backtest-only

  # Continuous loop (wrap with caffeinate to keep Mac awake):
  caffeinate -i python3 scripts/trading_orchestrator.py --loop --interval 3600

  # Show today's P&L:
  python3 scripts/trading_orchestrator.py --report

  # Clear a tripped equity-anomaly halt:
  python3 scripts/trading_orchestrator.py --clear-halt
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
from scripts.trading_data   import get_account, is_market_open, is_extended_hours, get_top_movers, get_afterhours_movers, EQUITY_UNIVERSE, ETF_UNIVERSE, CRYPTO_UNIVERSE
from scripts.trading_research import run_research
from scripts.trading_quant  import run_walk_forward
from scripts.trading_risk   import evaluate as risk_evaluate, is_daily_halted, MOMENTUM_BOOK_USD
from scripts.trading_core  import sweep_to_core, release_core, CORE_BUFFER_USD
from scripts.trading_execution import submit_order, sync_fills, get_open_positions, check_stops
from scripts.trading_options   import find_contract, size_contracts, submit_option_order
from scripts.trading_report import snapshot_equity, print_performance, send_alert, send_session_report
from scripts.trading_guard  import check_and_guard, clear_halt
from db.connection import Session
from db.schema import TradingSignal

# ── State file for CC cycle throttle ─────────────────────────────────────────
_CC_STATE_FILE  = Path(__file__).parent.parent / "data" / "cc_last_run.txt"
CC_CYCLE_SECONDS = 3600  # run CC cycle at most once per hour


def _get_regime() -> str:
    """
    'RISK-ON' if SPY is above its 200-day SMA, 'RISK-OFF' if below,
    'UNKNOWN' if the data can't be fetched. UNKNOWN fails FLAT — new entries
    blocked in both directions (stops/exits unaffected; check_stops runs regardless).
    """
    try:
        from scripts.trading_data import get_bars, get_quote
        bars = get_bars("SPY", days=320)  # 200 trading days needs ~300 calendar days
        if len(bars) < 200:
            return "UNKNOWN"
        sma200 = sum(b["c"] for b in bars[-200:]) / 200
        q = get_quote("SPY")
        spy_price = q.get("last") or q.get("ask") or 0
        if not spy_price:
            return "UNKNOWN"
        return "RISK-ON" if spy_price >= sma200 else "RISK-OFF"
    except Exception:
        return "UNKNOWN"


def _maybe_run_cc(dry_run: bool = False):
    """Run CC cycle at most once per hour. Uses a timestamp file as state."""
    try:
        import time as _time
        last = float(_CC_STATE_FILE.read_text().strip()) if _CC_STATE_FILE.exists() else 0
        if _time.time() - last < CC_CYCLE_SECONDS:
            secs_left = int(CC_CYCLE_SECONDS - (_time.time() - last))
            print(f"  [CC] Skipping — next run in {secs_left//60}m")
            return
        from scripts.trading_covered_calls import run_cc_cycle
        run_cc_cycle(dry_run=dry_run)
        if not dry_run:  # a dry-run shouldn't consume the real desk's 4h window
            _CC_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            _CC_STATE_FILE.write_text(str(_time.time()))
    except Exception as e:
        print(f"  ⚠️  CC cycle error: {e}")


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


def run_cycle(dry_run: bool = False, market_session: str = "equities",
              with_insiders: bool = False, with_options: bool = False,
              no_cc: bool = False, momentum: bool = False):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n{'='*60}")
    print(f"  Trading Desk Cycle — {now}  [{market_session}]"
          f"{'  [+momentum]' if momentum else ''}")
    print(f"{'='*60}")

    # ── Equity anomaly guard — before ANY trading this cycle ──────────────────
    # Read-only check (writes only a halt-flag file + alert if it trips); safe
    # to run under --dry-run too, so a smoke test still exercises it.
    halted, halt_reason = check_and_guard()
    if halted:
        print(f"  🛑 EQUITY ANOMALY HALT — {halt_reason}")
        print(f"       Clear with: python3 scripts/trading_orchestrator.py --clear-halt")
        return

    # ── Account check + day-open snapshot ─────────────────────────
    acct = get_account()
    equity = acct["equity"]
    print(f"\n  💰 Equity: ${equity:,.2f}   Cash: ${acct['cash']:,.2f}")

    # Write snapshot now so is_daily_halted() has a day-open baseline
    if not dry_run:
        snapshot_equity()

    # ponytail: daily halt checks whole-account equity — it spans both momentum + CC books
    if is_daily_halted(equity):
        msg = f"Daily halt active — portfolio down ≥2% today. No new trades."
        print(f"  🛑 {msg}")
        send_alert("Trading Desk — HALT", msg)
        return

    # ── CC/wheel cycle — the primary book (equities + extended sessions) ──────
    if market_session in ("equities", "extended") and not no_cc:
        _maybe_run_cc(dry_run=dry_run)

    if not momentum:
        # Momentum pipeline + SPY core sweep are retired as the default path —
        # the walk-forward gate was passing small-sample noise. Re-enable with --momentum.
        print(f"\n  [momentum] retired — pass --momentum to run research/quant/risk/execution + core sweep")
        if not dry_run:
            check_stops(session=market_session)  # still enforces stops on any legacy open momentum positions
            sync_fills()
        print(f"\n  [report] Equity snapshot...")
        if not dry_run:
            snapshot_equity()
        else:
            print(f"        [DRY RUN] Skipped snapshot.")
        print(f"\n  Cycle complete.")
        return

    # ── Momentum book — all sizing runs off $50k sub-book ─────────────────────
    momentum_equity = min(equity, MOMENTUM_BOOK_USD)
    print(f"  📦 Momentum book: ${momentum_equity:,.0f}  (full equity ${equity:,.0f})")

    # ── Insider signals (optional, fetched once per cycle) ────────
    insider_long:  set[str] = set()
    insider_short: set[str] = set()
    if with_insiders:
        print("\n  [0/4] Insider signals...")
        from scripts.trading_insiders import get_insider_signal, format_signal_block, get_insider_tickers
        insider_signal = get_insider_signal()
        insider_long, insider_short = get_insider_tickers(insider_signal)
        if insider_long or insider_short:
            print(f"        Long flags:  {sorted(insider_long)  or 'none'}")
            print(f"        Short flags: {sorted(insider_short) or 'none'}")

    # ── Step 1: Research ───────────────────────────────────────────
    if market_session == "crypto":
        symbols = CRYPTO_UNIVERSE
    elif market_session == "extended":
        symbols = get_afterhours_movers(EQUITY_UNIVERSE, n=15)
        print(f"  After-hours movers ({len(symbols)}): {symbols}")
    else:
        # Always evaluate the top-rated ETFs + the day's top S&P movers, then hold
        # the best MAX_POSITIONS by conviction. dict.fromkeys dedups, keeps order.
        movers  = get_top_movers(EQUITY_UNIVERSE, n=15)
        symbols = list(dict.fromkeys(ETF_UNIVERSE + movers))
        print(f"  ETFs + top movers ({len(symbols)}): {symbols}")
    print(f"\n  [1/4] Research agent ({len(symbols)} symbols)...")
    run_id = datetime.now(timezone.utc).isoformat()
    theses = run_research(symbols, market_session=market_session, dry_run=dry_run, run_id=run_id,
                          with_insiders=with_insiders)

    # ── Regime filter (runs before thesis loop, logged even if no theses) ────────
    regime = "N/A" if market_session == "crypto" else _get_regime()
    if regime == "UNKNOWN":
        print(f"\n  ⚠️  Regime: UNKNOWN (SPY data unavailable) — blocking NEW equity entries "
              f"both directions this cycle (fail-flat); stops/exits unaffected")
    elif regime != "N/A":
        print(f"\n  Regime: {regime} (SPY {'above' if regime == 'RISK-ON' else 'below'} 200d SMA)"
              f"{' — shorts filtered' if regime == 'RISK-ON' else ' — longs filtered'}")

    if not theses:
        print("  No theses returned. Nothing to trade.")
        return

    # ── Steps 2–4: Quant → Risk → Execute per thesis ──────────────
    # Symbols we already hold — skip them so we don't re-buy the same name every
    # cycle. Alpaca nets repeat buys into one position, so the risk agent's
    # MAX_POSITIONS count can't see the concentration; this DB check can.
    held_symbols = {p["symbol"] for p in get_open_positions()}
    # CC book underlyings are off-limits to the momentum desk (avoids double exposure)
    try:
        from scripts.trading_covered_calls import cc_held_symbols
        held_symbols |= cc_held_symbols()
    except Exception:
        pass  # ponytail: CC module optional; desk continues without it

    approved_count = 0
    # Highest conviction first → when more theses pass the gates than open slots,
    # the top MAX_POSITIONS win (the risk agent vetoes the rest at the cap).
    theses.sort(key=lambda t: t.get("conviction") or 0, reverse=True)
    for t in theses:
        symbol    = t.get("symbol", "")
        direction = t.get("direction", "LONG").lower()  # long / short
        conviction = t.get("conviction", 0)

        print(f"\n  ── {symbol} {direction.upper()} (conviction={conviction}) ──")

        if symbol in held_symbols:
            print(f"        ⏭  Already holding {symbol} — skipping to avoid stacking the same name")
            continue

        # Alpaca does not support shorting crypto — skip short crypto theses
        is_crypto = "/" in symbol
        if is_crypto and direction == "short":
            print(f"        ⏭  Skipping SHORT {symbol} — Alpaca doesn't support crypto shorts")
            continue

        # Regime filter: RISK-ON → only longs; RISK-OFF → only shorts;
        # UNKNOWN → fail flat, no new equity entries. Crypto unaffected.
        if not is_crypto:
            if regime == "UNKNOWN":
                print(f"        ⏭  Regime UNKNOWN — blocking new entry for {symbol} (fail-flat)")
                continue
            if regime == "RISK-ON"  and direction == "short":
                print(f"        ⏭  Regime RISK-ON  — skipping SHORT {symbol}")
                continue
            if regime == "RISK-OFF" and direction == "long":
                print(f"        ⏭  Regime RISK-OFF — skipping LONG  {symbol}")
                continue

        # Step 2: Quant gate (direction-aware). Crypto trades 24/7 — daily bars fire
        # the signal only 1-3x (no valid sample); hourly gives a real trade count.
        print(f"  [2/4] Quant gate...")
        if is_crypto:
            quant_result = run_walk_forward(symbol, days=60, direction=direction, timeframe="1Hour")
        elif symbol in ETF_UNIVERSE:
            # ETFs are smooth — 365d fires too few trades to clear the sample floor.
            quant_result = run_walk_forward(symbol, days=730, direction=direction)
        else:
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
            portfolio_equity=momentum_equity,
            extended_hours=(market_session == "extended"),
            conviction=conviction,
        )

        if decision.approved:
            print(f"        ✅ APPROVED  qty={decision.qty:.4f}  pos=${decision.position_usd:,.2f}  stop=${decision.stop_price:.2f}")
        else:
            print(f"        ❌ VETOED   {decision.veto_reason}")
            continue

        # Step 4: Execute
        print(f"  [4/4] Execution...")

        # Cash guard: if account cash < position notional, try to release from core SPY first
        if not dry_run and decision.approved and decision.position_usd > 0:
            try:
                cash_now = get_account().get("cash", 0)
                shortfall = decision.position_usd - (cash_now - CORE_BUFFER_USD)
                if shortfall > 0:
                    print(f"  [core] low cash — releasing ${shortfall:,.0f} before {symbol} entry")
                    release_core(shortfall)
            except Exception as _cge:
                print(f"  ⚠️  [core] cash guard failed ({_cge}) — continuing anyway")

        # Options eligibility:
        #   - Best-judgment path: conviction ≥ 0.80 (Claude's highest-conviction calls)
        #   - Insider path:       insider signal matches this direction (any conviction ≥ 0.60)
        # Options only during regular equities session — no extended or crypto options.
        insider_match = (
            (direction == "long"  and symbol in insider_long)
            or (direction == "short" and symbol in insider_short)
        )
        use_options = (
            with_options
            and market_session == "equities"
            and (conviction >= 0.80 or (insider_match and conviction >= 0.60))
        )

        if dry_run:
            tag = " [OPTIONS]" if use_options else ""
            print(f"        [DRY RUN] Would submit {symbol} {direction.upper()} qty={decision.qty:.4f}{tag}")
        elif use_options:
            contract, premium = find_contract(symbol, direction, entry_price)
            if contract:
                n = size_contracts(equity, premium)
                result = submit_option_order(contract, n)
                if result.get("submitted"):
                    approved_count += 1
                    cost = n * premium * 100
                    send_alert(
                        f"📊 {symbol} {direction.upper()} — Options Paper",
                        f"{n}x {contract}  est. cost=${cost:,.0f}  {'INSIDER' if insider_match else 'HIGH-CONV'}",
                    )
            else:
                print(f"        No options contract found for {symbol} — falling back to equity")
                result = submit_order(decision, signal_id=signal_id, session=market_session)
                if result.get("submitted"):
                    approved_count += 1
                    send_alert(
                        f"📈 {symbol} {direction.upper()} — Paper (equity fallback)",
                        f"qty={decision.qty:.4f}  notional=${decision.position_usd:,.2f}",
                    )
        else:
            result = submit_order(decision, signal_id=signal_id, session=market_session)
            if result.get("submitted"):
                approved_count += 1
                send_alert(
                    f"📈 {symbol} {direction.upper()} — Paper",
                    f"qty={decision.qty:.4f}  notional=${decision.position_usd:,.2f}  stop=${decision.stop_price:.2f}",
                )

    # (CC/wheel cycle already ran at the top of run_cycle, ahead of the momentum pipeline)

    # ── Core SPY sweep — idle cash → SPY after all other entries (--momentum only) ────

    # Only equities session (market hours); skipped for crypto/extended/idle.
    if market_session == "equities":
        sweep_to_core(dry_run=dry_run)

    # ── Reconcile fills ────────────────────────────────────────────
    # Stops are monitor-based (Alpaca can't rest stops on crypto or fractional equity) —
    # check live price vs stop and fire exits first, then sync_fills() reconciles every
    # fill (incl. those stop exits) → closes positions with realized P&L.
    if not dry_run:
        check_stops(session=market_session)
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
    ap.add_argument("--interval",      type=int, default=3600, help="Seconds between research cycles (default 3600)")
    ap.add_argument("--stop-interval", type=int, default=60, help="Seconds between stop checks within a cycle (default 60)")
    ap.add_argument("--dry-run",       action="store_true", help="No orders, no equity snapshot")
    ap.add_argument("--insiders",      action="store_true", help="Fetch Pelosi + Burry signals each cycle")
    ap.add_argument("--options",       action="store_true", help="Options trading: high-conviction + insider-flagged symbols")
    ap.add_argument("--backtest-only", action="store_true", help="Run quant gate on all symbols and exit")
    ap.add_argument("--report",        action="store_true", help="Print P&L table and exit")
    ap.add_argument("--market-session", default="auto", choices=["auto", "equities", "extended", "crypto", "idle"],
                    help="Force session type (default auto-detects by time)")
    ap.add_argument("--no-cc", action="store_true", help="Disable covered-call cycle this run")
    ap.add_argument("--momentum", action="store_true",
                    help="Also run the retired momentum pipeline (research→quant→risk→execution) + SPY core sweep")
    ap.add_argument("--clear-halt", action="store_true", help="Clear a tripped equity-anomaly halt and exit")
    args = ap.parse_args()

    if args.clear_halt:
        clear_halt()
        return

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
        if is_market_open():
            return "equities"
        if is_extended_hours():
            return "extended"
        return "idle"  # 8pm–4am ET: no active session

    if args.once:
        # Same fail-safe as --loop below: an Alpaca outage mid-cycle shouldn't crash
        # the process (matters once this runs unattended via launchd/cron).
        try:
            run_cycle(dry_run=args.dry_run, market_session=_session(),
                      with_insiders=args.insiders, with_options=args.options,
                      no_cc=args.no_cc, momentum=args.momentum)
        except Exception as e:
            msg = f"Cycle error: {e}"
            print(f"  ⚠️  {msg}")
            traceback.print_exc()
            send_alert("Trading Desk — ERROR", msg)
        return

    if args.loop:
        # Research/quant (the costly part — Claude + data) runs every --interval.
        # Stops are cheap (one quote per open position), so we enforce them every
        # --stop-interval in between without paying for extra research cycles.
        print(f"  Starting loop (research={args.interval}s, stops={args.stop_interval}s). "
              f"Wrap with 'caffeinate -i' to keep Mac awake.")
        last_session = None
        while True:
            sess = _session()
            try:
                # Session flip → activity report (skip idle transitions — nothing to report).
                if last_session and sess != last_session and not args.dry_run:
                    if "idle" not in (last_session, sess):
                        send_session_report(last_session, sess)
                last_session = sess
                if sess == "idle":
                    print(f"  Markets closed (8pm–4am ET). Next check in {args.stop_interval}s.")
                else:
                    run_cycle(dry_run=args.dry_run, market_session=sess,
                              with_insiders=args.insiders, with_options=args.options,
                              no_cc=args.no_cc, momentum=args.momentum)
            except KeyboardInterrupt:
                print("\n  Loop stopped by user.")
                break
            except Exception as e:
                msg = f"Cycle error: {e}"
                print(f"  ⚠️  {msg}")
                traceback.print_exc()
                send_alert("Trading Desk — ERROR", msg)
            # Sleep until the next research cycle, enforcing stops every stop_interval.
            elapsed = 0
            while elapsed < args.interval:
                time.sleep(min(args.stop_interval, args.interval - elapsed))
                elapsed += args.stop_interval
                if not args.dry_run:
                    try:
                        if check_stops(session=sess):  # only reconcile if an exit actually fired
                            sync_fills()
                    except KeyboardInterrupt:
                        raise
                    except Exception as e:
                        print(f"  ⚠️  Stop-check error: {e}")
        return

    ap.print_help()


if __name__ == "__main__":
    main()
