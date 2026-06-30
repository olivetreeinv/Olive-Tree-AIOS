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
| `references/social-media-examples.md` | **Read first.** Brian's real hook formulas, voice patterns, topic pillars, and content blocks — extracted from 12 published newsletters. Every brief must use these patterns. |
| `references/news-research.md` | Source stack, rate tables, macro event framework |
| `references/voice.md` | Brian's tone — direct, numbers-first, no filler |
| `references/higgsfield-cli.md` | Higgsfield CLI — AI image/video generation for Reels and carousel visuals |
| `references/canva-api.md` | Canva Connect API — design creation, export formats |
| `references/meta-api.md` | Meta Graph API — Instagram publishing endpoints |
| `references/gohighlevel-api.md` | GHL Social Planner API — scheduling and posting |
| `context/about-me.md` | Brian's identity and mission |
| `context/about-business.md` | Olive Tree's structure, markets, investor types |

---

## Execution

### Step 1: Read references

Read all reference files listed above before proceeding. This grounds the content in Brian's voice, active markets, and current data.

### Step 2: Scan for today's signals

Execute in this order. Do not skip tiers. Record the strongest signal from each.

#### Tier 1 — Pull first, every run (in priority order)

**1. CRE Daily** — `site:credaily.com multifamily`
Pull the top headline. Extract: headline, key stat or data point, why it matters to a multifamily investor or LP.

**2. GlobeSt** — `site:globest.com multifamily OR site:globest.com/sectors/multifamily`
Focus on Southeast/Sun Belt stories. Extract: headline, market, key number.

**3. CoStar** — `site:costar.com multifamily vacancy OR rent growth OR cap rate`
This is the data anchor. Extract: a specific number (vacancy %, rent growth %, cap rate range) that can be used as the carousel hook stat.

#### Tier 2 — Pull only if a macro event broke this week

Check: Is there a Fed decision, rate move, tariff, jobs report, inflation print, war/geopolitical event, or major housing legislation in the news this week?

If YES → pull from:
- **Reuters** or **AP News** — `site:reuters.com real estate OR rates` — the macro headline
- **Bloomberg** — `site:bloomberg.com commercial real estate OR treasury` — rate/credit depth
- **WSJ** — `site:wsj.com real estate OR economy` — institutional angle

Cross-reference against the "How Big Events Connect to Multifamily Underwriting" table in `references/news-research.md` and note the CRE impact to flag.

If NO macro event → skip Tier 2.

#### Rate snapshot — pull every run

Search for current rates from these two sources:
- **SF rates:** `site:mortgagenewsdaily.com 30 year mortgage rate today` — pull the current 30-yr fixed rate
- **MF rates:** `site:commercialloandirect.com multifamily loan rates` or `site:apartmentloanstore.com rates` — pull Fannie Mae and bridge loan current ranges

Compare to the rate table in `references/news-research.md`. Note if rates moved since last update — if they moved more than 0.25%, that's a signal in itself.

#### Source pairing — match signal to content angle

After pulling all signals, use this table from `references/news-research.md` to match the strongest signal to the right content angle:

| If the strongest signal is... | Use this angle |
|---|---|
| Rate move / Fed decision | "What [X]% means for your portfolio right now" |
| Southeast/Sun Belt data | "Why the Southeast is outperforming — and where we're looking" |
| Vacancy or rent growth data | "The market just shifted. Here's what it means for operators." |
| Capital flow / migration data | "Where smart money actually went. Follow the capital." |
| CRE loan maturity / distress | "[$X billion] in loans mature this year. Here's the opportunity." |
| Homebuyer affordability | "The window just opened for buyers. Here's the data." |
| Tax/policy change | "This policy change could put money back in your portfolio." |

#### Output of Step 2

Before moving to Step 3, state:

```
## Signal Report — [Date]

**Tier 1 signals:**
- CRE Daily: [headline] | Key stat: [number]
- GlobeSt: [headline] | Market: [region] | Key stat: [number]
- CoStar: [data point] | [what it means]

**Tier 2 (macro event this week? Y/N):**
- [Event if applicable] | CRE impact: [from the table]

**Rate snapshot:**
- 30-yr fixed (SF): [X]% ([up/down/flat] from last update)
- Fannie Mae (MF): [X–X]%
- Bridge: [X–X]%

**Strongest signal:** [one sentence]
**Matched content angle:** [from pairing table]
**Suggested pillar — Post 1 (MF):** [pillar name]
**Suggested pillar — Post 2 (SF):** [pillar name]

Confirm these topics or override before I build the briefs.
```

Wait for Brian's confirmation before proceeding to Step 3.

### Step 3: Generate ideation menu

**Before writing any brief, apply these rules from `references/social-media-examples.md`:**

**Hook formula — pick one per post:**
1. **Stat + Consequence** — "[Specific number]. [What happens next]." ← most used
2. **Contrarian** — "While [most people do X], [smart money does Y]."
3. **Seasonal/Timing** — "[Specific time] is [the opportunity]. Here's why."
4. **Direct Question** — "[Stat or fact]. [Question that puts reader in it]."

**Generate 5 hook variants** for slide 1 before picking the strongest. Apply the scroll test: "Would Brian stop for this?" Numbers must be specific — no vague language.

**Cross-genre borrowing — apply one structure per post:**
Pick a format from an adjacent genre and map it to the RE topic:
- Before/After (fitness/design) → Property or NOI transformation
- Journey arc (startup stories) → Deal case study told as a narrative
- Myth vs. Fact (personal finance) → "Conventional wisdom says X. Data says Y."
- Timed reveal (travel/nature) → "Wait for slide 5" tension build
- Numbered breakdown (fitness) → "5 numbers every LP must know"

**"Translation:" rule** — always include one slide that converts data to plain English.
**Urgency close** — final slide ends with: "Position now." / "The window closes when [event]." / "Are you?"

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

### Step 4: Build visuals

Read `references/higgsfield-cli.md` before this step.

**Carousel (multi-slide → export as individual JPEGs) — Canva:**
1. Use `mcp__claude_ai_Canva__create-design-from-brand-template` or `mcp__claude_ai_Canva__generate-design` to create the design
2. Build one page per slide in the design
3. Export: `mcp__claude_ai_Canva__export-design` with format `jpg`, specifying the pages array for each slide
4. Collect public URLs for each slide image

**Carousel hero image — Higgsfield (optional enhancement):**
- If Brian provides a property photo, run it through Higgsfield to produce a cinematic hero for Slide 1
- Pattern: `hf upload create ./photo.jpg` → `hf generate create nano_banana_2 --prompt "..." --image <uuid> --wait`
- Always run `hf generate cost nano_banana_2 --prompt "..."` first and show Brian the credit cost before proceeding

**Video post / Reel — Higgsfield (primary for AI-generated video):**
1. `hf account status` — confirm credit balance
2. `hf model list --video` — get current video model names
3. Upload source asset: `hf upload create ./asset.jpg`
4. Estimate cost: `hf generate cost <video_model> --prompt "..."`
5. Generate: `hf generate create <video_model> --prompt "..." --image <uuid> --wait --wait-timeout 20m`
6. Collect output MP4 URL from result

**Video post (Canva fallback — use when Higgsfield credits are low):**
1. Create a single-page animated design in Canva
2. Export: `mcp__claude_ai_Canva__export-design` with format `mp4`, quality `vertical_1080p`

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
