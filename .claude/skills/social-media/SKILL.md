# Social Media Skill — Olive Tree Investments
**Trigger:** `/social-media`, "instagram posts", "post to instagram", "create carousel", "schedule instagram"

---

## What this skill does

Thin entry — runs the **Instagram half** of the weekly content pipeline from an already-approved newsletter.

**Full pipeline (newsletter + IG together):** use `/marketing` instead.

If no newsletter has been approved yet this week, redirect: "Run `/marketing` first — IG posts are derived from the newsletter so everything stays cohesive."

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

## Key IDs

Same as `/marketing` — see the Key IDs table there.
