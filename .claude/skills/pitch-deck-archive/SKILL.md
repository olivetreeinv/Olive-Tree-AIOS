---
name: pitch-deck-archive
description: Searches Canva for "Pitch Deck" designs, exports each as a PDF, archives it to the "Olive Tree Investments - Pitch Decks" Drive folder, logs the tracking sheet, and writes a wiki note. Trigger on "/pitch-deck-archive", "archive my pitch decks", "back up my decks", "sync pitch decks from Canva".
---

## What this skill does

The Canva sibling of `/loom-sync` — turns your Canva pitch decks into a durable,
searchable archive. Searches Canva for designs matching a query (default
"Pitch Deck"), exports each to PDF, stores it in Drive, logs the tracking
sheet, and writes a wiki note. Deduped by Canva design ID — safe to re-run.

**One run = every matching deck exported + archived + logged.**

> Not to be confused with `/pitch-deck`, which *creates* a new deal deck in
> Canva. This skill *archives* decks that already exist.

## When to run

- **On demand** — after you create or revise a deck in Canva: "/pitch-deck-archive".
- Optionally on a weekly cloud routine (see Cloud note).

## How it works

`scripts/canva_sync.py` (stdlib-only). Per design:

1. **Search Canva** — `GET /designs?query="Pitch Deck"` (override with `--query`).
2. **Export** — starts a PDF export job, polls to completion, downloads the PDF.
3. **Archive** — uploads to the **Olive Tree Investments - Pitch Decks** Drive folder
   (`PITCHDECK_DRIVE_FOLDER_ID`).
4. **Log** — appends a row to the tracking sheet (`PITCHDECK_SHEET_ID`):
   Date Archived · Title · Design ID · Canva Edit URL · Drive PDF · Pages · Wiki Note · Status.
5. **Wiki** — writes `wiki/pitch-decks/<slug>.md` with links + a fill-in stub.

## Commands

```bash
python3 scripts/canva_sync.py                 # archive new "Pitch Deck" designs
python3 scripts/canva_sync.py --query "OM"    # different search term
python3 scripts/canva_sync.py --dry-run       # list matches, no export/write
```

## Auth — the important part

Canva refresh tokens are **single-use and rotate** on every refresh, and access
tokens die after ~4h. So:

- The rotating token lives in a **Drive-backed token store** (`scripts/canva_token_store.py`)
  — a private `.canva_tokens.json` in the **Olive Tree Investments - Systems** folder
  (never the shareable Pitch Decks folder). This is what lets cloud runs survive rotation.
- `canva_sync.py` prefers a still-valid access token (to avoid burning a refresh),
  and persists every rotation to both the store and `.env`.
- **If auth ever dies:** re-auth locally with `python3 scripts/canva_oauth_setup.py`
  (stdlib-only, opens a browser, no `source` needed), then re-seed the store:
  `python3 scripts/canva_token_store.py seed`.

## Cloud note

A weekly cloud routine needs only `CANVA_CLIENT_ID` / `CANVA_CLIENT_SECRET` +
`GOOGLE_*` in the cloud env — the refresh token is read from the Drive store, not
the cloud env. Pitch decks are low-churn and created deliberately, so on-demand is
often the better cadence; the real automation target is firing `/pitch-deck` on a
PURSUE LOI verdict, which reuses this same token store.

Run `/code-review` after editing `scripts/canva_sync.py` or `canva_token_store.py`.
