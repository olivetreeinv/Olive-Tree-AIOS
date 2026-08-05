#!/usr/bin/env python3
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

REPO = Path(__file__).resolve().parent.parent


def _gws_bin() -> str:
    """Resolve the gws binary. launchd strips PATH to /usr/bin:/bin, where gws
    (Homebrew) isn't found — so fall back to known install locations."""
    return (
        shutil.which("gws")
        or next((p for p in ("/opt/homebrew/bin/gws", "/usr/local/bin/gws",
                             os.path.expanduser("~/go/bin/gws")) if os.path.exists(p)), None)
        or "gws"  # last resort: let subprocess raise the usual FileNotFoundError
    )


def _creds_from_gws():
    """Credentials via the gws CLI, or None if it isn't installed / isn't authed."""
    try:
        result = subprocess.run(
            [_gws_bin(), "auth", "export", "--unmasked"],
            capture_output=True, text=True, check=True, timeout=30
        )
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return None

    try:
        creds = json.loads(result.stdout)
        return (creds["client_id"], creds["client_secret"], creds["refresh_token"])
    except (json.JSONDecodeError, KeyError):
        return None


def _creds_from_env():
    """Credentials straight from .env — no external binary, so this is the path
    that survives launchd's stripped PATH. Returns None if any key is unset."""
    load_dotenv(REPO / ".env", override=False)
    cid    = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
    secret = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
    refresh = os.environ.get("GOOGLE_REFRESH_TOKEN", "").strip()
    return (cid, secret, refresh) if all((cid, secret, refresh)) else None


def get_token():
    creds = _creds_from_gws() or _creds_from_env()
    if creds is None:
        raise RuntimeError(
            "No Google credentials. Either set GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / "
            "GOOGLE_REFRESH_TOKEN in .env, or run: gws auth login -s gmail,calendar,drive,sheets"
        )
    client_id, client_secret, refresh_token = creds

    # ponytail: 3 tries, 5s backoff — Google's token endpoint flakes (~1/wk from launchd)
    for attempt in range(3):
        try:
            resp = requests.post("https://oauth2.googleapis.com/token", data={
                "client_id":     client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type":    "refresh_token",
            }, timeout=30)
            resp.raise_for_status()
            return resp.json()["access_token"]
        except (requests.ConnectionError, requests.Timeout):
            if attempt == 2:
                raise
            time.sleep(5)


if __name__ == "__main__":
    src = "gws CLI" if _creds_from_gws() else ("`.env`" if _creds_from_env() else "none")
    print(f"credential source: {src}")
    print(f"access token: OK ({len(get_token())} chars)")
