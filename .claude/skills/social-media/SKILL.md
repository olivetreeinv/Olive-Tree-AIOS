# Social Media Skill — Olive Tree Investments
**Trigger:** `/social-media`, "social media ideas", "create instagram posts", "daily posts", "what should I post today", "create social content"

---

## What this skill does

Daily Instagram content engine for Olive Tree Investments. Generates 2 posts per day:
- **Post 1:** Multifamily real estate (investors, operators, deal flow)
- **Post 2:** Single family real estate (homebuyers, retail audience, broader reach)

For each post, creates two content formats:
- **Carousel** — multi-slide educational or story-driven post (3–8 slides)
- **Video post** — titled post with motion (Reel or animated graphic, 15–60 sec)

Full pipeline: Ideation → Canva design → Instagram publish via GHL Social Planner (or Meta Graph API as fallback).

---

## References (read before every run)

| File | Why |
|---|---|
| `references/news-research.md` | Source stack, rate tables, macro event framework |
| `references/voice.md` | Brian's tone — direct, numbers-first, no filler |
| `references/canva-api.md` | Canva Connect API — design creation, export formats |
| `references/meta-api.md` | Meta Graph API — Instagram publishing endpoints |
| `references/gohighlevel-api.md` | GHL Social Planner API — scheduling and posting |
| `context/about-me.md` | Brian's identity and mission |
| `context/about-business.md` | Olive Tree's structure, markets, investor types |

> Note: Brian will provide creative examples/templates. Until examples are provided, use placeholder structure and flag where examples should go.

---

## Execution

### Step 1: Read references

Read all reference files listed above before proceeding. This grounds the content in Brian's voice, active markets, and current data.

### Step 2: Scan for today's signals

Search 3 sources in parallel:

1. `site:credaily.com multifamily` — latest headline
2. `multifamily market news [current month year]` — top signal
3. `single family housing market news [current month year]` — top signal for SF post

Pull the most relevant current headline or data point from each. Note if a major macro/geopolitical event broke this week (check `references/news-research.md` — "How Big Events Connect to Multifamily Underwriting" table).

### Step 3: Generate ideation menu

Output **2 content briefs** — one per topic. Each brief covers both formats (carousel + video).

```
## Today's Content Brief — [Date]

---

### POST 1: Multifamily
**Topic:** [What it's about]
**Angle:** [Why it matters today — data point or news hook]
**Target audience:** [Potential LP / existing investor / operator]

**Carousel concept:**
- Slide 1: Hook / bold statement or stat
- Slide 2–6: One point per slide (education, breakdown, or story)
- Slide 7 (optional): CTA / takeaway

**Video concept:**
- Title card: [Bold headline — 5 words max]
- Motion type: Text reveal / slide transition / animated stat
- Audio: [Music mood — e.g. calm/professional, upbeat/motivational]
- Duration: ~30 sec
- Script outline: [3–4 beats]

---

### POST 2: Single Family
**Topic:** [What it's about]
**Angle:** [Why it matters today]
**Target audience:** [Homebuyer / first-time investor / general RE audience]

**Carousel concept:**
- Slide 1: Hook
- Slide 2–5: Key points
- Last slide: CTA

**Video concept:**
- Title card: [Bold headline]
- Motion type: [type]
- Duration: ~20–30 sec
- Script outline: [3–4 beats]
```

Show Brian the briefs and ask: "Want me to adjust anything before I build in Canva?"

### Step 4: Build in Canva

For each approved brief, create the designs using Canva Connect API (`references/canva-api.md`).

**Carousel (multi-slide → export as individual JPEGs):**
1. Use `mcp__claude_ai_Canva__create-design-from-brand-template` or `mcp__claude_ai_Canva__generate-design` to create the design
2. Build one page per slide in the design
3. Export: `mcp__claude_ai_Canva__export-design` with format `jpg`, specifying the pages array for each slide
4. Collect public URLs for each slide image

