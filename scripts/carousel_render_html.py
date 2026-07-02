#!/usr/bin/env python3
"""
carousel_render_html.py — premium HTML/CSS → PNG carousel renderer (Olive Tree).

Light & airy editorial slide system designed with the taste-skill principles:
soft off-white grounds, generous whitespace, one locked olive accent, refined
type (Outfit), a photo-top cover (no dark scrim), and a single inverted olive CTA.

Each slide is a self-contained 1080x1350 HTML block; Playwright screenshots each.
Same spec + output contract as the Pillow renderer, so Drive/Metricool/sheet flow
is unchanged. Hero image: supplied `cover_image` (e.g. Higgsfield) → Pexels
`cover_query` → Wikimedia. The accent color is derived from the hero photo; the
background stays light.

Usage:
    python3 scripts/carousel_render_html.py --json slides.json --out output/carousel/<slug>
    python3 scripts/carousel_render_html.py --demo
"""
from __future__ import annotations

import argparse
import base64
import colorsys
import html as _html
import json
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from carousel_render import source_cover, palette_from_image  # reuse photo sourcing + palette

ROOT = Path(__file__).resolve().parent.parent
LOGO_DARK = ROOT / "assets" / "brand" / "olive-tree-mark-dark.png"
LOGO_LIGHT = ROOT / "assets" / "brand" / "olive-tree-mark-white.png"
W, H = 1080, 1350

# Light & airy tokens (olive brand; NOT the banned cream/beige family).
BG = "#F4F5F1"        # soft light warm-neutral, faint green undertone
PANEL = "#FBFBF9"     # near-white panel
INK = "#1E2418"       # warm charcoal
MUTED = "#6B7060"     # muted olive-gray (body / footer)
ACCENT_DEFAULT = "#5A6A1E"  # olive green


def _b64(path):
    return base64.b64encode(Path(path).read_bytes()).decode()


def _accent_for_light(photo):
    """Olive-green brand base with a subtle tint pulled from the hero photo, kept
    dark/saturated enough to read on a light ground."""
    base = (90, 106, 30)  # #5A6A1E olive
    if not photo:
        return ACCENT_DEFAULT
    _, accent, _ = palette_from_image(photo)
    mix = tuple(0.7 * base[i] + 0.3 * accent[i] for i in range(3))  # 70% olive / 30% photo
    r, g, b = [c / 255 for c in mix]
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    s = max(s, 0.5)
    v = min(v, 0.55)          # cap brightness so it contrasts on light bg
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return f"#{int(r*255):02X}{int(g*255):02X}{int(b*255):02X}"


def _lum(hex_):
    r, g, b = (int(hex_[i:i+2], 16) for i in (1, 3, 5))
    return 0.299 * r + 0.587 * g + 0.114 * b


def _esc(t):
    return _html.escape(t or "")


CSS = """
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap');
* { margin:0; padding:0; box-sizing:border-box; }
.slide {
  width:1080px; height:1350px; position:relative; overflow:hidden;
  font-family:'Outfit',-apple-system,sans-serif; background:%(BG)s; color:%(INK)s;
  -webkit-font-smoothing:antialiased;
}
.pad { position:absolute; inset:0; padding:96px; display:flex; flex-direction:column; }
.progress { position:absolute; top:56px; left:96px; right:96px; height:5px;
  border-radius:3px; background:rgba(30,36,24,0.12); overflow:hidden; z-index:5; }
.progress > i { display:block; height:100%%; border-radius:3px; background:var(--accent); }
.kicker { font-size:30px; font-weight:600; letter-spacing:.14em; text-transform:uppercase;
  color:var(--accent); }
.rule { width:76px; height:4px; background:var(--accent); margin-top:22px; border-radius:2px; }
.headline { font-size:82px; font-weight:600; line-height:1.04; letter-spacing:-.02em; }
.body { font-size:42px; font-weight:300; line-height:1.42; color:%(MUTED)s; max-width:20ch; }
.foot { position:absolute; left:96px; right:96px; bottom:74px; display:flex;
  justify-content:space-between; align-items:center; font-size:29px; font-weight:500; color:%(MUTED)s; }
.mark { position:absolute; top:92px; right:96px; width:96px; height:96px; z-index:6; }
.mark img { width:100%%; height:100%%; object-fit:contain; }
.ghost { position:absolute; top:70px; right:80px; font-size:250px; font-weight:700;
  line-height:1; letter-spacing:-.04em; color:var(--accent); opacity:.12; z-index:1; }
.swipe { font-size:31px; font-weight:600; letter-spacing:.12em; text-transform:uppercase;
  color:var(--accent); }

/* Cover: photo on top, clean light panel below */
.cover .photo { position:absolute; top:0; left:0; width:1080px; height:812px;
  object-fit:cover; }
.cover .panel { position:absolute; left:0; right:0; top:812px; bottom:0; background:%(BG)s;
  padding:64px 96px 0; display:flex; flex-direction:column; }
.cover .kicker { font-size:28px; }
.cover .headline { font-size:70px; margin-top:20px; }
.cover .mark { top:832px; width:84px; height:84px; }  /* inside the light panel, always legible */

/* Content */
.content .stack { margin-top:150px; display:flex; flex-direction:column; }
.content .headline { margin-top:34px; }
.content .body { margin-top:30px; }
.content .uline { width:104px; height:6px; background:var(--accent); margin-top:26px; border-radius:3px; }

/* CTA: inverted olive */
.cta { background:var(--accent); color:%(CTA_TEXT)s; }
.cta .stack { margin-top:auto; margin-bottom:auto; }
.cta .headline { font-size:88px; }
.cta .body { color:%(CTA_TEXT)s; opacity:.9; }
.cta .progress { background:rgba(255,255,255,0.28); }
.cta .progress > i { background:%(CTA_TEXT)s; }
.cta .foot { color:%(CTA_TEXT)s; opacity:.85; }
""".strip()


