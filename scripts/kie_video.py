#!/usr/bin/env python3
"""kie_video.py — generate a Seedance 2.0 clip via kie.ai. Used by /cinematic-website.

Same createTask -> recordInfo poll flow as kie_hero.py, but keeps the hosted
result URL (needed to chain clips / reference images across generations).

COST: Seedance 2.0 std at 1080p/8s ran ~816 credits (~$4) per clip on 2026-07-07.
kie.ai allows the balance to go NEGATIVE — the guard below refuses to start a
clip without enough credits unless --force.

CLI:
    python3 scripts/kie_video.py --prompt "..." --out clip.mp4                  # 1080p 16:9 8s
    python3 scripts/kie_video.py --prompt "..." --out c.mp4 --ref-image URL     # identity reference
    python3 scripts/kie_video.py --prompt "..." --out c.mp4 --first-frame URL   # chain from a frame
    python3 scripts/kie_video.py --check                                        # balance only
"""
from __future__ import annotations
import argparse
import json
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.kie_hero import _key, _headers, credits, BASE

MODEL = "bytedance/seedance-2"
IMAGE_MODEL = "gpt-image-2-text-to-image"  # ~6 credits; for hero-image references
CREDITS_PER_CLIP = {"480p": 150, "720p": 350, "1080p": 850, "4k": 3500}  # rough guards, 8s std


def generate(prompt, out_path, *, resolution="1080p", aspect="16:9", duration=8,
             ref_images=None, first_frame=None, last_frame=None, image=False,
             poll_s=15, timeout_s=1200) -> tuple[Path, str] | None:
    """Returns (local_path, hosted_url) or None on failure."""
    key = _key()
    if not key:
        print("kie: KIE_API_KEY not set", file=sys.stderr)
        return None
    if image:
        model, inp = IMAGE_MODEL, {"prompt": prompt, "aspect_ratio": aspect}
    else:
        model = MODEL
        inp = {"prompt": prompt, "generate_audio": False, "resolution": resolution,
               "aspect_ratio": aspect, "duration": duration}
        if ref_images:
            inp["reference_image_urls"] = ref_images
        if first_frame:
            inp["first_frame_url"] = first_frame
        if last_frame:
            inp["last_frame_url"] = last_frame

    try:
        r = requests.post(f"{BASE}/createTask", headers=_headers(key),
                          json={"model": model, "input": inp}, timeout=60).json()
    except (requests.RequestException, ValueError) as e:
        print(f"kie: createTask request failed ({e})", file=sys.stderr)
        return None
    task_id = r.get("data", {}).get("taskId")
    if r.get("code") != 200 or not task_id:
        print(f"kie: createTask failed ({r.get('msg')})", file=sys.stderr)
        return None
    # taskId first: the task bills even if this process dies; recordInfo can recover it
    print(f"kie: taskId {task_id}", file=sys.stderr)

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        time.sleep(poll_s)
        try:
            rec = requests.get(f"{BASE}/recordInfo", headers=_headers(key),
                               params={"taskId": task_id}, timeout=30).json()
        except (requests.RequestException, ValueError):
            continue  # transient poll failure must not orphan a billed task
        state = rec.get("data", {}).get("state")
        if state == "success":
            urls = json.loads(rec["data"]["resultJson"] or "{}").get("resultUrls") or []
            if not urls:
                print("kie: success but no resultUrls (billed-but-empty?)", file=sys.stderr)
                return None
            out_path = Path(out_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                dl = requests.get(urls[0], timeout=180)
                dl.raise_for_status()
            except requests.RequestException:
                continue  # result stays available — retry download next poll
            out_path.write_bytes(dl.content)
            return out_path, urls[0]
        if state == "fail":
            print(f"kie: generation failed ({rec['data'].get('failMsg')})", file=sys.stderr)
            return None
    print("kie: timed out", file=sys.stderr)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt")
    ap.add_argument("--out")
    ap.add_argument("--resolution", default="1080p", choices=["480p", "720p", "1080p", "4k"])
    ap.add_argument("--aspect", default="16:9")
    ap.add_argument("--duration", type=int, default=8)
    ap.add_argument("--ref-image", action="append", help="reference image URL (repeatable)")
    ap.add_argument("--first-frame", help="start-frame image URL (clip chaining)")
    ap.add_argument("--last-frame", help="end-frame image URL")
    ap.add_argument("--image", action="store_true",
                    help="generate a still (GPT Image 2) instead of video; prints the hosted URL for use as --ref-image")
    ap.add_argument("--force", action="store_true", help="skip the credit-balance guard")
    ap.add_argument("--check", action="store_true", help="print credit balance and exit")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the request and cost estimate WITHOUT submitting (spends nothing)")
    a = ap.parse_args()

    bal = credits()
    if a.check:
        print(f"credits: {bal}")
        return 0
    if not a.prompt or not a.out:
        ap.error("provide --prompt and --out, or use --check")

    need = 6 if a.image else CREDITS_PER_CLIP[a.resolution] * a.duration / 8
    if a.dry_run:
        print(json.dumps({"dry_run": True, "balance": bal, "est_credits": need,
                          "resolution": a.resolution, "duration": a.duration,
                          "prompt": a.prompt, "out": a.out}))
        return 0
    if not a.force and (bal is None or bal < need):
        print(f"kie: balance {bal} < ~{need:.0f} credits needed. "
              f"Top up at kie.ai or pass --force.", file=sys.stderr)
        return 1

    res = generate(a.prompt, a.out, resolution=a.resolution, aspect=a.aspect,
                   duration=a.duration, ref_images=a.ref_image,
                   first_frame=a.first_frame, last_frame=a.last_frame, image=a.image)
    if not res:
        return 1
    path, url = res
    print(json.dumps({"path": str(path), "url": url, "credits_left": credits()}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
