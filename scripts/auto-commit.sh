#!/bin/sh
REPO="/Users/olivetree/Documents/Olive AIOS"
LOG="$REPO/logs/auto-commit.log"
cd "$REPO" || exit 1

DATE=$(date +%Y-%m-%d)
TIMESTAMP=$(date "+%Y-%m-%d %H:%M")

git add -A

if git diff --cached --quiet; then
  echo "[$TIMESTAMP] No changes — skipped." >> "$LOG"
  exit 0
fi

STATS=$(git diff --cached --shortstat)
git commit -m "Daily auto-commit $DATE"
echo "[$TIMESTAMP] Committed: $STATS" >> "$LOG"
