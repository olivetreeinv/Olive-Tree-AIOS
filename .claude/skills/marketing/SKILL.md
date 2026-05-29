# Marketing Skill — Olive Tree Investments
**Trigger:** `/marketing`, "blog ideas", "what should I write about this week", "generate blog ideas", "write a blog", "newsletter ideas"

---

## What this skill does

Weekly content engine for Olive Tree Investments. Two modes:

- **Ideation mode** (default): Scans live sources, generates 5–7 ranked blog ideas, presents them as a menu. Brian picks one.
- **Draft mode**: Takes Brian's chosen idea and writes a full blog post in Olive Tree voice.

Fully automated — no manual input needed. Pulls from live sources every run.

---

## References (read before every run)

| File | Why |
|---|---|
| `references/news-research.md` | Source stack, rate tables, blog angle pairings |
| `references/voice.md` | Brian's voice — direct, numbers-first, no filler |
| `references/buy-box.md` | Active markets — stay consistent with geographies |
| `context/about-me.md` | Brian's background and mission |
| `context/about-business.md` | Olive Tree's structure and investor types |

---

## Execution

### Step 1: Read references

Read all five reference files before doing anything else. This grounds every idea and every draft in Brian's actual business, markets, and voice.

### Step 2: Scan live sources (Ideation mode)

Search the following in parallel. Use WebSearch for each:

1. **CRE Daily** — `site:credaily.com multifamily` (last 7 days)
2. **GlobeSt** — `site:globest.com multifamily` (last 7 days)
3. **CoStar / Multifamily Dive** — `CoStar multifamily rent vacancy 2026` and `multifamilydive.com news 2026`
4. **Macro / Rates / Big Events** — `Federal Reserve interest rates commercial real estate 2026` and `10 year treasury SOFR multifamily 2026` and `[any major breaking news: war, tariffs, government policy, legislation] real estate impact 2026`
5. **BiggerPockets** — `site:biggerpockets.com multifamily syndication` (for LP education angle signals)
6. **Southeast / Active markets** — `multifamily Georgia Tennessee Alabama 2026 market`

Pull the 3–5 most relevant headlines or data points from each search. Note the source and date.

### Step 3: Cross-reference against Brian's context

Filter and rank signals through these lenses:

- **Timeliness** — is this happening *right now*? Breaking > evergreen.
- **Market relevance** — does it touch GA, TN, or AL? Does it touch the buy box (15–50 units, value-add)?
- **Audience fit** — would a potential LP or existing investor find this useful or credible?
- **Brian's differentiation** — is there an angle only an operator-on-the-ground can write? Prefer that over generic takes.
- **Rate environment** — always check current rate tables in `references/news-research.md`. Any week with a notable rate move gets a rate-angle idea in the list.
- **Big world events** — if a war, major tariff, significant legislation, or Fed surprise broke this week, it earns a slot in the idea list. Use the "How Big Events Connect to Multifamily Underwriting" table in `references/news-research.md` to identify the specific CRE angle. Don't write about the event generically — write about what it means for a multifamily buyer or LP in Georgia, Tennessee, or Alabama.

### Step 4: Generate idea menu

Output **5–7 blog ideas**, ranked by timeliness + audience fit. For each idea:

```
### [#]. [Headline]
**Angle:** One sentence — why this matters right now, from an investor or operator POV.
**Hook:** The opening line or stat that makes someone stop scrolling.
**Source anchor:** [Source name] — specific headline or data point to reference.
**Content type:** Market Intel | LP Education | Operator POV | Faith + Mission | Deal Transparency
**Estimated read time:** X min
```

Present as a numbered list. End with:

> "Which of these do you want to run with? Say the number and I'll write the full draft."

### Step 5: Draft mode (triggered when Brian picks an idea)

When Brian selects an idea (by number or description), write the full blog post.

**Draft structure:**

```
HEADLINE
[Punchy, specific — number or data point up front when possible]

INTRO (2–3 sentences)
[The hook. What's happening, why it matters, why Brian is the right person to say it.]

BODY (3–5 sections with subheads)
[Each section = one point. Lead with the insight, support with data or example.
No filler. No "it's a complex landscape." No generic platitudes.
Every section should pass: "Would a seasoned investor already know this?" If yes, cut or sharpen.]

CLOSE / CTA (2–3 sentences)
[What to do with this information. For LP-facing posts: subtle invitation to connect or learn more.
No hard sell. No "reach out today!" energy.]

SIGN-OFF
-Brian
```

**Voice rules (from `references/voice.md`):**
- Short sentences. Numbers up front.
- Dashes over commas for asides — like this.
- Bullet points over paragraphs when listing.
- No corporate filler ("in today's dynamic landscape", "it's important to note").
- Write like Brian talks, not like a press release.

**Length:** 400–700 words for a standard post. Flag if the topic warrants longer.

**After drafting**, ask:
> "Want me to also format this for LinkedIn (shorter, punchier opening) or as an email newsletter intro?"

---

## Output format

### Ideation mode output example:

```
## Blog Ideas — Week of [Date]

**What's moving this week:**
[2–3 sentence summary of the dominant signal from the source scan — rates, market shift, macro event]

---

### 1. [Headline]
**Angle:** ...
**Hook:** ...
**Source anchor:** ...
**Content type:** ...
**Estimated read time:** X min

### 2. [Headline]
...

[continue through 5–7]

---
Which one do you want to run with? Say the number and I'll write the full draft.
```

---

## Notes

- Rate tables in `references/news-research.md` are a snapshot. If the last-updated date is >7 days old, flag it before publishing any rate-sensitive content.
- Never fabricate headlines, data, or quotes. If a search returns no clear signal, say so and generate evergreen ideas from Brian's context instead.
- If two ideas are tied on timeliness, prefer the one that touches an active buy-box market (GA, TN, AL).
- BiggerPockets signals what retail investors are asking — use it to find LP education angles, not as a primary news source.
- For Faith + Mission ideas: these are powerful but use sparingly (1 per month max). Flag when suggesting one.
