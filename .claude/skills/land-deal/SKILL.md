---
name: land-deal
description: Track a land deal from PSA through close — computes spread/profit, runs the deal-killer checklist, logs status to the Land Deals tab, and fires post-close actions ($1K referral letter + neighbor first-look script). Trigger on "/land-deal", "track this deal", "deal-killer check", "close the deal", "post-close actions".
---

# Land Deal Skill — Olive Tree Investments

## What this skill does

The deal cockpit. After a seller says yes and `/land-contract` drafts the PSA,
this skill tracks the deal through close — computing spread, flagging deal-killers,
and firing post-close compounding actions after closing.

## Pipeline position

```
/land-contract → /land-deal (open) → deal-killer checks → status updates → /land-deal --post-close
```

## Running it

```bash
# Open a deal (looks up seller from Land Sellers tab)
python3 scripts/land_deal.py --parcel 0051-0574-005 \
    --contract-price 45400 --assignment-price 54000 --builder "LGI Homes"

# Update status as the deal progresses
python3 scripts/land_deal.py --parcel 0051-0574-005 --status psa-sent
python3 scripts/land_deal.py --parcel 0051-0574-005 --status psa-signed
python3 scripts/land_deal.py --parcel 0051-0574-005 --status assigned
python3 scripts/land_deal.py --parcel 0051-0574-005 --status closed

# Log a deal-killer flag (stored as JSON in the sheet)
python3 scripts/land_deal.py --parcel 0051-0574-005 --flag wetlands --severity high
python3 scripts/land_deal.py --parcel 0051-0574-005 --flag slope --severity low

# Post-close: print referral letter + neighbor first-look script
python3 scripts/land_deal.py --parcel 0051-0574-005 --post-close

# View all active deals
python3 scripts/land_deal.py --pipeline
```

## Status flow

```
new → psa-sent → psa-signed → assigned → in-dd → title-open → closed
                                                              ↘ terminated
```

## Deal-killer checklist (run for every deal)

| Issue | How to spot | Impact |
|---|---|---|
| wetlands | Aerial: gray/dead trees = standing water | Severe |
| wildlife | City planning: gopher tortoise, scrub jay | Can block building |
| slope | County GIS elevation; builder's tolerance | High in NW GA |
| utilities | County records: water/sewer at the street? | Lowers value |
| flood | FEMA / county GIS: zone A or AE | Lowers demand |
| main-road | Any map: main-road frontage | Builders avoid |
| title | Title search: liens, back taxes, heirs | Must resolve before close |
| back-taxes | County tax records | Net-to-seller reduction |

**No EMD risk.** The feasibility contingency lets you terminate for any reason
before closing — a high-severity kill = one termination email, no money lost.

## Post-close compounding

After every close:

1. **$1,000 referral letter** — handwritten, mailed within 48 hours. Pays $1K
   at the next closing if they refer a deal. ~12% CAC on an $8.6K average deal.
2. **Neighbor first-look call** — call adjacent owners before the builder re-lists.
   Neighbors pay above market (the lot has unique value to them).
3. **Same-owner check** — see if the seller owns other lots (they often do).

`--post-close` prints the referral letter draft and the neighbor script, and
marks both as pending in the Land Deals tab.

## Spread math

`Spread = Assignment Price − Contract Price`
`Profit ≈ Spread` (no holding costs, no commission)

Default assignment price = `Contract Price × 1.20` if you don't pass it.

## Notes

- Deal-killers are stored as JSON in the sheet (`{"wetlands": "high", "slope": "low"}`).
- A `terminated` deal still lives in the tab for tracking; it just won't appear in active
  pipeline by default.
