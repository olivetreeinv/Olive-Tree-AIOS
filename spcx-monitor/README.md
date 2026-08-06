# SPCX IPO-Day Monitor

Real-time exhaustion/top monitor for **SPCX** (Nasdaq, IPO ref **$135**).
**Alert-only — no order routing, no auto-trading.**

Live candle chart + signal banner in the browser, audible + SMS alerts, every
tick logged to SQLite, and a replay mode that scores how accurate the signals
actually were.

## Modes (auto-detected at startup)

| Mode | Data | Signals |
|---|---|---|
| **FULL** | Polygon trades/NBBO **+** Databento TotalView-ITCH L2/L3 depth | candle exhaustion + book pressure, blended composite (0.6 / 0.4) |
| **DEGRADED** | Polygon trades/NBBO only | candle exhaustion only — composite **is** the candle score (an empty book never dilutes it) |

Startup probes Databento for a live MBO snapshot (10s timeout). No license /
no key / no records → DEGRADED, with a persistent **"BOOK BLIND — watch Nasdaq
BookViewer manually"** banner in the UI. The active mode is shown in the
header and tagged on every logged signal.

## Quick start

```bash
cd spcx-monitor
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt        # databento is only needed for FULL mode
cp .env.example .env                   # fill in keys
python -m spcx.server                  # http://127.0.0.1:8765
```

Click **sound on** in the header once — browsers require a user gesture before
audio can play.

## Setup before the open (in order of lead time, costs flagged)

1. **Databento TotalView-ITCH license** (slowest — start first; license approval
   can take days): <https://databento.com/datasets/XNAS.ITCH>. Live ITCH is
   usage/subscription billed — check pricing before committing. *Optional: skip
   it and run DEGRADED.*
2. **Polygon real-time stocks plan** (instant, ~$199/mo tier for real-time;
   the free/starter tiers are delayed and won't cut it on IPO day):
   <https://polygon.io/pricing>
3. **BookViewer fallback** ($15/mo, instant) — manual depth view for DEGRADED
   mode: <https://www.nasdaq.com/solutions/data/equities/nasdaq-bookviewer>
4. **Twilio SMS** (instant, ~$0.0079/msg + number rental): <https://www.twilio.com>

## Signals

All scores are 0–1. Every fire is logged to SQLite with ts, price, mode, and
the raw component inputs.

- **Candle exhaustion** (always on, computed on closed 10s candles after a
  20-candle warmup): RSI(14) > 70 cross-down, 1-min ROC momentum rollover,
  lower-high after a ≥2% run, fading volume on up-candles.
- **Book pressure** (FULL only, computed 1×/sec from top-10 depth): bid/ask
  depth imbalance, ask wall within +1% of last (vs median level size), ask
  thinning (run) vs thickening (cap) over a 30s window.
- **Composite**: FULL = `0.6·candle + 0.4·book`; DEGRADED = candle only.

Candle components persist as a decayed max over the last ~70s of closes, so an
RSI cross-down, a lower high, and a volume fade that happen within a minute of
each other stack instead of blinking past each other one candle at a time.

**Alerts** (banner + beep + SMS, deduped): composite ≥ 0.65 (120s cooldown) and
%-gain milestones off $135 (+10/20/30/50/75/100, each fires once). Candle/book
threshold crossings are logged and shown in the feed but don't SMS.

## Replay / eval

Everything is recorded live: trades, NBBO quotes, 1 Hz top-10 book snapshots
(FULL only), and signal fires — all tagged with the session mode.

```bash
python -m spcx.replay --db data/spcx.db [--forward 60] [--drop 1.5]
```

Replay re-runs the *identical* signal code (`spcx/signals.py` is shared) over
the recorded ticks and scores each signal **separately** (candle / book /
composite) against realized local maxima:

- **peak** — candle high that's the max of its ±3-candle neighborhood and drops
  ≥ `--drop`% within `--forward` seconds.
- **precision** — fires where price actually fell ≥ `--drop`% from the *fire
  price* within `--forward` seconds (the alert was worth acting on).
- **recall** — peaks that had a fire within ±`--forward` seconds.
- **mean lead** — peak ts − fire ts; *negative* lead means the signal confirmed
  just after the top, which is normal for exhaustion-style signals.

Book eval runs only on FULL-mode sessions; on DEGRADED sessions it prints a
skip note instead of fake zeros.

Use one DB file per session (`SPCX_DB=data/spcx_YYYYMMDD.db`) to keep replays
clean.

## Notes / lean choices

- Raw ITCH messages aren't persisted — the book is recorded as 1 Hz top-10
  snapshots, which is what the signal consumes. Trades/quotes are stored in
  full, batched to SQLite (WAL) once a second.
- Databento callbacks run on its own thread against a lock-guarded book — no
  per-message event-loop hops at ITCH rates.
- Polygon feed reconnects forever with backoff; the UI auto-reconnects too.
- If SPCX's ticker isn't live in ITCH symbology until the open, the probe will
  fail at pre-market startup → restart the server near the open to re-probe,
  or just run DEGRADED.
