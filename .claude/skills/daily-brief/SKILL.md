---
name: daily-brief
description: Morning context pull for Brian Norton. Reads Gmail, Google Calendar, and Q3 priorities. Surfaces what matters today, identifies the #1 action, and drafts the first artifact ready to send. Trigger on "daily brief", "morning brief", "what's on my plate", "what do I have today", "run my brief", or "brief me".
---

## What this skill does

Runs a morning intelligence pull from Brian's connected systems. Surfaces the day's schedule, deal and investor emails from the last 24 hours, Q3 priority pulse, and one #1 action — then drafts the artifact that executes that action (email, follow-up, etc.) ready to review and send.

**One run = one clear morning + one ready-to-send draft.**

## When to run

- **Every weekday morning** — ideally before the first task.
- **Trigger phrases:** "daily brief", "morning brief", "what's on my plate", "what do I have today", "brief me", "run my brief".
- **Ideal timing:** Between 7–9 AM. Before outreach, calls, or underwriting work.
- **Integrated mode:** Also runs as optional Phase 0 of `/lets-get-to-work`. When called from there, skip the standalone header and flow directly into the pipeline session after the brief.

## Inputs

| Source | What it reads | Mechanism |
|---|---|---|
| Google Calendar | Today's events (full day) | Google Calendar MCP |
| Gmail | Unread + starred threads from last 24h | Gmail MCP |
| `context/priorities.md` | Q3 goals | Read |
| `context/about-me.md` | Role, top pain | Read |
| `connections.md` | Which tools are live vs. pending | Read |
| `decisions/log.md` | Recent decisions (last 3 entries) | Read (if exists) |
| `references/voice.md` | Brian's voice for draft output | Read |
| `logs/auto-commit.log` | Last night's AIOS auto-commit status | Read (last line) |

**GoHighLevel (CRM):** Not yet scripted. When `scripts/ghl_pipeline.py` exists and returns data, insert an LP Pipeline section automatically. Until then, skip silently — do not mention the gap in the brief output.

---

## API Reference — Google Workspace

Auth: OAuth 2.0. All requests use `Authorization: Bearer <access_token>`.
Credentials via: `gws auth export --unmasked > ~/.config/gws/credentials.json`
Load env: `source .env`

### Gmail API — `https://gmail.googleapis.com`

**Calls used in this skill:**

| Purpose | Method | Endpoint / CLI |
|---|---|---|
| Unread deal/investor emails, last 24h | GET | `/gmail/v1/users/me/messages?q=is:unread newer_than:1d` |
| Starred emails, last 24h | GET | `/gmail/v1/users/me/messages?q=is:starred newer_than:1d` |
| Fetch full message body | GET | `/gmail/v1/users/me/messages/{id}` |
| Search by keyword (broker, LOI, etc.) | GET | `/gmail/v1/users/me/threads?q=subject:LOI newer_than:1d` |
| Push draft to Gmail Drafts folder | POST | `/gmail/v1/users/me/drafts` |

**gws CLI equivalents:**
```bash
# Unread emails from last 24h
gws gmail messages list --params '{"q": "is:unread newer_than:1d", "maxResults": 20}'

# Starred emails
gws gmail messages list --params '{"q": "is:starred newer_than:1d", "maxResults": 10}'

# Deal signals — brokers, properties, LOIs
gws gmail messages list --params '{"q": "is:unread newer_than:1d (broker OR LOI OR listing OR multifamily OR apartment OR \"cap rate\" OR units OR doors)", "maxResults": 10}'

# Investor signals
gws gmail messages list --params '{"q": "is:unread newer_than:1d (invest OR LP OR \"limited partner\" OR commitment OR capital OR accredited)", "maxResults": 10}'

# Fetch full message
gws gmail messages get --id MESSAGE_ID

# Create a Gmail draft (push artifact directly to Drafts)
# Body must be base64-encoded RFC 2822 format
gws gmail drafts create --body '{"message": {"raw": "BASE64_ENCODED_EMAIL"}}'
```

**Scopes needed:** `gmail.readonly` (read) + `gmail.send` or `gmail.modify` (to push drafts)

**Draft format (RFC 2822, then base64-encode):**
```
From: brian@olivetreeinv.io
To: recipient@example.com
Subject: Your subject here
Content-Type: text/plain; charset=UTF-8

Email body here.

-Brian
```

