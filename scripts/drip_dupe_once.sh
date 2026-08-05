#!/bin/sh
# drip_dupe_once.sh — one-shot post-cutover drip check, then removes its own job.
#
# Scheduled for the morning after the MacBook→mini cutover (2026-08-05) to confirm
# the 9am drip fired from exactly one machine. launchd's StartCalendarInterval has
# no year field, so without self-removal this would fire again next month.

REPO="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.olivetree.drip-dupe-check"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

"$REPO/.venv/bin/python" "$REPO/scripts/drip_dupe_check.py" --notify \
	>>"$REPO/logs/drip-dupe-check.log" 2>&1

# Fire once, then retire.
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null
rm -f "$PLIST"
echo "$(date '+%Y-%m-%d %H:%M') one-shot complete, job removed" >>"$REPO/logs/drip-dupe-check.log"
