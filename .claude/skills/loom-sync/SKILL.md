---
name: loom-sync
description: Pulls Loom videos Brian shares to brian@olivetreeinv.io out of Gmail, downloads the MP4, archives it to the "Olive Tree Investments - Looms" Drive folder, logs a row to the Looms spreadsheet, and writes a wiki note per video. Trigger on "/loom-sync", "sync my looms", "archive my loom videos", "pull new looms", "back up my looms".
---

## What this skill does

Turns Loom from a fragile player into a durable, searchable library. Brian records a Loom, shares it to **brian@olivetreeinv.io** when done; this skill finds those emails, downloads the actual MP4, stores it in Drive, indexes it in the spreadsheet, and creates a wiki note so the *content* (not just the link) is searchable.

**One run = every newly-shared Loom archived to Drive + logged + wikied.** Deduped by Loom share URL — safe to run repeatedly.

## When to run

- **Automatically every Friday at 5pm ET** via the cloud routine (laptop can be off).
- **On demand:** "/loom-sync", "sync my looms", "pull new looms", "back up my looms".

## How it works

`scripts/loom_sync.py` (stdlib-only, cloud-ready). Pipeline per video:

1. **Gmail scan** — searches `loom.com/share` over the last N days (default 8; the Friday routine uses 8 to cover the week).
2. **Resolve** — pulls the title/description off the Loom share page; resolves the MP4 via Loom's `transcoded-url` endpoint, falling back to the CDN link in the page HTML.
3. **Archive** — downloads the MP4, uploads to the **Olive Tree Investments - Looms** Drive folder (`LOOM_DRIVE_FOLDER_ID`), sets it link-viewable.
4. **Log** — appends a row to the **Looms** tab of the spreadsheet (`LOOM_SHEET_ID`): Date Shared · Title · Loom URL · Drive MP4 · Description · Wiki Note · Status.
5. **Wiki** — writes `wiki/looms/YYYY-MM-DD-<slug>.md` with both links + a summary stub to fill in.

## Commands

```bash
python3 scripts/loom_sync.py                # sync last 8 days
python3 scripts/loom_sync.py --days 30      # look back N days
python3 scripts/loom_sync.py --dry-run      # list links only, no download/write
python3 scripts/loom_sync.py --url <share>  # process one Loom share URL directly
```

## Config (in `.env`)

| Var | Purpose |
|---|---|
| `LOOM_SHEET_ID` | The Looms spreadsheet (lives inside the Looms Drive folder) |
| `LOOM_DRIVE_FOLDER_ID` | `Olive Tree Investments - Looms` (under `… - Marketing`) |
| `LOOM_SHEET_TAB` | Tab name (default `Looms`) |
| `GOOGLE_CLIENT_ID/SECRET/REFRESH_TOKEN` | Gmail + Drive + Sheets access |

## Gotchas

- **Sharing must be "anyone with the link."** The MP4 download only works on public Looms — if a video is private, the row is logged with status "Link only" and no MP4 is archived. Tell Brian which ones to re-share.
- **The trigger is the email.** Brian must hit Share → email to brian@olivetreeinv.io after recording, or the video won't be seen. (Fully automatic capture would require Loom Business + a webhook — not worth it at current volume.)
- Run `/code-review` after editing `scripts/loom_sync.py`.
