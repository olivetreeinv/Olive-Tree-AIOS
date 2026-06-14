---
name: ipo-watch
description: Live IPO/stock-day monitoring with the spcx-monitor app — start the recorder for any ticker, arm the first-trade tripwire, and run the 5-minute judgment loop that texts Brian plain-English sell signals. Trigger on "/ipo-watch [TICKER] [ref price]", "watch the IPO", "monitor [ticker] today", "start the stock watch".
---

# IPO Watch Skill — Olive Tree Investments

Drives the **spcx-monitor** app (`spcx-monitor/` in the AIOS root) for live IPO-day
or event-day monitoring. Alert-only, no trading. Built and battle-tested on the
SPCX IPO (2026-06-12).

## Architecture (two independent layers)

1. **The app** — launchd service `com.olivetree.spcx-monitor`, survives crashes and
   reboots. Records every tick to SQLite, computes exhaustion signals, auto-texts
   threshold + milestone alerts via iMessage. Works with zero Claude involvement.
   Dashboard: http://127.0.0.1:8765 (status JSON at `/status`).
2. **The judgment loop** — Claude reads the tape every ~5 min via `/loop` (dynamic),
   judges if the top is in, texts plain-English verdicts. Requires laptop on +
   session open. The app's auto-alerts are the safety net when the loop is paused.

## Start a watch (any ticker)

1. Edit `~/Library/LaunchAgents/com.olivetree.spcx-monitor.plist` env vars:
   `SPCX_SYMBOL`, `IPO_REF_PRICE`, and a fresh `SPCX_DB` (`data/<ticker>_<date>.db`).
2. `launchctl unload <plist> && launchctl load <plist>`; confirm
   `curl -s http://127.0.0.1:8765/status` shows `"feed": "real-time trades"`.
3. Arm the first-trade tripwire (background Bash):
   `until [ "$(sqlite3 data/<db> 'SELECT COUNT(*) FROM trades' 2>/dev/null || echo 0)" -gt 0 ]; do sleep 5; done; echo FIRST TRADES`
4. Start the dynamic loop (no interval — self-paced): pre-open sleep long, then
   5-min reads (270s, keeps prompt cache warm) for the first 2 hours of trading,
   then 15-min until 16:00 ET.

## Each loop tick

- Tape: `cd spcx-monitor && python3 watch.py data/<db>`
- Exit signal: `gws gmail users messages list --params '{"userId": "me", "q": "subject:SOLD newer_than:1d", "maxResults": 3}'`
  — Brian emails himself "SOLD" from his phone to stand down the watch.
- Text verdicts via `osascript` iMessage to +14046432356. Plain English, NO
  jargon/scores/VWAP/RSI. Always include: % vs ref price, % off session high, and
  one call: "still climbing, hold" / "looks toppy, tighten up" / "top looks in — I'd sell".
  Text on read changes or bearish turns; max one reassurance per 30 min.
- If last trade age >120s mid-session: text possible LULD halt, don't read a stale tape as calm.

## After the close

`python3 -m spcx.replay --db data/<db>` — precision/recall/lead-time per signal.

## Hard-won gotchas (do not rediscover these)

- **TLS**: python.org macOS Python doesn't trust system certs — feed uses certifi
  (already fixed in `spcx/polygon_feed.py`). REST working ≠ websocket working.
- **Polygon plan tiers**: Starter = 15-min delayed aggregates only — useless for
  exit timing. The feed auto-negotiates (real-time trades → aggs → delayed) and
  re-probes every 5 min after a plan upgrade. Red "DELAYED" banner in UI when degraded.
- **Permissions**: osascript/watch.py/curl/gws/sqlite3 rules are allowlisted in
  `.claude/settings.local.json` so the loop runs unattended. If texts start
  prompting again, check that file first.
- **iMessage needs the Mac** — Twilio is wired as fallback once toll-free verification
  clears (TWILIO_* in root .env). Cloud can't run this watch (localhost + iMessage).
- **Verify the pipeline with a liquid ticker (e.g. MU) during market hours before
  the real event** — a second instance on port 8766:
  `SPCX_SYMBOL=MU IPO_REF_PRICE=<prev close> SPCX_DB=data/mu_test.db python3 -m uvicorn spcx.server:app --port 8766`
- **Usage limits**: each 5-min tick is cheap only if cache stays warm (≤270s spacing).
  Check /usage before a full-day watch; thin to 10-15 min ticks if weekly is tight.
