#!/usr/bin/env python3
"""
drip_worker.py — launchd target for the daily drip run (com.olivetree.drip).

Runs `drip.py run` then `newsletter.py scan-unsubs`, appending both outputs
to output/drip-runner.log. A python3 worker (not /bin/sh) because launchd
shell jobs can't read ~/Documents under TCC (exit 126) — same pattern as
the other com.olivetree.* jobs.

NOTE: move this job to the Mac mini M4 when it arrives this week.
"""

import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
LOG = ROOT / "output" / "drip-runner.log"

COMMANDS = [
    [sys.executable, str(ROOT / "scripts" / "drip.py"), "run"],
    [sys.executable, str(ROOT / "scripts" / "newsletter.py"), "scan-unsubs"],
]


def main():
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a") as log:
        log.write(f"\n===== {datetime.now().isoformat(timespec='seconds')} =====\n")
        ok = True
        for cmd in COMMANDS:
            log.write(f"$ {' '.join(cmd[1:])}\n")
            r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, timeout=600)
            log.write(r.stdout)
            if r.stderr:
                log.write(r.stderr)
            if r.returncode != 0:
                log.write(f"[exit {r.returncode}]\n")
                ok = False
        log.write("OK\n" if ok else "COMPLETED WITH ERRORS\n")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
