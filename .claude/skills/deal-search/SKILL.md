# Deal Search Skill — Olive Tree Investments
**Trigger:** `/deal-search`, "scan for new deals", "check listing alerts", "find new listings", "run deal search"

---

## What this skill does

Scans three sources for multifamily listings matching the buy box and logs results to the Deal Sourcing spreadsheet. Every listing is checked for buy-box fit (zip, unit count, type) before being logged.

**Sources:**
- **Crexi** — parses Gmail alert emails from saved searches
- **LoopNet** — parses Gmail alert emails from saved searches
- **FMLS** — direct API query (Georgia MLS; multifamily listings statewide)

**Pipeline:**
Crexi emails + LoopNet emails + FMLS API → filter buy box → deduplicate → availability check → log to Deal Sourcing

---

## One-time setup (required before first run)

### Crexi saved searches (email alerts)

1. Go to [crexi.com](https://www.crexi.com) → log in
2. Search **Multifamily / For Sale** in each buy-box zip
3. Filters: **Type = Multifamily**, **For Sale**, **Min Units = 15**, **Max Units = 50**
4. Save each search as `OTI - [zip]` (e.g. `OTI - 30341`)
5. Set alert frequency: **Daily**

### LoopNet saved searches (email alerts)

1. Go to [loopnet.com](https://www.loopnet.com) → log in
2. Search **Multifamily / For Sale** → enter each buy-box zip
3. Filters: **Property Type = Multifamily**, **For Sale**
4. Save each as `OTI - [zip]` → set frequency: **Daily**

> LoopNet names its alert emails after your saved search title — `OTI - [zip]` makes them easy to match in Gmail.

### FMLS API credentials

FMLS (First Multiple Listing Service) provides a REST API for active listings in Georgia markets. Required once:

1. Apply for FMLS Data API access at [fmls.com](https://www.fmls.com) (requires a licensed GA real estate contact or member account)
2. Add credentials to `.env`:
   ```
   FMLS_API_KEY=your_key
   FMLS_API_BASE=https://api.fmls.com/v1   # confirm with FMLS on activation
   ```
3. The script queries multifamily (`PropertyType=MultiFamily`) filtered to the 5 Georgia buy-box zips (30341, 30080, 30005) and any additional GA markets added to `BUY_BOX` in the script

> If FMLS access is not yet active, the script skips that source and logs a warning. LoopNet + Crexi still run.

---

## Active buy box

Authoritative list: `references/buy-box.md` (14 markets). The zip map used by the scripts lives in `deal_inbox.py` `BUY_BOX` — keep both in sync.

| Zip | Market |
|---|---|
| 30341 | Chamblee, GA |
| 30340 / 30360 | Doraville, GA |
| 30080 | Smyrna, GA |
| 30005 | Alpharetta, GA |
| 37207 | North Nashville, TN |
| 37115 | Madison, TN |
| 37408 | Chattanooga Southside, TN |
| 37087 | Lebanon, TN |
| 37918 | Knoxville, TN |
| 37804 | Maryville, TN |
| 37615 | Johnson City, TN |
| 35801 | Huntsville Core, AL |
| 35205 | Birmingham Urban, AL |
| 35806 | Huntsville Growth, AL |

---

## Running the script

```bash
# Standard weekly run (last 7 days of Crexi + LoopNet emails; live FMLS API call)
python3 scripts/deal_search.py

# Scan emails further back (FMLS always pulls live)
python3 scripts/deal_search.py --days 30

# Test run — parses and prints without writing to sheet
python3 scripts/deal_search.py --dry-run

# Specific source only
python3 scripts/deal_search.py --source crexi
python3 scripts/deal_search.py --source loopnet
python3 scripts/deal_search.py --source fmls
```

---

## Buy box filter

All 10 zips are hardcoded in `scripts/deal_search.py`. Deals are evaluated against:
- Zip in buy box + units 15–50 → logged `New` (🟢 fit)
- Zip in buy box + units 10–65 but outside 15–50 → logged `Near — Review` (🔶 near-miss — worth a broker call, since a 55-unit deal on a broker's book today can become a 45-unit split or lead to their next listing)
- Zip outside buy box, or units outside 10–65 → logged `Pass` (⚠️)

Every listing gets logged regardless of fit — broker contact info is captured on `Pass` and `Near — Review` rows too, for relationship tracking even when the deal itself doesn't qualify.

`NEAR_MIN`/`NEAR_MAX` (10/65) in `scripts/deal_search.py` set the near-miss unit band. Zip-adjacency (e.g. a submarket bordering Chamblee) isn't modeled — no geo dataset wired in yet; add if near-zip misses turn out to matter more than near-unit misses.

---

## Availability check

Before logging any listing as `New`, the script fetches the listing URL and checks for sold/expired signals (e.g. "no longer available", "listing removed"). Listings that fail availability are logged as `Pass — Unavailable`.

---

## What gets logged

### Deal Sourcing tab
Every non-duplicate listing found across all three sources.

Columns populated automatically:
`Market` | `Zip` | `Property Name` | `Address` | `Doors` | `Asking Price` | `Price/Unit` | `Platform` | `Brokerage` | `Broker Name` | `Broker Email` | `Broker Phone` | `Stage` | `Date Found` | `Notes`

Duplicates checked by address and property name.

---

## Live Crexi buy-box screen (no email alerts needed)

`python3 scripts/crexi_live.py --state GA --deals` screens EVERY active Crexi listing in the state against the buy box (matches + near-misses with links). Full coverage, not just what alerts caught. Local-only (cloud IPs are 403'd by Crexi).

---

## Off-market broker-site sweep

**Why:** off-market deals post on broker/brokerage sites FIRST — only hitting Crexi/LoopNet if they don't sell. Crexi/LoopNet are for broker discovery; the broker sites are the early deal source.

**How:**
1. `python3 scripts/broker_sites.py` — fetches every URL in `references/broker-sites.json` from the local IP, saves page text to `output/broker-sites/<date>/`.
2. Have Claude (or a background agent) extract listings from the .txt files: property, city, units, price, status. Only count clearly-active listings; advisor pages mix in closed transactions.
3. Screen vs buy box; cross-check names against `crexi_live --deals` output — a buy-box fit NOT on Crexi = pre-portal candidate → surface to Brian immediately with the broker's contact.
4. Grow the registry: when a new broker is added to the Brokers List, add their listings-page URL to `broker-sites.json` (M&M advisors: `marcusmillichap.com/advisors/{first-last}`).

**JS-app broker sites (M&M, Meybohm, GREA, MRG, Franklin Street) — need `@browser`:**
These render listings client-side; curl gets only a shell or a server error (M&M's `/mm/related/contentSearch` fails outside a real browser). When Brian has `@browser` connected, sweep them by DOM extraction:
1. Navigate to the advisor/listings URL, wait ~5s for the widget to populate.
2. Run `scripts/mm_listings_extractor.js` (paste into `javascript_tool`) → returns `[{name, city, units, price, cap}]`. Chain navigate→wait→extract across advisors in one `browser_batch`.
3. **Dedupe by office** — M&M advisors on the same team share one "Featured Listings" set (Mitchell/Welch/Shepard/Johnson/Brigel/Spaulding = one Atlanta inventory). Extract one advisor per office.
4. Screen vs buy box; cross-check names against `crexi_live --deals` (GA) — a buy-box fit NOT on Crexi = pre-portal candidate. NOTE: cross-check against the SAME state's Crexi scan (a TN listing absent from the GA scan isn't proven pre-portal until checked vs Crexi TN).
5. **Cross-check the Deals folder** (`scripts/analyzed_deals.py`) so already-worked-up deals don't re-surface: `match_analyzed(city_state, name, load_analyzed(token))` returns `(deal, strength)` — `address` = exact street match = ALREADY ANALYZED (skip); `city` = same city, verify it's not a dup before re-analyzing (a zip holds many properties, so city alone is only a nudge). `crexi_live --deals` already applies this automatically.

Proven 2026-07-13: surfaced Windgate Apartments (Chattanooga, 22u, $2.55M) off Cosgrove's page, not yet on Crexi. M&M's GA listings had already migrated to Crexi; the TN ones hadn't — exactly the pre-portal edge.

---

## Suggested cadence

Run **every Monday morning** as part of `/lets-get-to-work`: email-alert scan + `crexi_live --deals` + broker-site sweep. Alerts accumulate over the week — Monday scan catches everything from the prior 7 days.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| "No Crexi/LoopNet listings parsed" | Verify saved searches are set up on both platforms and alerts are arriving in Gmail |
| "FMLS source skipped" | FMLS credentials not set or API not yet active — set `FMLS_API_KEY` in `.env` |
| Duplicate deals getting through | Address format mismatch — check Notes column on the existing row |
| Auth error | Run `gws auth login -s gmail,sheets` then retry |

---

## Parser notes

The email parsers use regex patterns tuned to Crexi's and LoopNet's known alert email formats. On first run use `--dry-run` to verify parsing accuracy. If fields are missing, update the `find_*` functions in `scripts/deal_search.py`.

Reference: `references/google-workspace-api.md` for Gmail API details.

## Known ceiling: no live Crexi/LoopNet browsing

Confirmed 2026-07-07: both crexi.com and loopnet.com hard-403 non-browser requests (tested via `curl` and via Claude's own WebFetch tool) — this is Cloudflare/bot-wall protection, not a parser bug. That means:
- Gmail alert-email parsing is the only automated channel today for these two sources. FMLS runs on a real API and isn't affected.
- No code fix gets around the 403 — the only upgrade path is paying for the Crexi partner API / LoopNet (CoStar) enterprise API and setting `CREXI_API_KEY` / `LOOPNET_API_KEY` in `.env` (`scripts/broker_search.py` and `scripts/deal_search.py` already read those vars and will use the API automatically once set — no code change needed).
- If Brian has a specific listing URL or pasted listing text, hand it to Claude directly in chat — that's read as provided content, not fetched live, so it isn't blocked.
