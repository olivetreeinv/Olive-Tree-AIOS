#!/usr/bin/env python3
"""In-window browser preview for rendered carousels.

Builds output/carousel/_preview.html — a horizontal filmstrip of every deck's
slides — and ensures serve_range.py is running on the repo root so VSCode's
Simple Browser can open the localhost URL.

Usage:
  python3 scripts/carousel_preview.py <carousel_dir> [<carousel_dir> ...] [--port 8090]
Prints the http://localhost URL to paste/open in the in-window browser.
"""
import argparse
import socket
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _slides(d):
    return sorted(p.resolve() for p in Path(d).glob("slide*.png"))


def _motion(d):
    # any *motion*.mp4 in the deck dir, shown first as an autoplay loop
    return sorted(p.resolve() for p in Path(d).glob("*motion*.mp4"))


def _url(p):
    return "/" + p.relative_to(REPO).as_posix()


def build_html(dirs):
    blocks = []
    for d in dirs:
        d = Path(d)
        vids = "".join(
            f'<figure><video src="{_url(v)}" autoplay loop muted playsinline></video>'
            f'<figcaption>motion</figcaption></figure>'
            for v in _motion(d)
        )
        imgs = _slides(d)
        if not imgs and not vids:
            continue
        strip = vids + "".join(
            f'<figure><img src="{_url(img)}" loading="lazy">'
            f'<figcaption>{i}/{len(imgs)}</figcaption></figure>'
            for i, img in enumerate(imgs, 1)
        )
        blocks.append(f'<section><h2>{d.name}</h2><div class="strip">{strip}</div></section>')
    if not blocks:
        blocks.append('<p style="padding:24px">No slide*.png found in the given dirs.</p>')
    return (
        "<!doctype html><meta charset=utf-8><title>Carousel preview</title>"
        "<style>"
        "body{margin:0;background:#F5F2E9;font-family:Archivo,system-ui,sans-serif;color:#1B1E08}"
        "h2{padding:16px 20px 4px;font-size:15px;letter-spacing:.08em;text-transform:uppercase;color:#505A19}"
        ".strip{display:flex;gap:16px;overflow-x:auto;padding:12px 20px 28px;scroll-snap-type:x mandatory}"
        "figure{margin:0;flex:0 0 auto;scroll-snap-align:center}"
        "img,video{height:74vh;max-height:840px;border-radius:14px;box-shadow:0 8px 30px rgba(0,0,0,.15);display:block}"
        "figcaption{text-align:center;color:#505A19;font-size:13px;padding-top:6px}"
        "</style>" + "".join(blocks)
    )


def _server_up(port):
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def ensure_server(port):
    if _server_up(port):
        return "already running"
    log = open(REPO / "output" / "carousel" / "_preview_server.log", "ab")
    subprocess.Popen(
        [sys.executable, str(REPO / "scripts" / "serve_range.py"), str(REPO), str(port)],
        stdout=log, stderr=log, start_new_session=True,
    )
    for _ in range(25):  # serve_range binds fast; poll up to ~5s
        if _server_up(port):
            return "started"
        time.sleep(0.2)
    return "FAILED to start"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dirs", nargs="+", help="carousel output dirs (each holds slide*.png)")
    ap.add_argument("--port", type=int, default=8090)
    a = ap.parse_args()
    out = REPO / "output" / "carousel" / "_preview.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_html(a.dirs))
    status = ensure_server(a.port)
    print(f"server: {status} on :{a.port}")
    print(f"http://localhost:{a.port}/output/carousel/_preview.html")


if __name__ == "__main__":
    main()
