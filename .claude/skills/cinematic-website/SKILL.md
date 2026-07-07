---
name: cinematic-website
description: One-prompt cinematic website builder. Interviews Brian to pick one of 10 site templates (product reveal, journey, portfolio, e-commerce drop, restaurant, real-estate listing, vehicle, SaaS, agency/studio, gym), generates AI video clips via the KIE API (Seedance 2.0), builds a scroll-driven site, launches on localhost, and verifies every interaction headlessly before reporting done. Trigger on "/cinematic-website", "build me a cinematic website", "one-prompt website", "award-winning website for [X]", "video website for [client]".
---

# Cinematic Website Skill

Turns one sentence into a cinematic, scroll-driven website: AI-generated video via
**KIE API (Seedance 2.0)**, GSAP scroll choreography, launched and verified on localhost.
Adapted from Zubair Trabzada's One-Prompt Website Pack (built for Higgsfield MCP; we use KIE).

Working reference build: `site-cinematic/` (template 09 for Olive Tree, shipped 2026-07-07).

## Step 0 — Interview (always, before anything else)

Never guess the template. Use AskUserQuestion to establish, in this order:

1. **Template** — if Brian named a business type, suggest the matching template and confirm.
   Otherwise ask which of the 10 (grouped: product/vehicle · place/experience · people/brand · commerce/SaaS).
2. **Brand** — real business or fictional demo? If real: collect name, city, and any real
   assets (menu, photos, prices, socials). Real photos become Seedance image references —
   the site animates THEIR product, not an invented one. Never fake copy for a real brand
   without showing a draft.
3. **Fill-ins** — walk the chosen template's [bracketed] slots and shot list; let Brian
   swap shots or copy lines. Keep his answers verbatim in the prompts.
4. **Budget** — resolution + clip count → cost estimate (see below). Get explicit approval
   of the credit spend before generating anything.

## Cost & credit protocol (hard rules, learned 2026-07-07)

- Measured cost: Seedance 2.0 std, 1080p, 8s, no audio = **816-1,632 credits ($4-$8) per
  clip** (two same-spec sessions billed differently; quote the high end). 720p is roughly
  40% of that; 4K ~4x. Hero image reference: ~6 credits.
- `python3 scripts/kie_video.py --check` FIRST. kie.ai will let the balance go **negative**
  (it hit -1,512 once) — never rely on the API to stop you.
- **Never run kie_video.py "as a test" with a real prompt** — a submitted createTask bills
  even if you kill the local process. Use `--dry-run` for any smoke test or preview; it
  prints the request + estimate and spends nothing.
- Quote total estimated credits + dollars, offer 720p as the cheaper option, and wait for
  approval. The script's per-clip balance guard is a backstop, not the approval.
- Report actual credits spent (balance before/after) in the final summary.

## Generating the clips

All generation goes through `scripts/kie_video.py` (model `bytedance/seedance-2`,
defaults: std, 1080p, 16:9, 8s, no audio):

```bash
python3 scripts/kie_video.py --prompt "..." --out site-<slug>/assets/hero.mp4
```

