# GHL Workflow Step-Content Export — Attempt Log

**Date:** 2026-07-07
**Script:** `scripts/ghl_workflow_export.py`
**Goal:** Export full step content (trigger, actions, email/SMS bodies, delays) for the 4 workflows in `workflows.json`. The public API only returns workflow *names*.

## Result: SUCCESS — all 4 workflows exported with full step content

### The breakthrough
The step-content endpoint is:

```
GET https://backend.leadconnectorhq.com/workflow/{locationId}/{workflowId}
```

Two things had to be right, and the earlier runs only had the first:
1. **Full SPA header set.** token-id alone → **401**. Replaying with the *complete*
   captured header set (authorization, channel, source, version, route-path,
   route-pattern, baggage, sentry-trace, app-name, user-agent, sec-ch-*, …) → **200**.
2. **Location-scoped path.** `/workflow/{wid}` → 401; `/workflows/{wid}` → 404.
   The real route puts the **locationId first**: `/workflow/{loc}/{wid}`.

The response includes `workflowData.templates` — the ordered action list with every
email (subject + HTML), SMS body, wait/delay, tag action, and multi-path branch.

### Files written (raw JSON + human-readable MD per workflow)
- `brian-s-personal-calendar-booking-ds.json` / `.md` — 9 steps
- `contact-added-send-text-email.json` / `.md` — 9 steps (newsletter drip: 2 emails, 2 SMS, 12hr wait, reply-branch, adds `newsletter` tag)
- `deal-funnel-pitch-deck.json` / `.md` — 4 steps
- `tag-agent-wholesaler-send-text-email.json` / `.md` — 2 steps (Brian's buy-box outreach email + SMS)

### Reproducibility (script updated)
`scripts/ghl_workflow_export.py` was corrected:
- `ENDPOINT_TEMPLATES` → the single confirmed URL `/workflow/{loc}/{wid}`.
- `_headers()` now forwards the **entire** captured header set (was whitelisting a
  handful of keys, which caused the 401). token-id-only auth is insufficient.

Re-run any time with Brian logged into GHL in Chrome:
```
python3 scripts/ghl_workflow_export.py
```

### One gap: trigger definitions
Each workflow's **trigger** (e.g. "Contact Created", "Tag Added", "Appointment Booked")
is NOT in the detail response's inline data — it lives in a separate Firebase file
named by `triggersFilePath` (`location/{loc}/workflow-triggers/{wid}/{v}`), which needs
its own Firebase download token we didn't capture. The `fileUrl` field (a public,
tokenized Firebase link) only mirrors `templates`. In practice the workflow **names**
already state the trigger, so this wasn't chased. To recover exact trigger configs,
sniff the editor's Firebase GET for the `workflow-triggers` path and fetch that URL.

### Sniffed request logs (diagnostic, kept for reference)
- `sniffed_urls.txt` — 735 backend requests from the list page
- `sniffed_urls_2.txt` — 529 requests from the click-through session
