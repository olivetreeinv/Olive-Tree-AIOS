# Fathom → Meeting Log — Make Scenario Reference

**Purpose:** Auto-log every Fathom meeting summary (Google Meet + Zoom) to the Meeting Log Google Sheet.
**Created:** 2026-05-29
**Sheet:** [Meeting Log — Olive Tree Investments](https://docs.google.com/spreadsheets/d/1PyPmgCAB92aPjPSAYqbDbC6iVKQ9gi3Ti9m3xXOqoYo/edit)
**Sheet ID:** `1PyPmgCAB92aPjPSAYqbDbC6iVKQ9gi3Ti9m3xXOqoYo`

---

## Prerequisites

1. **Fathom** — signed up and connected to Google Calendar + Zoom. After each meeting, Fathom auto-saves a Google Doc to Drive (folder: "Fathom" or "Meeting Notes by Fathom" — confirm after first call).
2. **Anthropic API key** — in `.env` as `ANTHROPIC_API_KEY`. Used in Make's HTTP module.
3. **Make.com** — connected (see `connections.md`). Build this scenario at make.com.

---

## Scenario Overview — 3 modules

```
[Trigger] Google Drive: Watch Files in Folder
    ↓
[Module 1] Google Docs: Get Document Content
    ↓
[Module 2] HTTP: POST to Claude API (parse into structured JSON)
    ↓
[Module 3] Google Sheets: Add a Row → Meeting Log
```

---

## Module-by-Module Build Guide

### Trigger — Google Drive: Watch Files in Folder

| Field | Value |
|---|---|
| Connection | Your Google Drive (OAuth) |
| Folder | Select the Fathom output folder (confirm name after first Fathom call — usually "Fathom" or "Meeting Notes by Fathom") |
| Watch | New files only |
| File types | All |
| Maximum number of returned files | 1 |

> After setup: click "Run once" to pull in a test file from Fathom. This primes the trigger.

---

### Module 1 — Google Docs: Get Document Content

| Field | Value |
|---|---|
| Connection | Your Google Drive (OAuth) |
| Document ID | `{{1.id}}` (file ID from trigger) |

Returns the full plain-text content of the Fathom summary doc as `{{1.content}}` (or similar — check Make's output panel after first run to confirm the exact variable name).

---

### Module 2 — HTTP: Make a Request (Claude API)

| Field | Value |
|---|---|
| URL | `https://api.anthropic.com/v1/messages` |
| Method | POST |
| Headers | See below |
| Body type | Raw |
| Content type | JSON (application/json) |
| Request content | See body below |

**Headers:**

```
x-api-key: YOUR_ANTHROPIC_API_KEY
anthropic-version: 2023-06-01
content-type: application/json
```

**Request body (paste exactly, replace `{{doc_content}}` with Make's variable):**

```json
{
  "model": "claude-haiku-4-5-20251001",
  "max_tokens": 1024,
  "messages": [
    {
      "role": "user",
      "content": "Extract the following from this meeting summary and return ONLY valid JSON — no markdown, no explanation, no code fences. Use exactly these keys:\n\n{\n  \"date\": \"YYYY-MM-DD\",\n  \"meeting_title\": \"string\",\n  \"attendees\": \"comma-separated names\",\n  \"summary\": \"2-3 sentence summary of what was discussed\",\n  \"action_items\": \"bullet list of action items, one per line starting with -\",\n  \"follow_ups\": \"any next steps, commitments, or things to track — or 'None' if empty\",\n  \"source\": \"Zoom or Google Meet\",\n  \"fathom_link\": \"any Fathom share link found in the doc, or blank\"\n}\n\nMeeting summary:\n{{2.data.content}}"
    }
  ]
}
```

> **Note:** Replace `{{2.data.content}}` with the actual Make variable for the doc text from Module 1. Check Make's output inspector after a test run — it's usually something like `{{1.content}}` or `{{2.content}}`.

**Parse response:** After this module, add a **JSON: Parse JSON** module (or use Make's built-in JSON parser) on the response body to extract individual fields from the Claude output.

Claude returns:
```json
{
  "date": "2026-05-29",
  "meeting_title": "Deal Review — Chattanooga Southside",
  "attendees": "Brian Norton, Patrick Cosgrove",
  "summary": "Reviewed OM for 24-unit property on MLK Blvd...",
  "action_items": "- Request T-12 from Patrick\n- Run full underwriting by Friday",
  "follow_ups": "Patrick to send rent roll by EOW",
  "source": "Zoom",
  "fathom_link": "https://fathom.video/..."
}
```

---

### Module 3 — Google Sheets: Add a Row

| Field | Value |
|---|---|
| Connection | Your Google Drive (OAuth) |
| Spreadsheet ID | `1PyPmgCAB92aPjPSAYqbDbC6iVKQ9gi3Ti9m3xXOqoYo` |
| Sheet name | `Meetings` |
| Values | Map each column (see below) |

**Column mapping:**

| Sheet Column | Make Variable |
|---|---|
| Date | `{{json.date}}` |
| Meeting | `{{json.meeting_title}}` |
| Attendees | `{{json.attendees}}` |
| Summary | `{{json.summary}}` |
| Action Items | `{{json.action_items}}` |
| Follow-ups | `{{json.follow_ups}}` |
| Source | `{{json.source}}` |
| Fathom Link | `{{json.fathom_link}}` |

> Variable names depend on what you named your JSON parser module. Adjust accordingly.

---

## Testing the Scenario

1. Complete one Fathom-recorded meeting (or locate an existing Fathom doc in Drive).
2. In Make, click **Run once**.
3. Verify the trigger picks up the correct file.
4. Check Module 2 output — Claude should return clean JSON.
5. Check the Sheet — a new row should appear.

If Claude returns malformed JSON: check that the content variable is correctly mapped and the doc text is being passed. Add a **Tools: Set Variable** module between Module 1 and 2 to preview the raw content.

---

## Anthropic API — Cost Estimate

Model: `claude-haiku-4-5-20251001` (cheapest, fast, good at extraction)
Tokens per call: ~1,000–2,000 (input) + ~300 (output)
Cost: ~$0.001–0.002 per meeting

At 10 meetings/week → < $0.10/week.

---

## Sheet columns reference

| Column | Description |
|---|---|
| Date | YYYY-MM-DD format |
| Meeting | Title of the meeting |
| Attendees | Comma-separated names |
| Summary | 2–3 sentence overview |
| Action Items | Bullet list of tasks |
| Follow-ups | Next steps / commitments |
| Source | Zoom or Google Meet |
| Fathom Link | Direct link to Fathom recording/transcript |

---

## Future enhancements

- **Action item alert:** Add a Gmail module after the Sheet row — if Action Items is not empty, send Brian a summary email with the action list.
- **GHL contact tag:** If an attendee matches a GHL contact, tag them with the meeting date (when GHL is connected).
- **Daily brief integration:** Pull last 24h rows from Meeting Log sheet during `/daily-brief` to surface open action items.