---

### Google Calendar API — `https://www.googleapis.com/calendar/v3`

**Calls used in this skill:**

| Purpose | Method | Endpoint / CLI |
|---|---|---|
| Today's events (midnight to midnight) | GET | `/calendars/primary/events?timeMin=&timeMax=&singleEvents=true&orderBy=startTime` |
| All calendars (check for deal-specific) | GET | `/users/me/calendarList` |

**gws CLI equivalents:**
```bash
# Today's agenda (simplest)
gws calendar +agenda

# Today's events with full params (replace dates with today's range)
gws calendar events list --params '{
  "calendarId": "primary",
  "timeMin": "2026-05-27T00:00:00-05:00",
  "timeMax": "2026-05-27T23:59:59-05:00",
  "singleEvents": true,
  "orderBy": "startTime",
  "maxResults": 20
}'

# List all calendars (in case deals are on a separate calendar)
gws calendar calendarList list
```

**Scopes needed:** `calendar.readonly`

**Timezone note:** Brian is in Eastern time (US/Eastern, UTC-5 standard / UTC-4 DST). Construct `timeMin`/`timeMax` accordingly. Use today's date from the environment (`currentDate` memory = `2026-05-27` as of last update — always use actual system date).

---

### Push draft to Gmail (optional — offer after printing brief)

After surfacing the draft in chat, offer:
> *"Push this to your Gmail Drafts so it's ready to send from your phone?"*

If yes:
1. Construct RFC 2822 message string
2. Base64-encode (URL-safe)
3. POST to `/gmail/v1/users/me/drafts` with body `{"message": {"raw": "<encoded>"}}`
4. Confirm: *"Draft saved to Gmail — subject: [subject]."*

---

## Execution

### Step 1 — Pull today's calendar

Use the Google Calendar MCP **or** the `gws` CLI call above. Get all events for today (midnight to midnight, Eastern time).

Brian's timezone: **US/Eastern** (`America/New_York`). Construct `timeMin`/`timeMax` from today's date.

Format as a tight list:
- Time + event name + any location or join link
- Flag any deal-related events (broker calls, investor calls, site visits) with `📍`
- If calendar is empty: note "No events today."

### Step 2 — Scan Gmail (last 24h)

Use the Gmail MCP **or** the `gws` CLI calls above. Run three targeted searches in parallel:

**Query 1 — Deal signals (unread):**
```
q=is:unread newer_than:1d (broker OR LOI OR listing OR multifamily OR apartment OR "cap rate" OR units OR doors OR "offering memorandum" OR OM OR NOI OR "under contract" OR "due diligence")
```

**Query 2 — Investor / LP signals (unread):**
```
q=is:unread newer_than:1d (invest OR LP OR "limited partner" OR commitment OR capital OR accredited OR PPM OR webinar OR "soft commit")
```

**Query 3 — Starred (any topic):**
```
q=is:starred newer_than:1d
```

For each matching message ID, fetch the full message body (`GET /gmail/v1/users/me/messages/{id}`).

**Filter and categorize into three buckets:**

**Deals** — results from Query 1 + any starred emails about deals.

**Investors / LPs** — results from Query 2 + any starred emails about investors.

**Everything else** — starred emails not matching Deals or Investors buckets, or unread emails where subject contains: urgent, action, deadline, today, follow up.

For each email surfaced, show:
- Sender name + subject (one line)
- One-sentence summary of what they want or said
- Age (e.g., "3h ago")

If nothing matches any bucket: "Inbox clear — no deal or investor emails in the last 24h."

### Step 3 — Q3 Pulse

Read `context/priorities.md`. Show three lines — one per Q3 goal. Status is inferred from what you know (Gmail signals, recent decisions, calendar), not fabricated.

Format:
```
Deal under contract    ● not yet / ● in progress / ● done
LP commitments ($400K) ● $Xk soft / ● unknown
Broker pipeline (3+)   ● X active / ● unknown
```

Use `●` for status dot. Fill in numbers if you have signal; say "unknown" if you don't. Never guess a number you don't have.

### Step 4 — Identify the #1 action

Review everything surfaced in Steps 1–3. Pick the single highest-leverage action for today based on this priority order:

