# GoHighLevel API Reference — Olive Tree Investments

Researched 2026-05-27. Sources: [keith-wohnv/GHL-API-Docs](https://github.com/keith-wohnv/GHL-API-Docs) + [carlosgits/ghl-api-docs](https://github.com/carlosgits/ghl-api-docs).
Re-use this file instead of re-researching. Update "Last verified" when endpoints change.

**Last verified:** 2026-05-27
**API Version:** v2.0

---

## Authentication

**Base URL:** `https://services.leadconnectorhq.com`

### Required Headers on Every Request
```
Authorization: Bearer <YOUR_PRIVATE_INTEGRATION_TOKEN>
Version: 2021-07-28
Content-Type: application/json
Accept: application/json
```

### Getting Your Private Integration Token (One-Time Setup)

1. Go to your GHL agency account → **Settings → Private Integrations**
   (If not visible, enable it in Settings → Labs first)
2. Click **Create new Integration**
3. Give it a name (e.g., `Olive Tree AIOS`)
4. Select the scopes you need (see Scopes section below)
5. Copy the token immediately — you can't retrieve it again
6. Paste it into your `.env` file as `GHL_API_KEY`

**Token format:** `pit-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`

### Getting Your Location ID

Your Location ID is the sub-account identifier used in almost every API call.

```bash
# Find it via API (replace YOUR_TOKEN):
curl --request GET \
  --url "https://services.leadconnectorhq.com/locations/search?companyId=YOUR_AGENCY_ID" \
  --header "Authorization: Bearer YOUR_TOKEN" \
  --header "Version: 2021-07-28"
```

Or find it in GHL dashboard URL: `app.gohighlevel.com/location/[LOCATION_ID]/...`

Store it in `.env` as `GHL_LOCATION_ID`.

### Recommended Scopes for Olive Tree
Select these when creating your Private Integration:
- `contacts.readonly` / `contacts.write`
- `opportunities.readonly` / `opportunities.write`
- `conversations.readonly` / `conversations.write`
- `calendars.readonly` / `calendars.write`
- `locations.readonly`
- `users.readonly`

---

## Quick Test
```bash
# Verify your token works — get location info
curl --request GET \
  --url "https://services.leadconnectorhq.com/locations/$GHL_LOCATION_ID" \
  --header "Authorization: Bearer $GHL_API_KEY" \
  --header "Version: 2021-07-28" \
  --header "Accept: application/json"
```

---

## Contacts API
*Use for: investor contacts, broker contacts, leads*

**Version header:** `2021-07-28`

| Method | Endpoint | Description | Key Fields |
|---|---|---|---|
| POST | `/contacts/` | Create a contact | `firstName`, `lastName`, `email`, `phone`, `locationId` |
| GET | `/contacts/:contactId` | Get a contact by ID | — |
| PUT | `/contacts/:contactId` | Update a contact | any contact fields |
| DELETE | `/contacts/:contactId` | Delete a contact | — |
| GET | `/contacts/search/duplicate` | Find duplicates | `?email=` or `?phone=` + `?locationId=` |
| GET | `/contacts/business/:businessId` | Get contacts for a business | — |

### Contact Notes & Tasks
| Method | Endpoint | Description |
|---|---|---|
| POST | `/contacts/:contactId/notes` | Add a note to a contact |
| GET | `/contacts/:contactId/notes` | Get all notes |
| PUT | `/contacts/:contactId/notes/:id` | Update a note |
| DELETE | `/contacts/:contactId/notes/:id` | Delete a note |
| POST | `/contacts/:contactId/tasks` | Create a task (title, dueDate, assignedTo) |
| GET | `/contacts/:contactId/tasks` | List tasks |
| PUT | `/contacts/:contactId/tasks/:taskId` | Update a task |
| DELETE | `/contacts/:contactId/tasks/:taskId` | Delete a task |

### Tags & Workflows
| Method | Endpoint | Description |
|---|---|---|
| POST | `/contacts/:contactId/tags` | Add tags (array) |
| DELETE | `/contacts/:contactId/tags` | Remove tags |
| POST | `/contacts/bulk/tags/update/:type` | Bulk update tags across contacts |
| POST | `/contacts/:contactId/workflow/:workflowId` | Add contact to a workflow |
| DELETE | `/contacts/:contactId/workflow/:workflowId` | Remove from workflow |
| POST | `/contacts/:contactId/campaigns/:campaignId` | Add to campaign |
| DELETE | `/contacts/:contactId/campaigns/:campaignId` | Remove from campaign |

### Appointments
| Method | Endpoint | Description |
|---|---|---|
| GET | `/contacts/:contactId/appointments` | Get appointments for a contact |

### Example — Search for an investor contact
```bash
curl --request GET \
  --url "https://services.leadconnectorhq.com/contacts/search/duplicate?email=investor@email.com&locationId=$GHL_LOCATION_ID" \
  --header "Authorization: Bearer $GHL_API_KEY" \
  --header "Version: 2021-07-28"
```

---

## Opportunities API
*Use for: deal pipeline, investment stages, tracking soft commitments*

**Version header:** `2021-07-28`

| Method | Endpoint | Description | Key Fields |
|---|---|---|---|
| GET | `/opportunities/pipelines` | Get all pipelines | `?locationId=` (required) |
| GET | `/opportunities/search` | Search opportunities | `?location_id=`, `?pipeline_id=`, `?status=`, `?q=`, `?page=`, `?limit=` |
| POST | `/opportunities/search` | Advanced search with filters | `locationId`, `query`, `limit`, `page` |
| POST | `/opportunities/` | Create an opportunity | `pipelineId`, `locationId`, `name`, `contactId`, `status` |
| GET | `/opportunities/:id` | Get an opportunity | — |
| PUT | `/opportunities/:id` | Update an opportunity | `name`, `pipelineId`, `status`, `monetaryValue`, `assignedTo` |
| PUT | `/opportunities/:id/status` | Update status only | `status`, `lostReasonId` |
| POST | `/opportunities/upsert` | Create or update | `pipelineId`, `locationId`, `name`, `status` |
| DELETE | `/opportunities/:id` | Delete an opportunity | — |

### Status Values
`open` | `won` | `lost` | `abandoned`

### Example — Get all open opportunities (your investor pipeline)
```bash
curl --request GET \
  --url "https://services.leadconnectorhq.com/opportunities/search?location_id=$GHL_LOCATION_ID&status=open&limit=20" \
  --header "Authorization: Bearer $GHL_API_KEY" \
  --header "Version: 2021-07-28"
```

### Example — Create a soft commitment opportunity
```bash
curl --request POST \
  --url "https://services.leadconnectorhq.com/opportunities/" \
  --header "Authorization: Bearer $GHL_API_KEY" \
  --header "Version: 2021-07-28" \
  --header "Content-Type: application/json" \
  --data '{
    "pipelineId": "YOUR_PIPELINE_ID",
    "locationId": "'"$GHL_LOCATION_ID"'",
    "name": "Eddie - $50K Soft Commit",
    "contactId": "CONTACT_ID",
    "status": "open",
    "monetaryValue": 50000
  }'
```

---

## Conversations API
*Use for: SMS/email threads with investors and brokers*

**Version header:** `2021-04-15`

| Method | Endpoint | Description | Key Fields |
|---|---|---|---|
| POST | `/conversations/` | Create a conversation | `locationId`, `contactId` |
| GET | `/conversations/:conversationId` | Get conversation details | — |
| DELETE | `/conversations/:conversationId` | Delete a conversation | — |
| GET | `/conversations/:conversationId/messages` | Get messages in a thread | `?limit=`, `?type=` |
| GET | `/conversations/messages/:id` | Get a specific message | — |
| POST | `/conversations/messages` | Send a message | `type`, `contactId`, `status` |
| POST | `/conversations/messages/outbound` | Log an outbound call | `type`, `conversationId`, `call` object |
| POST | `/conversations/messages/upload` | Upload file attachments | `locationId`, `attachmentUrls` |

### Message Types
`SMS` | `Email` | `WhatsApp` | `IG` | `FB` | `Custom` | `Call`

---

## Calendars API
*Use for: broker meetings, investor calls, appointment tracking*

**Version header:** `2021-04-15`

### Calendars
| Method | Endpoint | Description |
|---|---|---|
| GET | `/calendars` | List all calendars in a location |
| GET | `/calendars/:calendarId` | Get calendar details |
| POST | `/calendars/` | Create a calendar |
| PUT | `/calendars/:calendarId` | Update a calendar |
| DELETE | `/calendars/:calendarId` | Delete a calendar |

### Events & Appointments
| Method | Endpoint | Description |
|---|---|---|
| GET | `/calendars/events` | Get calendar events |
| POST | `/calendars/events/appointments` | Create an appointment |
| GET | `/calendars/appointments/:appointmentId` | Get appointment details |
| PUT | `/calendars/appointments/:appointmentId` | Update appointment |
| DELETE | `/calendars/events/:eventId` | Delete an event |
| GET | `/calendars/free-slots` | Get available time slots |

### Appointment Notes
| Method | Endpoint | Description |
|---|---|---|
| POST | `/calendars/appointments/:appointmentId/notes` | Add note to appointment |
| GET | `/calendars/appointments/:appointmentId/notes` | Get notes |
| PUT | `/calendars/appointments/:appointmentId/notes/:noteId` | Update note |
| DELETE | `/calendars/appointments/:appointmentId/notes/:noteId` | Delete note |

---

## Locations API
*Use for: getting your sub-account info, custom fields, tags*

**Version header:** `2021-07-28`

| Method | Endpoint | Description |
|---|---|---|
| GET | `/locations/:locationId` | Get sub-account details |
| PUT | `/locations/:locationId` | Update sub-account |
| GET | `/locations/search` | Search sub-accounts |
| GET | `/locations/:locationId/customFields` | Get all custom fields |
| POST | `/locations/:locationId/customFields` | Create a custom field |
| GET | `/locations/:locationId/tags` | Get all tags |
| POST | `/locations/:locationId/tags` | Create a tag |
| GET | `/locations/:locationId/timezones` | Get available timezones |

---

## Useful Patterns for Olive Tree

### Check your investor pipeline status
```bash
# Get all open opportunities (soft commits in progress)
curl "https://services.leadconnectorhq.com/opportunities/search?location_id=$GHL_LOCATION_ID&status=open" \
  -H "Authorization: Bearer $GHL_API_KEY" \
  -H "Version: 2021-07-28"
```

### Find a broker contact by email
```bash
curl "https://services.leadconnectorhq.com/contacts/search/duplicate?email=broker@firm.com&locationId=$GHL_LOCATION_ID" \
  -H "Authorization: Bearer $GHL_API_KEY" \
  -H "Version: 2021-07-28"
```

### Add a note after a broker call
```bash
curl -X POST "https://services.leadconnectorhq.com/contacts/CONTACT_ID/notes" \
  -H "Authorization: Bearer $GHL_API_KEY" \
  -H "Version: 2021-07-28" \
  -H "Content-Type: application/json" \
  --data '{"body": "Spoke about 20-unit deal on Main St. Sending LOI next week.", "title": "Broker Call 2026-05-27"}'
```

---

## Social Planner API
*Use for: scheduling and posting Instagram content (carousels, images, video)*

**Version header:** `2021-07-28`
**Required scope:** `social-media-posting.readonly` / `social-media-posting.write`

### Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/social-media-posting/:locationId/posts` | Create / schedule a post |
| GET | `/social-media-posting/:locationId/posts` | List all posts |
| GET | `/social-media-posting/:locationId/posts/:postId` | Get a specific post |
| DELETE | `/social-media-posting/:locationId/posts/:postId` | Delete a post |
| GET | `/social-media-posting/:locationId/oauth/instagram/start` | Start Instagram OAuth |
| GET | `/social-media-posting/:locationId/accounts` | List connected social accounts |

### Supported Platforms & Post Types

| Platform | Image | Video | Carousel | Stories | Reels |
|---|---|---|---|---|---|
| Instagram | ✅ | ✅ | ✅ | ⚠️ reminder only | ✅ |
| Facebook | ✅ | ✅ | ✅ | — | — |

### Create Post — Key Parameters

```json
{
  "locationId": "YOUR_LOCATION_ID",
  "accountIds": ["INSTAGRAM_ACCOUNT_ID"],
  "summary": "Post caption text here",
  "media": [
    { "url": "https://public-url-to-image-or-video.jpg", "type": "image" }
  ],
  "scheduleDate": "2026-05-28T09:00:00Z",
  "status": "scheduled"
}
```

For carousels, pass multiple objects in the `media` array (up to 10).
For video, set `"type": "video"` and point `url` at an MP4.

### Rate Limit
25 posts per 24 hours per Instagram account.

### Example — Schedule an Instagram carousel
```bash
curl -X POST "https://services.leadconnectorhq.com/social-media-posting/$GHL_LOCATION_ID/posts" \
  -H "Authorization: Bearer $GHL_API_KEY" \
  -H "Version: 2021-07-28" \
  -H "Content-Type: application/json" \
  --data '{
    "locationId": "'"$GHL_LOCATION_ID"'",
    "accountIds": ["IG_ACCOUNT_ID"],
    "summary": "5 things every multifamily investor should know about today'\''s rate environment. 🧵",
    "media": [
      { "url": "https://your-cdn.com/slide1.jpg", "type": "image" },
      { "url": "https://your-cdn.com/slide2.jpg", "type": "image" },
      { "url": "https://your-cdn.com/slide3.jpg", "type": "image" }
    ],
    "scheduleDate": "2026-05-28T09:00:00Z",
    "status": "scheduled"
  }'
```

### Setup — Connect Instagram to GHL
1. GHL dashboard → **Social Planner → Add Account → Instagram**
2. Use Direct Instagram Integration (no Facebook Page required for Creator/Business accounts)
3. Or via API: `GET /social-media-posting/:locationId/oauth/instagram/start`
4. Add scope `social-media-posting.write` to your Private Integration token

---

## Full API Coverage (39 Categories)

Resources not covered above but available in GHL API v2:
Blogs, Brand Boards, Businesses, Campaigns, Companies, Conversation AI, Custom Fields, Custom Menus, Custom Values, Emails, Forms, Funnels, Invoices, Knowledge Base, Marketplace, Media, Objects, Payments, Products, Proposals, Users, Voice AI, Workflows, Webhooks (50+ event types), Agent Studio, Associations

Full docs: [keith-wohnv/GHL-API-Docs](https://github.com/keith-wohnv/GHL-API-Docs) | [carlosgits/ghl-api-docs](https://github.com/carlosgits/ghl-api-docs)
