# GHL Page Archive — olivetreeinv.io

Captured 2026-07-06/07, before GoHighLevel account cancellation.
Per page: raw server HTML (`curl`) + PDF snapshot (headless Chrome, JS rendered).
`content.md` = faithful text extraction of the 5 keeper pages (seed for the static-site rebuild).
`assets/` = 47 images referenced by the keeper pages (original media filenames; the GHL CDN serves
webp, so extensions are `.webp` regardless of original upload format).

## Key routing finding (matters for the rebuild)

- **`www.olivetreeinv.io` 301-redirects EVERY path to `/`** (the home step). Only the home
  page is reachable on the www host.
- **The apex `olivetreeinv.io` serves the real funnel steps** — all captures below were taken
  from the apex domain.
- Root (`/`) serves the home page on both hosts (`root.html` kept as proof).
- `/post` alone is 404; the blog lives at `/post/<slug>`. All 3 published posts captured.

## Page inventory

| Page | URL (apex) | Funnel | HTML | PDF | Status |
|---|---|---|---|---|---|
| Home | /home (also `/`) | Olive Tree Website | home.html (473K) | home.pdf (1.9M) | OK |
| Terms & Conditions | /terms-and-conditions | Olive Tree Website | terms-and-conditions.html (392K) | terms-and-conditions.pdf (528K) | OK |
| Privacy Policy | /privacy-policy | Olive Tree Website | privacy-policy.html (268K) | privacy-policy.pdf (428K) | OK |
| Partner With Us | /partner-with-us | Olive Tree Website | partner-with-us.html (95K) | partner-with-us.pdf (1.4M) | OK — calendar booking page ("Brian's Personal Calendar", 30 min, GHL widget `fd8cOUzYtG`); widget renders client-side, see PDF |
| 641 Powder Springs | /641_powder | 641 | 641_powder.html (682K) | 641_powder.pdf (12M) | OK — full deal page |
| Find My House (blog index) | /findmyhouse | Find My House blog | findmyhouse.html (72K) | findmyhouse.pdf (96K) | OK |
| Blog: Benefits of Investing in Real Estate | /post/new-blog-post | Find My House blog | post-new-blog-post.html (82K) | post-new-blog-post.pdf (172K) | OK |
| Blog: Buying a home versus renting | /post/new-blog-post-3301 | Find My House blog | post-new-blog-post-3301.html (87K) | post-new-blog-post-3301.pdf (180K) | OK |
| Blog: 5 Essential Tips for First-Time Homebuyers | /post/new-blog-post-6430 | Find My House blog | post-new-blog-post-6430.html (80K) | post-new-blog-post-6430.pdf (156K) | OK |
| Root landing | / | — | root.html (473K) | (same as home.pdf) | OK — identical to /home |

## Not captured (and why)

- **"Find My House - Website" funnel (15 steps) and "Investment" funnel (3 steps)** — no domain
  attached. Probed `/home-page`, `/seller`, `/home-5531`, `/investment`, `/invest`, `/opportunity`
  on both hosts: all 301 to `/`. These steps are only reachable inside the GHL editor/preview
  (expected). Export them from within GHL before cancellation if their content is wanted.
- `/post` bare path — 404 by design (blog posts are slug-addressed; all 3 slugs captured).

## Files

- `<slug>.html` — raw server HTML (GHL server-renders page content; usable for text/asset recovery).
- `<slug>.pdf` — headless-Chrome print of the fully rendered page (JS widgets included).
- `content.md` — extracted copy of the 5 keeper pages (home, terms, privacy, partner-with-us,
  641_powder): headings, body text, buttons, links, images in reading order. GHL renders
  desktop + mobile variants of some sections, so some blocks legitimately appear twice.
- `assets/` — 47 images: 45 page images at the largest responsive size (r_1200) + intl-tel-input
  flag sprites. Filenames = GHL media IDs, matching the `[image: ...]` references in content.md.
