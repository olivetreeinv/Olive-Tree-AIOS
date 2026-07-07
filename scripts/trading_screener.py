#!/usr/bin/env python3
"""
trading_screener.py — CSP/CC candidate screener for the Olive Tree Trading Desk
Premium Desk v2.

Ranks a curated liquid-optionable universe by IV richness, after filtering on
price band, option-spread quality, and upcoming earnings. Feeds the CSP-first
entry step in trading_covered_calls.py. Pure rules, no LLM call — except the
optional --ai event-screen pass, which is Claude Haiku flagging known binary
catalysts (FDA/litigation/M&A/guidance) the earnings-date filter can't see.

Self-contained by design: does NOT import trading_data.py (that module is
being modified in parallel elsewhere) — pulls stock bars and option snapshots
directly from the Alpaca REST API with its own small HTTP helpers.

Usage:
  python3 scripts/trading_screener.py            # ranked table
  python3 scripts/trading_screener.py --json     # machine-readable
  python3 scripts/trading_screener.py --ai        # + Claude event-screen pass
  python3 scripts/trading_screener.py --test      # self-check (no network)
"""

import argparse
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, stdev
from typing import Optional

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).parent.parent))
from db.connection import Session
from db.schema import TradingIVHistory

try:
    import yfinance as yf
except ImportError:
    yf = None  # graceful fallback — earnings filter treats every candidate as unknown → SKIP

# ── Candidate universe ────────────────────────────────────────────────────────
# ~38 liquid, weeklies-listed names, no meme/biotech binaries. Includes the
# legacy CC_UNIVERSE tickers plus additional sector coverage so the "max 2 per
# sector" rule in trading_covered_calls.py has real breadth to pick from.
SECTOR = {
    "AAPL": "Technology", "MSFT": "Technology", "NVDA": "Technology", "AMD": "Technology",
    "CSCO": "Technology", "INTC": "Technology", "ORCL": "Technology", "QCOM": "Technology",
    "HPQ": "Technology", "NOK": "Technology",
    "GOOGL": "Communication Services", "VZ": "Communication Services", "T": "Communication Services",
    "CMCSA": "Communication Services", "SIRI": "Communication Services", "VOD": "Communication Services",
    "AMZN": "Consumer Discretionary", "F": "Consumer Discretionary", "GM": "Consumer Discretionary",
    "CCL": "Consumer Discretionary", "NCLH": "Consumer Discretionary", "DAL": "Consumer Discretionary",
    "UAL": "Consumer Discretionary",
    "KO": "Consumer Staples", "WMT": "Consumer Staples", "KHC": "Consumer Staples",
    "MO": "Consumer Staples", "PM": "Consumer Staples",
    "XOM": "Energy", "CVX": "Energy", "OXY": "Energy", "SLB": "Energy", "KMI": "Energy", "MRO": "Energy",
    "JPM": "Financials", "BAC": "Financials", "WFC": "Financials", "C": "Financials",
    "PFE": "Healthcare", "MRK": "Healthcare",
}
CANDIDATE_UNIVERSE = list(SECTOR.keys())

# ── Screen constants ──────────────────────────────────────────────────────────
SCR_PRICE_MIN      = 10.0
SCR_PRICE_MAX      = 100.0
SCR_MAX_SPREAD_PCT = 0.10     # option bid/ask spread as % of mid
SCR_EARNINGS_BUFFER_DAYS = 2  # chosen expiry must end >= this many days BEFORE earnings
SCR_DTE_FLOOR      = 14       # shortest expiry we'll sell to duck under earnings
SCR_EARNINGS_CYCLE_DAYS = 85  # ponytail: quarterly estimate when only a past date is known
SCR_IV_HISTORY_MIN_DAYS  = 60 # stored days needed before switching to true IV-rank mode
SCR_IV_RANK_LOW, SCR_IV_RANK_HIGH = 40, 70   # true-rank gate band
SCR_BOOTSTRAP_RATIO_MIN  = 1.1 # ATM IV / 20d realized vol must clear this in bootstrap mode
SCR_BOOTSTRAP_IV_MIN     = 0.25

DEFAULT_MODEL = "claude-haiku-4-5-20251001"

# ── Minimal Alpaca REST helpers (self-contained — no trading_data.py import) ──
_ALPACA_DATA = "https://data.alpaca.markets"
_SSL = ssl.create_default_context()
try:
    import certifi
    _SSL.load_verify_locations(cafile=certifi.where())
