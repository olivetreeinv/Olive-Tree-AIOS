---
name: crm
description: Local CRM — search, tag, note, and manage contacts in data/olive.db (804 imported from GHL). Source of truth now that GoHighLevel is being decommissioned. Trigger on "/crm", "find contact", "look up [name] in crm", "tag these contacts", "who's on the newsletter list", "add [name] to crm", "show me contacts tagged [x]".
---

# CRM Skill — Olive Tree Investments

## What this is

Local replacement for GoHighLevel contacts. 804 contacts imported from GHL live in `data/olive.db` (contacts, contact_tags, contact_notes, email_log, drip_enrollments tables). GoHighLevel is being decommissioned — this is now the source of truth.

All contact work goes through `scripts/crm.py`. No API key, no cloud dependency, instant.

## Commands + examples

### Search
```bash
# By name, email, phone, or company (case-insensitive LIKE). Returns up to 50, shows total.
.venv/bin/python scripts/crm.py search "Brian"
.venv/bin/python scripts/crm.py search "investor" --tag newsletter
.venv/bin/python scripts/crm.py search "" --tag lp-prospect --tag newsletter   # AND across tags
```

### Show a contact
```bash
.venv/bin/python scripts/crm.py show 42            # by id
.venv/bin/python scripts/crm.py show jane@foo.com  # by email
# Shows: all fields, tags, notes (newest first), email log (last 5), drip enrollments
```

### Add a contact
```bash
.venv/bin/python scripts/crm.py add \
    --first Jane --last Doe --email jane@example.com \
    --phone 770-555-0100 --company "Acme Capital" \
    --address "123 Main St #200" --city Atlanta --state GA --zip 30303 \
    --website acmecapital.com \
    --tag investor --tag newsletter \
    --note "Met at Atlanta REIA, interested in next deal"
# Rejects duplicate email; add --force to overwrite.
```

### Tag / untag
```bash
.venv/bin/python scripts/crm.py tag   42 newsletter lp-prospect
.venv/bin/python scripts/crm.py untag 42 newsletter
.venv/bin/python scripts/crm.py tag   jane@foo.com investor
```

### Add a note
```bash
.venv/bin/python scripts/crm.py note 42 "Called 2026-07-06 — wants deal deck when under contract"
.venv/bin/python scripts/crm.py note jane@foo.com "Soft commit: $50K on next deal"
```

### Unsubscribe / re-subscribe
```bash
.venv/bin/python scripts/crm.py unsub 42
.venv/bin/python scripts/crm.py resub 42
```

### Segments table
```bash
.venv/bin/python scripts/crm.py segments
# Tag breakdown: active (subscribed) count + total count per tag.
# Bottom: totals for contacts, with email, with phone, unsubscribed.
```

### Import CSV
```bash
# Columns: first_name, last_name, email, phone, company, tags (semicolon-separated)
.venv/bin/python scripts/crm.py import-csv path/to/contacts.csv
# Upserts by email — updates existing, adds new, skips rows with no email.
```

## Resolution rules

Any subcommand that takes a contact reference (`ref`):
- **Integer** → looked up by id
- **Contains @** → looked up by email (case-insensitive)
- Anything else → error (must be int or email)

## Tags in use (as of import)

Run `segments` to see the live list. At import: 18 tags across 804 contacts (examples: newsletter, lp-prospect, investor, broker, warm-lead).

## Guidance

- This CLI is what to run when Brian asks about a contact, wants to tag a list, or logs a call outcome.
- For bulk tagging after a campaign or event, use `import-csv` with a tags column.
- `ghl_id` is preserved from import. If GHL ever needs a re-sync, match on that field.

## Drips (replaces GHL workflows, 2026-07-06)

Templates live in `templates/drips/<drip>/step-NN.md` — frontmatter (`delay_days`, `subject`) + body in Brian's voice, `{{first_name}}` supported. Three drips:

- `pitch-deck` — 3 steps (day 0/3/7). Replaces GHL "Deal Funnel Pitch Deck".
- `welcome` — 1 step. Replaces GHL "Contact added >> send text/email".
- `agent-wholesaler` — 1 step. Replaces GHL 'Tag "Agent/Wholesaler" >> send text/email'.

GHL's 4th workflow (calendar-booking notifier) needs no code — Google Calendar native notifications cover it.

```bash
.venv/bin/python scripts/drip.py list                                        # drips + step counts
.venv/bin/python scripts/drip.py enroll --contact jane@foo.com --drip welcome
.venv/bin/python scripts/drip.py enroll --tag pitchdeck --drip pitch-deck --dry-run
.venv/bin/python scripts/drip.py run [--dry-run]                             # send everything due
.venv/bin/python scripts/drip.py stop --contact 42 [--drip welcome]
.venv/bin/python scripts/drip.py status                                      # counts per drip
```

Sends go through Gmail API as brian@, log to `email_log` (drip_step=`drip:NAME:NN`). Unsubscribed contacts are skipped at enroll AND send time. Daily 9:00 launchd job `com.olivetree.drip` runs `drip_worker.py` (drip run + newsletter scan-unsubs) → `output/drip-runner.log`.
