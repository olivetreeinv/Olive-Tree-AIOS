# Marketing Skill — Olive Tree Investments
**Trigger:** `/marketing`, "write the newsletter", "weekly content", "create campaign", "newsletter", "blog ideas", "what should I write this week"

---

## What this skill does

Weekly content engine — one run produces the **newsletter campaign** (MF story + SF story → GHL draft) and the **Instagram posts** (carousels derived from that same newsletter, not re-scanned). One signal scan. One source of truth. Everything cohesive.

Two modes:
- **Full run** (default): Signal scan → newsletter draft → GHL campaign → IG posts rendered + scheduled
- **Newsletter only** (`--newsletter-only`): Stops after GHL draft

Nothing sends automatically. GHL draft = Brian reviews + clicks Send in GHL. IG posts = `draft: true` in Metricool until Brian approves.

---

## References (read before every run)

| File | Why |
|---|---|
| `references/social-media-examples.md` | **Read first.** Brian's 4 hook formulas, preview text patterns, newsletter opening formula, 7 pillars, 3 content blocks. Every story must use these. |
| `references/news-research.md` | Source stack, rate tables, macro event framework, angle pairings |
| `references/voice.md` | Brian's tone — direct, numbers-first, no filler, signs -Brian |
| `references/buy-box.md` | 13 active markets — stay consistent with active geographies |
| `context/about-me.md` | Brian's background and mission |
| `context/about-business.md` | Olive Tree's structure, markets, investor types |

---

## Execution

### Step 1: Read references

Read all six files above before proceeding.

---

### Step 2: Scan live signals (once — shared by newsletter + IG)

**Tier 1 — pull every run (in parallel):**

1. **CRE Daily** — `site:credaily.com multifamily` — top headline + key stat
2. **GlobeSt** — `site:globest.com multifamily` — Southeast/Sun Belt focus, key number
3. **CoStar** — `CoStar multifamily vacancy rent growth [year]` — data anchor (vacancy %, rent growth %)
4. **Southeast signal** — `multifamily Georgia Tennessee Alabama [year] rent apartment`

**Rate snapshot — pull every run:**
- SF: `site:mortgagenewsdaily.com 30 year mortgage rate today`
- MF: `site:commercialloandirect.com multifamily loan rates` or `site:apartmentloanstore.com rates`

Compare to `references/news-research.md` rate tables. Flag if >0.25% move or table is >7 days old.

**Tier 2 — pull only if a macro event broke this week:**

Check: Fed decision, rate move, tariff, jobs report, inflation print, war/geopolitical event, major housing legislation?

If YES → pull Reuters/AP (macro headline) + Bloomberg (rate/credit depth). Use the "How Big Events Connect to Multifamily Underwriting" table in `references/news-research.md` to identify the CRE angle. If NO → skip.

**Output Signal Report before proceeding:**

```
## Signal Report — [Date]

**Tier 1:**
- CRE Daily: [headline] | [key stat]
- GlobeSt: [headline] | [market] | [key stat]
- CoStar: [data point] | [implication]
- Southeast: [headline or data point]

**Tier 2 (macro event this week? Y/N):**
- [Event + CRE impact] OR N/A

**Rate snapshot:**
- 30-yr fixed (SF): [X]% ([up/down/flat] vs. reference)
- Fannie Mae (MF): [X–X]%
- Rate table last updated: [date] — [flag if stale]

**Strongest signal:** [one sentence]
**MF story angle:** [pillar + why now]
**SF story angle:** [pillar + why now]

Confirm angles or override before I draft.
```

**Wait for Brian's confirmation before Step 3.**

---

### Step 3: Draft the newsletter (MF story + SF story)

Structure each story using Brian's newsletter opening formula from `references/social-media-examples.md`:

```
[Month] brings [the thing most people overlook or get backward].

Here's what's happening: [1–2 specific data points]

Here's what the market isn't telling you: [the contrarian read]

Translation: [plain English implication for the reader]
```

**Subject line:** generate 3 variants using the 4 formulas from `references/social-media-examples.md`. Pick the strongest.

**Preview text:** 3–8 words. Stat or sharp consequence. Ends "Position now." when appropriate.

**MF Story** (pillars 1–5, 7 — investor/operator audience):
- 400–600 words in Brian's voice
- Numbers always specific — never "many investors", always "51% of investors"
- Contrarian setup: "While most... the data says..."
- "Translation:" move before the close
- Urgency close: "Position now." / "The window closes when [event]."
- Signs off: `-Brian`

