#!/usr/bin/env python3
"""
trading_suna.py — Premium Desk v3, Kenneth Suna's weekly income-wheel method.

A weekly, SHARE-FIRST, income-first covered-call/CSP wheel. Distinct from the v2
CSP-first monthly wheel in trading_covered_calls.py (which is untouched and still
runs by default). Selected with `--suna` on the orchestrator.

Reuses v2's tested primitives (option fetch, quotes, two-stage fills, order
submit, sync/assignment detection, the TradingCCPosition table) so `--status`,
`--report`, and assignment handling all work unchanged. Only what makes it *Suna*
lives here: movers discovery, premium-band ranking, entry-timing filter,
share-first multi-lot entry (sized to the $10k position cap), ~0.45Δ weekly
calls, the Wednesday roll trigger, and the underwater repair ladder.

Cycle:  SYNC (reused) → MANAGE → COVER → ENTER (share-first) → WHEEL

    python3 scripts/trading_suna.py --once --dry-run   # print intended actions
    python3 scripts/trading_suna.py --test             # offline rules self-check
    python3 scripts/trading_suna.py --discover          # just show the week's pool

Spec: wiki/trading-desk/_suna-redesign-spec.md
"""

import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))
from db.connection import Session
from db.schema import TradingCCPosition
from scripts.trading_movers import discover
from scripts.trading_data import get_quote, get_account, get_bars, get_news, is_market_open
from scripts.trading_report import send_alert
from scripts.trading_covered_calls import (
    OrderSide,
    _client, _sync, _get_option_snapshots, _option_quote, _parse_occ, _dte,
    _submit_limit, _fill_or_cancel, _two_stage_sell, _two_stage_buy,
    _annualized_yield, _sector_of, _close_cc_pos, get_next_earnings,
    earnings_max_expiry,
    CC_BOOK_USD, CC_MAX_UNDERLYINGS, CC_MAX_POSITION_USD, CC_MAX_PER_SECTOR,
    CC_CASH_BUFFER, CC_MIN_ANNUAL_YIELD, CC_PROFIT_CLOSE,
)

# ── Suna-specific config ──────────────────────────────────────────────────────
SUNA_DTE_MIN, SUNA_DTE_MAX = 3, 9        # weekly expirations (this Friday / next)
SUNA_CALL_DELTA = 0.45                    # income-first: near-the-money, assignment welcome
SUNA_CALL_BAND  = (0.38, 0.55)            # acceptable delta band around the target
SUNA_CSP_DELTA  = 0.30                    # wheel-back puts, a touch richer than v2's 0.25
SUNA_CSP_BAND   = (0.22, 0.40)

# Premium-band gate (weekly premium ÷ price), from the paid guide's risk bands:
PREM_MIN   = 0.008   # <0.8%/wk → too little premium, skip
PREM_MAX   = 0.025   # 0.8–2.5% is the sellable range
PREM_PAUSE = 0.030   # >3%/wk → ultra-volatile, Kenneth pauses; we skip entries

# Options-liquidity floor — movers surface illiquid names the blue-chip list never did.
LIQ_MAX_SPREAD_PCT = 0.10   # bid/ask spread as % of mid
LIQ_MIN_BID        = 0.05   # a real two-sided market, not a $0.00 bid

# Entry-timing filter: skip names that already ripped this week (Suna: wait for the
# pullback/consolidation, don't chase). 5-day return above this = "already surged".
RIP_5D_PCT = 0.12

# Structural-drop screen: a name down at least this much (daily % from the movers feed)
# gets the Haiku "structural vs transient" read before we buy the dip (Suna: buy the
# overreaction, avoid the deteriorating business).
DROP_SCREEN_PCT = -8.0
SUNA_MODEL = "claude-haiku-4-5-20251001"

# Repair ladder: when a lot is underwater, sell a call this many $ above spot so an
# intraweek pop is unlikely to exercise it (early-assignment guard), stepping the
# strike up toward basis each week.
REPAIR_OTM_GAP    = 2.0
REPAIR_TRIGGER_PCT = 0.05   # only "repair" (allow a below-basis strike) once >5% underwater

# Wednesday roll trigger for an ITM short call.
ROLL_ITM_DOLLARS = 1.0
WEDNESDAY = 2  # date.weekday(): Mon=0


