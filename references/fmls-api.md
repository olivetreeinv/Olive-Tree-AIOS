# FMLS API Reference — Olive Tree Investments

Researched 2026-06-08. Source: FMLS Marketplace docs, Bridge Interactive developer portal, RESO Web API standard.
Re-use this file instead of re-researching. Update "Last verified" when credentials are obtained.

**Last verified:** 2026-06-11 (credentials active — FMLS_API_TOKEN + FMLS_DATASET_ID in .env)

---

## What FMLS Is

First Multiple Listing Service — Georgia's primary MLS. Covers Atlanta metro and surrounding markets including all 10 of Olive Tree's active buy-box zips (Chamblee, Smyrna, Alpharetta, and surrounding GA markets).

---

## API Platform

FMLS uses **Bridge Interactive** as its data distribution platform. The API is RESO Web API certified (Platinum level) — RESTful, JSON/OData-based, RESO Data Dictionary compliant.

Two separate portals:
- **Bridge Data Output** — the actual listing data API (what scripts use)
- **FMLS Member API** — member-facing portal at `api.fmls.com` (member tools, not listing data)

---

## Base URL

```
https://api.bridgedataoutput.com/api/v2/OData/{dataset_id}/Property
```

`{dataset_id}` is assigned when you get access. Likely `FMLS` or an alphanumeric code — confirm after signup.

---

## Authentication

Bearer token from Bridge Interactive dashboard. Use the **Server Token** directly — no OAuth exchange needed.

```bash
Authorization: Bearer YOUR_SERVER_TOKEN
```

Stored in `.env` as `FMLS_API_TOKEN`. Dataset ID (`fmls`) as `FMLS_DATASET_ID`.
Client ID stored as `FMLS-CLIENT_ID` (not needed for API calls — kept for reference).

---

## Key Endpoints

### Search multifamily listings
```
GET https://api.bridgedataoutput.com/api/v2/OData/{dataset_id}/Property
  ?access_token={token}
  &$filter=PropertyType eq 'Residential Income' and StandardStatus eq 'Active'
  &$select=ListingKey,ListPrice,UnparsedAddress,PostalCode,BedroomsTotal,UnitCount,ListAgentEmail,ListAgentFullName,ListOfficeName,ListingUrl
  &$top=200
```

**PropertyType values for multifamily:**
- `ResidentialIncome` — RESO standard for income-producing residential (multifamily, 2–4 units, apartment buildings)
- `MultiFamily` — some MLSs use this instead; try both if `ResidentialIncome` returns nothing

### Filter by buy-box zip codes
```
$filter=PropertyType eq 'Residential Income'
  and StandardStatus eq 'Active'
  and PostalCode in ('30341','30080','30005','37207','37115','37408','37087','35801','35205','35806')
```

### Filter by unit count (15–50 units)
```
$filter=PropertyType eq 'Residential Income'
  and StandardStatus eq 'Active'
  and UnitCount ge 15
  and UnitCount le 50
```

### Full buy-box query (zip + unit count + active)
```
GET https://api.bridgedataoutput.com/api/v2/OData/{dataset_id}/Property
  ?access_token={token}
  &$filter=PropertyType eq 'Residential Income'
    and StandardStatus eq 'Active'
    and PostalCode in ('30341','30080','30005','37207','37115','37408','37087','35801','35205','35806')
    and UnitCount ge 15
    and UnitCount le 50
  &$select=ListingKey,ListPrice,UnparsedAddress,PostalCode,UnitCount,YearBuilt,ListAgentEmail,ListAgentFullName,ListOfficeName,ListingUrl,ModificationTimestamp
  &$orderby=ModificationTimestamp desc
  &$top=50
```

### Get a single listing by key
```
GET https://api.bridgedataoutput.com/api/v2/OData/{dataset_id}/Property('{ListingKey}')
  ?access_token={token}
```

---

## Useful Fields (RESO Data Dictionary)

| Field | Description |
|---|---|
| `ListingKey` | Unique listing ID |
| `ListPrice` | Asking price |
| `UnparsedAddress` | Full address string |
| `PostalCode` | Zip code |
| `UnitCount` | Number of units |
| `BedroomsTotal` | Total bedrooms |
| `YearBuilt` | Vintage |
| `GrossIncome` | Annual gross income (if populated) |
| `NetOperatingIncome` | NOI (if populated) |
| `CapRate` | Cap rate (if populated — often blank, verify) |
| `StandardStatus` | `Active`, `Pending`, `Closed` |
| `ListAgentEmail` | Broker email — use for Brokers List auto-add |
| `ListAgentFullName` | Broker name |
| `ListAgentDirectPhone` | Broker phone |
| `ListOfficeName` | Brokerage |
| `ListingUrl` | Direct link to listing |
| `ModificationTimestamp` | Last updated — use for `--days 7` delta queries |

---

## Delta Queries (new/updated listings since last run)

```
$filter=ModificationTimestamp gt {ISO_DATETIME}
  and PropertyType eq 'Residential Income'
  and StandardStatus eq 'Active'
```

Example: listings updated in last 7 days
```python
from datetime import datetime, timedelta
cutoff = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
# $filter=ModificationTimestamp gt {cutoff} and ...
```

---

## Access / Setup

**Brian is an FMLS member broker — application fee is waived.**

Steps to get credentials:
1. Go to [FMLS Marketplace](https://www.fmls.com/marketplace-info)
2. Register as a member brokerage requesting data access for internal brokerage tools
3. Sign data access agreement
4. Bridge Interactive issues `access_token` and `dataset_id`
5. Add both to `.env`: `FMLS_API_TOKEN` and `FMLS_DATASET_ID`

Contact: **Data@FMLS.com** | 678-904-0446

Full member API docs PDF: https://api.fmls.com/img/documentation/FMLS_MemberAPI.pdf

---

## Integration Plan (once credentials are in .env)

Replace or supplement `broker_search.py` email parsing with a direct FMLS pull:

```bash
python3 scripts/broker_search.py --source fmls --days 7
```

Logic:
1. Query FMLS API with full buy-box filter (zip + unit count + active)
2. Delta filter on `ModificationTimestamp` for `--days N`
3. Parse listing fields directly — no email parsing, no availability check needed (FMLS data is authoritative)
4. Same dedup + sheet logging as current flow
5. Broker extraction: if `ListAgentEmail` appears on 2+ listings → auto-add to Brokers List

This would make Phase 1 of `/lets-get-to-work` significantly more reliable than email alert parsing.
