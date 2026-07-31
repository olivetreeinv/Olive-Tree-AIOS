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
calls, the Friday-afternoon roll trigger, and the underwater repair ladder.

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
from functools import lru_cache
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))
from db.connection import Session
from db.schema import TradingCCPosition, TradingOrder
from scripts.trading_movers import discover
from scripts.trading_data import (
    get_quote, get_account, get_bars, get_news, is_market_open, _ET_TZ,
)
from scripts.trading_report import send_alert
from scripts.trading_covered_calls import (
    OrderSide,
    _client, _sync, _get_option_snapshots, _option_quote, _parse_occ, _dte,
    _submit_limit, _fill_or_cancel, _two_stage_sell, _two_stage_buy,
    _annualized_yield, _close_cc_pos, get_next_earnings,
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

# ── Stock-side selection filters (Suna's screener, wiki/trading-desk/kenneth-suna/
# how-to-use-screeners-for-covered-calls + covered-call-stocks-under-10) ───────
# Until 2026-07-31 the desk had NO stock-quality gate at all — only a 30-ticker
# denylist — so the movers feed filled the pool with leveraged single-stock ETFs
# (AMZU/AMZG/MSTU/NVD/KORU), bond ETFs (LQD/TLT) and micro-caps. Suna screens on
# four things before he ever looks at a chain; these are those four.
#
# Beta 1-2 and short interest 10-20% are what he states in the screener video.
# The under-$10 video widens SI to "10-20% or 20-30%, avoid >30%", so the SI
# ceiling here is 30% (Brian's call, 2026-07-31). The beta band stays at his
# stated 1-2; the >=3%/wk premium pause is the desk's real volatility ceiling.
# Measured on the live 242-name pool: EQUITY-only cuts 24, then these bands
# leave 11 candidates — proportionally in line with Suna's own 1,200 -> 9 demo.
SUNA_BETA_MIN, SUNA_BETA_MAX = 1.0, 2.0    # below 1 = staples/utilities, no premium
SUNA_SI_MIN,   SUNA_SI_MAX   = 0.10, 0.30  # short interest as % of float

# Junk filter — OURS, NOT SUNA'S. His equivalent step is "do I recognize any
# companies here?" (kenneth-suna/_transcripts/Iu3J4KhO0qg.txt), a query against
# 26 years of personal memory. The corpus contains NO market-cap, float, or
# liquidity number anywhere — his only hard figure is "penny stocks, anything $5
# and under", already covered by MOVERS_PRICE_MIN=$10 (and he breaks it himself:
# XRX $5.24, OPEN $5.17). These two floors are Brian's risk gate for the
# micro-caps the movers feed surfaces. Do not cite them as Suna's rule.
MIN_MARKET_CAP = 500_000_000
MIN_AVG_VOLUME = 500_000

# Gates named here COMPUTE AND LOG their verdict but do not reject. Remove a name
# to make it binding. Both start advisory: `trend` because it can intersect the
# downtrend-first pool at near-zero candidates, `quality` because its numbers are
# ours and the log should prove what they'd cut before they cut anything.
SHADOW_GATES = {"trend", "quality"}

# Repair ladder: when a lot is underwater, sell a call this many $ above spot so an
# intraweek pop is unlikely to exercise it (early-assignment guard), stepping the
# strike up toward basis each week. Scales with price — a flat $2 gap put the
# strike ~11% OTM on an $18 stock (unsellable); 3% of spot, floored at $0.50,
# capped at $2.00.
REPAIR_OTM_GAP_MIN, REPAIR_OTM_GAP_MAX, REPAIR_OTM_GAP_PCT = 0.50, 2.0, 0.03
REPAIR_TRIGGER_PCT = 0.05   # only "repair" (allow a below-basis strike) once >5% underwater

# Roll trigger for an ITM short call. FRIDAY AFTERNOON, not Wednesday — his words:
# "Friday afternoon, if it's looking pretty likely that it's going to close over
# that strike price, you just roll the contract to the next Friday"
# (kenneth-suna/_transcripts/5nNwGFWO5yU.txt). The old Wednesday trigger came from
# a paraphrase in the redesign spec; rolling two days early buys back time value
# he explicitly waits out, and an ITM call left to expire is assignment — which is
# the goal ("my shares will get assigned, which is my goal", 8fyt8c4_uEQ.txt).
ROLL_ITM_DOLLARS = 1.0
FRIDAY = 4        # date.weekday(): Mon=0
ROLL_HOUR_ET = 12  # "afternoon" — he never names an hour, so midday is our read

# Dead-lot escalation: a lot uncovered this many calendar days retries with a
# widened (up to N-day) expiry window before we give up and sell the shares.
DEAD_LOT_ESCALATE_DAYS = 5
DEAD_LOT_WIDE_DTE_MAX  = 14
UNCOVERED_STATE_FILE = Path(__file__).parent.parent / "data" / "suna_uncovered.json"


# ── Selection (pure; driven by the self-check with stubbed snapshots) ──────────
def _sellable(snap: dict, opt_type: str, dte_max: int = SUNA_DTE_MAX) -> Optional[dict]:
    """Parse+price one option snapshot into a candidate dict, or None if unusable.
    Applies the weekly DTE window and the liquidity floor. dte_max is overridable
    for the dead-lot escalation retry (widens past the normal weekly window)."""
    parsed = _parse_occ(snap.get("symbol", ""))
    if not parsed:
        return None
    o_type, exp_str, strike = parsed
    if o_type != opt_type or strike <= 0:
        return None
    dte = _dte(exp_str)
    if not (SUNA_DTE_MIN <= dte <= dte_max):
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


def pick_weekly_call(snaps: list[dict], price: float, min_strike: float = 0.0,
                     dte_max: int = SUNA_DTE_MAX) -> Optional[dict]:
    """Income-first weekly call: nearest ~0.45Δ inside the band, strike above
    min_strike (basis, or spot for repair). Falls back to the first strike above
    price when greeks are missing. dte_max: widened by the dead-lot escalation
    retry in _cover() when nothing sells in the normal weekly window."""
    calls = [c for c in (_sellable(s, "call", dte_max=dte_max) for s in snaps)
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


def _repair_gap(spot: float) -> float:
    """Repair-strike offset above spot: 3% of price, floored at $0.50, capped at
    $2.00. (Flat $2 was too wide for cheap stocks — SOFI at $18 put the strike
    ~11% OTM, so nothing sellable ever appeared in the weekly chain.)"""
    return max(REPAIR_OTM_GAP_MIN, min(REPAIR_OTM_GAP_MAX, REPAIR_OTM_GAP_PCT * spot))


def position_lots(price: float, avail: float) -> int:
    """How many 100-share lots to buy: fill the per-position cap ($10k), bounded
    by the book's available cash. Suna sizes into a name, not one token lot."""
    if price <= 0:
        return 0
    return int(min(CC_MAX_POSITION_USD, avail) // (price * 100))


@lru_cache(maxsize=512)
def suna_profile(symbol: str) -> dict:
    """Quote type + beta + short interest + sector for one symbol, in one yfinance
    call (~0.5s). Everything Suna's screener filters on. `{}` when unavailable —
    callers treat that as a reject, see stock_filters_ok()."""
    try:
        import yfinance as yf
        i = yf.Ticker(symbol).info
        p = {"quote_type": i.get("quoteType"), "beta": i.get("beta"),
             "short_float": i.get("shortPercentOfFloat"), "sector": i.get("sector"),
             # Same response, no extra call — feeds quality_ok().
             "market_cap": i.get("marketCap"), "avg_volume": i.get("averageVolume")}
        # yfinance has no beta for ~10% of real equities. Compute it from bars
        # rather than reject the name for a data gap. EQUITY only — an ETF has
        # no business here regardless of what its beta works out to.
        if p["beta"] is None and p["quote_type"] == "EQUITY":
            p["beta"] = beta_from_bars(symbol)
            p["beta_source"] = "bars"
        return p
    except Exception as e:
        print(f"  ⚠️  profile lookup failed for {symbol}: {e}")
        return {}


def _daily_returns(symbol: str, days: int = 365) -> list[tuple[str, float]]:
    """(date, close-to-close return) pairs from Alpaca daily bars."""
    bars = [b for b in get_bars(symbol, days=days, timeframe="1Day") if b.get("c")]
    return [(bars[i]["t"][:10], bars[i]["c"] / bars[i - 1]["c"] - 1)
            for i in range(1, len(bars))]


@lru_cache(maxsize=1)
def _spy_returns() -> dict:
    """Benchmark leg of the beta calc. Cached — one fetch per process."""
    return dict(_daily_returns("SPY"))


BETA_MIN_OVERLAP = 120   # ~6 months of shared trading days before a beta is trustworthy


def beta_from_bars(symbol: str) -> Optional[float]:
    """Beta vs SPY from 1y of daily bars, for the ~10% of real equities where
    yfinance has no beta field (measured 2026-07-31: 23 of 218, including AAPL,
    AMZN, RBLX, RIVN). Without this the gate silently rejects them for a data
    gap rather than a Suna criterion. Alpaca bars are already paid for.

    None when the histories don't overlap enough to be meaningful (new listings,
    recent IPOs) — the caller treats that as a reject, same as a missing beta.
    """
    try:
        spy = _spy_returns()
        pairs = [(r, spy[d]) for d, r in _daily_returns(symbol) if d in spy]
        if len(pairs) < BETA_MIN_OVERLAP:
            return None
        n = len(pairs)
        mx = sum(p[0] for p in pairs) / n
        my = sum(p[1] for p in pairs) / n
        var = sum((p[1] - my) ** 2 for p in pairs)
        if var <= 0:
            return None
        return sum((p[0] - mx) * (p[1] - my) for p in pairs) / var
    except Exception as e:
        print(f"  ⚠️  beta calc failed for {symbol}: {e}")
        return None


def stock_filters_ok(profile: dict) -> tuple[bool, str]:
    """Suna's four stock-side screener filters. Returns (passes?, reason).

    Fails CLOSED, unlike already_ripped(): a name whose type/beta/short interest
    we can't verify is exactly the junk this gate exists to reject, and skipping
    an entry is free — there are 200+ other names in the pool. Only ETFs and
    delisted tickers actually return empty here (verified against the live pool:
    every leveraged/inverse product resolves quoteType=ETF).
    """
    if profile.get("quote_type") != "EQUITY":
        return False, f"not a single-name stock (quoteType={profile.get('quote_type')})"
    beta = profile.get("beta")
    if beta is None:
        return False, "no beta"
    if not (SUNA_BETA_MIN <= beta <= SUNA_BETA_MAX):
        return False, f"beta {beta:.2f} outside {SUNA_BETA_MIN}-{SUNA_BETA_MAX}"
    si = profile.get("short_float")
    if si is None:
        return False, "no short interest"
    if not (SUNA_SI_MIN <= si <= SUNA_SI_MAX):
        return False, f"short interest {si:.1%} outside {SUNA_SI_MIN:.0%}-{SUNA_SI_MAX:.0%}"
    return True, f"beta {beta:.2f}, SI {si:.1%}"


def _gate(name: str, ok: bool, why: str, symbol: str) -> bool:
    """Shadow-aware reject. Returns True to continue, False to skip the name."""
    if ok:
        return True
    if name in SHADOW_GATES:
        print(f"  👻 {symbol}: SHADOW {name} would reject — {why}")
        return True
    print(f"  ⏭  {symbol}: {why}")
    return False


def quality_ok(profile: dict) -> tuple[bool, str]:
    """Junk filter (ours — see MIN_MARKET_CAP). Fails OPEN on missing data:
    stock_filters_ok() already fails closed on the same profile, so anything
    reaching here has real fundamentals; a null cap is a yfinance gap, not junk."""
    cap = profile.get("market_cap")
    if cap is not None and cap < MIN_MARKET_CAP:
        return False, f"market cap ${cap/1e6:,.0f}M < ${MIN_MARKET_CAP/1e6:,.0f}M"
    vol = profile.get("avg_volume")
    if vol is not None and vol < MIN_AVG_VOLUME:
        return False, f"avg volume {vol:,.0f} < {MIN_AVG_VOLUME:,}"
    return True, "cap/volume ok"


def _sma(values: list[float], period: int) -> Optional[float]:
    return sum(values[-period:]) / period if len(values) >= period else None


def entry_signals(symbol: str) -> dict:
    """Every price/volume entry signal from ONE bars call (was a 7-day call for
    the rip test alone; 320 calendar days ≈ 200 trading days, the window
    trading_orchestrator._get_regime already uses).

        {"ripped": bool, "above_50dma": bool|None, "above_200dma": bool|None,
         "rvol": float|None}

    Fail-open on any error → `{}`, and callers treat missing keys as "allow",
    matching the old already_ripped() behaviour.
    """
    try:
        bars = get_bars(symbol, days=320, timeframe="1Day")
    except Exception:
        return {}
    closes = [b["c"] for b in bars if b.get("c")]
    if len(closes) < 2:
        return {}
    last = closes[-1]
    # Genuinely 5 TRADING days now. The old already_ripped() took closes[0] of a
    # days=7 fetch, but get_bars pads +10 calendar days, so it was measuring ~11
    # trading days against a constant named RIP_5D_PCT — a wider window flags
    # more names, so this loosens the filter slightly toward its stated intent.
    sig: dict = {"ripped": (last - closes[-6]) / closes[-6] >= RIP_5D_PCT
                 if len(closes) >= 6 else False}
    for period, key in ((50, "above_50dma"), (200, "above_200dma")):
        sma = _sma(closes, period)
        sig[key] = None if sma is None else last > sma
    # rvol is LOGGED, never gated: Suna says "an increase in volume" but never
    # names a baseline, so any threshold would be ours dressed as his.
    vols = [b["v"] for b in bars if b.get("v") is not None]
    if len(vols) >= 21:
        base = sum(vols[-21:-1]) / 20
        sig["rvol"] = vols[-1] / base if base else None
    return sig


def trend_ok(sig: dict) -> tuple[bool, str]:
    """Suna's one crisp technical trigger: price back above BOTH the 50-day and
    200-day moving averages — "it's going to cross over the 50-day moving
    average ... and cross over the 200 day moving average. This is a very
    bullish indicator" (kenneth-suna/_transcripts/MDBy-6aGw3A.txt, part 12).

    Fail-open: a name without 200 sessions of history (recent IPO) isn't
    judged by a rule that needs them.
    """
    below = [name for key, name in (("above_50dma", "50DMA"), ("above_200dma", "200DMA"))
             if sig.get(key) is False]
    if below:
        return False, f"below {' and '.join(below)}"
    return True, "above 50/200DMA"


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


def suna_sector(symbol: str) -> str:
    """Real sector from the yfinance profile we already fetch.

    Replaces v2's hardcoded SECTOR dict, which only knew the retired 38-name
    blue-chip universe: measured on the live 478-name pool, 95% resolved to
    "Unknown" — and _enter() skips the per-sector cap for Unknown, so
    CC_MAX_PER_SECTOR was decorative and all 8 slots could pile into one sector.
    On a 12-name sample of screener survivors, 7 were Consumer Cyclical.

    No fallback to the old dict on purpose: it uses GICS names ("Consumer
    Discretionary") where yfinance uses Yahoo's ("Consumer Cyclical"), so mixing
    them would split one real sector across two cap buckets. Costs nothing —
    suna_profile() is lru_cached and _enter() calls it for every candidate.
    """
    return suna_profile(symbol).get("sector") or "Unknown"


def csp_collateral() -> float:
    """Options buying power — the pool Alpaca actually checks when securing a put.
    Fail-closed (0) if the account can't be read, so the wheel sits out rather
    than firing orders it can't collateralise."""
    try:
        return float(get_account().get("options_buying_power", 0) or 0)
    except Exception as e:
        print(f"  ⚠️  account fetch failed ({e}) — treating CSP collateral as $0")
        return 0.0


def csp_max_strike(price: float, book_free: float, opt_bp: float) -> float:
    """Highest put strike we can actually sell: bounded by spot (never above the
    price we'd happily own it at), the per-position cap, the book's notional
    room, AND the broker's collateral. Returns 0 when nothing fits.

    The last bound is the one that was missing — a put needs strike*100 in
    OPTIONS buying power, and Alpaca rejects the order outright if it isn't
    there, so an unbounded strike burned two order attempts every cycle.
    """
    cap = min(price, CC_MAX_POSITION_USD / 100, max(book_free, 0) / 100, max(opt_bp, 0) / 100)
    return cap if cap > 0 else 0.0


def broker_shares(client, symbol: str) -> int:
    """Shares Alpaca actually shows for a symbol (0 if none/unreadable).

    A covered call is only 'covered' against the BROKER's position book, not
    ours. Selling before the share fill lands there — or against a lot our DB
    still believes in but Alpaca has already assigned away — is what produced
    13x "account not eligible to trade uncovered option contracts".
    """
    try:
        return int(float(client.get_open_position(symbol).qty))
    except Exception:
        return 0


def await_shares(client, symbol: str, want: int, timeout: int = 15) -> int:
    """Poll until the broker shows `want` shares, up to timeout. Returns the
    count seen. A filled buy order is not the same event as a visible position —
    they can land a beat apart, and the cover sell in between reads as naked."""
    import time
    deadline = time.monotonic() + timeout
    while True:
        have = broker_shares(client, symbol)
        if have >= want or time.monotonic() >= deadline:
            return have
        time.sleep(1)


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


def _log_option_fill(s, symbol: str, side: str, qty: int, fill_price: float, label: str):
    """Append a trading_orders row for one option fill. This is the source of
    truth --status reads for WTD/MTD premium: option legs get RE-SOLD IN PLACE on
    the same trading_cc_positions row (opened_at never moves), so the old
    opened_at-filtered premium calc goes blind on resold legs. Options only —
    share buys/sells aren't logged here."""
    now = datetime.now(timezone.utc).isoformat()
    s.add(TradingOrder(symbol=symbol, side=side, qty=qty, order_type=label,
                       filled_price=fill_price, filled_qty=qty, status="filled",
                       submitted_at=now, filled_at=now))


# ── Dead-lot state (uncovered-lot escalation) ───────────────────────────────────
def _load_uncovered() -> dict:
    """{symbol: first_fail_date_iso} — ponytail: smallest persistent counter for
    tracking how long a lot has gone uncovered; upgrade to a DB column only if
    more per-lot state accrues."""
    try:
        return json.loads(UNCOVERED_STATE_FILE.read_text())
    except Exception:
        return {}


def _save_uncovered(state: dict):
    UNCOVERED_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    UNCOVERED_STATE_FILE.write_text(json.dumps(state))


def _exit_lot(client, s, row, spot) -> Optional[float]:
    """Sell the shares to recycle capital when a lot can't be covered even at the
    widened 14-day expiry. Mirrors ENTER's share-buy order pattern (marketable
    limit + fill_or_cancel, single stage — no options involved). Returns the fill
    price, or None if unfilled (caller keeps the escalation clock running)."""
    shares = row.shares_qty or 0
    oid = _submit_limit(client, row.underlying, shares, OrderSide.SELL,
                        round(spot * 0.997, 2), label="dead-lot exit")
    fill = _fill_or_cancel(client, oid, timeout=45)
    if fill is None:
        print(f"  ⚠️  {row.underlying}: exit sell unfilled — retries next cycle")
        return None
    pnl = (fill - (row.avg_cost or 0)) * shares
    row.status = "closed"
    row.closed_at = datetime.now(timezone.utc).isoformat()
    row.realized_pnl = (row.realized_pnl or 0) + pnl
    s.commit()
    send_alert("Suna Desk — Dead Lot Exit",
               f"{row.underlying}: sold {shares}sh @ ${fill:.2f} to exit — P&L ${pnl:+,.0f}")
    return fill


def _handle_dead_lot(client, s, row, spot, underwater, min_strike, snaps, state, dry_run) -> None:
    """Called when a lot can't be covered this cycle (no weekly call, or the only
    one fails the premium band). Tracks the first-fail date in state; once stuck
    >= DEAD_LOT_ESCALATE_DAYS, retries with a widened (up to 14-day) expiry, and
    if that's still unsellable, alerts and — unless dry_run — sells the shares."""
    sym = row.underlying
    first_fail = state.get(sym)
    if not first_fail:
        state[sym] = date.today().isoformat()
        return
    days_stuck = (date.today() - date.fromisoformat(first_fail)).days
    if days_stuck < DEAD_LOT_ESCALATE_DAYS:
        return
    wide = pick_weekly_call(snaps, spot, min_strike=min_strike, dte_max=DEAD_LOT_WIDE_DTE_MAX)
    ok = wide and premium_band_ok(wide["premium"], spot)[0]
    if ok:
        print(f"  🗓  {sym}: {days_stuck}d uncovered — widening to a {wide['dte']}-day expiry")
        label = "repair-cover" if underwater else "cover"
        _sell_call_row(client, s, row, wide, spot, label, dry_run)
        if row.option_symbol:  # sell went through
            del state[sym]
        return
    msg = f"{sym}: no sellable call for {days_stuck} days — selling shares to recycle capital"
    print(f"  🚨 {msg}")
    send_alert("Suna Desk — Dead Lot", msg)
    # Clear the clock only on a real fill — an unfilled exit must retry next
    # cycle, not restart the 5-day escalation wait.
    if not dry_run and _exit_lot(client, s, row, spot) is not None:
        del state[sym]


def _roll_window(now_utc: Optional[datetime] = None) -> bool:
    """True during Suna's roll window: Friday, midday ET onward.
    # ponytail: reuses trading_data._ET_TZ, a hardcoded UTC-4 — correct Mar-Nov,
    # an hour early in winter. One threshold on a name that's already >$1 ITM
    # doesn't justify a tz layer; revisit if a real intraday rule shows up.
    """
    et = (now_utc or datetime.now(timezone.utc)).astimezone(_ET_TZ)
    return et.weekday() == FRIDAY and et.hour >= ROLL_HOUR_ET


# ── Step 2: MANAGE (profit-close, Friday-afternoon ITM roll, repair) ──────────
def _manage(client, dry_run: bool = False):
    print("\n  [SUNA 2/5] Manage (profit-close / Fri ITM roll)...")
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
                    _log_option_fill(s, row.option_symbol, "buy", contracts, fill, "profit-close")
                    row.realized_pnl = (row.realized_pnl or 0) + (prem_in - fill * 100 * contracts)
                    row.option_symbol = None; row.option_type = None
                    row.strike = 0; row.expiry = None; row.premium_received = 0
                    s.commit()
                continue
            # Friday-afternoon roll: short call > $1 ITM → roll out-and-up, NET CREDIT only.
            try:
                q = get_quote(row.underlying); spot = q.get("last") or q.get("ask") or 0
            except Exception:
                spot = 0
            itm = spot and row.strike and spot - row.strike >= ROLL_ITM_DOLLARS
            if itm and _roll_window():
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
    _log_option_fill(s, row.option_symbol, "buy", contracts, close_fill, "roll-close")
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
        _log_option_fill(s, nxt["symbol"], "sell", contracts, fill, "roll-open")
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
    state = _load_uncovered()
    before = dict(state)
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
            min_strike = basis if not underwater else spot + _repair_gap(spot)
            snaps = _get_option_snapshots(row.underlying, opt_type="call", dte_min=SUNA_DTE_MIN)
            best = pick_weekly_call(snaps, spot, min_strike=min_strike)
            ok, why = premium_band_ok(best["premium"], spot) if best else (False, "")
            if not best or not ok:
                if not best:
                    tag = "repair strike" if underwater else f"strike ≥ basis ${basis:.2f}"
                    print(f"  ⚠️  {row.underlying}: no weekly call at {tag} — hold uncovered")
                else:
                    print(f"  ⏭  {row.underlying}: {why} — hold uncovered")
                _handle_dead_lot(client, s, row, spot, underwater, min_strike, snaps, state, dry_run)
                continue
            label = "repair-cover" if underwater else "cover"
            if underwater:
                print(f"  🩹 {row.underlying}: REPAIR — spot ${spot:.2f} < basis ${basis:.2f}, "
                      f"sell ${best['strike']:g} call (ladder up next week)")
            _sell_call_row(client, s, row, best, spot, label, dry_run)
            state.pop(row.underlying, None)  # covered — clear any escalation tracking
        s.commit()
    finally:
        s.close()
    if state != before:
        _save_uncovered(state)


def _sell_call_row(client, s, row, call, spot, label, dry_run):
    contracts = max(1, (row.shares_qty or 0) // 100)
    # Only the broker's share count makes a call "covered". Our DB can be ahead
    # of Alpaca (fill not landed) or behind it (already assigned away) — either
    # way the sell is rejected as uncovered, so check before burning two stages.
    if not dry_run:
        have = broker_shares(client, row.underlying)
        if have < 100 * contracts:
            print(f"  ⏭  {row.underlying}: broker shows {have}sh, need {100*contracts} "
                  f"— skipping {label}, sync will reconcile")
            return
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
        _log_option_fill(s, call["symbol"], "sell", contracts, fill, label)
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
        sector_counts = Counter(suna_sector(u) for u in held)
        live = _live_symbols(client)
        if live is None:
            print("  ⏭  can't see live account — skipping entries this cycle"); return

        avail = _book_available(open_rows)
        # Floor = cheapest permissible lot (movers price band starts at $10 → $1,000
        # per 100sh) + slippage headroom. Was $5k (half the position cap), which
        # parked up to $5k idle whenever the tail couldn't fund a full-size entry.
        if avail < 1_200:
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
            # Resolve price (most-actives rows lack it).
            price = cand.get("price")
            if not price:
                try:
                    q = get_quote(tkr); price = q.get("last") or q.get("ask") or 0
                except Exception:
                    price = 0
            if not price or price < 10:
                continue
            # Suna's stock-side screener (type/beta/short interest) — first network
            # call in the chain because it rejects the most: ~10% of the pool
            # survives it, so it saves the bars/earnings/chain calls below.
            profile = suna_profile(tkr)
            ok, why_stock = stock_filters_ok(profile)
            if not ok:
                print(f"  ⏭  {tkr}: {why_stock}")
                continue
            if not _gate("quality", *quality_ok(profile), tkr):
                continue
            # Per-sector cap, now on the REAL sector from the profile above rather
            # than v2's blue-chip dict (which resolved 95% of this pool to
            # "Unknown" and was skipped, letting all 8 slots pile into one sector).
            # Still skips Unknown — a shared bucket capped at 2 would throttle the
            # desk — but that bucket is now the yfinance gaps, not the whole pool.
            sector = suna_sector(tkr)
            if sector != "Unknown" and sector_counts[sector] >= CC_MAX_PER_SECTOR:
                print(f"  ⏭  {tkr}: {sector} already has {CC_MAX_PER_SECTOR} positions")
                continue
            sig = entry_signals(tkr)          # one bars call → rip + trend + rvol
            if sig.get("ripped"):
                print(f"  ⏭  {tkr}: already ripped this week — wait for pullback")
                continue
            if not _gate("trend", *trend_ok(sig), tkr):
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
            rvol = sig.get("rvol")
            print(f"  🛒 ENTER {tkr}: buy {lots*100}sh ~${price:.2f} (${cost:,.0f}), "
                  f"sell ${call['strike']:g} call {call['expiry']} "
                  f"prem=${call['premium']*100*lots:,.0f} ({why}; {why_stock}"
                  f"{f'; rvol {rvol:.1f}x' if rvol else ''}) [{sector}]")
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
            # The buy FILLED, but Alpaca's position book can lag the fill by a
            # beat — sell into that gap and the call reads as naked. Wait for the
            # shares to actually appear; _cover() re-covers next cycle if not.
            have = await_shares(client, tkr, 100 * lots)
            if have < 100 * lots:
                print(f"  ⏳ {tkr}: broker shows {have}sh of {100*lots} — "
                      f"deferring cover to next cycle")
                sector_counts[sector] += 1; avail -= cost; entered += 1
                continue
            b, a, m = _option_quote(call["symbol"])
            if m <= 0:
                b, a, m = call["bid"], call["ask"], call["premium"]
            fill = _two_stage_sell(client, call["symbol"], b, a, m, call["strike"],
                                   call["dte"], qty=lots, label="cover-on-entry")
            if fill is not None:
                _log_option_fill(s, call["symbol"], "sell", lots, fill, "enter")
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
        # A CSP is collateralised out of OPTIONS buying power — the only pool
        # Alpaca checks. _book_available() is book-notional capped by equity
        # `buying_power` (2-4x margin), so it happily reported five figures free
        # while the broker had ~$1.1k of actual collateral. Every CSP the wheel
        # has ever attempted was rejected for exactly this.
        opt_bp = csp_collateral()
        if assigned and opt_bp <= 0:
            print("  ⏭  no options buying power — skipping the wheel this cycle")
            return
        for row in assigned:
            try:
                q = get_quote(row.underlying); price = q.get("last") or q.get("ask") or 0
            except Exception:
                price = 0
            if not price:
                continue
            max_strike = csp_max_strike(price, free, opt_bp)
            if max_strike <= 0:
                print(f"  ⏭  {row.underlying}: ${opt_bp:,.0f} options buying power "
                      f"can't secure a single put — skip")
                continue
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
                _log_option_fill(s, put["symbol"], "sell", 1, fill, "csp")
                s.add(TradingCCPosition(
                    underlying=row.underlying, shares_qty=0, avg_cost=0,
                    option_symbol=put["symbol"], option_type="put",
                    strike=put["strike"], expiry=put["expiry"],
                    premium_received=fill * 100,
                    status="open", opened_at=datetime.now(timezone.utc).isoformat()))
                row.status = "wheeled"
                s.commit()
                # Both pools shrink: the book's notional AND the broker's actual
                # collateral. Missing the second let one cycle queue several CSPs
                # the account could only ever secure one of.
                free -= put["strike"] * 100
                opt_bp -= put["strike"] * 100 - fill * 100
                send_alert("Suna Desk — Wheel",
                           f"🎡 {row.underlying} sold ${put['strike']:g} CSP {put['expiry']} "
                           f"for ${fill*100:,.0f}")
        s.commit()
    finally:
        s.close()


def _check_stale_legs(market_open: bool):
    """After SYNC, flag any open row whose option leg's expiry is already past.
    SYNC only reconciles a leg once it drops out of Alpaca's book (expired-
    worthless or assigned) — if Alpaca hasn't processed that yet (e.g. a Monday
    assignment-processing lag), the row sits open with a stale expiry and SYNC's
    branch never fires. A leg that expired Friday is expected to look stale over
    the weekend, so only alert once the market's open (Alpaca should have caught
    up by then)."""
    if not market_open:
        return
    s = Session()
    try:
        stale = [r for r in _open_rows(s)
                if r.option_symbol and r.expiry and r.expiry < date.today().isoformat()]
    finally:
        s.close()
    if stale:
        syms = ", ".join(f"{r.underlying} ({r.expiry})" for r in stale)
        print(f"\n  ⚠️  Stale leg(s) past expiry, not reconciled by sync: {syms}")
        send_alert("Suna Desk — Stale Leg", f"⚠️ Not reconciled by sync: {syms}")


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
    market_open = is_market_open()
    _check_stale_legs(market_open)
    if not market_open:
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
    # Next Friday that's still >= SUNA_DTE_MIN out, so the live DTE filter in
    # _sellable() doesn't reject the fixture depending on what weekday the test runs.
    days_out = (4 - date.today().weekday()) % 7
    if days_out < SUNA_DTE_MIN:
        days_out += 7
    fri = date.today() + timedelta(days=days_out)
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

    # Suna's stock-side screener. Real profiles, captured from yfinance 2026-07-31.
    def prof(qt, beta, si, sector=None):
        return {"quote_type": qt, "beta": beta, "short_float": si, "sector": sector}

    good = prof("EQUITY", 1.94, 0.196, "Technology")          # SMCI — in both bands
    assert stock_filters_ok(good)[0] is True, "SMCI should pass"
    # Every leveraged/inverse product resolves ETF with null fundamentals — the
    # exact junk (AMZU/MSTU/NVD/KORU/LQD) that flooded the pool before this gate.
    assert stock_filters_ok(prof("ETF", None, None))[0] is False, "ETF must be rejected"
    assert stock_filters_ok({})[0] is False, "unresolvable symbol must fail CLOSED"
    # KO: beta 0.35 — the low-vol staple the beta floor exists to reject.
    passed, why_ko = stock_filters_ok(prof("EQUITY", 0.349, 0.0112, "Consumer Defensive"))
    assert passed is False and "beta" in why_ko, f"KO should fail on beta: {why_ko}"
    # SOFI beta 2.15 — just outside the stated band (Brian chose the stated 1-2).
    assert stock_filters_ok(prof("EQUITY", 2.149, 0.147))[0] is False, "beta ceiling not enforced"
    # HIMS SI 31.9% — above Suna's "avoid >30%" line, even though beta is fine.
    passed, why_hims = stock_filters_ok(prof("EQUITY", 1.80, 0.3194))
    assert passed is False and "short interest" in why_hims, f"HIMS SI: {why_hims}"
    # ONFO: beta ok, but SI 1.06% — no short pressure, no premium. Floor catches it.
    assert stock_filters_ok(prof("EQUITY", 2.0, 0.0106))[0] is False, "SI floor not enforced"
    # Band edges are inclusive on both ends.
    assert stock_filters_ok(prof("EQUITY", 1.0, 0.10))[0] is True, "lower edges must pass"
    assert stock_filters_ok(prof("EQUITY", 2.0, 0.30))[0] is True, "upper edges must pass"

    # Beta-from-bars fallback: covariance math, driven offline. A name that moves
    # exactly 1.5x SPY every day must come back as beta 1.5.
    # Build SPY as a walk and the stock as exactly 1.5x its daily return.
    # NOTE: patch via globals(), not `import scripts.trading_suna` — run as a
    # script this module is __main__, and the imported copy is a different object.
    spy_px, stk_px = [100.0], [50.0]
    for i in range(200):
        r = 0.01 if i % 3 else -0.008
        spy_px.append(spy_px[-1] * (1 + r))
        stk_px.append(stk_px[-1] * (1 + 1.5 * r))
    def _bars(sym, days=365, timeframe="1Day"):
        px = spy_px if sym == "SPY" else stk_px
        return [{"t": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}T00:00:00Z", "c": c}
                for i, c in enumerate(px)]
    g = globals()
    _real_bars = g["get_bars"]
    g["get_bars"] = _bars
    _spy_returns.cache_clear()
    try:
        b = beta_from_bars("FAKE")
        assert b is not None and abs(b - 1.5) < 0.02, f"beta-from-bars wrong: {b}"
        # Too little overlap → None (reject), never a bogus number.
        g["get_bars"] = lambda sym, days=365, timeframe="1Day": _bars(sym)[:50]
        _spy_returns.cache_clear()
        assert beta_from_bars("FAKE") is None, "short history must return None"
    finally:
        g["get_bars"] = _real_bars
        _spy_returns.cache_clear()

    # Put pick respects cash cap.
    pexp = exp
    puts = [_snap(f"HIMS{pexp}P{int(54*1000):08d}", -0.30, 0.93, 1.00),
            _snap(f"HIMS{pexp}P{int(58*1000):08d}", -0.45, 1.88, 1.95)]
    pput = pick_weekly_put(puts, max_strike=55.0)
    assert pput and pput["strike"] == 54, f"put cash cap failed: {pput}"

    # DTE window: a 30-DTE call is out of the weekly window.
    far = (date.today() + timedelta(days=30)).strftime("%y%m%d")
    assert _sellable(_snap(f"HIMS{far}C{int(58*1000):08d}", 0.45, 1.0, 1.1), "call") is None

    # Dead-lot DTE widening: a 12-DTE call sits outside the normal 3-9 weekly
    # window but inside the widened 14-day dead-lot retry window.
    wide_exp = (date.today() + timedelta(days=12)).strftime("%y%m%d")
    wide_snap = _snap(f"HIMS{wide_exp}C{int(59*1000):08d}", 0.40, 1.20, 1.30)
    assert pick_weekly_call([wide_snap], price=56.0, min_strike=56.0) is None, \
        "12-DTE call should be rejected by the default 3-9 DTE weekly window"
    assert pick_weekly_call([wide_snap], price=56.0, min_strike=56.0,
                            dte_max=DEAD_LOT_WIDE_DTE_MAX) is not None, \
        "dead-lot escalation (dte_max=14) should accept a 12-DTE call"

    # Repair-gap formula: 3% of spot, floored at $0.50, capped at $2.00.
    assert abs(_repair_gap(18.0) - 0.54) < 1e-9, "3% of $18 = $0.54"
    assert _repair_gap(5.0) == REPAIR_OTM_GAP_MIN, "below floor → floor"
    assert _repair_gap(200.0) == REPAIR_OTM_GAP_MAX, "above cap → cap"

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

    # ── Entry signals: SMA/rip/rvol math on stubbed bars (no network) ─────────
    def bars(closes, vols=None):
        vols = vols or [1_000_000] * len(closes)
        return [{"t": f"2026-01-{i%28+1:02d}", "c": c, "v": v}
                for i, (c, v) in enumerate(zip(closes, vols))]

    assert _sma([1, 2, 3, 4], 2) == 3.5
    assert _sma([1, 2], 50) is None, "not enough history → None, never a partial SMA"

    # 250 flat sessions at $10, then a close at $12: above both SMAs, and the
    # 5-TRADING-day rip test (closes[-6]) sees +20% → ripped.
    flat = [10.0] * 250 + [12.0]
    orig_get_bars = sys.modules[__name__].get_bars
    try:
        sys.modules[__name__].get_bars = lambda *a, **k: bars(flat)
        sig = entry_signals("STUB")
        assert sig["ripped"] is True, f"5-day rip not detected: {sig}"
        assert sig["above_50dma"] is True and sig["above_200dma"] is True
        assert trend_ok(sig)[0] is True

        # Below both averages → the trend gate rejects, and names both.
        sys.modules[__name__].get_bars = lambda *a, **k: bars([10.0] * 250 + [7.0])
        down = entry_signals("STUB2")
        ok, why = trend_ok(down)
        assert ok is False and "50DMA" in why and "200DMA" in why, why

        # Short history (recent IPO): no SMA → fail OPEN, don't judge on a rule
        # that needs 200 sessions.
        sys.modules[__name__].get_bars = lambda *a, **k: bars([10.0] * 20 + [11.0])
        short = entry_signals("STUB3")
        assert short["above_200dma"] is None
        assert trend_ok(short)[0] is True, "missing history must fail open"

        # rvol: 20 sessions at 1M, today 3M → 3.0x. Logged, never gated.
        sys.modules[__name__].get_bars = lambda *a, **k: bars(
            [10.0] * 21 + [10.1], [1_000_000] * 21 + [3_000_000])
        assert abs(entry_signals("STUB4")["rvol"] - 3.0) < 1e-9

        # Bars unavailable → {} , and every caller treats that as allow.
        def boom(*a, **k):
            raise RuntimeError("offline")
        sys.modules[__name__].get_bars = boom
        assert entry_signals("STUB5") == {}
        assert trend_ok({})[0] is True, "no signals must fail open"
    finally:
        sys.modules[__name__].get_bars = orig_get_bars

    # ── Shadow gates: log but do not reject; binding gates reject ─────────────
    assert _gate("trend", False, "below 200DMA", "X") is True, "shadowed gate must allow"
    assert _gate("nope", False, "some reason", "X") is False, "unshadowed gate must reject"
    assert _gate("trend", True, "fine", "X") is True

    # ── Junk filter (ours, not Suna's) — fails OPEN on missing data ───────────
    assert quality_ok({"market_cap": 18e9, "avg_volume": 50e6})[0] is True
    assert quality_ok({"market_cap": 100e6, "avg_volume": 50e6})[0] is False, "cap floor"
    assert quality_ok({"market_cap": 18e9, "avg_volume": 100_000})[0] is False, "volume floor"
    assert quality_ok({})[0] is True, "missing fundamentals must fail open"
    assert quality_ok({"market_cap": MIN_MARKET_CAP,
                       "avg_volume": MIN_AVG_VOLUME})[0] is True, "edges inclusive"

    # ── Roll window: Friday afternoon ET only ────────────────────────────────
    def utc(day, hour):   # 2026-08-03 is a Monday → +day gives the weekday
        return datetime(2026, 8, 3 + day, hour, tzinfo=timezone.utc)
    for day in range(7):
        for hour in (14, 20):          # 10am and 4pm ET
            want = (day == 4 and hour == 20)
            assert _roll_window(utc(day, hour)) is want, \
                f"roll window wrong for weekday {day} at {hour}:00 UTC"

    # ── CSP collateral: the bug that made the wheel 0-for-8 ──────────────────
    # Live failure reproduced: QCOM $165 put needed $16,190 of options buying
    # power against $1,166 available. The old code bounded the strike by
    # _book_available() (book notional, capped by 2-4x equity buying_power) and
    # never looked at the collateral pool Alpaca actually checks.
    assert csp_max_strike(price=170.0, book_free=40_000, opt_bp=1_166) == 11.66, \
        "collateral must bound the strike — this is the 0-for-8 wheel bug"
    # With real collateral, the per-position cap binds instead ($10k / 100).
    assert csp_max_strike(price=170.0, book_free=40_000, opt_bp=50_000) == 100.0
    # Spot binds when it's the smallest — never agree to buy above the market.
    assert csp_max_strike(price=42.0, book_free=40_000, opt_bp=50_000) == 42.0
    # Book notional still binds when it's tightest.
    assert csp_max_strike(price=170.0, book_free=3_000, opt_bp=50_000) == 30.0
    # No collateral (or an unreadable account → 0.0) → no put, not a doomed order.
    assert csp_max_strike(price=170.0, book_free=40_000, opt_bp=0) == 0.0
    assert csp_max_strike(price=170.0, book_free=-5_000, opt_bp=50_000) == 0.0

    # ── Sector cap uses the real sector, not v2's blue-chip dict ─────────────
    suna_profile.cache_clear()
    _orig_profile = sys.modules[__name__].suna_profile
    try:
        sys.modules[__name__].suna_profile = lambda s: (
            {"sector": "Consumer Cyclical"} if s == "GME" else {})
        assert suna_sector("GME") == "Consumer Cyclical"
        assert suna_sector("NOSECTOR") == "Unknown", "missing sector → Unknown, not a crash"
    finally:
        sys.modules[__name__].suna_profile = _orig_profile
        suna_profile.cache_clear()

    # ── Covered-call coverage: the other 13 rejections ───────────────────────
    class _Pos:
        def __init__(self, qty): self.qty = qty

    class _StubClient:
        def __init__(self, qty): self._qty = qty
        def get_open_position(self, sym):
            if self._qty is None:
                raise RuntimeError("position does not exist")
            return _Pos(str(self._qty))

    assert broker_shares(_StubClient(300), "X") == 300
    assert broker_shares(_StubClient(None), "X") == 0, "no position → 0, never a crash"
    # await_shares returns immediately once the count is there (no sleep in test).
    assert await_shares(_StubClient(200), "X", want=200, timeout=0) == 200
    assert await_shares(_StubClient(0), "X", want=200, timeout=0) == 0

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