# ── Selection (pure; driven by the self-check with stubbed snapshots) ──────────
def _sellable(snap: dict, opt_type: str) -> Optional[dict]:
    """Parse+price one option snapshot into a candidate dict, or None if unusable.
    Applies the weekly DTE window and the liquidity floor."""
    parsed = _parse_occ(snap.get("symbol", ""))
    if not parsed:
        return None
    o_type, exp_str, strike = parsed
    if o_type != opt_type or strike <= 0:
        return None
    dte = _dte(exp_str)
    if not (SUNA_DTE_MIN <= dte <= SUNA_DTE_MAX):
        return None
    quote = snap.get("latestQuote", {}) or {}
    bid = float(quote.get("bp", 0) or 0)
    ask = float(quote.get("ap", 0) or 0)
    mid = (bid + ask) / 2 if (bid or ask) else 0.0
    if mid <= 0 or bid < LIQ_MIN_BID:
        return None
    if ask > 0 and (ask - bid) / mid > LIQ_MAX_SPREAD_PCT:
        return None  # spread too wide → illiquid chain, skip
    greeks = snap.get("greeks", {}) or {}
    delta = greeks.get("delta", None)
    if delta is not None:
        delta = abs(delta)
    return {"symbol": snap["symbol"], "strike": strike, "expiry": exp_str,
            "dte": dte, "delta": delta, "premium": mid, "bid": bid, "ask": ask}


def pick_weekly_call(snaps: list[dict], price: float, min_strike: float = 0.0
                     ) -> Optional[dict]:
    """Income-first weekly call: nearest ~0.45Δ inside the band, strike above
    min_strike (basis, or spot for repair). Falls back to the first strike above
    price when greeks are missing."""
    calls = [c for c in (_sellable(s, "call") for s in snaps)
             if c and c["strike"] >= min_strike]
    if not calls:
        return None
    lo, hi = SUNA_CALL_BAND
    band = [c for c in calls if c["delta"] is not None and lo <= c["delta"] <= hi]
    if band:
        return min(band, key=lambda c: abs(c["delta"] - SUNA_CALL_DELTA))
    otm = [c for c in calls if c["strike"] >= price] or calls
    return {**min(otm, key=lambda c: c["strike"]), "_fallback": True}


def pick_weekly_put(snaps: list[dict], max_strike: float) -> Optional[dict]:
    """Wheel-back weekly put: nearest ~0.30Δ inside the band, strike ≤ max_strike
    (cash available). Falls back to nearest 3% OTM below spot."""
    puts = [p for p in (_sellable(s, "put") for s in snaps)
            if p and p["strike"] <= max_strike]
    if not puts:
        return None
    lo, hi = SUNA_CSP_BAND
    band = [p for p in puts if p["delta"] is not None and lo <= p["delta"] <= hi]
    if band:
        return min(band, key=lambda p: abs(p["delta"] - SUNA_CSP_DELTA))
    return {**min(puts, key=lambda p: abs(p["strike"] - max_strike * 0.97)),
            "_fallback": True}


def premium_band_ok(premium: float, price: float) -> tuple[bool, str]:
    """Suna's premium risk band on a weekly call. Returns (sellable?, reason)."""
    if price <= 0:
        return False, "no price"
    pct = premium / price
    if pct < PREM_MIN:
        return False, f"prem {pct:.2%}/wk < {PREM_MIN:.1%} floor"
    if pct >= PREM_PAUSE:
        return False, f"prem {pct:.2%}/wk ≥ {PREM_PAUSE:.0%} — pause (too volatile)"
    if pct > PREM_MAX:
        return True, f"prem {pct:.2%}/wk (aggressive)"
    return True, f"prem {pct:.2%}/wk"