except Exception:
    pass


def _alpaca_headers() -> dict:
    key    = os.getenv("ALPACA_API_KEY", "")
    secret = os.getenv("ALPACA_SECRET_KEY", "")
    if not key or not secret:
        raise EnvironmentError("ALPACA_API_KEY / ALPACA_SECRET_KEY not set in .env")
    return {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret, "Accept": "application/json"}


def _http_get(url: str, headers: dict) -> dict:
    req = urllib.request.Request(url, headers=headers)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, context=_SSL, timeout=15) as r:
                return json.loads(r.read())
        except (urllib.error.URLError, TimeoutError):
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))


def _stock_closes(symbol: str, days: int = 25) -> list[float]:
    """Recent daily closes from Alpaca stock bars (feed from ALPACA_DATA_FEED, default sip)."""
    feed  = os.getenv("ALPACA_DATA_FEED", "sip")
    end   = datetime.now(timezone.utc).date()
    start = end - timedelta(days=days + 15)  # buffer for weekends/holidays
    url = (f"{_ALPACA_DATA}/v2/stocks/{symbol}/bars"
           f"?timeframe=1Day&start={start}&end={end}&feed={feed}&limit={days + 15}")
    try:
        data = _http_get(url, _alpaca_headers())
        return [b["c"] for b in (data.get("bars") or [])]
    except Exception as e:
        print(f"  ⚠️  bars fetch failed for {symbol}: {e}")
        return []


def _stock_quote(symbol: str) -> float:
    try:
        data = _http_get(f"{_ALPACA_DATA}/v2/stocks/{symbol}/quotes/latest?feed="
                         f"{os.getenv('ALPACA_DATA_FEED', 'sip')}", _alpaca_headers())
        q = data.get("quote", {})
        bid, ask = float(q.get("bp", 0) or 0), float(q.get("ap", 0) or 0)
        return (bid + ask) / 2 if (bid or ask) else 0.0
    except Exception:
        return 0.0


def _parse_occ(sym: str) -> Optional[tuple[str, str, float]]:
    """OCC symbol → (type, expiry_iso, strike). Same scheme as trading_covered_calls._parse_occ."""
    try:
        strike = int(sym[-8:]) / 1000.0
        opt_type = {"C": "call", "P": "put"}[sym[-9]]
        expiry = datetime.strptime(sym[-15:-9], "%y%m%d").date().isoformat()
        return opt_type, expiry, strike
    except Exception:
        return None


def _dte(expiry_str: str) -> int:
    try:
        return (date.fromisoformat(expiry_str) - date.today()).days
    except Exception:
        return -1


def _get_option_snapshots(underlying: str, dte_min: int, dte_max: int,
                          opt_type: str = "call") -> list[dict]:
    """Option snapshots (greeks + IV + quotes) in a DTE window. [] on error."""
    today = date.today()
    base = (
        f"{_ALPACA_DATA}/v1beta1/options/snapshots/{underlying}"
        f"?feed=opra&limit=1000&type={opt_type}"
        f"&expiration_date_gte={today + timedelta(days=dte_min)}"
        f"&expiration_date_lte={today + timedelta(days=dte_max)}"
    )
    out, token, page = [], None, 0
    while page < 5:
        url = base + (f"&page_token={token}" if token else "")
        try:
            data = _http_get(url, _alpaca_headers())
        except Exception as e:
            print(f"  ⚠️  option snapshots failed for {underlying}: {e}")
            break
        for sym, snap in (data.get("snapshots") or {}).items():
            out.append({"symbol": sym, **snap})
        token = data.get("next_page_token")
        page += 1
        if not token:
            break
    return out


