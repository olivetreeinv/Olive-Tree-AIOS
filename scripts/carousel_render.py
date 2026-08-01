#!/usr/bin/env python3
"""
carousel_render.py — render Instagram carousel slides for Olive Tree Investments.

Free, local, no browser. Pure Pillow. Turns slide copy into 1080x1350 PNGs.

Cover slide is always a PHOTO (hero image + scrim + overlaid title + minimal
white logo). The rest of the deck's palette is derived FROM that photo (a dark
tone for the background + a saturated accent), so each carousel matches its
cover. If no photo is available it falls back to the Olive Tree brand palette.

Photo source: a Brian-supplied image (`cover_image`) wins; otherwise auto-sourced
by `cover_query` from Pexels (if PEXELS_API_KEY set) else Wikimedia Commons.

Slide types give rhythm: cover (1) / content (middle) / cta (last). Each carries
a top progress bar.

Usage:
    python3 scripts/carousel_render.py --json slides.json --out output/carousel/<slug>
    python3 scripts/carousel_render.py --demo

slides.json:
    {
      "handle": "@olivetreeinv.io",
      "cover_query": "Atlanta Georgia skyline",   # auto-sourced hero
      "cover_image": "path.jpg",                   # optional: use this photo instead
      "slides": [ {"kicker","title","body","type"} , ... ]
    }
"""
from __future__ import annotations

import argparse
import colorsys
import json
import os
import sys
from collections import Counter
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps

_LOGO_MARK = str(Path(__file__).resolve().parent.parent / "assets" / "brand" / "olive-tree-mark-white.png")

# Fallback brand palette (Olive Tree logo) — used when there's no cover photo.
BRAND = {
    "bg":        (27, 30, 8),
    "title":     (255, 255, 255),
    "body":      (218, 212, 197),
    "kicker":    (183, 150, 90),
    "rule":      (125, 139, 60),
    "ghost":     (36, 40, 15),
    "footer":    (139, 144, 114),
    "track":     (46, 49, 32),
    "cta_bg":    (80, 90, 25),
    "cta_title": (255, 255, 255),
    "cta_body":  (218, 212, 197),
    "handle":    "@olivetreeinv.io",
    "logo_path": _LOGO_MARK,
}
W, H = 1080, 1350
MARGIN = 96
_UA = {"User-Agent": "OliveTreeAIOS/1.0 (brian@olivetreeinv.io)"}

_BOLD = [("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 0),
         ("/System/Library/Fonts/HelveticaNeue.ttc", 1)]
_REG = [("/System/Library/Fonts/Supplemental/Arial.ttf", 0),
        ("/System/Library/Fonts/HelveticaNeue.ttc", 0)]


def _font(cands, size):
    for path, idx in cands:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size, index=idx)
            except OSError:
                continue
    return ImageFont.load_default()


def _wrap(d, text, font, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if d.textlength(trial, font=font) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur); cur = w
    if cur:
        lines.append(cur)
    return lines


def _block(d, lines, font, fill, x, y, lead):
    for ln in lines:
        d.text((x, y), ln, font=font, fill=fill); y += lead
    return y


# --- Photo sourcing ---------------------------------------------------------
def _load_env_key(name):
    """Return env var, falling back to a line in the project .env."""
    if os.environ.get(name):
        return os.environ[name]
    env = Path(__file__).resolve().parent.parent / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line.startswith(f"{name}=") and not line.startswith("#"):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def _pexels(query, dest):
    key = _load_env_key("PEXELS_API_KEY")
    if not key:
        return None
    r = requests.get("https://api.pexels.com/v1/search",
                     headers={"Authorization": key},
                     params={"query": query, "orientation": "portrait", "per_page": 1},
                     timeout=20)
    if r.status_code != 200 or not r.json().get("photos"):
        return None
    url = r.json()["photos"][0]["src"]["portrait"]
    dest.write_bytes(requests.get(url, timeout=30).content)
    return dest


def _wikimedia(query, dest):
    r = requests.get("https://commons.wikimedia.org/w/api.php", headers=_UA, timeout=20,
                     params={"action": "query", "format": "json", "generator": "search",
                             "gsrsearch": f"{query} filetype:bitmap", "gsrnamespace": 6,
                             "gsrlimit": 8, "prop": "imageinfo",
                             "iiprop": "url|size|mime", "iiurlwidth": 1350})
    pages = r.json().get("query", {}).get("pages", {})
    best = None
    for p in pages.values():
        ii = (p.get("imageinfo") or [{}])[0]
        if ii.get("mime", "").startswith("image") and ii.get("width", 0) >= 1200:
            best = ii.get("thumburl") or ii.get("url"); break
    if not best:
        return None
    dest.write_bytes(requests.get(best, headers=_UA, timeout=30).content)
    return dest


