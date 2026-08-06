# Google Workspace API Reference — Olive Tree Investments

Researched 2026-05-26. Source: [googleworkspace/cli](https://github.com/googleworkspace/cli) + Google API docs.
Re-use this file instead of re-researching. Update the "Last verified" date when endpoints change.

**Last verified:** 2026-05-26

---

## Authentication

### How it works
All Google Workspace APIs use OAuth 2.0. You need:
1. A Google Cloud project with APIs enabled
2. An OAuth 2.0 Client ID (Desktop app type)
3. A refresh token obtained via the auth flow

### Token endpoint
```
POST https://oauth2.googleapis.com/token
```
Body (to refresh an access token):
```json
{
  "client_id": "YOUR_CLIENT_ID",
  "client_secret": "YOUR_CLIENT_SECRET",
  "refresh_token": "YOUR_REFRESH_TOKEN",
  "grant_type": "refresh_token"
}
```
Returns a short-lived `access_token` (1 hour TTL). Use this in the `Authorization: Bearer <token>` header on every API call.

### Quick setup via gws CLI
```bash
# Install
brew install googleworkspace-cli

# One-time auth (opens browser)
gws auth login -s drive,gmail,calendar,sheets

# Export credentials for use in scripts
gws auth export --unmasked > ~/.config/gws/credentials.json
```

### Environment variables
See `.env` file in project root. Load with: `source .env`

---

## OAuth Scopes — Recommended Minimal Set

| Service | Scope | Permission Level |
|---------|-------|-----------------|
| Gmail | `https://www.googleapis.com/auth/gmail.readonly` | Read email |
| Gmail | `https://www.googleapis.com/auth/gmail.send` | Send email |
| Gmail | `https://www.googleapis.com/auth/gmail.modify` | Read + label + trash |
| Calendar | `https://www.googleapis.com/auth/calendar.readonly` | Read calendar |
| Calendar | `https://www.googleapis.com/auth/calendar.events` | Create/edit events |
| Drive | `https://www.googleapis.com/auth/drive.readonly` | Read files |
| Drive | `https://www.googleapis.com/auth/drive.file` | Files created by app |
| Sheets | `https://www.googleapis.com/auth/spreadsheets` | Read + write sheets |

---

## Gmail API

**Base URL:** `https://gmail.googleapis.com`
**All requests use:** `Authorization: Bearer <access_token>`
**User ID:** Use `me` for the authenticated user (e.g., `/gmail/v1/users/me/messages`)

### Most useful for Olive Tree

| What you want | Method | Endpoint |
|---|---|---|
| Search emails (brokers, investors) | GET | `/gmail/v1/users/me/messages?q=from:broker` |
| Get a full email | GET | `/gmail/v1/users/me/messages/{id}` |
| List threads with a contact | GET | `/gmail/v1/users/me/threads?q=from:eddie@example.com` |
| Send an email | POST | `/gmail/v1/users/me/messages/send` |
| Create a draft | POST | `/gmail/v1/users/me/drafts` |
| List all drafts | GET | `/gmail/v1/users/me/drafts` |
| Get Gmail profile | GET | `/gmail/v1/users/me/profile` |

### Messages — Full Reference

| Method | HTTP | Endpoint | Purpose |
|--------|------|----------|---------|
| list | GET | `/gmail/v1/users/me/messages` | List messages (use `?q=` to search) |
| get | GET | `/gmail/v1/users/me/messages/{id}` | Fetch full message |
| send | POST | `/gmail/v1/users/me/messages/send` | Send message (base64 RFC 2822) |
| insert | POST | `/gmail/v1/users/me/messages` | Insert without sending |
| modify | POST | `/gmail/v1/users/me/messages/{id}/modify` | Add/remove labels |
| trash | POST | `/gmail/v1/users/me/messages/{id}/trash` | Move to trash |
| delete | DELETE | `/gmail/v1/users/me/messages/{id}` | Permanently delete |
| batchModify | POST | `/gmail/v1/users/me/messages/batchModify` | Bulk label changes |
| batchDelete | POST | `/gmail/v1/users/me/messages/batchDelete` | Bulk delete |

### Threads

| Method | HTTP | Endpoint | Purpose |
|--------|------|----------|---------|
| list | GET | `/gmail/v1/users/me/threads` | List threads (use `?q=` to search) |
| get | GET | `/gmail/v1/users/me/threads/{id}` | Full thread with all messages |
| modify | POST | `/gmail/v1/users/me/threads/{id}/modify` | Modify labels on thread |
| trash | POST | `/gmail/v1/users/me/threads/{id}/trash` | Trash full thread |
| delete | DELETE | `/gmail/v1/users/me/threads/{id}` | Delete thread |

### Drafts

| Method | HTTP | Endpoint | Purpose |
|--------|------|----------|---------|
| create | POST | `/gmail/v1/users/me/drafts` | Create draft |
| list | GET | `/gmail/v1/users/me/drafts` | List drafts |
| get | GET | `/gmail/v1/users/me/drafts/{id}` | Fetch draft |
| update | PUT | `/gmail/v1/users/me/drafts/{id}` | Update draft |
| send | POST | `/gmail/v1/users/me/drafts/send` | Send a draft |
| delete | DELETE | `/gmail/v1/users/me/drafts/{id}` | Delete draft |

### Labels

| Method | HTTP | Endpoint | Purpose |
|--------|------|----------|---------|
| list | GET | `/gmail/v1/users/me/labels` | List all labels |
| create | POST | `/gmail/v1/users/me/labels` | Create label |
| get | GET | `/gmail/v1/users/me/labels/{id}` | Get label |
| update | PUT | `/gmail/v1/users/me/labels/{id}` | Update label |
| delete | DELETE | `/gmail/v1/users/me/labels/{id}` | Delete label |

### Search Query Examples (`?q=`)
```
q=from:john@brokerfirm.com          # From a specific person
q=subject:LOI                       # Subject contains LOI
q=label:investor-leads              # By label
q=after:2026/01/01 before:2026/06/01  # Date range
q=has:attachment filename:pdf       # PDF attachments
q=is:unread from:broker             # Unread from brokers
```

---

## Google Calendar API

**Base URL:** `https://www.googleapis.com/calendar/v3`
**Calendar ID:** Use `primary` for the main calendar.

### Most useful for Olive Tree

| What you want | Method | Endpoint |
|---|---|---|
| See this week's events | GET | `/calendars/primary/events?timeMin=...&timeMax=...` |
| Create a meeting | POST | `/calendars/primary/events` |
| Check availability | POST | `/freeBusy` |
| List all calendars | GET | `/users/me/calendarList` |
| Update an event | PATCH | `/calendars/primary/events/{eventId}` |

### Events — Full Reference

| Method | HTTP | Endpoint | Purpose |
|--------|------|----------|---------|
| list | GET | `/calendars/{calId}/events` | List events (add `?timeMin=` & `?timeMax=`) |
| get | GET | `/calendars/{calId}/events/{eventId}` | Get event details |
| insert | POST | `/calendars/{calId}/events` | Create new event |
| quickAdd | POST | `/calendars/{calId}/events/quickAdd?text=...` | Natural language event creation |
| update | PUT | `/calendars/{calId}/events/{eventId}` | Replace event |
| patch | PATCH | `/calendars/{calId}/events/{eventId}` | Partial update |
| delete | DELETE | `/calendars/{calId}/events/{eventId}` | Delete event |
| move | POST | `/calendars/{calId}/events/{eventId}/move` | Move to different calendar |
| instances | GET | `/calendars/{calId}/events/{eventId}/instances` | Recurring event instances |
| watch | POST | `/calendars/{calId}/events/watch` | Push notifications on changes |

### CalendarList

| Method | HTTP | Endpoint | Purpose |
|--------|------|----------|---------|
| list | GET | `/users/me/calendarList` | All calendars for user |
| get | GET | `/users/me/calendarList/{calendarId}` | Specific calendar details |
| insert | POST | `/users/me/calendarList` | Subscribe to a calendar |
| patch | PATCH | `/users/me/calendarList/{calendarId}` | Update calendar settings |
| delete | DELETE | `/users/me/calendarList/{calendarId}` | Unsubscribe from calendar |

### Freebusy (Availability)

| Method | HTTP | Endpoint | Purpose |
|--------|------|----------|---------|
| query | POST | `/freeBusy` | Check free/busy for calendars |

### Events List — Key Query Params
```
timeMin=2026-05-26T00:00:00Z    # Start of range (RFC3339)
timeMax=2026-06-02T00:00:00Z    # End of range
q=investor                       # Search term
singleEvents=true               # Expand recurring events
orderBy=startTime               # Sort by start
maxResults=50                   # Limit results
```

---

## Google Drive API

**Base URL:** `https://www.googleapis.com`

### Most useful for Olive Tree

| What you want | Method | Endpoint |
|---|---|---|
| Search for deal docs | GET | `/drive/v3/files?q=name+contains+'underwriting'` |
| List files in a folder | GET | `/drive/v3/files?q='FOLDER_ID'+in+parents` |
| Download/read a file | GET | `/drive/v3/files/{fileId}?alt=media` |
| Upload a doc | POST | `/drive/v3/files` (multipart) |
| Get file metadata | GET | `/drive/v3/files/{fileId}` |
| Share a file | POST | `/drive/v3/files/{fileId}/permissions` |

### Files — Full Reference

| Method | HTTP | Endpoint | Purpose |
|--------|------|----------|---------|
| list | GET | `/drive/v3/files` | List/search files |
| get | GET | `/drive/v3/files/{fileId}` | File metadata |
| get (download) | GET | `/drive/v3/files/{fileId}?alt=media` | Download file content |
| export | GET | `/drive/v3/files/{fileId}/export?mimeType=...` | Export Google Doc/Sheet |
| create | POST | `/drive/v3/files` | Upload new file |
| update | PATCH | `/drive/v3/files/{fileId}` | Update metadata or content |
| copy | POST | `/drive/v3/files/{fileId}/copy` | Duplicate a file |
| delete | DELETE | `/drive/v3/files/{fileId}` | Permanently delete |

### Permissions (Sharing)

| Method | HTTP | Endpoint | Purpose |
|--------|------|----------|---------|
| list | GET | `/drive/v3/files/{fileId}/permissions` | Who has access |
| create | POST | `/drive/v3/files/{fileId}/permissions` | Share with someone |
| update | PATCH | `/drive/v3/files/{fileId}/permissions/{permId}` | Change permission level |
| delete | DELETE | `/drive/v3/files/{fileId}/permissions/{permId}` | Revoke access |

### Files Search Query Examples (`q=`)
```
name contains 'underwriting'              # File name search
mimeType = 'application/vnd.google-apps.spreadsheet'  # Sheets only
'FOLDER_ID' in parents                    # Files in a folder
modifiedTime > '2026-01-01T00:00:00'     # Recently modified
trashed = false                           # Exclude trash
```

### Export MIME Types (for Google Docs/Sheets)
```
Google Sheets → application/vnd.openxmlformats-officedocument.spreadsheetml.sheet  (xlsx)
Google Docs   → application/vnd.openxmlformats-officedocument.wordprocessingml.document (docx)
Google Docs   → text/plain
Any           → application/pdf
```

---

## Google Sheets API

**Base URL:** `https://sheets.googleapis.com`

### Most useful for Olive Tree (underwriting models, LP tracking)

| What you want | Method | Endpoint |
|---|---|---|
| Read a range of cells | GET | `/v4/spreadsheets/{id}/values/{range}` |
| Write to cells | PUT | `/v4/spreadsheets/{id}/values/{range}` |
| Append rows | POST | `/v4/spreadsheets/{id}/values/{range}:append` |
| Read full sheet metadata | GET | `/v4/spreadsheets/{id}` |
| Read multiple ranges | GET | `/v4/spreadsheets/{id}/values:batchGet` |
| Update multiple ranges | POST | `/v4/spreadsheets/{id}/values:batchUpdate` |

### Values — Full Reference

| Method | HTTP | Endpoint | Purpose |
|--------|------|----------|---------|
| get | GET | `/v4/spreadsheets/{id}/values/{range}` | Read a range (e.g. `Sheet1!A1:Z100`) |
| update | PUT | `/v4/spreadsheets/{id}/values/{range}` | Write to a range |
| append | POST | `/v4/spreadsheets/{id}/values/{range}:append` | Append rows after last data |
| clear | POST | `/v4/spreadsheets/{id}/values/{range}:clear` | Clear a range |
| batchGet | GET | `/v4/spreadsheets/{id}/values:batchGet` | Read multiple ranges at once |
| batchUpdate | POST | `/v4/spreadsheets/{id}/values:batchUpdate` | Write to multiple ranges |
| batchClear | POST | `/v4/spreadsheets/{id}/values:batchClear` | Clear multiple ranges |

### Spreadsheets (Metadata & Structure)

| Method | HTTP | Endpoint | Purpose |
|--------|------|----------|---------|
| get | GET | `/v4/spreadsheets/{id}` | Full metadata, sheet names, ranges |
| create | POST | `/v4/spreadsheets` | Create new spreadsheet |
| batchUpdate | POST | `/v4/spreadsheets/{id}:batchUpdate` | Add sheets, format cells, etc. |

### Range Notation Examples
```
Sheet1!A1:D10       # Specific range
Sheet1!A:A          # Entire column A
Sheet1!1:1          # Entire row 1
Sheet1              # Entire sheet
'LP Tracker'!B2:F50 # Sheet with spaces (use single quotes)
```

---

## gws CLI Quick Reference

Install: `brew install googleworkspace-cli`

### Gmail
```bash
gws gmail messages list --params '{"maxResults": 10, "q": "from:broker"}'
gws gmail messages get --id MESSAGE_ID
gws gmail +send --to investor@email.com --subject "Deal Update" --body "..."
gws gmail threads list --params '{"q": "label:investors"}'
```

### Calendar
```bash
gws calendar +agenda                            # Today's agenda
gws calendar events list --params '{"calendarId": "primary", "maxResults": 10}'
gws calendar +insert --summary "Broker Call" --start "2026-05-27T10:00:00" --end "2026-05-27T11:00:00"
```

### Drive
```bash
gws drive files list --params '{"q": "name contains '\''underwriting'\''"}'
gws drive files get --id FILE_ID
gws drive +upload --file ./deal-summary.pdf --name "123 Main St Deal Summary"
```

### Sheets
```bash
gws sheets spreadsheets values get --spreadsheetId SHEET_ID --range "Sheet1!A1:Z100"
gws sheets +append --spreadsheetId SHEET_ID --range "LP Tracker!A:A" --values '["Brian","$50K","Soft"]'
gws sheets spreadsheets get --id SHEET_ID    # Get sheet structure/metadata
```

---

## API Enable Checklist (Google Cloud Console)

Before calling these APIs, enable them in your Google Cloud project:
- Gmail API → `console.cloud.google.com/apis/library/gmail.googleapis.com`
- Google Calendar API → `console.cloud.google.com/apis/library/calendar-json.googleapis.com`
- Google Drive API → `console.cloud.google.com/apis/library/drive.googleapis.com`
- Google Sheets API → `console.cloud.google.com/apis/library/sheets.googleapis.com`

---

## Next Tools to Add Reference Guides For
- GoHighLevel CRM API → `references/gohighlevel-api.md`
- QuickBooks API → `references/quickbooks-api.md`
