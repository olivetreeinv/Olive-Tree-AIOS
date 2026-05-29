#!/usr/bin/env python3
"""
Canva OAuth Setup — Olive Tree Investments
Run once to authorize and save tokens to .env.
Requires: CANVA_CLIENT_ID and CANVA_CLIENT_SECRET already in .env

Usage:
    cd "Olive AIOS"
    source .env
    python3 scripts/canva_oauth_setup.py
"""

import os
import sys
import base64
import hashlib
import secrets
import urllib.parse
import webbrowser
import http.server
import threading
import requests
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
REDIRECT_PORT = 8765
REDIRECT_URI = f"http://127.0.0.1:{REDIRECT_PORT}/callback"
AUTHORIZE_URL = "https://www.canva.com/api/oauth/authorize"
TOKEN_URL = "https://api.canva.com/rest/v1/oauth/token"
ENV_FILE = Path(__file__).parent.parent / ".env"

SCOPES = [
    "design:content:read",
    "design:content:write",
    "design:meta:read",
    "asset:read",
    "asset:write",
    "brandtemplate:content:read",
    "brandtemplate:meta:read",
    "folder:read",
    "folder:write",
    "profile:read",
]

# ── PKCE helpers ──────────────────────────────────────────────────────────────
def generate_pkce():
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    return verifier, challenge

# ── Local callback server ─────────────────────────────────────────────────────
auth_code = None
auth_state = None

class CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code, auth_state
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        auth_code = params.get("code", [None])[0]
        auth_state = params.get("state", [None])[0]
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(b"""
        <html><body style='font-family:sans-serif;padding:40px;'>
        <h2>&#10003; Canva connected!</h2>
        <p>You can close this tab and return to the terminal.</p>
        </body></html>""")

    def log_message(self, format, *args):
        pass  # suppress server logs

# ── Token exchange ─────────────────────────────────────────────────────────────
def exchange_code(client_id, client_secret, code, verifier):
    creds = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    r = requests.post(
        TOKEN_URL,
        headers={
            "Authorization": f"Basic {creds}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": verifier,
            "client_id": client_id,
        },
    )
    if r.status_code != 200:
        print(f"\n✗ Token exchange failed: {r.status_code} {r.text}")
        sys.exit(1)
    return r.json()

# ── Write tokens to .env ───────────────────────────────────────────────────────
def update_env(access_token, refresh_token):
    if not ENV_FILE.exists():
        print(f"✗ .env not found at {ENV_FILE}")
        sys.exit(1)

    content = ENV_FILE.read_text()
    lines = content.splitlines()
    updated = {k: False for k in ("CANVA_ACCESS_TOKEN", "CANVA_REFRESH_TOKEN")}

    new_lines = []
    for line in lines:
        if line.startswith("CANVA_ACCESS_TOKEN="):
            new_lines.append(f"CANVA_ACCESS_TOKEN={access_token}")
            updated["CANVA_ACCESS_TOKEN"] = True
        elif line.startswith("CANVA_REFRESH_TOKEN="):
            new_lines.append(f"CANVA_REFRESH_TOKEN={refresh_token}")
            updated["CANVA_REFRESH_TOKEN"] = True
        else:
            new_lines.append(line)

    # Append any that weren't replaced
    for key, was_updated in updated.items():
        if not was_updated:
            value = access_token if key == "CANVA_ACCESS_TOKEN" else refresh_token
            new_lines.append(f"{key}={value}")

    ENV_FILE.write_text("\n".join(new_lines) + "\n")
    print(f"✓ Tokens saved to .env")

# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    client_id = os.getenv("CANVA_CLIENT_ID")
    client_secret = os.getenv("CANVA_CLIENT_SECRET")

    if not client_id or not client_secret:
        print("✗ CANVA_CLIENT_ID and CANVA_CLIENT_SECRET must be in .env")
        print("  Run: source .env  before running this script")
        sys.exit(1)

    verifier, challenge = generate_pkce()
    state = secrets.token_urlsafe(16)

    auth_params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "scope": " ".join(SCOPES),
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    auth_url = f"{AUTHORIZE_URL}?{urllib.parse.urlencode(auth_params)}"

    # Start local callback server
    server = http.server.HTTPServer(("127.0.0.1", REDIRECT_PORT), CallbackHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    print("\n── Canva OAuth Setup ─────────────────────────────────────────")
    print("Opening browser for authorization...")
    print(f"\nIf browser doesn't open, visit:\n{auth_url}\n")
    webbrowser.open(auth_url)

    # Wait for callback
    print("Waiting for authorization callback...", end="", flush=True)
    while auth_code is None:
        import time; time.sleep(0.5)
        print(".", end="", flush=True)
    server.shutdown()
    print(" done.\n")

    # Exchange code for tokens
    print("Exchanging code for tokens...")
    tokens = exchange_code(client_id, client_secret, auth_code, verifier)

    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")
    expires_in = tokens.get("expires_in", "unknown")

    print(f"✓ Access token received (expires in {expires_in}s)")
    print(f"✓ Refresh token received")

    # Save to .env
    update_env(access_token, refresh_token)

    # Verify connection
    print("\nVerifying connection...")
    r = requests.get(
        "https://api.canva.com/rest/v1/users/me",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    if r.status_code == 200:
        user = r.json().get("user", {})
        print(f"✓ Connected as: {user.get('display_name', 'unknown')} ({user.get('email', '')})")
        print("\n── Setup complete! ───────────────────────────────────────────")
        print("Canva is ready. Run 'source .env' to load the new tokens.\n")
    else:
        print(f"⚠ Token saved but verification returned {r.status_code} — check scopes")

if __name__ == "__main__":
    main()