**SF Story** (pillar 6 — homebuyer/retail audience):
- 250–350 words — shorter, simpler
- Rate environment + affordability + seasonal timing angle
- Same voice, lighter on operator jargon

**Output:**

```
## Newsletter Draft — [Month YYYY]

**Subject:** [chosen subject line]
**Preview text:** [3–8 words]

---

### MF Story
[full draft — 400–600 words]

---

### SF Story
[full draft — 250–350 words]
```

Show draft. Ask: "Approve to create the GHL draft campaign, or any edits first?"

**Wait for Brian's approval before Step 4.**

---

### Step 4: Create GHL draft campaign

**Endpoint:**
```
POST https://services.leadconnectorhq.com/emails/public/v2/locations/{locationId}/campaigns/email-campaign
```

**Headers:**
```
Authorization: Bearer $GHL_API_KEY
Version: 2021-07-28
Content-Type: application/json
```

**Payload:**
```json
{
  "name": "[Month YYYY] Newsletter",
  "editorType": "builder",
  "timeZone": "America/New_York",
  "userId": "MUh3VFRYXFNyRGYpj38n",
  "subject": "[chosen subject line]",
  "templateId": "683b400fcba7be06e0d38c5d",
  "editorContent": {
    "editorData": {
      "content": "[newsletter HTML body]"
    }
  }
}
```

Creates as `status: draft` — does NOT send to any contacts.

> ⚠️ **Send is NOT available via API.** Brian must send manually: GHL → Marketing → Email Campaigns → Drafts → Send.
> ⚠️ **Delete is NOT available via API** for v2-created campaigns. Cleanup is manual in GHL.

Confirm once created:
```
✅ GHL draft campaign created: "[Month YYYY] Newsletter"
GHL → Marketing → Email Campaigns → Drafts
Nothing has been sent.
```

If `--newsletter-only` flag: stop here.

---

### Step 5: Derive IG briefs from newsletter

**Do NOT re-scan signals.** Use the approved newsletter content as source of truth.

Map each story to a carousel spec using the carousel-adaptation rules in `references/social-media-examples.md`:

**Post 1 (MF) — from the MF story:**
- Cover slide: newsletter subject line adapted as bold hook + `cover_query` for Pexels
- Body slides (2–4): the 3 strongest data points / contrarian moves from the MF story, one per slide
- Translation slide: the "Translation:" sentence from the story in bold
- CTA slide (inverted olive): "Position now." + "Follow @olivetreeinv"

**Post 2 (SF) — from the SF story:**
- Cover slide: SF hook + `cover_query`
- Body slides (2–4): top 3 points
- CTA slide: seasonal or rate close

**Output:**

```
## IG Post Briefs — [Date]

### POST 1: Multifamily
**Slide spec (JSON-ready):**
[
  {"type": "cover", "kicker": "MARKET INTEL", "title": "[hook]", "body": "[subhook]", "cover_query": "[pexels search]"},
  {"type": "content", "kicker": "[LABEL]", "title": "[point]", "body": "[support line]"},
  {"type": "content", "kicker": "TRANSLATION", "title": "[plain English]", "body": ""},
  {"type": "cta", "kicker": "OLIVE TREE", "title": "[urgency close]", "body": "Follow @olivetreeinv"}
]
**Caption:** [hook] / [2–3 value lines] / [soft CTA] / [3–5 hashtags]

### POST 2: Single Family
[same structure]
```

Show briefs. Ask: "Approve to render and schedule?"

**Wait for Brian's approval before Step 6.**

---

### Step 6: Render → host → schedule → log

**Cover art — source in this order (anti-slop ladder):**

1. **Brian's own art (best)** — Luma Dream Machine board (`app.lumalabs.ai/boards`), Midjourney, or ChatGPT images. Brian downloads the image; pass its path as `"cover_image"` in the slide spec JSON. Manual by design — no Luma API integration (usage-billed, not worth automating at current volume).
2. **Higgsfield** — `python3 scripts/higgsfield_hero.py --prompt "[subject]" --out output/carousel/[slug]/hero.png` (2 credits/image; checks balance first, falls back automatically). Then pass as `cover_image`.
3. **Pexels via `cover_query` (last resort)** — query must name a real, specific place or scene from the story ("Atlanta Midtown skyline dusk", not "city buildings" or "business meeting"). Generic stock is the #1 slop tell.

Prompt recipe for 1 & 2: real place from the story + light/airy editorial photo language, vertical 4:5. Never text-in-image, never people's faces (AI hands/faces = instant slop flag).

