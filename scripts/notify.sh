#!/bin/sh
# notify.sh — reusable local notifier for the Olive AIOS.
# Usage: notify.sh "Title" "Message body"
# Fires a macOS banner (always) and an iMessage-to-self (if NOTIFY_IMESSAGE_TO is set).
#
# NOTIFY_IMESSAGE_TO is read from "<repo>/.env" (e.g. NOTIFY_IMESSAGE_TO="+15551234567"
# or an Apple ID email). Phone/email must be a handle your Messages.app is signed in to.

REPO="/Users/olivetree/Documents/Olive AIOS"
TITLE="${1:-Olive AIOS}"
MESSAGE="${2:-(no message)}"

# Pull handles/creds from .env if present.
# Read a var from .env: strip quotes, inline "# comment", and surrounding whitespace.
env_val() {
  grep -E "^$1=" "$REPO/.env" | head -1 | cut -d= -f2- \
    | sed -E 's/[[:space:]]*#.*$//; s/^[[:space:]]+//; s/[[:space:]]+$//' \
    | tr -d '"' | tr -d "'"
}
if [ -f "$REPO/.env" ]; then
  NOTIFY_IMESSAGE_TO=$(env_val NOTIFY_IMESSAGE_TO)
  TWILIO_ACCOUNT_SID=$(env_val TWILIO_ACCOUNT_SID)
  TWILIO_AUTH_TOKEN=$(env_val TWILIO_AUTH_TOKEN)
  TWILIO_FROM=$(env_val TWILIO_FROM)
  TWILIO_TO=$(env_val TWILIO_TO)
  NTFY_TOPIC=$(env_val NTFY_TOPIC)
fi

# 1) macOS banner (shows at the Mac).
osascript -e "display notification \"$MESSAGE\" with title \"$TITLE\" sound name \"Glass\""

# 1b) ntfy push — the reliable phone notifier (free, no carrier/verification needed).
if [ -n "$NTFY_TOPIC" ]; then
  curl -s -H "Title: $TITLE" -d "$MESSAGE" "https://ntfy.sh/$NTFY_TOPIC" >/dev/null
fi

# 2) Twilio SMS — arrives as a real inbound text, so the phone actually notifies.
# (iMessage-to-self lands silently — no push — which is why this channel exists.)
if [ -n "$TWILIO_ACCOUNT_SID" ] && [ -n "$TWILIO_TO" ]; then
  curl -s -X POST "https://api.twilio.com/2010-04-01/Accounts/$TWILIO_ACCOUNT_SID/Messages.json" \
    --data-urlencode "To=$TWILIO_TO" \
    --data-urlencode "From=$TWILIO_FROM" \
    --data-urlencode "Body=$TITLE: $MESSAGE" \
    -u "$TWILIO_ACCOUNT_SID:$TWILIO_AUTH_TOKEN" >/dev/null
fi

# 3) iMessage to self — disabled; ntfy push covers phone notifications.
# Restore by uncommenting if you want the Mac Messages thread history back.
# if [ -n "$NOTIFY_IMESSAGE_TO" ]; then
#   osascript <<EOF
# tell application "Messages"
#     set targetService to 1st service whose service type = iMessage
#     set targetBuddy to buddy "$NOTIFY_IMESSAGE_TO" of targetService
#     send "$TITLE: $MESSAGE" to targetBuddy
# end tell
# EOF
# fi
