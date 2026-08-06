#!/usr/bin/env python3
"""
trading_research.py — Research agent for the Olive Tree Trading Desk.

Calls Claude (Haiku by default for cost; override with --model) with recent
price data + market context to produce ranked trading theses in JSON.
Each thesis: symbol, direction, conviction (0–1), rationale, catalyst, horizon.

Only the quant gate + risk agent determine whether a thesis gets traded.
Claude's output is purely directional conviction — the machines decide size.

Usage:
  python3 scripts/trading_research.py                      # run on full equity universe
  python3 scripts/trading_research.py --symbols SPY AAPL   # specific symbols
  python3 scripts/trading_research.py --market-session crypto  # overnight crypto
  python3 scripts/trading_research.py --dry-run            # no API call, print prompt only
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.trading_data import (
    get_bars, get_quote, get_snapshot, get_news, get_technicals,
    get_fear_greed, get_top_movers, get_intraday_bars, get_vwap_context,
    EQUITY_UNIVERSE, CRYPTO_UNIVERSE,
)
from db.connection import Session
from db.schema import TradingThesis

# Haiku: fast + cheap for repeated research calls. ~$0.01–0.03/cycle.
# Bump to claude-opus-4-8 for a deeper thesis if needed.
DEFAULT_MODEL = "claude-haiku-4-5-20251001"


def _build_symbol_block(symbol: str, is_crypto: bool = False) -> str:
    """Build a rich per-symbol context block for the prompt."""
    lines = [f"### {symbol}"]

    # Price momentum from bars
    try:
        bars   = get_bars(symbol, days=20)
        closes = [b["c"] for b in bars[-10:]] if bars else []
        if len(closes) >= 5:
            pct_5d  = (closes[-1] / closes[-5]  - 1) * 100
            pct_10d = (closes[-1] / closes[0]   - 1) * 100 if len(closes) >= 10 else 0
            lines.append(f"Price: {closes[-1]:.2f}  5d: {pct_5d:+.1f}%  10d: {pct_10d:+.1f}%")
    except Exception:
        pass

    # Snapshot (equities only — intraday data)
    if not is_crypto:
        snap = get_snapshot(symbol)
        if snap.get("change_pct") is not None:
            vol_str  = f"  vol: {int(snap['volume']):,}" if snap.get("volume") else ""
            vwap_val = snap.get("vwap") or 0
            vwap_str = f"  VWAP: {vwap_val}" if vwap_val else ""
            open_val = snap.get("open") or 0
            open_str = f"  open: {open_val}" if open_val else ""
            hi, lo   = snap.get("high") or 0, snap.get("low") or 0
            rng_str  = f"  range: {lo}–{hi}" if hi and lo else ""
            lines.append(f"Today: {snap['change_pct']:+.2f}%{vwap_str}{open_str}{rng_str}{vol_str}")

    # Technicals (equities only)
    if not is_crypto:
        tech = get_technicals(symbol)
        if tech:
            macd_str = f"  MACD hist: {tech.get('macd_hist',0):+.3f}" if "macd_hist" in tech else ""
            lines.append(f"RSI(14): {tech.get('rsi','n/a')}{macd_str}")

    # Intraday candles + VWAP (equities only)
    if not is_crypto:
        vwap_ctx = get_vwap_context(symbol)
        if vwap_ctx:
            pos = "above" if vwap_ctx["above_vwap"] else "below"
            lines.append(
                f"VWAP: {vwap_ctx['vwap']}  price {pos} VWAP by {abs(vwap_ctx['price_vs_vwap_pct']):.2f}%"
                f"  5m trend: {vwap_ctx['trend_5m']}"
            )

        bars_5m = get_intraday_bars(symbol, minutes=5, limit=6)
        if len(bars_5m) >= 3:
            from datetime import datetime as _dt
            candle_lines = []
            for b in reversed(bars_5m[:5]):
                # Alpaca returns ISO strings; Polygon-era data was epoch ms
                t   = b["t"]
                dt  = _dt.fromisoformat(t).astimezone() if isinstance(t, str) else _dt.fromtimestamp(t / 1000)
                ts  = dt.strftime("%H:%M")
                dir_arrow = "▲" if b["c"] >= b["o"] else "▼"
                candle_lines.append(f"  {ts} {dir_arrow} o={b['o']}  h={b['h']}  l={b['l']}  c={b['c']}  v={int(b['v'])}")
            lines.append("5-min candles (recent):")
            lines.extend(candle_lines)

    # Live quote
    try:
        q = get_quote(symbol)
        lines.append(f"Live bid/ask: {q['bid']} / {q['ask']}")
    except Exception:
        pass

    # News headlines (equities only; crypto news via Alpaca is sparse)
    if not is_crypto:
        news = get_news(symbol, limit=4)
        if news:
            lines.append("Recent news:")
            for n in news:
                lines.append(f"  [{n['published']}] {n['title']}")

    return "\n".join(lines)


def build_prompt(symbols: list[str], market_session: str = "equities",
                 insider_block: str = "") -> str:
    today     = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    is_crypto = market_session == "crypto"
    is_ext    = market_session == "extended"

    # Macro context block
    macro_lines = [f"## Market Context — {today}  Session: {market_session.upper()}"]
    if is_crypto:
        fg = get_fear_greed()
        if fg:
            macro_lines.append(f"Crypto Fear & Greed Index: {fg['value']}/100 — {fg['label']}")
            if fg["value"] <= 20:
                macro_lines.append("  ⚠️  Extreme Fear — historically contrarian long signal; assess capitulation vs. trend continuation.")
            elif fg["value"] >= 80:
                macro_lines.append("  ⚠️  Extreme Greed — assess whether upside is priced in.")
    else:
        # Use SPY snapshot as macro backdrop (equities + extended sessions)
        spy = get_snapshot("SPY")
        if spy.get("change_pct") is not None:
            macro_lines.append(f"SPY today: {spy['change_pct']:+.2f}%  VWAP: {spy.get('vwap','')}")
        spy_tech = get_technicals("SPY")
        if spy_tech.get("rsi"):
            macro_lines.append(f"SPY RSI(14): {spy_tech['rsi']}  MACD hist: {spy_tech.get('macd_hist',0):+.3f}")
        fg = get_fear_greed()
        if fg:
            macro_lines.append(f"Crypto Fear & Greed (risk appetite proxy): {fg['value']}/100 — {fg['label']}")
        if is_ext:
            macro_lines.append("Session: EXTENDED HOURS (4–8pm ET). Focus on earnings surprises, "
                               "post-catalyst gaps, and names with significant after-hours moves. "
                               "Wider spreads — only high-conviction setups.")

    macro_block = "\n".join(macro_lines)

    # Per-symbol blocks
    symbol_blocks = []
    for sym in symbols:
        symbol_blocks.append(_build_symbol_block(sym, is_crypto=is_crypto))

    symbols_text = "\n\n".join(symbol_blocks)

    insider_section = f"\n{insider_block}\n" if insider_block else ""

    return f"""{macro_block}
{insider_section}
## Symbol Data

