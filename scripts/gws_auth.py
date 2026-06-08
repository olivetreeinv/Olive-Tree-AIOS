#!/usr/bin/env python3
import json
import subprocess
import requests


def get_token():
    try:
        result = subprocess.run(
            ["gws", "auth", "export", "--unmasked"],
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

    resp = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id":     client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type":    "refresh_token",
    }, timeout=10)
    resp.raise_for_status()
    return resp.json()["access_token"]