def position_lots(price: float, avail: float) -> int:
    """How many 100-share lots to buy: fill the per-position cap ($10k), bounded
    by the book's available cash. Suna sizes into a name, not one token lot."""
    if price <= 0:
        return 0
    return int(min(CC_MAX_POSITION_USD, avail) // (price * 100))


def already_ripped(symbol: str) -> bool:
    """Entry-timing filter: True if the stock already surged this week (skip the
    chase). 5-day close-to-now return above RIP_5D_PCT. Fail-open (can't tell → allow)."""
    try:
        bars = get_bars(symbol, days=7, timeframe="1Day")
        closes = [b.get("c") for b in bars if b.get("c")]
        if len(closes) < 2:
            return False
        return (closes[-1] - closes[0]) / closes[0] >= RIP_5D_PCT
    except Exception:
        return False


_DROP_CACHE: dict[str, tuple[bool, str]] = {}


def _classify_drop(headlines: list[dict], symbol: str) -> tuple[bool, str]:
    """Pure Haiku classification of a dropper's news → (is_structural, reason).
    Split out so the self-check can drive the parsing with a stubbed client."""
    news = "\n".join(f"- {h['title']}" for h in headlines[:5]) or "(no recent headlines)"
    prompt = f"""A covered-call desk is deciding whether to buy the dip on {symbol}, which just dropped sharply.
Recent headlines:
{news}

Classify the drop:
- "structural" = the business is deteriorating (multi-quarter guidance cut, secular decline, fraud/accounting, big dilution, lost core customer, failed product/trial). Do NOT buy.
- "transient" = a one-off or overreaction likely to recover (single-quarter miss, macro/sector selloff, sympathy move, analyst downgrade, short-term guidance noise). Safe to sell premium against.
When the headlines are thin or ambiguous, prefer "transient".

Return ONLY JSON, no prose, no fences: {{"verdict":"structural|transient","reason":"one line"}}"""
    import anthropic
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
    msg = client.messages.create(model=SUNA_MODEL, max_tokens=200,
                                 messages=[{"role": "user", "content": prompt}])
    raw = msg.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    data = json.loads(raw)
    structural = str(data.get("verdict", "")).lower() == "structural"
    return structural, str(data.get("reason", ""))[:120]


def structural_drop_screen(symbol: str) -> tuple[bool, str]:
    """True if the drop looks STRUCTURAL (reject the buy). Cached per cycle.
    Fail-open on any error (missing package, API failure, bad JSON) → treat as
    transient/allow, so the screen can never block the whole desk."""
    if symbol in _DROP_CACHE:
        return _DROP_CACHE[symbol]
    try:
        result = _classify_drop(get_news(symbol), symbol)
    except Exception as e:
        print(f"  ⚠️  drop-screen failed for {symbol} ({e}) — allowing (transient)")
        result = (False, "screen failed — allowed")
    _DROP_CACHE[symbol] = result
    return result


# ── DB / cash helpers ─────────────────────────────────────────────────────────
def _open_rows(s):
    return s.query(TradingCCPosition).filter_by(status="open").all()


def _deployed(open_rows) -> float:
    """Capital the CC/wheel book has committed: share lots at cost + CSP collateral.
    The DB is the source of truth for this book's deployment."""
    return sum((r.avg_cost or 0) * (r.shares_qty or 0) for r in open_rows) + \
           sum((r.strike or 0) * 100 for r in open_rows
               if r.option_type == "put" and not r.shares_qty)


def _book_available(open_rows) -> float:
    """Cash the $50k book can still deploy = notional book − committed − buffer, then
    capped by the paper account's real buying power (the account is shared with the v2
    + momentum books, so buying_power is the true ceiling). Book-notional accounting —
    NOT Alpaca `cash` minus deployed, which double-counts share cost already reflected
    in `cash`. Fail-closed: large negative if the account can't be read, so nothing
    deploys when the account is invisible."""
    avail = CC_BOOK_USD - _deployed(open_rows) - CC_BOOK_USD * CC_CASH_BUFFER
    try:
        bp = get_account().get("buying_power", 0)
    except Exception as e:
        print(f"  ⚠️  account fetch failed ({e}) — skipping deployment this cycle")
        return -1e9
    return min(avail, bp)


def _live_symbols(client) -> Optional[set]:
    """Underlyings with any live Alpaca position/order — off-limits (Alpaca nets
    same-symbol lots, breaking assignment detection). None = couldn't fetch → skip."""
    try:
        syms = {p.symbol for p in client.get_all_positions()}
        for o in client.get_orders():
            syms.add(o.symbol)
            if _parse_occ(o.symbol):
                syms.add(o.symbol[:-15])
        return syms
    except Exception as e:
        print(f"  ⚠️  could not fetch live positions/orders ({e})")
        return None


# ── Step 2: MANAGE (profit-close, Wednesday ITM roll, repair) ──────────────────
def _manage(client, dry_run: bool = False):
    print("\n  [SUNA 2/5] Manage (profit-close / Wed ITM roll)...")
    s = Session()
    try:
        for row in _open_rows(s):
            if not (row.option_symbol and row.option_type == "call" and row.shares_qty):
                continue
            bid, ask, mid = _option_quote(row.option_symbol)
            if mid <= 0:
                continue
            contracts = max(1, (row.shares_qty or 0) // 100)
            prem_in = row.premium_received or 0
            # Profit-close: bought back for ≤ (1−60%) of premium collected.
            if prem_in > 0 and mid * 100 * contracts <= prem_in * (1 - CC_PROFIT_CLOSE):
                print(f"  💰 {row.underlying}: profit-close — buy back ${mid*100*contracts:,.0f} "
                      f"vs ${prem_in:,.0f} collected")
                fill = _two_stage_buy(client, row.option_symbol, bid, ask, mid,
                                      qty=contracts, dry_run=dry_run, label="profit-close")
                if fill is not None and not dry_run:
                    row.realized_pnl = (row.realized_pnl or 0) + (prem_in - fill * 100 * contracts)
                    row.option_symbol = None; row.option_type = None
                    row.strike = 0; row.expiry = None; row.premium_received = 0
                    s.commit()
                continue
            # Wednesday roll: short call > $1 ITM → roll out-and-up for a NET CREDIT only.
            try:
                q = get_quote(row.underlying); spot = q.get("last") or q.get("ask") or 0
            except Exception:
                spot = 0
            itm = spot and row.strike and spot - row.strike >= ROLL_ITM_DOLLARS
            if itm and date.today().weekday() >= WEDNESDAY:
                _roll(client, s, row, spot, buyback=(bid, ask, mid), dry_run=dry_run)
        s.commit()
    finally:
        s.close()


def _roll(client, s, row, spot, buyback, dry_run):
    """Roll an ITM weekly call out (+1 week) and up, net-credit only; else let it
    ride to assignment (the wheel picks it up)."""
    contracts = max(1, (row.shares_qty or 0) // 100)
    bid, ask, mid = buyback
    snaps = _get_option_snapshots(row.underlying, opt_type="call", dte_min=SUNA_DTE_MIN)
    # Roll target: higher strike than current, above spot, next weekly.
    nxt = pick_weekly_call(snaps, spot, min_strike=max(row.strike + 0.5, spot))
    if not nxt:
        print(f"  ↪  {row.underlying}: no roll target — ride to assignment")
        return
    net_credit = nxt["premium"] - mid            # sell new − buy back old, per share
    if net_credit <= 0:
        print(f"  ↪  {row.underlying}: roll would be a net debit "
              f"(${net_credit*100*contracts:,.0f}) — ride to assignment, wheel handles it")
        return
    print(f"  🔁 {row.underlying}: roll ${row.strike:g}→${nxt['strike']:g} "
          f"{row.expiry}→{nxt['expiry']} net credit ${net_credit*100*contracts:,.0f}")
    if dry_run:
        return
    close_fill = _two_stage_buy(client, row.option_symbol, bid, ask, mid,
                                qty=contracts, label="roll-close")
    if close_fill is None:
        return
    # Book the close and clear the option NOW — if the new sell fails below, the lot
    # is left cleanly uncovered so _cover re-covers it next cycle (never stranded
    # marked-covered against a contract that no longer exists in Alpaca).
    row.realized_pnl = (row.realized_pnl or 0) + (row.premium_received or 0) - close_fill * 100 * contracts
    row.option_symbol = None; row.option_type = None
    row.strike = 0; row.expiry = None; row.premium_received = 0
    s.commit()
    n_bid, n_ask, n_mid = _option_quote(nxt["symbol"])
    if n_mid <= 0:
        n_bid, n_ask, n_mid = nxt["bid"], nxt["ask"], nxt["premium"]
    fill = _two_stage_sell(client, nxt["symbol"], n_bid, n_ask, n_mid,
                           nxt["strike"], nxt["dte"], qty=contracts, label="roll-open")
    if fill is not None:
        row.option_symbol = nxt["symbol"]; row.option_type = "call"
        row.strike = nxt["strike"]; row.expiry = nxt["expiry"]; row.premium_received = fill * 100 * contracts
        s.commit()
        send_alert("Suna Desk — Roll",
                   f"🔁 {row.underlying} rolled to ${nxt['strike']:g} {nxt['expiry']} "
                   f"(+${net_credit*100*contracts:,.0f} credit)")
    else:
        print(f"  ⚠️  {row.underlying}: closed old call but new sell unfilled — "
              f"lot left uncovered, _cover retries next cycle")


# ── Step 3: COVER (sell a weekly call on any uncovered lot; repair-aware) ──────
def _cover(client, dry_run: bool = False):
    print("\n  [SUNA 3/5] Cover uncovered lots...")
    s = Session()
    try:
        for row in _open_rows(s):
            if row.option_symbol or not row.shares_qty:
                continue  # already has a short call, or it's a CSP row
            try:
                q = get_quote(row.underlying); spot = q.get("last") or q.get("ask") or 0
            except Exception:
                spot = 0
            if not spot:
                continue
            basis = row.avg_cost or 0
            underwater = spot < basis * (1 - REPAIR_TRIGGER_PCT)
            # Normal: never sell below basis. Repair: deeply underwater → sell a
            # call a few $ above spot (below basis, with an early-assignment guard),
            # laddering up toward basis each week.
            min_strike = basis if not underwater else spot + REPAIR_OTM_GAP
            snaps = _get_option_snapshots(row.underlying, opt_type="call", dte_min=SUNA_DTE_MIN)
            best = pick_weekly_call(snaps, spot, min_strike=min_strike)
            if not best:
                tag = "repair strike" if underwater else f"strike ≥ basis ${basis:.2f}"
                print(f"  ⚠️  {row.underlying}: no weekly call at {tag} — hold uncovered")
                continue
            ok, why = premium_band_ok(best["premium"], spot)
            if not ok:
                print(f"  ⏭  {row.underlying}: {why} — hold uncovered")
                continue
            label = "repair-cover" if underwater else "cover"
            if underwater:
                print(f"  🩹 {row.underlying}: REPAIR — spot ${spot:.2f} < basis ${basis:.2f}, "
                      f"sell ${best['strike']:g} call (ladder up next week)")
            _sell_call_row(client, s, row, best, spot, label, dry_run)
        s.commit()
    finally:
        s.close()


def _sell_call_row(client, s, row, call, spot, label, dry_run):
    contracts = max(1, (row.shares_qty or 0) // 100)
    yld = _annualized_yield(call["premium"], call["strike"], call["dte"])
    ok, why = premium_band_ok(call["premium"], spot)
    print(f"  🧾 {row.underlying}: sell {call['symbol']} exp {call['expiry']} "
          f"strike=${call['strike']:g} prem=${call['premium']*100*contracts:,.0f} "
          f"({why}, {yld:.0%}/yr) [{label}]")
    b, a, m = _option_quote(call["symbol"])
    if m <= 0:
        b, a, m = call["bid"], call["ask"], call["premium"]
    fill = _two_stage_sell(client, call["symbol"], b, a, m, call["strike"], call["dte"],
                           qty=contracts, dry_run=dry_run, label=label)
    if fill is not None and not dry_run:
        row.option_symbol = call["symbol"]; row.option_type = "call"
        row.strike = call["strike"]; row.expiry = call["expiry"]
        row.premium_received = fill * 100 * contracts
        s.commit()
        send_alert(f"Suna Desk — {label.title()}",
                   f"🧾 {row.underlying} sold ${call['strike']:g} call {call['expiry']} "
                   f"for ${fill*100*contracts:,.0f}")


# ── Step 4: ENTER (share-first on the week's movers pool) ──────────────────────
def _enter(client, dry_run: bool = False):
    print("\n  [SUNA 4/5] Enter share-first (movers → premium band)...")
    s = Session()
    try:
        open_rows = _open_rows(s)
        held = {r.underlying for r in open_rows}
        slots = CC_MAX_UNDERLYINGS - len(held)
        if slots <= 0:
            print(f"  ⏭  At max {CC_MAX_UNDERLYINGS} underlyings — no entries"); return

        from collections import Counter
        sector_counts = Counter(_sector_of(u) for u in held)
        live = _live_symbols(client)
        if live is None:
            print("  ⏭  can't see live account — skipping entries this cycle"); return

        avail = _book_available(open_rows)
        if avail < CC_MAX_POSITION_USD * 0.5:
            print(f"  ⏭  book cash too low (${avail:,.0f}) — skipping entry"); return

        pool = discover()
        print(f"  🔎 {len(pool)} movers in pool")
        entered = 0
        for cand in pool:
            if entered >= slots:
                break
            tkr = cand["symbol"]
            if tkr in held or tkr in live:
                continue
            sector = _sector_of(tkr)
            # The per-sector cap only applies to KNOWN sectors. Most movers-pool names
            # aren't in the v2 SECTOR map and resolve to "Unknown"; capping that shared
            # bucket at 2 would throttle the whole desk to ~2 entries/cycle.
            if sector != "Unknown" and sector_counts[sector] >= CC_MAX_PER_SECTOR:
                continue
            # Resolve price (most-actives rows lack it).
            price = cand.get("price")
            if not price:
                try:
                    q = get_quote(tkr); price = q.get("last") or q.get("ask") or 0
                except Exception:
                    price = 0
            if not price or price < 10:
                continue
            if already_ripped(tkr):
                print(f"  ⏭  {tkr}: already ripped this week — wait for pullback")
                continue
            # Earnings guard (reuse v2's resolver): skip if earnings before our weekly expiry.
            max_exp = earnings_max_expiry(get_next_earnings(tkr))
            if max_exp and (max_exp - date.today()).days < SUNA_DTE_MIN:
                print(f"  ⏭  {tkr}: earnings inside the weekly window — skip")
                continue
            snaps = _get_option_snapshots(tkr, opt_type="call", dte_min=SUNA_DTE_MIN)
            call = pick_weekly_call(snaps, price, min_strike=price)  # 1-strike-OTM (≥ spot)
            if not call:
                continue
            ok, why = premium_band_ok(call["premium"], price)
            if not ok:
                print(f"  ⏭  {tkr}: {why}")
                continue
            lots = position_lots(price, avail)
            if lots < 1:
                continue
            cost = price * 100 * lots
            # Structural-drop screen (Haiku) — only for meaningful droppers, and only
            # now that the name has cleared every cheap filter, so we spend tokens on
            # names we'd actually buy. Buy the overreaction, skip the broken business.
            is_dropper = cand.get("source") == "losers" or (cand.get("pct_change") or 0) <= DROP_SCREEN_PCT
            if is_dropper:
                structural, why_drop = structural_drop_screen(tkr)
                if structural:
                    print(f"  🚩 {tkr}: structural drop — {why_drop} — skip")
                    continue
            print(f"  🛒 ENTER {tkr}: buy {lots*100}sh ~${price:.2f} (${cost:,.0f}), "
                  f"sell ${call['strike']:g} call {call['expiry']} "
                  f"prem=${call['premium']*100*lots:,.0f} ({why}) [{sector}]")
            if dry_run:
                sector_counts[sector] += 1; avail -= cost; entered += 1
                continue
            # Buy shares (marketable limit a touch above ask), then cover.
            oid = _submit_limit(client, tkr, 100 * lots, OrderSide.BUY, round(price * 1.003, 2),
                                label="share buy")
            sh_fill = _fill_or_cancel(client, oid, timeout=45)
            if sh_fill is None:
                print(f"  ⏳ {tkr}: share buy unfilled — retry next cycle")
                continue
            row = TradingCCPosition(
                underlying=tkr, shares_qty=100 * lots, avg_cost=sh_fill,
                status="open", opened_at=datetime.now(timezone.utc).isoformat(),
            )
            s.add(row); s.commit()
            b, a, m = _option_quote(call["symbol"])
            if m <= 0:
                b, a, m = call["bid"], call["ask"], call["premium"]
            fill = _two_stage_sell(client, call["symbol"], b, a, m, call["strike"],
                                   call["dte"], qty=lots, label="cover-on-entry")
            if fill is not None:
                row.option_symbol = call["symbol"]; row.option_type = "call"
                row.strike = call["strike"]; row.expiry = call["expiry"]
                row.premium_received = fill * 100 * lots
                s.commit()
            send_alert("Suna Desk — Entry",
                       f"🛒 {tkr}: {lots*100}sh @ ${sh_fill:.2f} + ${call['strike']:g} call "
                       f"{call['expiry']} for ${(fill or 0)*100*lots:,.0f}")
            sector_counts[sector] += 1; avail -= cost; entered += 1
        if entered == 0:
            print("  No entries passed movers → premium-band → timing filters.")
    finally:
        s.close()


# ── Step 5: WHEEL (sell a weekly CSP on assigned names) ────────────────────────
def _wheel(client, dry_run: bool = False):
    print("\n  [SUNA 5/5] Wheel (weekly CSP on assigned)...")
    s = Session()
    try:
        assigned = s.query(TradingCCPosition).filter_by(status="assigned").all()
        free = _book_available(_open_rows(s))
        for row in assigned:
            try:
                q = get_quote(row.underlying); price = q.get("last") or q.get("ask") or 0
            except Exception:
                price = 0
            if not price:
                continue
            max_strike = min(price, CC_MAX_POSITION_USD / 100, max(free, 0) / 100)
            snaps = _get_option_snapshots(row.underlying, opt_type="put", dte_min=SUNA_DTE_MIN)
            put = pick_weekly_put(snaps, max_strike)
            if not put:
                print(f"  ⚠️  {row.underlying}: no weekly put fits cash/DTE — skip")
                continue
            ok, why = premium_band_ok(put["premium"], price)
            if not ok:
                # Capital-efficiency rule: don't reserve thousands for a token put.
                print(f"  ⏭  {row.underlying}: {why} — skip CSP, redeploy cash to a CC")
                continue
            print(f"  🎡 Wheel {row.underlying}: sell {put['symbol']} exp {put['expiry']} "
                  f"strike=${put['strike']:g} prem=${put['premium']*100:,.0f} ({why})")
            if dry_run:
                continue
            b, a, m = _option_quote(put["symbol"])
            if m <= 0:
                b, a, m = put["bid"], put["ask"], put["premium"]
            fill = _two_stage_sell(client, put["symbol"], b, a, m, put["strike"], put["dte"],
                                   label="CSP wheel")
            if fill is not None:
                s.add(TradingCCPosition(
                    underlying=row.underlying, shares_qty=0, avg_cost=0,
                    option_symbol=put["symbol"], option_type="put",
                    strike=put["strike"], expiry=put["expiry"],
                    premium_received=fill * 100,
                    status="open", opened_at=datetime.now(timezone.utc).isoformat()))
                row.status = "wheeled"
                s.commit()
                free -= put["strike"] * 100
                send_alert("Suna Desk — Wheel",
                           f"🎡 {row.underlying} sold ${put['strike']:g} CSP {put['expiry']} "
                           f"for ${fill*100:,.0f}")
        s.commit()
    finally:
        s.close()


# ── Public API ────────────────────────────────────────────────────────────────
def run_suna_cycle(dry_run: bool = False):
    """One full weekly Suna wheel cycle. Called by the orchestrator under --suna."""
    print(f"\n  {'─'*60}")
    print(f"  Suna Weekly Cycle {'[DRY RUN] ' if dry_run else ''}"
          f"— {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"  {'─'*60}")
    _DROP_CACHE.clear()   # fresh structural/transient reads each cycle (loop runs for days)
    client = _client()
    _sync(client, dry_run)                       # reused: assignment/expiry reconciliation
    if not is_market_open():
        print("\n  Market closed — sync done; skipping manage/cover/enter/wheel.")
        return
    _manage(client, dry_run)
    _cover(client, dry_run)
    _enter(client, dry_run)
    _wheel(client, dry_run)
    print("\n  Suna cycle complete.")


# ── self-check ────────────────────────────────────────────────────────────────
def _snap(sym, delta, bid, ask):
    return {"symbol": sym, "greeks": {"delta": delta},
            "latestQuote": {"bp": bid, "ap": ask}}


def _test():
    from datetime import timedelta
    fri = (date.today() + timedelta(days=(4 - date.today().weekday()) % 7 or 7))
    exp = fri.strftime("%y%m%d")

    def occ(strike, kind="C"):
        return f"HIMS{exp}{kind}{int(strike*1000):08d}"

    # Weekly calls at $56 spot: 0.45Δ near $58, plus an illiquid wide-spread one.
    snaps = [
        _snap(occ(57), 0.55, 1.40, 1.50),
        _snap(occ(58), 0.45, 1.05, 1.15),   # target
        _snap(occ(60), 0.30, 0.55, 0.62),
        _snap(occ(62), 0.18, 0.20, 0.60),   # spread 200% of mid → liquidity-rejected
    ]
    pick = pick_weekly_call(snaps, price=56.0, min_strike=56.0)
    assert pick and abs(pick["strike"] - 58) < 1e-6, f"call pick wrong: {pick}"
    assert pick["delta"] == 0.45

    # Liquidity floor drops the wide-spread contract.
    assert _sellable(snaps[3], "call") is None, "wide spread should be rejected"
    assert _sellable(snaps[1], "call") is not None

    # never-below-basis: min_strike filters out the $57 strike when basis is $58.
    hi = pick_weekly_call(snaps, price=56.0, min_strike=58.0)
    assert hi and hi["strike"] >= 58, "min_strike (basis) not enforced"

    # Premium bands.
    assert premium_band_ok(1.15, 56.0)[0] is True             # 2.05% → aggressive-but-ok
    assert premium_band_ok(0.20, 56.0)[0] is False            # 0.36% → below floor
    assert premium_band_ok(2.00, 56.0)[0] is False            # 3.57% → pause
    ok, why = premium_band_ok(1.50, 56.0)                     # 2.68% → aggressive band (>2.5%, <3%)
    assert ok and "aggressive" in why, f"expected aggressive band: {why}"

    # Put pick respects cash cap.
    pexp = exp
    puts = [_snap(f"HIMS{pexp}P{int(54*1000):08d}", -0.30, 0.93, 1.00),
            _snap(f"HIMS{pexp}P{int(58*1000):08d}", -0.45, 1.88, 1.95)]
    pput = pick_weekly_put(puts, max_strike=55.0)
    assert pput and pput["strike"] == 54, f"put cash cap failed: {pput}"

    # DTE window: a 30-DTE call is out of the weekly window.
    far = (date.today() + timedelta(days=30)).strftime("%y%m%d")
    assert _sellable(_snap(f"HIMS{far}C{int(58*1000):08d}", 0.45, 1.0, 1.1), "call") is None

    # Structural-drop screen: cache + fail-open, no network.
    _DROP_CACHE.clear()
    _DROP_CACHE["BADCO"] = (True, "guidance cut 3 quarters")   # structural → reject
    _DROP_CACHE["DIPCO"] = (False, "one-off macro selloff")    # transient → allow
    assert structural_drop_screen("BADCO")[0] is True
    assert structural_drop_screen("DIPCO")[0] is False
    # Classifier error (no network in the self-check) → fail-open (allow), never blocks.
    global _classify_drop
    _orig = _classify_drop
    _classify_drop = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("offline"))
    try:
        assert structural_drop_screen("ERRS_XYZ")[0] is False
    finally:
        _classify_drop = _orig

    # Lot sizing: fill the $10k cap, bounded by available cash.
    assert position_lots(25.0, 50_000) == 4      # $10k cap → 4 lots
    assert position_lots(80.0, 50_000) == 1      # $8k lot, 2 would breach cap
    assert position_lots(120.0, 50_000) == 0     # one lot > $10k cap → no entry
    assert position_lots(25.0, 3_000) == 1       # cash-bound below the cap
    assert position_lots(25.0, 2_000) == 0       # can't afford one lot

    print("✅ trading_suna self-check passed")


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="Run one cycle")
    ap.add_argument("--dry-run", action="store_true", help="No orders")
    ap.add_argument("--discover", action="store_true", help="Print the week's movers pool and exit")
    ap.add_argument("--test", action="store_true", help="Offline rules self-check")
    args = ap.parse_args()
    if args.test:
        _test(); return
    if args.discover:
        for r in discover():
            pc = f"{r['pct_change']:+.1f}%" if r["pct_change"] is not None else "n/a"
            print(f"  {r['symbol']:6s} {pc:>7s}  [{r['source']}]")
        return
    run_suna_cycle(dry_run=args.dry_run or not args.once)


if __name__ == "__main__":
    main()