1. **Hot deal signal** — a broker emailed with a property, OM, or listing → respond fast, deals go cold
2. **LP follow-up** — an investor asked a question or expressed interest → follow up while they're warm
3. **Broker relationship** — haven't emailed a key broker in 5+ days AND no deal pipeline → outreach
4. **Calendar prep** — a deal call or investor call is today → prep talking points
5. **Everything else**

State the #1 action in one sentence. Then immediately draft it (Step 5).

### Step 5 — Draft the artifact

Draft the artifact that executes the #1 action. Match Brian's voice from `references/voice.md`.

**For a broker reply or outreach:**
- Subject line if new email
- Body: direct, 3–5 sentences max
- Bullets over paragraphs if listing anything
- Sign: `-Brian`
- Include placeholder brackets for anything you don't know: `[property address]`, `[asking price]`, `[deal name]`

**For an LP follow-up:**
- Address their specific question (from the email summary)
- One paragraph, warm but not salesy
- Sign: `-Brian`
- Include deal name/details if you have them; bracket if not

**For calendar prep (today's call):**
- 3–5 bullet talking points for the meeting
- One "ask" to close on

**Label the draft clearly:**
```
---
Draft: [type — broker reply / LP follow-up / broker outreach / call prep]
To: [recipient if known]
Subject: [subject if email]
---
[body]
```

After the draft, add one line: *"Review and adjust before sending. Brackets = fill in."*

## Output format

Print directly in chat. No preamble. Start with the date header.

```
# Daily Brief — {Day, Month DD}

## Today
{calendar items, one per line, ● or 📍 prefix}

## Inbox Pulse
**Deals**
{list or "Clear"}

**Investors / LPs**
{list or "Clear"}

**Other**
{list or omit if empty}

## Q3 Pulse
Deal under contract    ● {status}
LP commitments ($400K) ● {status}
Broker pipeline (3+)   ● {status}

## AIOS Sync
{last line from logs/auto-commit.log — e.g. "[2026-05-29 21:00] Committed: 3 files changed" or "No changes — skipped." If file missing: omit section.}

## Standing Reminder
● Look into mobile capability / control for AIOS

## #1 Action Today
{one sentence}

---
{Draft block}
---
*Review and adjust before sending. Brackets = fill in.*
```

**Keep the whole brief under one screen.** If inbox has 10 emails, summarize — don't list all 10. Signal over noise.

## Output contract

Every `/daily-brief` run produces:
1. **One brief** — printed in chat, fits one screen
2. **One draft artifact** — email, follow-up, or call prep, ready to edit and send
3. **No files written** — brief is ephemeral by default

**After printing, offer two options (one line each):**
- *"Push draft to Gmail Drafts?"* → POST to `/gmail/v1/users/me/drafts`, confirm with subject line
- *"Save brief to `briefs/brief-{date}.md`?"* → write file only if Brian says yes

**Gmail draft push — required scopes:** `gmail.readonly` + `gmail.modify` (or `gmail.send`).
If Gmail scope is read-only only, skip the push offer silently.

## Critical rules

1. **Never fabricate data.** If Gmail returns nothing, say so. If calendar is empty, say so. Don't fill gaps with guesses.
2. **One draft only.** Don't produce multiple drafts — pick the #1 action and draft that one.
3. **Match voice.** Direct. Short sentences. Numbers up front. No filler. `-Brian` sign-off.
4. **Brief stays under one screen.** Ruthlessly trim if it runs long.
5. **Don't mention pending connections** (GHL, QuickBooks, Apple Messages) in the brief output. Silence is cleaner than "feature not yet available."
6. **Q3 Pulse uses real signal.** If you have no data to infer status, say "unknown" — never invent a number.
7. **Always draft something.** Even if the inbox is clear and calendar is empty, the draft is "cold broker outreach" — pulling a name from any broker context in recent decisions or memory.

## Expansion hooks

When new connections come online, insert these sections automatically:

| Connection | Section to add |
|---|---|
| GoHighLevel CRM (`scripts/ghl_pipeline.py`) | **LP Pipeline** — active investors, stage, last contact |
| Apple Messages (any future connection) | **DM Pulse** — broker or investor DMs from last 24h |
| QuickBooks | **Cash Pulse** — current operating balance vs. threshold |

No edits to this SKILL.md needed — skill detects the mechanism in `connections.md` and includes the section if the connection is live.