def _atm_contract(snaps: list[dict], spot: float, dte_min: int, dte_max: int,
                  max_expiry: Optional[date] = None) -> Optional[dict]:
    """Pick the nearest-the-money contract from the LONGEST expiry inside the DTE
    window that also ends on/before max_expiry (the pre-earnings cutoff). When
    earnings don't interfere, longest-expiry preference lands 30-45 DTE as before.
    Returns dict(symbol, strike, expiry, dte, iv, bid, ask, mid) or None."""
    cands = []
    for snap in snaps:
        parsed = _parse_occ(snap.get("symbol", ""))
        if not parsed:
            continue
        _, exp_str, strike = parsed
        dte = _dte(exp_str)
        if not (dte_min <= dte <= dte_max):
            continue
        if max_expiry and date.fromisoformat(exp_str) > max_expiry:
            continue  # expiry would cross earnings — sell the shorter one instead
        iv = snap.get("impliedVolatility")
        if iv is None:
            iv = (snap.get("greeks") or {}).get("impliedVolatility")
        if not iv or iv <= 0:
            continue
        quote = snap.get("latestQuote", {}) or {}
        bid, ask = float(quote.get("bp", 0) or 0), float(quote.get("ap", 0) or 0)
        mid = (bid + ask) / 2 if (bid or ask) else 0
        if mid <= 0 or strike <= 0:
            continue
        cands.append({"symbol": snap["symbol"], "strike": strike, "expiry": exp_str, "dte": dte,
                      "iv": float(iv), "bid": bid, "ask": ask, "mid": mid})
    if not cands:
        return None
    longest = max(c["expiry"] for c in cands)
    return min((c for c in cands if c["expiry"] == longest),
               key=lambda c: abs(c["strike"] - spot))


# ── Pure filter functions (network-free, self-check driven) ──────────────────
def price_ok(price: float, lo: float = SCR_PRICE_MIN, hi: float = SCR_PRICE_MAX) -> bool:
    return lo <= price <= hi


def spread_ok(bid: float, ask: float, max_pct: float = SCR_MAX_SPREAD_PCT) -> bool:
    mid = (bid + ask) / 2
    if mid <= 0:
        return False
    return (ask - bid) / mid <= max_pct


def next_earnings_from(dates: list[date], today: Optional[date] = None) -> Optional[date]:
    """Resolve 'next earnings' from a mixed past/future date list.
    Future dates win (earliest). Only past dates known → estimate last + 85 days.
    # ponytail: 85d quarterly-cycle guess, conservative early; replace with a real
    # calendar source if the estimate proves too loose."""
    today = today or date.today()
    future = [d for d in dates if d >= today]
    if future:
        return min(future)
    if dates:
        return max(dates) + timedelta(days=SCR_EARNINGS_CYCLE_DAYS)
    return None


def earnings_max_expiry(earnings_dt: Optional[date],
                        buffer_days: int = SCR_EARNINGS_BUFFER_DAYS) -> Optional[date]:
    """Latest expiry we'll sell given an earnings date: earnings - buffer. None = unknown."""
    return earnings_dt - timedelta(days=buffer_days) if earnings_dt else None


def realized_vol_annualized(closes: list[float]) -> float:
    """Annualized stdev of daily log returns over the given closes (~20d window)."""
    if len(closes) < 5:
        return 0.0
    import math
    rets = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes)) if closes[i - 1] > 0]
    if len(rets) < 4:
        return 0.0
    return stdev(rets) * (252 ** 0.5)


def iv_rank(atm_iv: float, history: list[float]) -> float:
    """0–100 percentile rank of atm_iv within the stored history (inclusive)."""
    if not history:
        return 50.0
    below = sum(1 for h in history if h <= atm_iv)
    return 100.0 * below / len(history)


def passes_iv_gate(atm_iv: float, history: list[float], realized_vol: float,
                   min_days: int = SCR_IV_HISTORY_MIN_DAYS) -> tuple[bool, str, float]:
    """
    Two-mode IV richness gate:
      - "rank" mode (>= min_days stored history): true IV rank must land in [40, 70].
      - "bootstrap" mode (< min_days history): ATM IV / 20d realized vol >= 1.1 AND
        ATM IV >= 25% annualized (no year of history yet to compute a real rank).
    Returns (passed, mode, metric).
    """
    if len(history) >= min_days:
        rank = iv_rank(atm_iv, history)
        return (SCR_IV_RANK_LOW <= rank <= SCR_IV_RANK_HIGH), "rank", rank
    if realized_vol <= 0:
        return False, "bootstrap", 0.0
    ratio = atm_iv / realized_vol
    passed = ratio >= SCR_BOOTSTRAP_RATIO_MIN and atm_iv >= SCR_BOOTSTRAP_IV_MIN
    return passed, "bootstrap", ratio


