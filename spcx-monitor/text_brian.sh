#!/bin/bash
# Send an iMessage to Brian. Usage: text_brian.sh "message"
osascript - "$1" <<'EOF'
on run argv
  tell application "Messages"
    set t to first service whose service type = iMessage
    send (item 1 of argv) to buddy "+14046432356" of t
  end tell
end run
EOF
echo "text sent"
