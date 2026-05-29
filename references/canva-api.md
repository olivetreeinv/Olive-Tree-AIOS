# Canva Connect API Reference — Olive Tree Investments

Researched 2026-05-27. Source: [canva.dev/docs/connect](https://www.canva.dev/docs/connect/)
Re-use this file instead of re-researching. Update "Last verified" when endpoints change.

**Last verified:** 2026-05-27
**API Version:** v1

---

## Authentication

### How it works
Canva Connect uses **OAuth 2.0 Authorization Code flow with PKCE** (Proof Key for Code Exchange, SHA-256).

- Access tokens expire after **4 hours**
- Refresh tokens are long-lived — use them to get new access tokens without re-authorizing
- Credentials stored in `.env` — never commit `.env` to git

### Environment Variables
```
CANVA_CLIENT_ID=your_client_id
CANVA_CLIENT_SECRET=your_client_secret
CANVA_ACCESS_TOKEN=obtained_via_oauth_flow
CANVA_REFRESH_TOKEN=obtained_via_oauth_flow
```

### Key Endpoints
| Purpose | Method | URL |
|---|---|---|
| Authorize (browser) | GET | `https://www.canva.com/api/oauth/authorize` |
| Redirect URI (registered) | — | `http://127.0.0.1:8765/callback` (Canva requires IP, not `localhost`) |
| Exchange code for token | POST | `https://api.canva.com/rest/v1/oauth/token` |
| Refresh access token | POST | `https://api.canva.com/rest/v1/oauth/token` |
| Introspect token | POST | `https://api.canva.com/rest/v1/oauth/introspect` |
| Revoke token | POST | `https://api.canva.com/rest/v1/oauth/token/revoke` |

### Required headers on every API call
```
Authorization: Bearer <access_token>
Content-Type: application/json
```

### OAuth setup (one-time)
Run `python3 scripts/canva_oauth_setup.py` — opens browser, captures callback, saves tokens to `.env`.

### Refresh token (automated — run in scripts)
```python
import requests, os, base64

def refresh_canva_token():
    creds = base64.b64encode(
        f"{os.getenv('CANVA_CLIENT_ID')}:{os.getenv('CANVA_CLIENT_SECRET')}".encode()
    ).decode()
    r = requests.post(
        "https://api.canva.com/rest/v1/oauth/token",
        headers={"Authorization": f"Basic {creds}", "Content-Type": "application/x-www-form-urlencoded"},
        data={"grant_type": "refresh_token", "refresh_token": os.getenv("CANVA_REFRESH_TOKEN")}
    )
    return r.json()["access_token"]
```

---

## OAuth Scopes — Recommended for Olive Tree

| Scope | Permission |
|---|---|
| `design:content:read` | Read design content |
| `design:content:write` | Create and edit designs |
| `design:meta:read` | Read design metadata |
| `asset:read` | Read uploaded assets |
| `asset:write` | Upload assets |
| `brandtemplate:content:read` | Read brand template content (for autofill) |
| `brandtemplate:meta:read` | Read brand template metadata |
| `comment:read` | Read comments |
| `comment:write` | Create comments |
| `folder:read` | Read folders |
| `folder:write` | Create and manage folders |
| `profile:read` | Read user profile |

---

## Base URL
```
https://api.canva.com/rest/v1
```

---

## Designs API
*Use for: LP pitch decks, deal summaries, investor updates*

| Method | Endpoint | Description |
|---|---|---|
| POST | `/designs` | Create a new design |
| GET | `/designs` | List designs |
| GET | `/designs/{designId}` | Get a specific design |
| GET | `/designs/{designId}/pages` | Get pages of a design |
| GET | `/designs/{designId}/export-formats` | Get available export formats |

### Create a design
```json
POST /designs
{
  "design_type": { "type": "presentation" },
  "title": "Olive Tree - [Deal Name] Investment Summary"
}
```

---

## Brand Templates API
*Use for: autofilling LP pitch deck templates with deal data*

| Method | Endpoint | Description |
|---|---|---|
| GET | `/brand-templates` | List all brand templates |
| GET | `/brand-templates/{brandTemplateId}` | Get template details |
| GET | `/brand-templates/{brandTemplateId}/dataset` | Get autofill fields available |

### Get autofill dataset (what fields the template accepts)
```bash
curl https://api.canva.com/rest/v1/brand-templates/$TEMPLATE_ID/dataset \
  -H "Authorization: Bearer $CANVA_ACCESS_TOKEN"
```

---

## Autofill API
*Use for: auto-populating LP pitch deck template with deal-specific data*

| Method | Endpoint | Description |
|---|---|---|
| POST | `/autofills` | Create an autofill job |
| GET | `/autofills/{jobId}` | Get autofill job status/result |

### Create an autofill job (fills template with deal data)
```json
POST /autofills
{
  "brand_template_id": "YOUR_TEMPLATE_ID",
  "title": "Olive Tree - Lebanon TN Deal Summary",
  "data": {
    "deal_name": { "type": "text", "text": "The Reserve at Lebanon" },
    "market": { "type": "text", "text": "Lebanon, TN" },
    "units": { "type": "text", "text": "40" },
    "price_per_unit": { "type": "text", "text": "$130,000" },
    "pref_return": { "type": "text", "text": "6%" },
    "target_irr": { "type": "text", "text": "18.21%" },
    "equity_multiple": { "type": "text", "text": "2.09x" }
  }
}
```

---

## Exports API
*Use for: exporting pitch decks as PDF to attach to investor emails*

| Method | Endpoint | Description |
|---|---|---|
| POST | `/exports` | Create an export job |
| GET | `/exports/{exportId}` | Get export status + download URL |

### Export a design as PDF
```json
POST /exports
{
  "design_id": "YOUR_DESIGN_ID",
  "format": {
    "type": "pdf",
    "export_quality": "pro"
  }
}
```

### Poll until complete, then download
```python
import requests, time, os

def export_design_as_pdf(design_id, access_token):
    headers = {"Authorization": f"Bearer {access_token}"}
    # Start export job
    r = requests.post(
        "https://api.canva.com/rest/v1/exports",
        json={"design_id": design_id, "format": {"type": "pdf", "export_quality": "pro"}},
        headers=headers
    )
    job_id = r.json()["job"]["id"]
    # Poll until done
    while True:
        status = requests.get(f"https://api.canva.com/rest/v1/exports/{job_id}", headers=headers).json()
        if status["job"]["status"] == "success":
            return status["job"]["result"]["url"]  # Download URL
        time.sleep(2)
```

---

## Assets API
*Use for: uploading property photos into pitch deck designs*

| Method | Endpoint | Description |
|---|---|---|
| POST | `/assets` | Upload a new asset (file) |
| GET | `/assets/{assetId}` | Get asset details |
| PATCH | `/assets/{assetId}` | Update asset metadata |
| DELETE | `/assets/{assetId}` | Delete an asset |
| POST | `/asset-uploads` | Upload by URL |

### Upload a property photo
```python
requests.post(
    "https://api.canva.com/rest/v1/assets",
    headers={"Authorization": f"Bearer {token}", "Asset-Upload-Metadata": '{"name_base64": "..."}'},
    data=open("property_photo.jpg", "rb")
)
```

---

## Folders API
*Use for: organizing designs by deal or market*

| Method | Endpoint | Description |
|---|---|---|
| POST | `/folders` | Create a folder |
| GET | `/folders/{folderId}/items` | List items in a folder |
| POST | `/folders/{folderId}/items/move` | Move a design into a folder |
| DELETE | `/folders/{folderId}` | Delete a folder |

---

## Users API
```bash
# Verify your access token works
curl https://api.canva.com/rest/v1/users/me \
  -H "Authorization: Bearer $CANVA_ACCESS_TOKEN"
```

---

## Useful Patterns for Olive Tree

### Full deal pitch deck workflow
```
1. Broker sends listing → market research → PURSUE
2. Pull deal data (unit count, price/unit, market, returns)
3. POST /autofills → fill LP pitch deck template with deal data
4. Poll autofill job until complete → get new design_id
5. POST /exports → export as PDF
6. Poll export job → get download URL
7. Attach PDF to Gmail via Gmail API → send to investor list
```

### Folder structure in Canva
```
Olive Tree Investments/
├── Active Deals/
│   ├── Lebanon TN - The Reserve/
│   └── [next deal]/
├── Templates/
│   └── LP Pitch Deck Template
└── Archives/
```

---

## Quick Test — Verify Credentials
```bash
source .env
curl https://api.canva.com/rest/v1/users/me \
  -H "Authorization: Bearer $CANVA_ACCESS_TOKEN" \
  -H "Content-Type: application/json"
```

Expected: `{"team_user": {"user_id": "...", "team_id": "..."}}`
Note: Canva Connect API returns `team_user` (not `user`). 200 = token valid.

---

## Webhooks (optional — for automation triggers)
```
POST /webhooks  →  create a webhook
Events: design.update, comment.create, folder.update, team.user.pre-deactivate
```
