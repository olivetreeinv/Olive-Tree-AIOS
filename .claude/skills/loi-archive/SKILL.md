---
name: loi-archive
description: Searches Drive for LOI Google Docs, exports each to PDF, archives to the "Olive Tree Investments - LOI" folder, logs the tracking sheet, and writes a wiki note. Trigger on "/loi-archive", "archive my LOIs", "sync LOIs to Drive", "back up my letters of intent".
---

## What this skill does

Finds every LOI Google Doc in Drive (name contains "LOI" or "Letter of Intent"),
exports it to PDF, stores the PDF in the central **Olive Tree Investments - LOI**
folder, logs a row to the LOI tracking sheet, and writes a `wiki/lois/` note.
Deduped by source Doc ID — safe to re-run any time.

> Not to be confused with `/loi`, which *creates* a new LOI for a deal. This
> skill *archives* LOIs that already exist.

## When to run

- **After any new LOI is drafted and saved** by `/loi` — "/loi-archive" to snapshot it.
- Runs automatically every Friday 7pm ET via the "Deal Docs — Weekly" cloud routine.

## How it works

`scripts/loi_sync.py` (stdlib-only). Per doc:

1. **Search Drive** — queries for Google Docs with "LOI" or "Letter of Intent" in the name.
2. **Export** — converts each Google Doc to PDF via the Drive export API.
3. **Archive** — uploads the PDF to **Olive Tree Investments - LOI** folder
   (`LOI_DRIVE_FOLDER_ID`).
4. **Log** — appends a row to the LOI tracking sheet (`LOI_SHEET_ID`):
   Date · Property/Address · Deal Folder · LOI Doc · LOI PDF · Offer Price · Status · Wiki Note.
   (Offer Price and Status are left blank for manual fill.)
5. **Wiki** — writes `wiki/lois/<slug>.md` with links + a fill-in stub.

## Commands

```bash
python3 scripts/loi_sync.py            # archive new LOI docs
python3 scripts/loi_sync.py --dry-run  # list matches, no export/write
```

## Key IDs

| Resource | ID |
|---|---|
| LOI folder (Drive) | `1o2Soa4FxxSpgGxrpFSOqFBD-p7z5-S_O` |
| LOI tracking sheet | `1S8KuW1n8vTnMnP7U5AYWqosjl8sTxudamNybNqkZ8P4` |
| Deals parent folder | `1pLWVMaLPy-8Rt1NGQsX2wg2oNDonWC-p` |

## Auth

Google only — no Canva. Needs `GOOGLE_*` env vars (or `gws auth export` locally).
The cloud routine already has `GOOGLE_*` set.

## Cloud note

Runs as part of the "Deal Docs — Weekly" routine every Friday 7pm ET alongside
`deal_index.py`. Commits `wiki/lois/` to `main` after each run.

Run `/code-review` after editing `scripts/loi_sync.py`.
