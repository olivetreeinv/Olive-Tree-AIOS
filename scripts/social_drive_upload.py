#!/usr/bin/env python3
"""
social_drive_upload.py — upload a rendered carousel to Brian's social Drive folder,
make the slides public, and return the direct image URLs for Metricool.

Convention: one dated+titled subfolder per post inside SOCIAL_FOLDER_ID:
    <SOCIAL_FOLDER>/<YYYY-MM-DD — Title>/slide01.png …

Each slide is shared "anyone with link" and returned as the direct-image form
https://lh3.googleusercontent.com/d/<id> (no redirect; Metricool re-hosts it).

CLI:
    python3 scripts/social_drive_upload.py \
        --slides-dir output/carousel/2026-06-30-supply-fell \
        --date 2026-06-30 --title "Apartment Supply Fell 61%"
"""
from __future__ import annotations
import argparse, glob, json, sys
from pathlib import Path
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gws_auth import get_token
from deal_archive import upload_file

DRIVE = "https://www.googleapis.com/drive/v3"
# Brian's "Instagram Post Drafts" Drive folder (provided 2026-06-30).
SOCIAL_FOLDER_ID = "1a46dKGTj8ggEWbTaRN-TuZv_EL__a6AY"


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


def _find_or_make_folder(tok, name, parent):
    safe = name.replace("'", "\\'")
    q = (f"name='{safe}' and mimeType='application/vnd.google-apps.folder' "
         f"and '{parent}' in parents and trashed=false")
    r = requests.get(f"{DRIVE}/files", headers=_h(tok),
                     params={"q": q, "fields": "files(id)"}, timeout=30)
    r.raise_for_status()
    files = r.json().get("files", [])
    if files:
        return files[0]["id"]
    r = requests.post(f"{DRIVE}/files", headers=_h(tok),
                      json={"name": name, "mimeType": "application/vnd.google-apps.folder",
                            "parents": [parent]}, timeout=30)
    r.raise_for_status()
    return r.json()["id"]


def upload_carousel(slides_dir: str, date_str: str, title: str,
                    parent: str = SOCIAL_FOLDER_ID) -> dict:
    """Upload all slide*.png in slides_dir. Returns {folder_id, urls:[...]}."""
    tok = get_token()
    sub = _find_or_make_folder(tok, f"{date_str} — {title}", parent)
    urls = []
    for p in sorted(glob.glob(f"{slides_dir}/slide*.png")):
        fid = upload_file(tok, sub, p, display_name=Path(p).name)
        requests.post(f"{DRIVE}/files/{fid}/permissions",
                      headers={**_h(tok), "Content-Type": "application/json"},
                      data=json.dumps({"role": "reader", "type": "anyone"}),
                      timeout=30).raise_for_status()
        urls.append(f"https://lh3.googleusercontent.com/d/{fid}")
    return {"folder_id": sub, "urls": urls}


def upload_video(video_path: str, date_str: str, title: str,
                 parent: str = SOCIAL_FOLDER_ID) -> str:
    """Upload one MP4, share public, return a direct-download URL Metricool can fetch.
    NOTE: the lh3.googleusercontent.com form used for images 404s on video — Metricool
    needs the raw-bytes download URL (verified 2026-07-07: it re-hosts it to its own CDN,
    which also sidesteps the 'link Google Drive in Metricool' requirement)."""
    tok = get_token()
    sub = _find_or_make_folder(tok, f"{date_str} — {title}", parent)
    fid = upload_file(tok, sub, video_path, display_name=Path(video_path).name)
    requests.post(f"{DRIVE}/files/{fid}/permissions",
                  headers={**_h(tok), "Content-Type": "application/json"},
                  data=json.dumps({"role": "reader", "type": "anyone"}),
                  timeout=30).raise_for_status()
    return f"https://drive.usercontent.google.com/download?id={fid}&export=download"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slides-dir", help="folder of slide*.png (image carousel)")
    ap.add_argument("--video", help="path to an .mp4 (motion cover) instead of slides")
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--title", required=True)
    args = ap.parse_args()
    if args.video:
        print(upload_video(args.video, args.date, args.title))
        return
    if not args.slides_dir:
        ap.error("provide --slides-dir or --video")
    out = upload_carousel(args.slides_dir, args.date, args.title)
    print(f"folder: https://drive.google.com/drive/folders/{out['folder_id']}")
    print("\n".join(out["urls"]))


if __name__ == "__main__":
    main()
