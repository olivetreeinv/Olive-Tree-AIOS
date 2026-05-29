# Meta Graph API — Instagram Publishing Reference
**Last updated:** 2026-05-28
**Owner:** Brian Norton, CEO
**Purpose:** Technical reference for posting to Instagram via Meta Graph API. Used by the social media skill. Re-use this file instead of re-researching.

**API Version:** v21.0 (current as of May 2026)

---

## Authentication

### Access Token Types
- **Instagram User Access Token** (preferred) — via Instagram Login
- **Facebook Page Access Token** — via Facebook Login

### Required Permissions
| Scope | Required for |
|---|---|
| `instagram_business_content_publish` | Publishing all content types |
| `instagram_basic` | Reading account info |
| `pages_read_engagement` | Required if using Facebook Login path |

### Where to Get Tokens
1. Go to [developers.facebook.com](https://developers.facebook.com)
2. Create an App → Business type
3. Add Instagram Graph API product
4. Generate a User Access Token with the scopes above
5. Exchange for a Long-Lived Token (60-day expiry — refresh before expiry)
6. Store in `.env` as `META_ACCESS_TOKEN` and `META_IG_USER_ID`

### Environment Variables to Add
```
META_ACCESS_TOKEN=your_long_lived_token
META_IG_USER_ID=your_instagram_user_id
```

---

## Base URLs

| Use | Host |
|---|---|
| All API calls | `https://graph.instagram.com` or `https://graph.facebook.com` |
| Video uploads (Reels) | `https://rupload.facebook.com/ig-api-upload/<container_id>` |

---

## Supported Content Types

| Type | `media_type` | Notes |
|---|---|---|
| Single image | *(default)* | JPEG only |
| Single video | `VIDEO` | MP4 recommended |
| Reel | `REELS` | Max 90 seconds via API |
| Story | `STORIES` | 15 sec video or image |
| Carousel | `CAROUSEL` | Up to 10 mixed images/videos |

---

## Publishing Flows

### 1. Single Image Post
```
POST /{IG_USER_ID}/media
  → image_url (public JPEG URL)
  → caption
  → access_token

Returns: container_id

POST /{IG_USER_ID}/media_publish
  → creation_id = container_id
  → access_token

Returns: media_id (published)
```

### 2. Carousel Post (multi-image)
```
# Step 1: Create a container for EACH slide (up to 10)
POST /{IG_USER_ID}/media
  → image_url = "https://public-url/slide1.jpg"
  → is_carousel_item = true
  → access_token
→ Returns: child_container_id_1

# Repeat for each slide → child_container_id_2, _3, etc.

# Step 2: Create parent carousel container
POST /{IG_USER_ID}/media
  → media_type = CAROUSEL
  → children = "child_id_1,child_id_2,child_id_3"
  → caption = "Post caption here"
  → access_token
→ Returns: carousel_container_id

# Step 3: Publish
POST /{IG_USER_ID}/media_publish
  → creation_id = carousel_container_id
  → access_token
→ Returns: published_media_id
```

### 3. Reel (Video with Motion)
```
# Step 1: Create container with resumable upload flag
POST /{IG_USER_ID}/media
  → media_type = REELS
  → upload_type = resumable
  → caption = "Post caption"
  → access_token
→ Returns: container_id

# Step 2: Upload video file
POST https://rupload.facebook.com/ig-api-upload/{container_id}
  → Headers: Authorization, offset=0, file_size
  → Body: raw video bytes (MP4)

# Step 3: Check upload status
GET /{container_id}?fields=status_code

# Step 4: Publish (when status_code = FINISHED)
POST /{IG_USER_ID}/media_publish
  → creation_id = container_id
→ Returns: published_media_id
```

---

## Key Parameters

| Parameter | Type | Description |
|---|---|---|
| `image_url` | string | Publicly accessible JPEG URL |
| `video_url` | string | Publicly accessible MP4 URL (non-resumable) |
| `media_type` | string | `VIDEO`, `REELS`, `STORIES`, `CAROUSEL` |
| `is_carousel_item` | boolean | Set `true` for each carousel child |
| `children` | string | Comma-separated child container IDs |
| `caption` | string | Post text (hashtags OK) |
| `upload_type` | string | `resumable` for Reels video upload |
| `alt_text` | string | Accessibility text for images |
| `access_token` | string | Your long-lived user token |

---

## Rate Limits

| Limit | Value |
|---|---|
| Posts per 24 hours | 100 (carousels count as 1) |
| Check current usage | `GET /{IG_USER_ID}/content_publishing_limit` |

Container expiry: **24 hours** — publish within 24 hrs of creating a container or it expires.

---

## Media Requirements

| Type | Format | Max Size | Notes |
|---|---|---|---|
| Image | JPEG only | — | Must be publicly accessible URL |
| Video (standard) | MP4 | — | Public URL |
| Reel video | MP4 | 90 sec max via API | Resumable upload to rupload.facebook.com |
| Carousel child image | JPEG | Up to 10 items | Each needs its own container first |

---

## vs. GoHighLevel Social Planner

Both can post to Instagram. Choose based on use case:

| Factor | Meta Graph API (direct) | GHL Social Planner |
|---|---|---|
| Setup complexity | Higher (token management) | Lower (OAuth in GHL UI) |
| Scheduling | Manual (you set publish time) | Built-in scheduler |
| Reel publishing | Full support | Full support |
| Carousel | Full support | Full support |
| Rate limit | 100/day | 25/day |
| Best for | Maximum control, automation scripts | Simpler scheduling, visual queue |

**Recommendation for Olive Tree:** Use GHL Social Planner for day-to-day scheduled posts. Use Meta Graph API directly if GHL rate limits become a constraint or for custom automation scripts.

---

## Useful Links

- [Meta Instagram Publishing Docs](https://developers.facebook.com/docs/instagram-platform/content-publishing/)
- [Meta for Developers — App Setup](https://developers.facebook.com/apps/)
- [Instagram Graph API Media Reference](https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media/)
- [Reels Publishing Guide](https://postproxy.dev/blog/instagram-reels-api-publishing-guide/)
