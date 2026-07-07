---
name: land-scout
description: Screen a zip for land-wholesaling viability from county parcel data — vacant lots, out-of-state absentee owners, cookie-cutter uniformity, and a Go/No-Go. Phase 1 of the land pipeline. Trigger on "/land-scout", "scout [zip]", "is [zip] good for land wholesaling", "screen this land market".
---

# Land Scout Skill — Olive Tree Investments

## What this skill does

Screens a zip code for **land-wholesaling** viability straight from county
tax-assessor parcel data (no Zillow, no scraping). Computes the three tests from
`references/land-wholesale-buy-box.md` and writes a Go/No-Go to the **Land
Markets** tab of the land workbook (`LAND_SHEET_ID`).

This is **Phase 1** of the land pipeline:
`/land-scout` → `/land-builders` → `/land-sellers` → `/land-mail` · `/land-call` → `/land-contract` → `/land-deal`

## References (read first)

| File | Why |
|---|---|
| `references/land-wholesale-buy-box.md` | Authoritative — markets, the 3 tests, seller acreage bands |
| `references/land-wholesale-playbook.md` | The builder-first method and why absentee inventory matters |

## The three tests

1. **Building demand** — new construction present (builder signal; confirm by calling builders in `/land-builders`).
2. **Uniform inventory** — cookie-cutter score (acreage CV → uniformity 0–1).
3. **Absentee pool at a workable basis** — count of vacant + out-of-state-owned lots, their median acreage, and avg land value.

Verdict is driven by the absentee seller pool; uniformity + basis are context.
`GO` ≥ 50 absentee lots · `WATCH` 10–49 · `NO-GO` < 10 — but read the basis: a
high-value, non-uniform metro (e.g. Forsyth) can clear the count and still be a
poor wholesale market.

## Running it

```bash
# Screen + log to the Land Markets tab (Bartow is the default county)
python3 scripts/land_markets.py --zip 30120 --city Cartersville

# Screen only, no write
python3 scripts/land_markets.py --zip 30120 --dry-run

# Another county (must be wired in scripts/land_parcels.py COUNTIES)
python3 scripts/land_markets.py --county forsyth-ga --zip 30040 --dry-run

# Override the seller acreage band (default: bartow 1–10 ac)
python3 scripts/land_markets.py --zip 30184 --min-acres 1 --max-acres 10

# Scout an UNWIRED county via ReportAll (nationwide, by zip) — for the 6-state
# SE candidates whose counties run qPublic/Schneider or geometry-only AGO layers.
# Needs REPORTALL_API_KEY with live quota. Bills per parcel returned → --cap guards it.
python3 scripts/land_markets.py --zip 30506 --county hall-ga --source reportall --cap 2000
```

**Note:** `--source reportall` leaves Total/Vacant parcel counts blank (no free
count-only endpoint); the seller pool `Vacant Out-of-State` is the capped in-band
pool (a floor if `--cap` is hit — verdict still holds once it clears 50).

## Wired counties

- **bartow-ga** (default) — launch market; situs zip, ~57.5K parcels. Cartersville 30120/30121, White 30184, Emerson 30137.
- **forsyth-ga** — GIS test county (rejected market); bbox-based, no situs zip.

To add a county: add a config block to `COUNTIES` in `scripts/land_parcels.py`
(ArcGIS-Online-hosted parcel layer + field map + `vacant_where`; set
`zip_field` if it has a situs zip, else add a `ZIP_BBOX` entry). Only
ArcGIS-Online (`services*.arcgis.com`) orgs are reachable.

## Output

A scorecard (total parcels → vacant → vacant+out-of-state seller pool →
in-band lots → uniformity → median acres → avg land value → VERDICT/score),
upserted to the **Land Markets** tab and mirrored to `olive.db` (`land_markets`).

## After a GO

Call 2–3 builders/developers in the zip for a buy box (`/land-builders`), then
pull the seller list (`/land-sellers`).

## Troubleshooting

| Symptom | Fix |
|---|---|
| `LAND_SHEET_ID not set` | `python3 scripts/land_setup.py` |
| `has no vacant_where` | The county config needs a server-side vacant filter — add one to `COUNTIES`. |
| `has no situs zip and no bbox` | Add the zip to `ZIP_BBOX` or pass `--bbox west,south,east,north`. |
| 5xx from the GIS server | Transient; the client retries 3× with backoff. Re-run if it persists. |
