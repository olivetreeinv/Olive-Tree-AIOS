#!/bin/sh
# notify.sh — reusable local notifier for the Olive AIOS.
# Usage: notify.sh "Title" "Message body"
# Fires a macOS banner (always) and an ntfy push (if NTFY_TOPIC is set).
#
# ntfy is the ONLY channel that actually buzzes the phone. Two others were tried
# and removed 2026-07-31: iMessage-to-self lands silently (no push), and the
# Twilio SMS leg never had a TWILIO_TO to send to, so it had never once fired.
# TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN stay in .env on purpose — they are not
# alerting creds, scripts/rr_leads.py pulls rank-and-rent call logs with them.
#
# NTFY_TOPIC is read from "<repo>/.env"; the phone subscribes to the same topic
# in the ntfy app. No account, carrier, or verification needed.

REPO="$(cd "$(dirname "$0")/.." && pwd)"
TITLE="${1:-Olive AIOS}"
MESSAGE="${2:-(no message)}"

# Read a var from .env: strip quotes, inline "# comment", and surrounding whitespace.
env_val() {
  grep -E "^$1=" "$REPO/.env" | head -1 | cut -d= -f2- \
    | sed -E 's/[[:space:]]*#.*$//; s/^[[:space:]]+//; s/[[:space:]]+$//' \
    | tr -d '"' | tr -d "'"
}
if [ -f "$REPO/.env" ]; then
  NTFY_TOPIC=$(env_val NTFY_TOPIC)
fi

# 1) macOS banner (shows at the Mac). Pass text as args, not interpolated, so
# quotes/newlines in the message can't break the AppleScript.
osascript -e 'on run {t, m}' \
          -e 'display notification m with title t sound name "Glass"' \
          -e 'end run' "$TITLE" "$MESSAGE" 2>/dev/null

# 2) ntfy push — the phone notifier.
if [ -n "$NTFY_TOPIC" ]; then
  curl -s -H "Title: $TITLE" -d "$MESSAGE" "https://ntfy.sh/$NTFY_TOPIC" >/dev/null
fi