# ── DB helpers: daily ATM-IV history ──────────────────────────────────────────
def store_iv(symbol: str, atm_iv: float, day: Optional[str] = None):
    """Upsert today's ATM IV for symbol (unique on symbol+date)."""
    day = day or date.today().isoformat()
    s = Session()
    try:
        row = s.query(TradingIVHistory).filter_by(symbol=symbol, date=day).first()
        if row:
            row.atm_iv = atm_iv
        else:
            s.add(TradingIVHistory(symbol=symbol, date=day, atm_iv=atm_iv,
                                   created_at=datetime.now(timezone.utc).isoformat()))
        s.commit()
    finally:
        s.close()


def iv_history(symbol: str) -> list[float]:
    """All stored ATM-IV values for a symbol, oldest first."""
    s = Session()
    try:
        rows = (s.query(TradingIVHistory).filter_by(symbol=symbol)
                .order_by(TradingIVHistory.date.asc()).all())
        return [r.atm_iv for r in rows if r.atm_iv is not None]
    finally:
        s.close()


# ── Earnings lookup (yfinance, graceful fallback) ─────────────────────────────
def get_next_earnings(symbol: str) -> Optional[date]:
    """Next earnings date (future-filtered; past-only data → +85d estimate via
    next_earnings_from). None if unavailable/unknown (fail-safe → SKIP)."""
    if yf is None:
        print(f"  ⚠️  yfinance not installed — {symbol} earnings unknown, will SKIP")
        return None
    try:
        tk = yf.Ticker(symbol)
        try:
            df = tk.get_earnings_dates(limit=12)
            if df is not None and not df.empty:
                nxt = next_earnings_from([d.date() for d in df.index])
                if nxt:
                    return nxt
        except Exception:
            pass
        cal = tk.calendar
        if isinstance(cal, dict):
            dates = [d if isinstance(d, date) and not isinstance(d, datetime) else d.date()
                     for d in (cal.get("Earnings Date") or []) if d]
            return next_earnings_from(dates)
    except Exception as e:
        print(f"  ⚠️  earnings lookup failed for {symbol}: {e}")
    return None


