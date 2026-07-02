---
name: land-builders
description: Capture and look up land builders'/developers' buy boxes (price/acre, lot sizes, zips, conditions) — the buyer-first step that sets seller offer prices. Trigger on "/land-builders", "add a builder", "log builder buy box", "what price for [zip]", "who buys land in [zip]".
---

# Land Builders Skill — Olive Tree Investments

## What this skill does

Records the **buy box** of the spec builders / land buyers you call, into the
**Land Builders** tab + `olive.db`. Buying is buyer-first: a builder's price/acre
is the anchor `/land-sellers` uses to compute every offer (`offer = price × acres
× (1 − spread)`). A seller list with no builder behind it is just a mailing list.

Pipeline position: run after a `/land-scout` **GO**, before `/land-sellers`.

## References

| File | Why |
|---|---|
| `references/land-cold-call-scripts.md` | Script #1 — the builder first call (what to ask) |
| `references/land-wholesale-buy-box.md` | How the buy box feeds offers + spread targets |

## The builder first call (what to capture)

> "I see you've been building around [zip]. I bring builders off-market land.
> What would you pay per acre for a buildable lot here, what sizes, and what
> kills a deal for you — slope, wetlands, utilities? How fast can you close?"

Capture: **price/acre** (or price/lot), lot-size range, zips, conditions,
volume/month, close timeline, tier (A/B/C).

## Running it

```bash
# Add / update a builder (dedups on name)
python3 scripts/land_builders.py --add \
    --name "Jane Doe" --company "Acme Homes" --phone 770-555-0100 \
    --email jane@acme.com --markets 30120,30121 \
    --price-per-acre 8000 --min-acres 1 --max-acres 10 \
    --volume 3 --conditions "no wetlands; <10% slope; road frontage" \
    --timeline "30 days" --tier A

# List builders (optionally filter to a market)
python3 scripts/land_builders.py --list
python3 scripts/land_builders.py --list --market 30120

# Offer anchor: highest builder $/acre covering a zip
python3 scripts/land_builders.py --price-for 30120

# Auto-discover builder leads for a zip via Google Places (unverified rows to call)
python3 scripts/land_builders.py --discover-builders 30120
```

## How to find builders to call

After a GO scout, builders show up three ways:
1. **`--discover-builders [zip]`** — fastest. Google Places search ("home builders" + "land developers" in the zip) drops name/phone/city/website into the sheet as `Tier=unverified` rows. Dedups by phone (one builder, not one row per community they sell). No email — Places doesn't carry it; capture it on the call. Needs `GOOGLE_MAPS_API_KEY` in `.env` (Places API **New** enabled; ~$0/mo at this volume — $200/mo free credit, ~2 calls/zip).
2. **New-construction parcels** — recently built lots in the zip (county data / a drive-by).
3. **WebSearch** — "[city] GA home builders"; call the names that recur.

Discovered rows have blank buy-box fields (price/acre, lot band, conditions), so `/land-sellers` and `--price-for` safely ignore them until you call and `--add` to verify. Occasional false positives (a subdivision POI, a gov office) — skip on the call. LGI Homes already appears as an out-of-state land buyer in Bartow data — a known national builder to approach.

## Output

A row per builder in the **Land Builders** tab + `land_builders` in `olive.db`.
`--price-for` returns the $/acre `/land-sellers` should anchor offers to.

## Note

A `Test Builder LLC` demo row may exist from setup — delete it in the sheet
before working real builders.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `--price-for` says none on file | Add a builder with `--price-per-acre` covering that zip. |
| Markets show as a big number | Fixed — land sheet I/O uses RAW input so zips stay text. |
| `LAND_SHEET_ID not set` | `python3 scripts/land_setup.py` |
