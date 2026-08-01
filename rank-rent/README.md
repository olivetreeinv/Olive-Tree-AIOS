# Rank & Rent Site Factory

See `PLAN.md` for the business model. This is the "build a site" mechanics.

## Add a new site

1. Copy an existing config as a starting point:
   ```
   mkdir -p rank-rent/sites/<new-slug>
   cp rank-rent/sites/cartersville-tree/site.json rank-rent/sites/<new-slug>/site.json
   ```
2. Edit `site.json` — business name, niche, phone (use `"PHONE_TBD"` until a Twilio
   tracking number is provisioned), email, city/state, colors, services (real copy,
   400-600 words each, 3-4 FAQs), service areas (1-2 paragraphs each). Schema is
   documented in the docstring at the top of `scripts/rr_sitegen.py`.
3. Build it:
   ```
   python3 scripts/rr_sitegen.py <new-slug>
   ```
   Output lands in `rank-rent/sites/<new-slug>/dist/`. The build always runs a
   self-check afterward (one `<h1>` per page, valid JSON-LD, required files present)
   and exits non-zero if anything fails.
4. Open `dist/index.html` in a browser to eyeball it before deploying.

## Deploy `dist/` to Cloudflare Pages

**Drag-and-drop (fastest, no CLI):**
1. Go to the Cloudflare dashboard -> Workers & Pages -> Create -> Pages -> Upload assets.
2. Drag the site's `dist/` folder in. Cloudflare serves it as-is (static files, clean
   folder URLs already baked in — no build step needed on their end).
3. Point the custom domain at the Pages project once purchased.

**CLI (`npx wrangler`, no local install needed):**
```
npx wrangler pages deploy rank-rent/sites/<slug>/dist --project-name=<slug>
```
First run prompts a Cloudflare login. Re-running redeploys the latest `dist/`.

## Notes

- Contact form posts to `https://formsubmit.co/{email}` (free, no backend needed).
  First submission on a new email requires a one-time confirmation click from
  formsubmit.co — do that before promoting the site.
- Update `"site_url"` in `site.json` once a real domain is purchased (defaults to
  a placeholder `https://<slug>.example.com`, which only affects sitemap/JSON-LD
  absolute URLs, not the page content itself).
