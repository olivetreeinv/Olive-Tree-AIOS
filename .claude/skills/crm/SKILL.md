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
python3 scripts/crm.py search "Brian"
python3 scripts/crm.py search "investor" --tag newsletter
python3 scripts/crm.py search "" --tag lp-prospect --tag newsletter   # AND across tags
```

### Show a contact
```bash
python3 scripts/crm.py show 42            # by id
python3 scripts/crm.py show jane@foo.com  # by email
# Shows: all fields, tags, notes (newest first), email log (last 5), drip enrollments
```

### Add a contact
```bash
python3 scripts/crm.py add \
    --first Jane --last Doe --email jane@example.com \
    --phone 770-555-0100 --company "Acme Capital" \
    --tag investor --tag newsletter \
    --note "Met at Atlanta REIA, interested in next deal"
# Rejects duplicate email; add --force to overwrite.
```

### Tag / untag
```bash
python3 scripts/crm.py tag   42 newsletter lp-prospect
python3 scripts/crm.py untag 42 newsletter
python3 scripts/crm.py tag   jane@foo.com investor
```

### Add a note
```bash
python3 scripts/crm.py note 42 "Called 2026-07-06 — wants deal deck when under contract"
python3 scripts/crm.py note jane@foo.com "Soft commit: $50K on next deal"
```

### Unsubscribe / re-subscribe
```bash
python3 scripts/crm.py unsub 42
python3 scripts/crm.py resub 42
```

### Segments table
```bash
python3 scripts/crm.py segments
# Tag breakdown: active (subscribed) count + total count per tag.
# Bottom: totals for contacts, with email, with phone, unsubscribed.
```

### Import CSV
```bash
# Columns: first_name, last_name, email, phone, company, tags (semicolon-separated)
python3 scripts/crm.py import-csv path/to/contacts.csv
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
- Email sends are not yet wired — the email_log and drip tables are here for when `/capital-raise` launches campaigns. For now, send via Gmail MCP and log with `note`.
- `ghl_id` is preserved from import. If GHL ever needs a re-sync, match on that field.
