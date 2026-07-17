#!/usr/bin/env python3
"""
sig_gif.py — animated circular headshot for Brian's email signature.

Free, local, no browser, no API. Pillow + numpy. Takes brian.jpg, circle-crops
it onto a Bone ground, and animates a brass shimmer highlight rotating once
around a brass ring. Frame 0 is a finished-looking clean ring (so Outlook, which
shows only a GIF's first frame, still looks right).

Output: site/sig/brian.gif  (deployed → https://olivetreeinv.io/sig/brian.gif)

Usage:
    python3 scripts/sig_gif.py            # build + self-check
    python3 scripts/sig_gif.py --out X    # custom output path
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
PHOTO = ROOT / "templates" / "newsletter-assets" / "brian.jpg"
OUT = ROOT / "site" / "sig" / "brian.gif"

BONE = (245, 242, 233)      # #F5F2E9 solid ground (dodges dark-mode inversion)
BRASS = np.array([183, 150, 90])    # #B7965A ring base
HILITE = np.array([238, 222, 186])  # lighter brass — the travelling shimmer

OUT_PX = 300        # served at 2x, displayed at 150px in the signature
N_FRAMES = 24       # ~2s per rotation at 90ms/frame
RING_W = 7          # ring thickness (px)
GAP = 5             # gap between photo edge and ring (px)
SIGMA = 0.55        # shimmer arc half-width (radians, ~32°)
SS = 2              # supersample for edge antialiasing


def _circle_photo(diameter: int) -> Image.Image:
    """brian.jpg center-cropped to a circle of the given diameter (RGBA)."""
    photo = ImageOps.fit(Image.open(PHOTO).convert("RGB"), (diameter, diameter),
                         method=Image.LANCZOS, centering=(0.5, 0.42))
    mask = Image.new("L", (diameter * SS, diameter * SS), 0)
    from PIL import ImageDraw
    ImageDraw.Draw(mask).ellipse((0, 0, diameter * SS - 1, diameter * SS - 1), fill=255)
    mask = mask.resize((diameter, diameter), Image.LANCZOS)  # AA edge
    photo = photo.convert("RGBA")
    photo.putalpha(mask)
    return photo


def _ring_frame(theta: float) -> Image.Image:
    """One RGBA ring image with the shimmer highlight peaked at angle theta."""
    w = OUT_PX * SS
    c = w / 2
    r_out = c - 2 * SS
    r_in = r_out - RING_W * SS
    ys, xs = np.mgrid[0:w, 0:w]
    dx, dy = xs - c + 0.5, ys - c + 0.5
    rad = np.hypot(dx, dy)
    ang = np.arctan2(dy, dx)
    ring = (rad >= r_in) & (rad <= r_out)

    # wrapped angular distance to theta, then a gaussian shimmer bump 0..1
    d = np.angle(np.exp(1j * (ang - theta)))
    hi = np.exp(-(d / SIGMA) ** 2)
    color = BRASS + (HILITE - BRASS) * hi[..., None]  # (w,w,3)

    rgba = np.zeros((w, w, 4), np.uint8)
    rgba[..., :3] = np.clip(color, 0, 255).astype(np.uint8)
    rgba[..., 3] = np.where(ring, 255, 0).astype(np.uint8)
    img = Image.fromarray(rgba, "RGBA")
    return img.resize((OUT_PX, OUT_PX), Image.LANCZOS)  # AA edges


def build(out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    r_out = OUT_PX / 2 - 2
    photo_d = int((r_out - RING_W - GAP) * 2)
    photo = _circle_photo(photo_d)
    off = (OUT_PX - photo_d) // 2

    rgb = []
    for f in range(N_FRAMES):
        theta = 2 * np.pi * f / N_FRAMES
        base = Image.new("RGBA", (OUT_PX, OUT_PX), BONE + (255,))
        base.alpha_composite(photo, (off, off))
        base.alpha_composite(_ring_frame(theta))
        rgb.append(base.convert("RGB"))

    # one shared palette from frame 0 → only the ring pixels differ frame-to-frame,
    # so disposal=1 + optimize stores tiny diffs (the photo center is identical).
    pal = rgb[0].quantize(colors=128, method=Image.MEDIANCUT)
    frames = [f.quantize(palette=pal, dither=Image.NONE) for f in rgb]
    frames[0].save(out_path, save_all=True, append_images=frames[1:],
                   duration=90, loop=0, disposal=1, optimize=True)
    return out_path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()
    path = build(Path(args.out))

    # self-check: exists, animated, within a sane email ceiling
    kb = path.stat().st_size / 1024
    with Image.open(path) as im:
        n = getattr(im, "n_frames", 1)
    assert path.exists(), "GIF not written"
    assert n > 1, f"not animated (n_frames={n})"
    assert kb < 600, f"GIF too heavy for email: {kb:.0f}KB"
    flag = "" if kb <= 250 else "  (over 250KB target — still ships)"
    print(f"✓ {path}  ·  {n} frames  ·  {kb:.0f}KB{flag}")


if __name__ == "__main__":
    main()
