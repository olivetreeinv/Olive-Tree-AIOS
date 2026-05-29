# Broker Search Skill — Olive Tree Investments
**Trigger:** `/broker-search`, "scan for new deals", "check listing alerts", "find new listings", "run broker search"

---

## What this skill does

Scans Gmail for Crexi and LoopNet listing alert emails, parses each property, filters against the buy box, and logs results to the Deal Sourcing spreadsheet. Brokers are only added to the Brokers List if they have **2 or more active listings** in the scan AND are not already in the sheet.

**Pipeline:**
Gmail alerts → parse listings → filter buy box → deduplicate → log deals → evaluate brokers → log qualifying brokers

---

## One-time setup (required before first run)

Brian must create saved searches on both platforms. Do this once — alerts come automatically after.

### Crexi saved searches

1. Go to [crexi.com](https://www.crexi.com) → log in
2. Search for **Multifamily / For Sale** in each zip code below
3. Apply filters: **Type = Multifamily**, **For Sale**, **Min Units = 15**, **Max Units = 50**
4. Click **Save Search** → name it exactly: `OTI - [zip]` (e.g. `OTI - 30341`)
5. Set alert frequency: **Daily**
6. Repeat for all 9 zips:

| Zip | Market |
|---|---|
| 30341 | Chamblee, GA |
| 30080 | Smyrna, GA |
| 30005 | Alpharetta, GA |
| 37207 | North Nashville, TN |
| 37115 | Madison, TN |
| 37408 | Chattanooga Southside, TN |
| 35801 | Huntsville Core, AL |
| 35205 | Birmingham Urban, AL |
| 35806 | Huntsville Growth, AL |

### LoopNet saved searches

1. Go to [loopnet.com](https://www.loopnet.com) → log in
2. Search **Multifamily / For Sale** → enter each zip code in the search bar
3. Apply filters: **Property Type = Multifamily**, **For Sale**
4. Click **Save Search** → name it: `OTI - [zip]`
5. Set frequency: **Daily**
6. Repeat for all 9 zips above

> LoopNet uses your saved search title as the email subject line — naming them `OTI - [zip]` makes them easy to filter in Gmail.

---

## Running the script

```bash
# Standard weekly run (last 7 days)
python3 scripts/broker_search.py

# Scan further back (good for first run after setting up alerts)
python3 scripts/broker_search.py --days 30

# Test run — parses and prints without writing to sheet
python3 scripts/broker_search.py --dry-run
```

---

## Broker add rules

A broker is added to the Brokers List **only if both conditions are true:**

1. **2 or more active listings** found in the current scan (across all emails in the date window)
2. **Not already in the Brokers List** — checked by email address first, then by name

Brokers with only 1 listing are tracked in the scan output but not logged. Run again the following week — if they keep listing, they'll qualify.

New brokers are added with:
- **Tier = B** (relationship not yet established)
- **Buy Box Sent = No** (prompts you to send the buy box doc)
- **Status = "New — Found via Alert"**

---

## Buy box filter

All 9 active zips are hardcoded in `scripts/broker_search.py`. Deals are evaluated against:
- Zip code in buy box → logged as `New`
- Zip outside buy box → logged as `Pass` with a ⚠️ flag in Notes
- Unit count outside 15–50 → logged as `Pass` with a ⚠️ flag in Notes

Flagged deals still get logged — they're useful for broker relationship tracking even if the deal doesn't fit.

---

## What gets logged

### Deal Sourcing tab
Every new (non-duplicate) listing found in the emails, regardless of buy box fit. Duplicates are checked by address and property name.

Columns populated automatically:
`Market` | `Zip` | `Property Name` | `Address` | `Doors` | `Asking Price` | `Price/Unit` | `Platform` | `Brokerage` | `Broker Name` | `Broker Email` | `Broker Phone` | `Stage` | `Date Found` | `Notes`

### Brokers List tab
Only brokers meeting the 2-listing threshold who aren't already in the sheet.

Columns populated automatically:
`Brokerage` | `Broker Name` | `Email` | `Phone` | `Markets/Zips` | `Specialty` | `Tier` | `Buy Box Sent` | `# Deals Sent` | `Last Contact` | `Status` | `Notes`

---

## Suggested cadence

Run **every Monday morning** after `/daily-brief`. Alerts accumulate over the week — Monday scan catches everything from the prior 7 days.

To schedule automatically, run `/schedule` and set:
```
Every Monday at 7:00 AM: python3 scripts/broker_search.py
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| "No listings parsed" | Check that saved searches are set up on Crexi/LoopNet and alerts are arriving in Gmail |
| Broker not being added | Check they have 2+ listings in the scan window — try `--days 14` |
| Duplicate deals getting through | Address format mismatch — check the Notes column for the existing deal's address |
| Auth error | Run `gws auth login -s gmail,sheets` then retry |

---

## Parser notes

The email parser uses regex patterns tuned to Crexi and LoopNet's known email formats. When the first real alerts arrive, run with `--dry-run` to verify parsing accuracy. If fields are missing or wrong, update the regex patterns in `scripts/broker_search.py` under the `find_*` functions.

Reference: `references/google-workspace-api.md` for Gmail API details.
