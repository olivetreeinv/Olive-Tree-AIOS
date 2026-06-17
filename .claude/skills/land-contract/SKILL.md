---
name: land-contract
description: Draft the assignable Vacant Land PSA (to seller) and Assignment Agreement (to builder) for a parcel that passed the deal-killer check. Saves both docs locally + uploads to Drive under "Olive Tree Investments - Deals / Land Wholesale / [parcel]/". Trigger on "/land-contract", "draft PSA for [parcel]", "generate land contracts", "fill in the contract".
---

# Land Contract Skill — Olive Tree Investments

## What this skill does

Takes a parcel from the **Land Sellers** tab (with an accepted or agreed offer)
and drafts two attorney-reviewed contracts:

1. **PSA** (`PSA_<parcel>.txt`) — the assignable Vacant Land Purchase & Sale
   Agreement between Brian (Buyer, and/or Assigns) and the seller.
2. **Assignment** (`Assignment_<parcel>.txt`) — assigns the PSA to the builder
   (Assignee) in exchange for the spread.

Both docs are saved locally under `output/land-contracts/<date>-<parcel>/` and
uploaded to **Google Drive → Olive Tree Investments - Deals / Land Wholesale /
[parcel]/**.

## ⚠️ Attorney review is mandatory

These templates are starting points only. Have a Georgia real estate attorney
review both before sending to any party. Do not mail or e-sign either document
without counsel sign-off.

## Prerequisites

- Parcel must exist in the **Land Sellers** tab (run `/land-sellers` first).
- A builder must exist in the **Land Builders** tab (run `/land-builders` first),
  or pass `--builder` and `--assignment-price` manually.
- Offer must be agreed / verbally accepted by the seller (use `/land-call` to
  log outcome as `interested` or `contracted` first).

## Running it

```bash
# Draft both contracts for a parcel (auto-selects builder by zip)
python3 scripts/land_contract.py --parcel 0051-0574-005

# Override the builder and assignment price
python3 scripts/land_contract.py --parcel 0051-0574-005 \
    --builder "LGI Homes" --assignment-price 54000

# Preview filled contracts in the terminal — no files written
python3 scripts/land_contract.py --parcel 0051-0574-005 --dry-run
```

## Spread math

`Assignment Price` = what the builder pays total.
`Assignment Fee (your spread)` = Assignment Price − Contract Price (offer to seller).

Default: Assignment Price = Offer × 1.20 (20% markup). Pass `--assignment-price`
to use the exact number you've negotiated with the builder.

## Pipeline position

```
/land-sellers → /land-call (interested) → /land-contract → /land-deal
```

## Outputs

| File | Contents |
|---|---|
| `PSA_<parcel>.txt` | Assignable PSA to send to seller for signature |
| `Assignment_<parcel>.txt` | Assignment of contract to builder |
| Drive: `Olive Tree Investments - Deals / Land Wholesale / <parcel>/` | Both docs |

## Key contract clauses (non-negotiable)

- **Assignability** — "Buyer and/or Assigns" + explicit assignment right.
- **Feasibility contingency to closing** — Buyer can walk with no EMD at any
  time before closing. Removes all downside.
- **EMD at closing, not at signing** — $250 due only at close. No upfront risk.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Parcel not found in Land Sellers tab` | Run `/land-sellers --zip [zip]` first. |
| Assignment names blank | Add builder via `/land-builders` or pass `--builder`. |
| Drive upload fails | Docs saved locally anyway; upload manually or re-run. |
| Template placeholders still unfilled | Check Parcel ID matches exactly (case-sensitive). |
