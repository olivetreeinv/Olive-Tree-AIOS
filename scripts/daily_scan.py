#!/usr/bin/env python3
"""
daily_scan.py — Two-sided best-trades scan for the trading desk.

Screens a broad, liquid universe through the quant gate in BOTH directions and
ranks the day's best LONGS and best SHORTS. Optionally runs Claude deep research
on the combined shortlist and emails the report.

The single source of truth for "the day's best trades" — data_compare.py pulls
its daily symbol set from here so the feed comparison covers what we'd trade.

Usage:
  python3 scripts/daily_scan.py                       # print two-sided scan
  python3 scripts/daily_scan.py --research            # + Claude theses on the shortlist (Opus, ~$)
  python3 scripts/daily_scan.py --email               # email the report (daily_brief_cloud.py)
  python3 scripts/daily_scan.py --top 6               # N per side (default 8)
"""

import argparse
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")   # quiet numpy/pandas RuntimeWarnings from the short backtest path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.trading_quant import run_walk_forward

BROAD_UNIVERSE = [
    "AAPL", "MSFT", "NVDA", "AVGO", "AMD", "MU", "AMAT", "LRCX", "KLAC", "MRVL",
    "QCOM", "TXN", "ARM", "SMCI", "PLTR", "ORCL", "CRM", "NOW", "PANW", "CRWD",
    "SNOW", "ADBE", "NFLX", "DELL", "AMZN", "GOOGL", "META", "TSLA", "UBER",
    "ABNB", "BKNG", "COST", "WMT", "HD", "MCD", "SBUX", "DIS", "JPM", "GS", "MS",
    "BAC", "V", "MA", "AXP", "LLY", "UNH", "ABBV", "ISRG", "XOM", "CVX", "COP",
    "CAT", "GE", "COIN", "MSTR", "SOFI", "SHOP", "IONQ", "UFO", "SMH", "XLE", "XLF",
]


def screen_two_sided(universe: list[str] | None = None) -> dict:
    """Run the gate long AND short on each name. Returns {'long': [...], 'short': [...]},
    each a list of (symbol, sharpe, trades, dd, win) sorted by Sharpe desc (gate passers only)."""
    universe = universe or BROAD_UNIVERSE
    out = {"long": [], "short": []}
    for direction in ("long", "short"):
        for t in universe:
            try:
                r = run_walk_forward(t, days=365, direction=direction)
            except Exception:
                continue
            o = r.get("oos", {})
            if r.get("passed_gate") and "sharpe" in o:
                out[direction].append((t, o["sharpe"], o["n_trades"], o["max_drawdown"], o["win_rate"]))
        out[direction].sort(key=lambda x: -x[1])
    return out


def daily_symbols(top: int = 8, anchors=("SPY", "QQQ")) -> list[str]:
    """The day's tradeable set for the feed comparison: anchors + top longs + top shorts."""
    s = screen_two_sided()
    picks = [t for t, *_ in s["long"][:top]] + [t for t, *_ in s["short"][:top]]
    seen, syms = set(), list(anchors)
    for p in picks:
        if p not in seen and p not in anchors:
            syms.append(p); seen.add(p)
    return syms


def _fmt_side(title: str, rows: list, top: int) -> list[str]:
    lines = [f"{title} ({len(rows)} passed gate):"]
    if not rows:
        lines.append("  (none cleared the gate)")
        return lines
    lines.append(f"  {'SYM':6}{'Sharpe':>8}{'Trades':>8}{'DD':>8}{'Win':>6}")
    for t, sh, n, dd, w in rows[:top]:
        lines.append(f"  {t:6}{sh:>8.2f}{n:>8}{dd:>8.1%}{w:>6.0%}")
    return lines


def report(top: int = 8, do_research: bool = False) -> str:
    s = screen_two_sided()
    L = _fmt_side("📈 BEST LONGS", s["long"], top)
    S = _fmt_side("📉 BEST SHORTS", s["short"], top)
    out = ["Two-sided daily scan — quant gate, both directions\n", *L, "", *S]

    if do_research:
        from scripts.trading_research import run_research
        shortlist = [t for t, *_ in s["long"][:top]] + [t for t, *_ in s["short"][:top]]
        shortlist = list(dict.fromkeys(shortlist))  # dedupe, keep order
        out += ["", "🔬 Deep research (live read on the shortlist):"]
        theses = run_research(shortlist, market_session="equities", model="claude-opus-4-8")
        if not theses:
            out.append("  (no high-conviction theses)")
        for t in sorted(theses, key=lambda x: -x.get("conviction", 0)):
            out.append(f"  {t['symbol']} {t['direction']} conv={t.get('conviction')} — {t.get('rationale','')[:140]}")
    out.append("\nNote: gate passers in a strong uptrend often show 100% win — confirm the live read before chasing.")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="Two-sided best-trades daily scan")
    ap.add_argument("--top", type=int, default=8, help="N per side (default 8)")
    ap.add_argument("--research", action="store_true", help="Add Claude deep research (Opus, ~$)")
    ap.add_argument("--email", action="store_true", help="Email the report via daily_brief_cloud.py")
    args = ap.parse_args()

    text = report(top=args.top, do_research=args.research)
    print(text)

    if args.email:
        import subprocess, tempfile, os
        from datetime import date
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write(text); path = f.name
        try:
            send = subprocess.run([sys.executable, "scripts/daily_brief_cloud.py", "send",
                            "--to", "brian@olivetreeinv.io",
                            "--subject", f"Two-sided trade scan — {date.today():%b %d}",
                            "--body-file", path], capture_output=True, text=True, timeout=120)
            if send.returncode == 0:
                print("\n  📧 Emailed.")
            else:
                print(f"\n  ✗ Email failed (exit {send.returncode}): {send.stderr.strip()[:300]}")
        except subprocess.TimeoutExpired:
            print("\n  ✗ Email failed: timed out after 120s")
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass


if __name__ == "__main__":
    main()
