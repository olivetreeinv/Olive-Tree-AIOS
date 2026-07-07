# Social Media Skill — Olive Tree Investments
**Trigger:** `/social-media`, "instagram posts", "post to instagram", "create carousel", "schedule instagram", "quote post", "inspirational quote"

---

## What this skill does

Thin entry — two jobs:

1. **Carousels** — runs the **Instagram half** of the weekly content pipeline from an already-approved newsletter.
2. **Quote posts** — standalone single-image quote graphics (see Quote Posts section). These do NOT require a newsletter.

**Full pipeline (newsletter + IG together):** use `/marketing` instead.

If no newsletter has been approved yet this week (and it's not a quote post), redirect: "Run `/marketing` first — IG posts are derived from the newsletter so everything stays cohesive."

---

## When to use this

- Newsletter content is already approved in chat or a GHL draft exists
- Brian wants to push just the IG step without re-running the newsletter
- Re-rendering or re-scheduling a post that needs a fix

---

## Execution

### Step 1: Get newsletter content

Ask: "Which newsletter should I derive the IG posts from — the draft we just wrote in chat, or the latest GHL draft?"

- **From chat:** use the MF + SF stories already in context.
- **From GHL:** `GET https://services.leadconnectorhq.com/emails/public/v2/locations/$GHL_LOCATION_ID/campaigns/email-campaign` — find the latest draft, pull subject + body content.

### Steps 2–4: Derive briefs → render → host → schedule → log

Follow **Steps 5 and 6** of `/marketing` exactly — same slide spec format, same hosting recipe, same Metricool scheduling call, same log command.

See [.claude/skills/marketing/SKILL.md] for the full spec.

---

## Quote Posts

Single-image typography posts — Fraunces serif on the light olive system, quote mark, attribution. Zero photos = zero stock-slop risk.

**Where quotes come from (in order — this is the anti-slop rule):**

1. **Brian's own lines** — "Translation:" sentences from past newsletters, contrarian reads, deal lessons, underwriting one-liners. His words, his brand. Default `who`/`role` = Brian Norton, Founder.
2. **Scripture / faith-mission** — fits the Olive Tree mission, but **max 1/month** (same cadence rule as faith posts). Set `who` to the verse reference, `role` to "".
3. **Named investors/operators** (Buffett, Munger, etc.) — sparingly, only when it lands on a point Brian actually makes. Always correctly attributed.

**Never:** generic inspo ("Hustle harder", "Dream big"), unattributed quotes, fabricated attributions. If it could appear on any random motivation account, kill it.

**Render:**
```bash
cat > /tmp/quote.json <<'EOF'
{"slides": [{"type": "quote", "title": "[the quote]", "who": "[optional]", "role": "[optional]"}]}
EOF
python3 scripts/carousel_render_html.py --json /tmp/quote.json --out output/carousel/[date]-quote
```
Sizing is automatic by quote length; keep quotes under ~180 characters — shorter is stronger.

Show the PNG to Brian, then host/schedule/log exactly like a carousel (Step 6 of `/marketing`: `social_drive_upload.py` → Metricool `draft: true` → `social_sheet.py` with type "Quote").

**Caption:** 1–2 lines expanding the quote in Brian's voice + 3 hashtags. No "✨" energy.

**Cadence:** 1–2/week between carousels. Best slot: check Metricool best-time; default 12:00 PM ET.

---

## Key IDs

Same as `/marketing` — see the Key IDs table there.