**Render** (HTML renderer — primary):
```bash
python3 scripts/carousel_render_html.py --json /tmp/slides_mf.json \
    --out output/carousel/[date]-mf
python3 scripts/carousel_render_html.py --json /tmp/slides_sf.json \
    --out output/carousel/[date]-sf
```

Show rendered PNGs to Brian. Ask: "Approve to upload and schedule?"

**Host** (once approved):
```bash
python3 scripts/social_drive_upload.py \
    --slides-dir output/carousel/[date]-mf \
    --date YYYY-MM-DD --title "MF Story Title"
# → prints lh3.googleusercontent.com/d/<id> URLs in slide order

python3 scripts/social_drive_upload.py \
    --slides-dir output/carousel/[date]-sf \
    --date YYYY-MM-DD --title "SF Story Title"
```

**Best time:**
```
mcp__claude_ai_Metricool_Instragram_MCP__getBestTimeToPostByNetwork
  network: instagram, brandId: 6192268, timezone: America/New_York
```
Default: Post 1 (MF) = 9:00 AM ET | Post 2 (SF) = 6:00 PM ET. Adjust if Metricool data differs significantly.

**Schedule** (Metricool MCP — primary):
```
mcp__claude_ai_Metricool_Instragram_MCP__createScheduledPost
  blogId: 6192268
  info: {
    text: "<caption>",
    media: ["<lh3_url_1>", "<lh3_url_2>", ...],   ← in slide order
    providers: [{"network": "instagram"}],
    instagramData: {"type": "POST"},
    publicationDate: {dateTime: "YYYY-MM-DDTHH:mm:ss", timezone: "America/New_York"},
    autoPublish: true,
    draft: true   ← always draft on first run
  }
```

**Fallback** (if Metricool fails): GHL Social Planner → `POST /social-media-posting/$GHL_LOCATION_ID/posts` — see `references/gohighlevel-api.md`.

**Log** (once per post):
```bash
python3 scripts/social_sheet.py \
    --date YYYY-MM-DD --title "Title" --type "MF Carousel" \
    --topic "..." --caption "..." \
    --slides "<drive_folder_url>" --metricool "<plannerUrl>" \
    --status Draft
```

**Final confirm:**
```
✅ Weekly content pipeline complete — [Date]

NEWSLETTER
GHL draft: "[Month YYYY] Newsletter"
GHL → Marketing → Email Campaigns → Drafts — nothing sent

INSTAGRAM
Post 1 (MF) — [time] ET | [N] slides | draft in Metricool
Post 2 (SF) — [time] ET | [N] slides | draft in Metricool

Nothing has been sent or published.
Approve each in GHL and Metricool when ready.
```

---

## Caption formula

```
[Hook line — specific stat or question]

[2–3 short lines of value]

[Soft CTA — "Save this." / "Tag someone who needs to see this."]

[3–5 hashtags]
```

**Hashtag pools:**
- MF: `#multifamilyinvesting #apartmentinvesting #realestateinvesting #passiveincome #syndicationinvesting #atlantarealestate #georgiarealestate`
- SF: `#realestate #homebuying #firsttimehomebuyer #housingmarket #realestatetips #atlantahomes #georgiahomes`

---

## Key IDs

| Item | Value |
|---|---|
| GHL Location ID | `$GHL_LOCATION_ID` (SLq7B2pldVzfQLKjGpvw) |
| Newsletter template | `683b400fcba7be06e0d38c5d` |
| Campaign userId | `MUh3VFRYXFNyRGYpj38n` |
| Metricool brandId/blogId | `6192268` |
| IG Posts sheet | `1wSdYytgnEZrLGiwVarA-OIN2OfJ1WOlB7MOYBMdRKrQ` |
| Social Drive folder | `1a46dKGTj8ggEWbTaRN-TuZv_EL__a6AY` |

---

## Notes

- **Rate tables age fast.** Flag if `references/news-research.md` is >7 days old before any rate-angle content.
- **Never fabricate data.** If a source isn't returning live results, note it and ask Brian to verify.
- **Faith + Mission posts:** powerful but max 1/month. Flag when suggesting one.
- **GHL send + delete not available via API.** Brian does both manually in GHL.
- **Metricool free tier:** 20 posts/month cap. Always `draft: true` on first run.
- **IG posts always derived from newsletter** — never run a second signal scan. One source of truth.
- **`carousel_render_html.py` is the primary renderer.** Pillow (`carousel_render.py`) kept only for `source_cover`/`palette_from_image` helpers.
