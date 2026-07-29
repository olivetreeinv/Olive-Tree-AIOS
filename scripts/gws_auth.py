#!/usr/bin/env python3
import json
import os
import shutil
import subprocess
import time

import requests


def _gws_bin() -> str:
    """Resolve the gws binary. launchd strips PATH to /usr/bin:/bin, where gws
    (Homebrew) isn't found — so fall back to known install locations."""
    return (
        shutil.which("gws")
        or next((p for p in ("/opt/homebrew/bin/gws", "/usr/local/bin/gws",
                             os.path.expanduser("~/go/bin/gws")) if os.path.exists(p)), None)
        or "gws"  # last resort: let subprocess raise the usual FileNotFoundError
    )


def get_token():
    try:
        result = subprocess.run(
            [_gws_bin(), "auth", "export", "--unmasked"],
            capture_output=True, text=True, check=True, timeout=30
        )
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
        raise RuntimeError(
            "Could not export gws credentials. Run: gws auth login -s gmail,calendar,drive,sheets"
        ) from e

    try:
        creds = json.loads(result.stdout)
        client_id     = creds["client_id"]
        client_secret = creds["client_secret"]
        refresh_token = creds["refresh_token"]
    except (json.JSONDecodeError, KeyError) as e:
        raise RuntimeError(
            "gws credentials are malformed or incomplete. Re-run: gws auth login"
        ) from e

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
