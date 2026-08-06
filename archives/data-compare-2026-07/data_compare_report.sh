#!/bin/bash
# July 8 one-shot: generate the Polygon-vs-Alpaca verdict, email it, then
# self-remove BOTH launchd jobs so nothing persists past the experiment.
set -uo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"

OUT=/tmp/datacompare_report.txt
python3 scripts/data_compare.py --report > "$OUT" 2>&1 || true

# Email the verdict (uses GOOGLE_* creds from .env, same path as the daily brief)
python3 scripts/daily_brief_cloud.py send \
  --to brian@olivetreeinv.io \
  --subject "Polygon vs Alpaca — week verdict (July 8)" \
  --body-file "$OUT" || true

# Self-clean: stop and delete both LaunchAgents
LA="$HOME/Library/LaunchAgents"
launchctl unload "$LA/com.olivetree.datacompare.plist" 2>/dev/null || true
launchctl unload "$LA/com.olivetree.datacompare.report.plist" 2>/dev/null || true
rm -f "$LA/com.olivetree.datacompare.plist" "$LA/com.olivetree.datacompare.report.plist"
