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

# Pull NOTIFY_IMESSAGE_TO from .env if present.
if [ -f "$REPO/.env" ]; then
  NOTIFY_IMESSAGE_TO=$(grep -E '^NOTIFY_IMESSAGE_TO=' "$REPO/.env" | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'")
fi

# 1) macOS banner (shows at the Mac).
osascript -e "display notification \"$MESSAGE\" with title \"$TITLE\" sound name \"Glass\""

# 2) iMessage to self (reaches your phone), only if a handle is configured.
if [ -n "$NOTIFY_IMESSAGE_TO" ]; then
  osascript <<EOF
tell application "Messages"
    set targetService to 1st service whose service type = iMessage
    set targetBuddy to buddy "$NOTIFY_IMESSAGE_TO" of targetService
    send "$TITLE: $MESSAGE" to targetBuddy
end tell
EOF
fi