{symbols_text}

## Your Task

You are a quantitative analyst for a private trading account. Based on the data above, return a JSON array of your highest-conviction trading theses.

Rules:
- Only include symbols listed above.
- Direction must be LONG or SHORT — commit to a direction based on evidence.
- Conviction: 0.0–1.0. Only include theses with conviction ≥ 0.5.
  - 0.7+: strong signal (news catalyst + technicals aligned)
  - 0.5–0.69: moderate (one clear signal, others neutral)
- Use news, RSI, MACD, Fear & Greed, and price trend together — not price alone.
- RSI < 35 = oversold (long bias), RSI > 65 = overbought (short bias).
- MACD histogram turning positive = bullish momentum shift; negative = bearish.
- Horizon: "intraday", "swing" (2–5 days), or "position" (1–4 weeks).{"" if not is_ext else " Extended-hours plays are almost always intraday — set horizon accordingly."}
- Return ONLY valid JSON. No prose, no markdown fences.

JSON schema:
[{{"symbol":"SPY","direction":"LONG","conviction":0.75,"rationale":"...","catalyst":"...","horizon":"swing"}}]

Return 1–5 theses sorted by conviction descending. If nothing clears 0.5, return [].
"""


def run_research(
    symbols: list[str],
    market_session: str = "equities",
    model: str = DEFAULT_MODEL,
    dry_run: bool = False,
    save: bool = True,
    run_id: str | None = None,
    with_insiders: bool = False,
) -> list[dict]:
    """
    Run the research agent and return a list of thesis dicts.
    Saves each thesis to SQLite (trading_theses) unless save=False.
    """
    insider_block = ""
    if with_insiders:
        from scripts.trading_insiders import get_insider_signal, format_signal_block
        print("  📋 Fetching insider signals...")
        insider_block = format_signal_block(get_insider_signal())

    prompt = build_prompt(symbols, market_session, insider_block)

    if dry_run:
        print("── [DRY RUN] Prompt ─────────────────────────────────────────")
        print(prompt)
        return []

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
    if run_id is None:
        run_id = datetime.now(timezone.utc).isoformat()

    print(f"  🔬 Research agent ({model}) — {len(symbols)} symbols...")
    msg = client.messages.create(
        model=model,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = msg.content[0].text.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
        if raw.endswith("```"):
            raw = raw.rsplit("```", 1)[0]
        raw = raw.strip()

    cost_in  = msg.usage.input_tokens
    cost_out = msg.usage.output_tokens
    print(f"  Tokens: {cost_in} in / {cost_out} out")

    try:
        theses = json.loads(raw)
    except json.JSONDecodeError:
        print(f"  ⚠️  Claude returned non-JSON: {raw[:200]}")
        return []

    if not isinstance(theses, list):
        print(f"  ⚠️  Expected list, got {type(theses)}")
        return []

    now = datetime.now(timezone.utc).isoformat()
    if save and theses:
        s = Session()
        try:
            for t in theses:
                row = TradingThesis(
                    run_id=run_id,
                    symbol=t.get("symbol", ""),
                    direction=t.get("direction", ""),
                    conviction=t.get("conviction", 0),
                    rationale=t.get("rationale", ""),
                    catalyst=t.get("catalyst", ""),
                    horizon=t.get("horizon", ""),
                    created_at=now,
                )
                s.add(row)
            s.commit()
        finally:
            s.close()

    return theses


def main():
    ap = argparse.ArgumentParser(description="Research agent — Claude market theses")
    ap.add_argument("--symbols", nargs="+", help="Override symbol list")
    ap.add_argument("--market-session", default="equities", choices=["equities", "crypto", "extended"],
                    help="Session context for prompt")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--dry-run",   action="store_true", help="Print prompt, no API call")
    ap.add_argument("--insiders",  action="store_true", help="Inject Congress + Burry 13F signals into prompt")
    args = ap.parse_args()

    symbols = args.symbols or (CRYPTO_UNIVERSE if args.market_session == "crypto" else EQUITY_UNIVERSE)
    theses  = run_research(symbols, args.market_session, args.model, args.dry_run,
                           with_insiders=args.insiders)

    if not args.dry_run:
        print(f"\n── {len(theses)} thesis(es) returned ─────────────────────────")
        for t in theses:
            stars = "★" * round(t.get("conviction", 0) * 5)
            print(f"  {stars} {t['symbol']} {t['direction']} (conviction={t.get('conviction')}) [{t.get('horizon')}]")
            print(f"     {t.get('rationale', '')}")
            if t.get("catalyst"):
                print(f"     Catalyst: {t['catalyst']}")


if __name__ == "__main__":
    main()