def source_cover(query, out_dir):
    """Return a local path to a hero photo for `query`, or None."""
    dest = Path(out_dir) / "_cover_src.jpg"
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        return _pexels(query, dest) or _wikimedia(query, dest)
    except Exception:
        return None


# --- Palette from photo -----------------------------------------------------
def palette_from_image(path):
    """Derive (bg, accent, ghost) from a photo. bg = darkened dominant; accent =
    a bright saturated representative color."""
    img = Image.open(path).convert("RGB"); img.thumbnail((120, 120))
    px = list(img.getdata()); n = len(px)
    avg = (sum(p[0] for p in px) // n, sum(p[1] for p in px) // n, sum(p[2] for p in px) // n)
    bg = tuple(max(8, int(c * 0.30)) for c in avg)            # deep, text-safe
    common = Counter((p[0] // 24 * 24, p[1] // 24 * 24, p[2] // 24 * 24) for p in px).most_common(24)
    best, best_score = None, -1.0
    for (r, g, b), cnt in common:
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        if v < 0.30:
            continue
        score = s * (0.5 + 0.5 * v) * (cnt ** 0.15)
        if score > best_score:
            best_score, best = score, (r, g, b)
    if best is None:
        return BRAND["bg"], BRAND["kicker"], BRAND["ghost"]
    h, s, v = colorsys.rgb_to_hsv(*[c / 255 for c in best])
    accent = tuple(int(c * 255) for c in colorsys.hsv_to_rgb(h, max(s, 0.55), max(v, 0.72)))
    ghost = tuple(min(255, int(bc + (ac - bc) * 0.18)) for bc, ac in zip(bg, accent))
    return bg, accent, ghost


def _palette(brand, photo):
    """Working palette dict for the whole deck."""
    p = {**brand}
    if photo:
        bg, accent, ghost = palette_from_image(photo)
        p.update(bg=bg, kicker=accent, rule=accent, ghost=ghost,
                 track=tuple(int(c * 0.5 + b * 0.5) for c, b in zip(accent, bg)),
                 cta_bg=accent)
        # CTA text colour by accent luminance.
        lum = 0.299 * accent[0] + 0.587 * accent[1] + 0.114 * accent[2]
        p["cta_title"] = (28, 30, 22) if lum > 150 else (255, 255, 255)
        p["cta_body"] = (40, 44, 30) if lum > 150 else (235, 238, 224)
    return p


def _progress(d, index, total, color, track):
    y, x0, x1 = 56, MARGIN, W - MARGIN
    d.rounded_rectangle([x0, y, x1, y + 6], radius=3, fill=track)
    d.rounded_rectangle([x0, y, x0 + (x1 - x0) * (index / total), y + 6], radius=3, fill=color)


def _paste_logo(img, path, x, y, box=104):
    if path and Path(path).exists():
        lg = Image.open(path).convert("RGBA"); lg.thumbnail((box, box))
        img.paste(lg, (x, y), lg)


def _footer(d, brand, index, total, color):
    fy = H - MARGIN - 10
    f = _font(_BOLD, 30)
    d.text((MARGIN, fy), brand.get("handle", BRAND["handle"]), font=f, fill=color)
    c = f"{index}/{total}"
    d.text((W - MARGIN - d.textlength(c, font=f), fy), c, font=f, fill=color)


# --- Cover (photo) ----------------------------------------------------------
def render_cover_photo(photo, slide, index, total, brand, out_path):
    base = ImageOps.fit(Image.open(photo).convert("RGB"), (W, H), method=Image.LANCZOS)
    # Bottom-weighted dark scrim for text legibility + light top scrim for logo/bar.
    scrim = Image.new("L", (1, H), 0)
    for y in range(H):
        bottom = min(1.0, max(0.0, (y - H * 0.30) / (H * 0.70))) ** 1.25 * 0.92
        top = max(0.0, (H * 0.16 - y) / (H * 0.16)) * 0.45
        scrim.putpixel((0, y), int(255 * max(bottom, top)))
    base = Image.composite(Image.new("RGB", (W, H), (6, 8, 5)), base, scrim.resize((W, H)))
    d = ImageDraw.Draw(base)

    _progress(d, index, total, (255, 255, 255), (255, 255, 255, 90))
    _paste_logo(base, brand.get("logo_path"), W - MARGIN - 104, 96)

    swipe_y = H - MARGIN - 90
    title = slide.get("title", "")
    tlines = _wrap(d, title, _font(_BOLD, 92), W - 2 * MARGIN)
    block_h = len(tlines) * 108
    top = swipe_y - 50 - block_h
    kicker = slide.get("kicker")
    if kicker:
        d.text((MARGIN, top - 64), kicker.upper(), font=_font(_BOLD, 34), fill=brand["kicker"])
    _block(d, tlines, _font(_BOLD, 92), (255, 255, 255), MARGIN, top, 108)
    if total > 1:
        d.text((MARGIN, swipe_y), "SWIPE  →", font=_font(_BOLD, 34), fill=brand["kicker"])
    _footer(d, brand, index, total, (235, 235, 230))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    base.save(out_path, "PNG")
    return out_path


# --- Text slides (content / cta) -------------------------------------------
def render_slide(slide, index, total, brand, out_path, stype="content"):
    is_cta = stype == "cta"
    bg = brand["cta_bg"] if is_cta else brand["bg"]
    title_c = brand["cta_title"] if is_cta else brand["title"]
    body_c = brand["cta_body"] if is_cta else brand["body"]
    accent = brand["cta_title"] if is_cta else brand["kicker"]

    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)
    max_w = W - 2 * MARGIN

    _progress(d, index, total, title_c if is_cta else brand["kicker"], brand["track"])

    if stype == "content":
        num = f"{index:02d}"
        nf = _font(_BOLD, 230)
        d.text((W - MARGIN - d.textlength(num, font=nf), 96), num, font=nf, fill=brand["ghost"])
    if is_cta:
        _paste_logo(img, brand.get("logo_path"), W - MARGIN - 104, 100)

    y = MARGIN + 60
    kicker = slide.get("kicker")
    if kicker and not is_cta:
        d.text((MARGIN, y), kicker.upper(), font=_font(_BOLD, 34), fill=accent)
        y += 56
        d.line([(MARGIN, y), (MARGIN + 80, y)], fill=brand["rule"], width=4)

    tsize = 78
    title = slide.get("title", "")
    tb = max(y + 40, 380)
    if title:
        tlines = _wrap(d, title, _font(_BOLD, tsize), max_w)
        tb = _block(d, tlines, _font(_BOLD, tsize), title_c, MARGIN, max(y + 40, 380), tsize + 16)
        if stype == "content":
            d.line([(MARGIN, tb + 6), (MARGIN + 110, tb + 6)], fill=brand["rule"], width=6)
            tb += 36

    body = slide.get("body", "")
    if body:
        _block(d, _wrap(d, body, _font(_REG, 44), max_w), _font(_REG, 44), body_c, MARGIN, tb + 24, 60)

    _footer(d, brand, index, total, brand["cta_body"] if is_cta else brand["footer"])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG")
    return out_path


def render_carousel(spec, out_dir):
    out_dir = Path(out_dir)
    brand0 = {**BRAND}
    if spec.get("handle"):
        brand0["handle"] = spec["handle"]
    if spec.get("logo_path"):
        brand0["logo_path"] = spec["logo_path"]

    # Resolve the cover photo (supplied wins, else auto-source).
    photo = spec.get("cover_image")
    if photo and not Path(photo).exists():
        photo = None
    if not photo and spec.get("cover_query"):
        p = source_cover(spec["cover_query"], out_dir)
        photo = str(p) if p else None

    brand = _palette(brand0, photo)

    slides = spec["slides"]
    total = len(slides)
    paths = []
    for i, slide in enumerate(slides, start=1):
        stype = slide.get("type") or ("cover" if i == 1 else "cta" if i == total else "content")
        dest = out_dir / f"slide{i:02d}.png"
        if i == 1 and photo:
            render_cover_photo(photo, slide, i, total, brand, dest)
        else:
            render_slide(slide, i, total, brand, dest, "content" if i == 1 else stype)
        paths.append(dest)
    return paths


def demo():
    spec = {
        "cover_query": "Atlanta Georgia skyline",
        "slides": [
            {"kicker": "Single Family", "title": "Nearly 40% of Southern listings just cut their price."},
            {"kicker": "The shift", "title": "Inventory is climbing.", "body": "4.5 months of supply — the most balanced market buyers have seen in years."},
            {"title": "The window is open. Position now.", "body": "Rates near 6.2%, prices off 2.4%. Buyers have leverage again."},
        ],
    }
    out = Path(__file__).resolve().parent.parent / "output" / "carousel" / "_demo"
    paths = render_carousel(spec, out)
    assert len(paths) == 3
    for p in paths:
        assert p.exists() and Image.open(p).size == (W, H)
    print(f"OK — {len(paths)} slides at {W}x{H} -> {out}")


def main():
    ap = argparse.ArgumentParser(description="Render Instagram carousel slides (Olive Tree).")
    ap.add_argument("--json"); ap.add_argument("--out"); ap.add_argument("--demo", action="store_true")
    a = ap.parse_args()
    if a.demo:
        demo(); return
    if not a.json or not a.out:
        ap.error("provide --json and --out, or use --demo")
    print("\n".join(str(p) for p in render_carousel(json.loads(Path(a.json).read_text()), a.out)))


if __name__ == "__main__":
    sys.exit(main())
