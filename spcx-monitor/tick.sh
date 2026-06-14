#!/bin/bash
# One-command loop tick: tape read + SOLD-email check. Allowlisted so the
# watch loop runs unattended. Usage: tick.sh [db_path]
cd "$(dirname "$0")" || exit 1
DB="${1:-data/spcx_ipoday_20260612.db}"
python3 watch.py "$DB"
echo "--- SOLD check ---"
gws gmail users messages list --params '{"userId": "me", "q": "subject:SOLD newer_than:1d", "maxResults": 3}' 2>/dev/null \
  | python3 -c "import json,sys; d=json.load(sys.stdin); n=d.get('resultSizeEstimate',0); print(f'SOLD emails: {n}')" \
  || echo "SOLD check: gmail query failed"
echo "--- feed ---"
curl -s --max-time 5 http://127.0.0.1:8765/status \
  | python3 -c "import json,sys; s=json.load(sys.stdin); print('feed:', (s.get('feed') or {}).get('name','?'))" \
  || echo "feed: server unreachable"