- **Hero-image trick (identity consistency — don't skip when the template calls for it):**
  generate ONE hero image first, then pass its hosted URL to every clip:
  ```bash
  python3 scripts/kie_video.py --image --prompt "..." --out ref.png   # prints hosted URL
  python3 scripts/kie_video.py --prompt "..." --ref-image <URL> --out clip1.mp4
  ```
  For real products/people, upload Brian's photo instead (see upload below) and use that URL.
- **Clip chaining (journey templates 02/06/07):** each clip's final frame becomes the next
  clip's start frame so N clips scrub as one unbroken move:
  ```bash
  ffmpeg -sseof -0.05 -i clip1.mp4 -frames:v 1 last1.jpg
  curl -X POST https://kieai.redpandaai.co/api/file-stream-upload \
    -H "Authorization: Bearer $KIE_API_KEY" -F "file=@last1.jpg"   # hosted URL in response (24h temp)
  python3 scripts/kie_video.py --prompt "..." --first-frame <URL> --out clip2.mp4
  ```
  Chained clips generate sequentially; independent clips run in parallel as background tasks.
- Failed generations cost 0 credits; retry twice before falling back.

## Building the site

- Invoke the **taste-skill** for design standards. The template's explicit art direction
  (custom cursor, pure black, serif body, etc.) overrides taste-skill defaults — the brief is law.
- Stack: vanilla HTML/CSS/JS in `site-<slug>/` + vendored GSAP/ScrollTrigger (copy from
  `site-cinematic/vendor/`). No framework, no build step.
- Fonts: self-host woff2 (curl the Google Fonts CSS with a browser UA, download, rewrite
  URLs). Gotcha: URLs inside CSS resolve relative to the CSS file, not the page.
- **Scroll-scrub videos must be re-encoded with a keyframe every frame** or seeking stutters:
  ```bash
  ffmpeg -i clip.mp4 -c:v libx264 -g 1 -crf 21 -pix_fmt yuv420p -an -movflags +faststart clip-scrub.mp4
  ```
  Scrub = GSAP ScrollTrigger tweening `video.currentTime` over a tall pinned section.
  Hover/background clips need no re-encode. If clips run heavy, compress: `-crf 26 -vf scale=1280:-2`.
- Always include `prefers-reduced-motion` fallbacks and an explicit mobile collapse.

## Launch & verify (never skip; "done" means verified)

1. Serve with `python3 scripts/serve_range.py site-<slug> 8090`.
   **Never `python -m http.server`** — it lacks HTTP Range support, so Chrome plays video
   but silently cannot seek: every scroll-scrub sticks at frame 0.
2. Playwright (bundled chromium is fine once Range works) — assert, per template:
   scrub advances `currentTime` with scroll; pinned/kinetic steps show the right element
   at the right scroll position (check computed opacity at 3+ scroll points); hover
   reveals play; counters/HUDs update; forms render. Zero console errors.
3. Screenshot every section and actually look at the images before declaring done.
4. Final report: localhost URL, what was verified, actual credit spend.

---

# The 10 Templates

Shot prompts below are the creative spec — fill [brackets] from the interview, keep the
rest intact on first build. All clips: std, 1080p, 16:9, no audio, ~8s unless noted.
"Iterate like a director": after v1, take feeling-based notes ("hero 20% slower") and translate.

## 01 · Product Reveal (luxury physical product)
Watches, jewelry, audio gear, sneakers — anything premium with parts.
**Ref image first:** the product, [brushed black titanium case, gold detail visible], black void.
**Shots:** (1) HERO ORBIT — slow 360° studio turntable, floating, rim lighting, faint gold dust.
(2) MACRO FLY-THROUGH — extreme close-up glide across surfaces/mechanisms, light rippling.
(3) EXPLODED ASSEMBLY — product assembles itself from floating components converging.
**Site:** scroll-scrub hero orbit (scrolling rotates the product) → "[Crafted in Darkness]"
story → macro details over clip 2 → exploded view with spec callouts → "[Edition of 88 — $X]"
→ private waitlist CTA. Off-black, gold accent, high-contrast serif display + minimal sans.
Copy: quiet, expensive, very few words.

## 02 · The Journey (chained descent/ascent)
Experiences, tourism, expeditions, museums — scroll = a journey. **CHAINED: 5 clips, each
final frame starts the next.** Ref image first: the vehicle/vessel, kept consistent.
**Shots:** surface/start → descent through light → light dies → total dark with sparks of
life → destination floor, hero hold. (Works as mountain ascent, rocket launch, factory tour.)
**Site:** concatenated clips scroll-scrubbed as one descent; fixed HUD meter counting
[0m → 3,800m] with zone labels; one striking fact pinned per zone → craft/spec callouts →
"[8 seats. $250,000.]" → manifest CTA. Background color-grades with depth; single
bioluminescent accent; thin technical sans, HUD micro-details.

## 03 · Personal Portfolio (starring the person)
Creators, freelancers, consultants. Needs a well-lit front-facing photo — upload it and pass
as identity reference on EVERY clip; keep wardrobe identical. Generate 2-3 takes of the hero
orbit, keep the one where likeness holds; input photo quality decides everything.
**Shots:** (1) HERO ORBIT — subject arms crossed, black-void studio, [accent] rim light, slow
360° orbit. (2) THE BUILDER — at a dark desk, floating holographic screens of their work,
push-in. (3) THE CLOSER — walking toward camera down a glowing gallery, hero pose.
**Site:** scrub hero orbit; [NAME] massive display type tracking in letter-by-letter; animated
stats counting up on scroll; THREE PILLARS over clip 2 (offers, one at a time); WORK cards over
clip 3 (3 best projects, hover motion); finale CTA + socials. Ink black, one accent, cream
type, bold condensed display, kinetic type, subtle grain.

## 04 · The Drop (e-commerce / streetwear)
**Ref image first:** lookbook shot of model in full fit. For a real store use actual product
photos as references.
**Shots:** (1) HERO 16:9 — model walks toward camera through rooftop fog, neon glow, fabric
moving. (2) PRODUCT SPINS — three separate **1:1** clips, each garment 360° on invisible
mannequin, concrete-gray studio. (3) FABRIC MACRO — stitching, zipper teeth, embossed logo.
**Site:** scrub the walk; brand + drop name massive; live countdown timer; product grid of 3
cards that autoplay spins on hover (name, price, size selector, demo Add-to-Cart drawer);
fabric manifesto ("Built heavy. Cut clean."); sticky cart; one marquee strip; "Notify me"
email capture. Concrete gray + matte black, one acid accent, brutalist condensed type.

## 05 · The Restaurant (local business — sellable)
**Shots:** (1) HERO — slow-mo macro of [ribeye searing over open flame], embers rising, amber
light. (2) THE ROOM — slow dolly through moody dining room at golden hour. (3) THE CRAFT —
overhead chef's hands plating, steam curling.
**Site:** full-bleed scrub hero, elegant serif name + "[Wood fire. Nothing else.]" → story over
clip 2, restrained copy → two-column menu (real menu if real client) → private dining over
clip 3 → hours + map + Reserve form (date/party size). Near-black, warm cream, ember accent,
film grain, slow parallax. Copy: sparse, sensory. Mobile: menu collapses to one column.
For a real restaurant this is a $2,000-$5,000 deliverable.

## 06 · The Listing (real estate — Brian's wheelhouse)
Realtors, developers, rentals, hotels. **Ref image first** (tower/property at dusk);
**chain clips 2-4** for one continuous tour. For real listings use actual listing photos as
start frames — Seedance turns stills into cinematic movement.
**Shots:** (1) APPROACH — aerial curving around the property at dusk. (2) ARRIVAL — glide from
entry into the main living space. (3) FLOW — continuous move through kitchen/primary suite
toward terrace doors. (4) TERRACE — out into the night view, timelapse clouds.
**Site:** scrub the chained tour (scrolling walks the buyer through); fixed progress indicator
naming each space; hero line → facts strip (beds · baths · sq ft) → gallery → amenities
reveals → price section → "Request a Private Showing" form + agent card. Ink background,
champagne-gold accent, thin elegant serif, generous whitespace.

## 07 · The Machine (vehicle / big product)
**Ref image first** (the machine, consistent everywhere); **chain the drive clips.**
**Shots:** (1) REVEAL — dust settles to reveal it motionless; lights ignite. (2) THE RUN — low
tracking shot launching across terrain. (3) THE CANYON — threading terrain at speed, camera
whipping. (4) NIGHT MODE — only its light signature carving through dark.
**Site:** scrub the chained run (scrolling drives it); corner HUD climbing [0 → 250 mph] with
scroll; ultrawide-type hero → performance counters → design macro stills → night section →
configurator teaser (3 paint options recoloring a hero still) → "[Reserve — $1,000]" CTA.
Black on black, one electric accent, ultrawide condensed type.

## 08 · The Product Launch (SaaS / app)
**Shots:** (1) HERO — dark void, glowing data particles swirl and assemble into a floating
dashboard with a rising graph pulsing like a heartbeat. (2) THE SIGNAL — macro glide across
holographic charts, one red anomaly caught. (3) THE CALM — dashboard on a laptop in a bright
minimal office. For a real tool, replace clip 3 with a real screen recording — generated hero
+ real product is the credibility combo.
**Site:** scrub the particle assembly (dashboard builds itself as visitor scrolls); value-prop
headline + "Start free"; logo strip; three feature blocks pinned over clip 2 (one line each);
metric counters; screenshot in browser frame; 3-tier pricing (middle highlighted); FAQ
accordion; final CTA over clip 3. Near-black hero fading to white body, single accent,
geometric sans, glass cards.

## 09 · The Studio (agency / creative)
Built once as `site-cinematic/` — reuse its code as the starting point.
**Shots:** (1) HERO — black ink blooming through water, extreme slow motion, flashing gold.
(2) THE WORK — oversized typography posters sliding past on gallery walls, sideways dolly.
(3) THE PEOPLE — team silhouettes working late, city bokeh through the window.
**Site:** scrub ink bloom behind enormous name (80% viewport) + manifesto line typing itself;
kinetic section slamming one word per scroll step; 4-case-study grid with hover video reveals
(clip 2 crops via object-position); editorial two-column services; team over clip 3; oversized
footer question + email + socials. Pure black + bone white, gold accent exactly 3x, brutalist
display + refined serif, gold dot-and-ring cursor.

## 10 · The Gym (fitness / local business — sellable)
**Shots:** (1) HERO — slow-mo chalk clap blooming through a shaft of light in a dark gym.
(2) THE IRON — macro tracking along a loaded barbell, knurling and chalk. (3) THE GRIND —
runner sprinting at dawn, low fast tracking, breath visible.
**Site:** scrub chalk-cloud hero, massive industrial type + "[Earn it.]" → philosophy, one line
per scroll step → programs grid (hover states; swipeable cards on mobile) → coaches cards →
results counters → 3-tier pricing + "First week free" → schedule + map + signup form.
Charcoal, bone-white type, one blood-red accent, heavy condensed display, grain + vignette.
Swap in a real gym's schedule/prices/photos: another $2,000+ deliverable.

---

## Going live (on request)

Push to GitHub and deploy free on Cloudflare Pages, then connect a custom domain.
Compress videos for web first (`-crf 26`, scale to 1280w) — typically ~90% smaller.