# ── AI event-screen (Claude Haiku, opt-in) ────────────────────────────────────
def ai_event_screen(candidates: list[dict]) -> list[dict]:
    """
    Ask Claude Haiku to flag candidates with known pending binary events (FDA,
    litigation, guidance, M&A) the mechanical filters can't see. Returns the
    candidate list minus flagged names. On any API error, returns candidates
    unchanged with a logged warning — never blocks the screener.
    """
    if not candidates:
        return candidates
    try:
        import anthropic
    except ImportError:
        print("  ⚠️  anthropic package not installed — skipping AI event-screen")
        return candidates

    names = ", ".join(f"{c['symbol']} ({c.get('sector', '?')})" for c in candidates)
    prompt = f"""You are screening cash-secured-put candidates for a wheel-strategy options desk.
Candidates: {names}

Flag ONLY names with a KNOWN pending binary event in the next ~6 weeks — FDA decision,
major litigation ruling, M&A/activist situation, or a guidance event materially bigger
than a routine earnings print. Do not flag names just for normal earnings season.

Return ONLY valid JSON, no prose, no markdown fences:
[{{"symbol":"XXX","reason":"one line"}}]
Return [] if nothing qualifies."""

    try:
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
        msg = client.messages.create(
            model=DEFAULT_MODEL, max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
            if raw.endswith("```"):
                raw = raw.rsplit("```", 1)[0]
            raw = raw.strip()
        flags = json.loads(raw)
        flagged = {f["symbol"]: f.get("reason", "") for f in flags if isinstance(f, dict) and f.get("symbol")}
        if flagged:
            for sym, reason in flagged.items():
                print(f"  🚩 AI event-screen flagged {sym}: {reason}")
        return [c for c in candidates if c["symbol"] not in flagged]
    except Exception as e:
        print(f"  ⚠️  AI event-screen failed ({e}) — passing candidates through unflagged")
        return candidates


# ── Main screen ────────────────────────────────────────────────────────────────
def screen_candidates(dte_min: int = 30, dte_max: int = 45, ai: bool = False,
                      universe: Optional[list[str]] = None) -> list[dict]:
    """
    Ranked (richest IV first) candidate list: symbol, price, atm_iv, iv_metric,
    iv_mode, earnings_date, sector. Filters: price band → earnings-aware expiry
    selection (longest expiry ending >= 2d before earnings, floor SCR_DTE_FLOOR)
    → spread → IV gate. dte_min is the PREFERRED window floor; expiries down to
    SCR_DTE_FLOOR are used only to duck under an earnings date.
    """
    universe = universe or CANDIDATE_UNIVERSE
    out = []
    for symbol in universe:
        price = _stock_quote(symbol)
        if not price_ok(price):
            continue
        earn = get_next_earnings(symbol)
        if earn is None:
            print(f"  ⏭  {symbol}: earnings unknown — skip (fail-safe)")
            continue
        max_exp = earnings_max_expiry(earn)
        snaps = _get_option_snapshots(symbol, SCR_DTE_FLOOR, dte_max, opt_type="call")
        atm = _atm_contract(snaps, price, SCR_DTE_FLOOR, dte_max, max_expiry=max_exp)
        if not atm:
            print(f"  ⏭  {symbol}: no expiry >= {SCR_DTE_FLOOR} DTE clears earnings {earn} — skip")
            continue
        if not spread_ok(atm["bid"], atm["ask"]):
            print(f"  ⏭  {symbol}: spread {(atm['ask'] - atm['bid']) / atm['mid']:.0%} of mid > "
                  f"{SCR_MAX_SPREAD_PCT:.0%} cap — skip")
            continue
        store_iv(symbol, atm["iv"])
        hist = iv_history(symbol)
        rv = realized_vol_annualized(_stock_closes(symbol))
        passed, mode, metric = passes_iv_gate(atm["iv"], hist, rv)
        if not passed:
            print(f"  ⏭  {symbol}: IV gate failed ({mode}={metric:.2f}, ATM IV {atm['iv']:.0%}) — skip")
            continue
        out.append({
            "symbol": symbol, "price": round(price, 2), "atm_iv": round(atm["iv"], 4),
            "iv_metric": round(metric, 2), "iv_mode": mode,
            "earnings_date": earn.isoformat() if earn else None,
            "expiry": atm["expiry"], "dte": atm["dte"],
            "sector": SECTOR.get(symbol, "Unknown"),
        })
    out.sort(key=lambda c: c["atm_iv"], reverse=True)
    if ai:
        out = ai_event_screen(out)
    return out


# ── Self-check ─────────────────────────────────────────────────────────────────
def _self_check():
    """Pure-function tests: price/spread/earnings filters + both IV-gate modes."""
    print("── Screener self-check ─────────────────────────────────────────────\n")

    assert price_ok(50.0) and not price_ok(9.99) and not price_ok(100.01)
    print("  ✅ price band: $10-$100 inclusive")

    assert spread_ok(1.00, 1.05)          # 5% spread, passes
    assert not spread_ok(1.00, 1.30)      # ~26% spread, fails
    assert not spread_ok(0.0, 0.0)        # no quote → fail
    print("  ✅ spread filter: <=10% of mid passes, wide spread fails")

    # Earnings resolution: future dates win; past-only → last + 85d estimate; empty → None
    today = date(2026, 7, 7)
    assert next_earnings_from([date(2026, 5, 12), date(2026, 8, 5)], today) == date(2026, 8, 5), \
        "future date must win over a past one"
    est = next_earnings_from([date(2026, 2, 10), date(2026, 5, 12)], today)
    assert est == date(2026, 5, 12) + timedelta(days=85), f"past-only → last+85d estimate, got {est}"
    assert next_earnings_from([], today) is None, "no dates → None (fail-safe skip)"
    assert earnings_max_expiry(date(2026, 8, 5)) == date(2026, 8, 3), "cutoff = earnings - 2d"
    assert earnings_max_expiry(None) is None
    print("  ✅ earnings resolution: future-filtered, past-only → +85d estimate, cutoff = earnings-2d")

    # Longest-clearing-expiry selection + 14-DTE floor
    def occ(days_out: int, strike: float) -> str:
        return f"AAPL{(date.today() + timedelta(days=days_out)).strftime('%y%m%d')}C{int(strike*1000):08d}"
    def snap(days_out: int, strike: float, iv: float = 0.30) -> dict:
        return {"symbol": occ(days_out, strike), "impliedVolatility": iv,
                "latestQuote": {"bp": 1.0, "ap": 1.05}}
    snaps = [snap(21, 50), snap(35, 50), snap(42, 50), snap(35, 55)]
    # No earnings constraint → longest expiry (42d) wins
    atm = _atm_contract(snaps, spot=50.0, dte_min=SCR_DTE_FLOOR, dte_max=45)
    assert atm and atm["dte"] == 42, f"longest expiry should win unconstrained: {atm}"
    # Earnings at 30d out → cutoff 28d → only the 21-DTE expiry clears
    atm = _atm_contract(snaps, spot=50.0, dte_min=SCR_DTE_FLOOR, dte_max=45,
                        max_expiry=date.today() + timedelta(days=28))
    assert atm and atm["dte"] == 21, f"pre-earnings expiry should be chosen: {atm}"
    # ATM preference inside the chosen expiry: $50 beats $55 at spot 50
    atm2 = _atm_contract(snaps, spot=50.0, dte_min=SCR_DTE_FLOOR, dte_max=45)
    assert atm2 and atm2["strike"] == 50, f"nearest-the-money should win within expiry: {atm2}"
    # Earnings at 10d out → cutoff 8d < 14-DTE floor → nothing clears → None (skip name)
    atm = _atm_contract(snaps, spot=50.0, dte_min=SCR_DTE_FLOOR, dte_max=45,
                        max_expiry=date.today() + timedelta(days=8))
    assert atm is None, "no expiry >= 14 DTE clears earnings → skip"
    print("  ✅ expiry selection: longest clearing expiry wins, ducks under earnings, 14-DTE floor skips")

    # Bootstrap mode: <60 stored days, need IV/RV >= 1.1 and IV >= 25%
    passed, mode, ratio = passes_iv_gate(atm_iv=0.32, history=[], realized_vol=0.25)
    assert mode == "bootstrap" and passed, f"32% IV vs 25% RV should pass bootstrap: {ratio}"
    passed2, _, _ = passes_iv_gate(atm_iv=0.20, history=[], realized_vol=0.25)
    assert not passed2, "IV below the 25% floor must fail bootstrap even if ratio is high"
    passed3, _, _ = passes_iv_gate(atm_iv=0.26, history=[], realized_vol=0.25)
    assert not passed3, "ratio 1.04 < 1.1 must fail bootstrap"
    print("  ✅ bootstrap mode: IV/RV>=1.1 AND IV>=25% required")

    # Rank mode: >=60 stored days, need rank in [40,70]
    history = [0.20 + 0.01 * i for i in range(70)]  # 0.20..0.89, uniform
    mid_iv = history[27]   # ~rank 40
    rich_iv = history[5]   # low rank (~7%) — too cheap, gate should reject
    passed_r, mode_r, rank_r = passes_iv_gate(mid_iv, history, realized_vol=0.30)
    assert mode_r == "rank" and passed_r, f"rank {rank_r} should land in [40,70]"
    passed_low, _, rank_low = passes_iv_gate(rich_iv, history, realized_vol=0.30)
    assert not passed_low, f"low rank {rank_low} should fail the [40,70] gate"
    print(f"  ✅ rank mode (60+ days): rank {rank_r:.0f} passes, rank {rank_low:.0f} rejected")

    assert iv_rank(0.50, []) == 50.0, "empty history → neutral 50 rank"
    print("  ✅ iv_rank: empty history → neutral 50")

    print("\n  All screener self-checks passed. ✅")


# ── CLI ────────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="CSP/CC candidate screener — Olive Tree Trading Desk")
    ap.add_argument("--json", action="store_true", help="Print JSON instead of a table")
    ap.add_argument("--ai",   action="store_true", help="Run the Claude event-screen pass")
    ap.add_argument("--dte-min", type=int, default=30)
    ap.add_argument("--dte-max", type=int, default=45)
    ap.add_argument("--test", action="store_true", help="Run self-check (no network)")
    args = ap.parse_args()

    if args.test:
        _self_check()
        return

    candidates = screen_candidates(args.dte_min, args.dte_max, ai=args.ai)
    if args.json:
        print(json.dumps(candidates, indent=2))
        return

    print(f"\n── Screened Candidates (richest IV first, {len(candidates)} passed) ──────────")
    if not candidates:
        print("  No candidates cleared price/spread/earnings/IV filters.")
    for c in candidates:
        print(f"  {c['symbol']:6s} ${c['price']:>7.2f}  ATM IV {c['atm_iv']:.1%}  "
              f"{c['iv_mode']:>9s}={c['iv_metric']:.2f}  exp={c['expiry']} ({c['dte']}d)  "
              f"earnings={c['earnings_date'] or 'unknown'}  {c['sector']}")


if __name__ == "__main__":
    main()
