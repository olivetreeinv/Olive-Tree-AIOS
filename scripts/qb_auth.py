#!/usr/bin/env python3
"""
QuickBooks OAuth 2.0 production token capture.
Spins up a local server on port 8888, opens the Intuit auth page,
captures the callback, and prints the refresh token + realm ID.
"""
import base64
import http.server
import json
import os
import pathlib
import secrets
import sys
import threading
import urllib.parse
import urllib.request
import webbrowser


def _load_credentials():
    """Read client id/secret from env vars, falling back to .mcp.json.
    Never hardcode secrets in source — this file is committed."""
    client_id = os.environ.get("QUICKBOOKS_CLIENT_ID")
    client_secret = os.environ.get("QUICKBOOKS_CLIENT_SECRET")
    if client_id and client_secret:
        return client_id, client_secret

    mcp_path = pathlib.Path(__file__).resolve().parent.parent / ".mcp.json"
    try:
        env = json.loads(mcp_path.read_text())["mcpServers"]["quickbooks"]["env"]
        return env["QUICKBOOKS_CLIENT_ID"], env["QUICKBOOKS_CLIENT_SECRET"]
    except (FileNotFoundError, KeyError, json.JSONDecodeError) as e:
        sys.exit(
            "Missing QuickBooks credentials. Set QUICKBOOKS_CLIENT_ID and "
            f"QUICKBOOKS_CLIENT_SECRET, or ensure .mcp.json has them ({e})."
        )


CLIENT_ID, CLIENT_SECRET = _load_credentials()
REDIRECT_URI = "http://localhost:8888/callback"
SCOPE = "com.intuit.quickbooks.accounting"
AUTH_URL = "https://appcenter.intuit.com/connect/oauth2"
TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"

state = secrets.token_urlsafe(16)
result = {}
server_done = threading.Event()


class CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if not self.path.startswith("/callback"):
            self.send_response(404)
            self.end_headers()
            return

        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        code = params.get("code", [None])[0]
        realm_id = params.get("realmId", [None])[0]
        returned_state = params.get("state", [None])[0]

        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()

        if returned_state != state:
            self.wfile.write(b"<h1>State mismatch - possible CSRF. Abort.</h1>")
            server_done.set()
            return

        if not code:
            self.wfile.write(b"<h1>No code returned. Auth failed.</h1>")
            server_done.set()
            return

        # Exchange code for tokens
        credentials = base64.b64encode(
            f"{CLIENT_ID}:{CLIENT_SECRET}".encode()
        ).decode()
        body = urllib.parse.urlencode({
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
        }).encode()

        req = urllib.request.Request(
            TOKEN_URL,
            data=body,
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                tokens = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            err = e.read().decode()
            self.wfile.write(f"<h1>Token exchange failed</h1><pre>{err}</pre>".encode())
            server_done.set()
            return

        result["refresh_token"] = tokens.get("refresh_token")
        result["realm_id"] = realm_id

        self.wfile.write(
            b"<h1>Success! You can close this tab.</h1>"
            b"<p>Switch back to your terminal to see your tokens.</p>"
        )
        server_done.set()

    def log_message(self, *args):
        pass  # silence access logs


def main():
    auth_params = urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPE,
        "state": state,
    })
    auth_link = f"{AUTH_URL}?{auth_params}"

    server = http.server.HTTPServer(("localhost", 8888), CallbackHandler)
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()

    print("Opening Intuit authorization page in your browser...")
    print(f"\nIf it doesn't open automatically, paste this URL:\n{auth_link}\n")
    webbrowser.open(auth_link)

    server_done.wait(timeout=120)
    server.shutdown()

    if not result:
        print("Timed out or failed — no tokens captured.")
        return

    # Keep the refresh token out of terminal scrollback — write it to a 0600 file.
    out = pathlib.Path(__file__).parent.parent / ".qb_tokens"
    out.write_text(
        f"QUICKBOOKS_REFRESH_TOKEN={result['refresh_token']}\n"
        f"QUICKBOOKS_REALM_ID={result['realm_id']}\n"
    )
    out.chmod(0o600)
    tok = result["refresh_token"] or ""
    print("\n--- PRODUCTION TOKENS ---")
    print(f"QUICKBOOKS_REFRESH_TOKEN={tok[:6]}…{tok[-4:]} (full value in {out.name})")
    print(f"QUICKBOOKS_REALM_ID={result['realm_id']}")
    print(f"\nFull tokens saved to {out} — paste into .mcp.json, set QUICKBOOKS_ENVIRONMENT=production, then delete the file.")


if __name__ == "__main__":
    main()