**Video post (animated/motion → export as MP4):**
1. Create a single-page animated design in Canva
2. Use a template with motion/transition effects
3. Export: `mcp__claude_ai_Canva__export-design` with format `mp4`, quality `vertical_1080p` (for Instagram Reels format)
4. Collect public MP4 URL

**Design specs for Instagram:**
- Carousel slides: 1080×1080px (square) or 1080×1350px (portrait) — JPEG
- Reel/Video: 1080×1920px vertical — MP4, max 90 sec
- Brand colors and fonts: pull from Canva brand kit via `mcp__claude_ai_Canva__list-brand-kits`

> Until Brian provides example templates/designs, flag each design with: "Built from [template name] — replace with your brand template when examples are provided."

### Step 5: Post to Instagram

**Primary path — GHL Social Planner** (`references/gohighlevel-api.md`):

```
POST /social-media-posting/{locationId}/posts

Carousel:
{
  "locationId": "$GHL_LOCATION_ID",
  "accountIds": ["IG_ACCOUNT_ID"],
  "summary": "[Caption with hashtags]",
  "media": [
    { "url": "slide1.jpg", "type": "image" },
    { "url": "slide2.jpg", "type": "image" },
    ...
  ],
  "scheduleDate": "[today at 9:00 AM ET]",
  "status": "scheduled"
}

Video:
{
  "media": [{ "url": "reel.mp4", "type": "video" }],
  "scheduleDate": "[today at 6:00 PM ET]"
}
```

**Fallback path — Meta Graph API** (`references/meta-api.md`):
- Use if GHL rate limit (25/day) is hit or GHL is unavailable
- Carousel: create child containers → create parent → publish
- Video/Reel: resumable upload to rupload.facebook.com → publish

**Default posting schedule:**
- Post 1 (Multifamily): 9:00 AM local time
- Post 2 (Single Family): 6:00 PM local time
- Adjust based on Metricool best-time data (`mcp__claude_ai_Metricool_Instragram_MCP__getBestTimeToPostByNetwork`)

### Step 6: Confirm and log

After scheduling:
```
✅ Scheduled for today:

POST 1 (Multifamily Carousel) — 9:00 AM
Topic: [topic]
Slides: [n] | Caption: [first 60 chars...]

POST 1 (Multifamily Reel) — 9:00 AM
Duration: [x sec] | Caption: [first 60 chars...]

POST 2 (Single Family Carousel) — 6:00 PM
Topic: [topic]

POST 2 (Single Family Reel) — 6:00 PM

Want to adjust timing, swap topics, or edit captions before these go live?
```

---

## Caption Formula

Each caption follows this structure:

```
[Hook line — bold stat or question]

[2–3 short lines of value — what to know]

[Soft CTA — "Save this." / "Tag someone who needs to see this." / "Follow for more."]

[3–5 hashtags relevant to topic and market]
```

**Hashtag pools:**
- Multifamily: #multifamilyinvesting #apartmentinvesting #realestateinvesting #passiveincome #syndicationinvesting #atlantarealestate #georgiarealestate
- Single family: #realestate #homebuying #firsttimehomebuyer #housingmarket #realestatetips #atlantahomes #georgiahomes

---

## Posting Decision — GHL vs Meta API

| Situation | Use |
|---|---|
| Normal daily scheduling | GHL Social Planner |
| > 20 posts queued in GHL today | Meta Graph API |
| Need full Reel control (custom thumbnail, audio) | Meta Graph API |
| Quick test / manual schedule | GHL Social Planner |

---

## Notes

- **Brian will provide creative examples** — once provided, store them in `references/social-media-examples.md` and reference that file in Step 4 for template matching.
- Rate limits: GHL = 25 posts/day per IG account. Meta = 100 posts/day.
- Canva containers expire after 24 hours without publication — always export and store URLs before scheduling.
- Images must be JPEG for Instagram via Meta API (Canva JPG export satisfies this).
- Use Metricool analytics weekly to check which content type (carousel vs video) is outperforming and adjust the ratio.
- Never post without Brian's approval on first run. After first week of approval, can move to auto-schedule with daily summary review.
