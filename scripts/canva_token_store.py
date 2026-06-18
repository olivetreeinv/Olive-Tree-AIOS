#!/usr/bin/env python3
"""
Canva Token Store — Olive Tree Investments

Persists the rotating Canva token pair in a PRIVATE Google Drive file so
cloud runs survive Canva's single-use refresh-token rotation. The Drive
file is the durable source of truth; .env is the local convenience copy.

Why: Canva refresh tokens are single-use — each refresh issues a new one.
A stateless cloud routine can't save the new token to its own env, so it
reads/writes the token here (Drive) each run instead.

Stdlib-only (urllib), uses loom_sync's Google auth + HTTP helpers.
The store file is named `.canva_tokens.json` and lives in the Pitch Decks
Drive folder. It is never shared (owner-private) and never committed to git.
"""

import json
import os
import urllib.parse
import uuid

import loom_sync as G
from loom_sync import _http, _auth

STORE_FILENAME = ".canva_tokens.json"
# Store the credential in the PRIVATE "Olive Tree Investments - Systems" folder
# — NOT the Pitch Decks folder, which holds shareable deck PDFs (sharing that
# folder would leak this refresh token). Override via CANVA_TOKEN_FOLDER_ID.
STORE_FOLDER_ID = os.environ.get(
    "CANVA_TOKEN_FOLDER_ID", "1WjtT0oClNy_pLEETDbWfJBYsuvYHrIAZ").strip()


def _find_store_file(gtoken):
    q = (f"name='{STORE_FILENAME}' and '{STORE_FOLDER_ID}' in parents "
         "and trashed=false")
    params = urllib.parse.urlencode({"q": q, "fields": "files(id,name)"})
    data = _http("GET", f"{G.DRIVE_BASE}/files?{params}", headers=_auth(gtoken), timeout=30)
    files = data.get("files", [])
    return files[0]["id"] if files else None


def load_tokens(gtoken):
    """Return the stored token dict, or {} if no store file yet."""
    fid = _find_store_file(gtoken)
    if not fid:
        return {}
    raw = _http("GET", f"{G.DRIVE_BASE}/files/{fid}?alt=media",
                headers=_auth(gtoken), raw=True, timeout=30)
    try:
        return json.loads(raw.decode())
    except (ValueError, UnicodeDecodeError):
        return {}


def save_tokens(gtoken, tokens):
    """Create or overwrite the private store file with the token dict."""
    content = json.dumps(tokens, indent=2).encode()
    fid = _find_store_file(gtoken)
    if fid:
        # Update existing file's media (stays private, no parents change).
        _http("PATCH",
              f"{G.DRIVE_UPLOAD}/{fid}?uploadType=media",
              headers={**_auth(gtoken), "Content-Type": "application/json"},
              data=content, timeout=60)
        return fid

    # Create new multipart (metadata + media); owner-private by default.
    boundary = uuid.uuid4().hex
    meta = {"name": STORE_FILENAME, "parents": [STORE_FOLDER_ID]}
    body = b"".join([
        f"--{boundary}\r\n".encode(),
        b"Content-Type: application/json; charset=UTF-8\r\n\r\n",
        json.dumps(meta).encode(), b"\r\n",
        f"--{boundary}\r\n".encode(),
        b"Content-Type: application/json\r\n\r\n",
        content, b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ])
    resp = _http("POST", f"{G.DRIVE_UPLOAD}?uploadType=multipart&fields=id",
                 headers={**_auth(gtoken),
                          "Content-Type": f"multipart/related; boundary={boundary}"},
                 data=body, timeout=60)
    return resp["id"]


def seed_from_env(gtoken):
    """One-time: write the current .env Canva token pair into the Drive store."""
    tokens = {
        "access_token":  os.environ.get("CANVA_ACCESS_TOKEN", ""),
        "refresh_token": os.environ.get("CANVA_REFRESH_TOKEN", ""),
    }
    if not tokens["refresh_token"]:
        raise RuntimeError("No CANVA_REFRESH_TOKEN in env to seed the store.")
    fid = save_tokens(gtoken, tokens)
    return fid


if __name__ == "__main__":
    # Seed the store from current .env creds: python3 scripts/canva_token_store.py seed
    import sys
    from loom_sync import _load_dotenv, get_token
    _load_dotenv()
    if len(sys.argv) > 1 and sys.argv[1] == "seed":
        gt = get_token()
        fid = seed_from_env(gt)
        print(f"Seeded Canva token store → Drive file {fid} (private).")
    else:
        gt = get_token()
        print(json.dumps({k: (v[:12] + "…" if isinstance(v, str) and v else v)
                          for k, v in load_tokens(gt).items()}, indent=2))