def _slide_html(slide, i, total, stype, handle, accent, photo_b64):
    frac = i / total
    foot = (f'<div class="foot"><span>{_esc(handle)}</span>'
            f'<span>{i}/{total}</span></div>')
    prog = f'<div class="progress"><i style="width:{frac*100:.1f}%"></i></div>'

    if stype == "cover":
        logo = (f'<div class="mark"><img src="data:image/png;base64,{_b64(LOGO_DARK)}"></div>')
        kick = f'<div class="kicker">{_esc(slide.get("kicker",""))}</div>' if slide.get("kicker") else ""
        swipe = f'<div class="swipe" style="margin-top:auto;padding-bottom:30px">swipe &rarr;</div>' if total > 1 else ""
        return (f'<div class="slide cover">'
                f'<img class="photo" src="data:image/jpeg;base64,{photo_b64}">'
                f'{prog}'
                f'<div class="panel">{kick}'
                f'<div class="headline">{_esc(slide.get("title",""))}</div>{swipe}</div>'
                f'{logo}{foot}</div>')

    if stype == "cta":
        logo = (f'<div class="mark"><img src="data:image/png;base64,{_b64(LOGO_LIGHT)}"></div>')
        body = f'<div class="body">{_esc(slide.get("body",""))}</div>' if slide.get("body") else ""
        return (f'<div class="slide cta"><div class="pad">{prog}'
                f'<div class="stack"><div class="headline">{_esc(slide.get("title",""))}</div>{body}</div>'
                f'</div>{logo}{foot}</div>')

    # content
    ghost = f'<div class="ghost">{i:02d}</div>'
    kick = (f'<div class="kicker">{_esc(slide.get("kicker",""))}</div><div class="rule"></div>'
            if slide.get("kicker") else "")
    body = f'<div class="body">{_esc(slide.get("body",""))}</div>' if slide.get("body") else ""
    return (f'<div class="slide content">{ghost}<div class="pad">{prog}'
            f'<div class="stack">{kick}'
            f'<div class="headline">{_esc(slide.get("title",""))}</div>'
            f'<div class="uline"></div>{body}</div></div>{foot}</div>')


def _page_html(spec, accent, photo_b64):
    slides = spec["slides"]
    total = len(slides)
    handle = spec.get("handle", "@olivetreeinv.io")
    cta_text = "#F4F5F1" if _lum(accent) < 150 else "#1E2418"
    css = CSS % {"BG": BG, "PANEL": PANEL, "INK": INK, "MUTED": MUTED, "CTA_TEXT": cta_text}
    body = []
    for idx, s in enumerate(slides, 1):
        stype = s.get("type") or ("cover" if idx == 1 else "cta" if idx == total else "content")
        if idx == 1 and not photo_b64:
            stype = "content"  # no hero available -> fall back to text slide
        body.append(_slide_html(s, idx, total, stype, handle, accent, photo_b64))
    return (f'<!doctype html><html><head><meta charset="utf-8"><style>:root{{--accent:{accent}}}'
            f'{css}</style></head><body>{"".join(body)}</body></html>')


def render_carousel(spec, out_dir):
    from playwright.sync_api import sync_playwright
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Resolve hero photo (supplied wins, else source it).
    photo = spec.get("cover_image")
    if photo and not Path(photo).exists():
        photo = None
    if not photo and spec.get("cover_query"):
        p = source_cover(spec["cover_query"], out_dir)
        photo = str(p) if p else None

    accent = _accent_for_light(photo)
    photo_b64 = _b64(photo) if photo else ""
    page_html = _page_html(spec, accent, photo_b64)

    paths = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=2)
        page.set_content(page_html)
        page.evaluate("document.fonts.ready")
        page.wait_for_timeout(600)
        slides = page.query_selector_all(".slide")
        for i, el in enumerate(slides, 1):
            dest = out_dir / f"slide{i:02d}.png"
            el.screenshot(path=str(dest))
            paths.append(dest)
        browser.close()
    # normalize to exactly 1080x1350 (device_scale_factor doubles pixels)
    for pth in paths:
        img = Image.open(pth)
        if img.size != (W, H):
            img.resize((W, H), Image.LANCZOS).save(pth)
    return paths


def demo():
    spec = {
        "cover_query": "bright airy modern living room home interior sunlight",
        "slides": [
            {"kicker": "Single Family", "title": "Nearly 40% of Southern listings just cut their price."},
            {"kicker": "The shift", "title": "Inventory is climbing.", "body": "4.5 months of supply, the most balanced market buyers have seen in years."},
            {"title": "The window is open. Position now.", "body": "Rates near 6.2%, prices off 2.4%. Buyers have leverage again."},
        ],
    }
    out = ROOT / "output" / "carousel" / "_demo_html"
    paths = render_carousel(spec, out)
    assert len(paths) == 3
    for p in paths:
        assert p.exists() and Image.open(p).size == (W, H)
    print(f"OK — {len(paths)} slides -> {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json"); ap.add_argument("--out"); ap.add_argument("--demo", action="store_true")
    a = ap.parse_args()
    if a.demo:
        demo(); return
    if not a.json or not a.out:
        ap.error("provide --json and --out, or use --demo")
    print("\n".join(str(p) for p in render_carousel(json.loads(Path(a.json).read_text()), a.out)))


if __name__ == "__main__":
    sys.exit(main())
