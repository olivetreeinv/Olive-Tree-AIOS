#!/usr/bin/env python3
"""
goal_watch.py — goal-aware monitor: not just "is it running" (heartbeat's
job) but "is it meeting its GOAL". Gathers deterministic launchd status +
evidence-command output per registry target, mines the last 24h of skill
runs from session transcripts, and makes ONE claude -p judge call to grade
each ON GOAL / OFF GOAL / NO DATA with a one-line fix. ntfy-pushes when
anything is OFF GOAL; writes a daily report.

Usage:
  python3 scripts/goal_watch.py             # judge, print, no push
  python3 scripts/goal_watch.py --dry       # print the judge prompt, skip claude + notify
  python3 scripts/goal_watch.py --no-notify # judge, print, don't push
  python3 scripts/goal_watch.py --notify    # judge, print, ntfy push if OFF GOAL
  python3 scripts/goal_watch.py --target dailyscan   # only that target

launchd: com.olivetree.goal-watch — weekdays 12:30pm ET.
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

from dotenv import load_dotenv
load_dotenv(REPO / ".env")

REGISTRY = REPO / "references" / "goal-registry.json"
SESSIONS_DIR = Path.home() / ".claude/projects/-Users-olivetree-Documents-Olive-AIOS"
SKILLS_DIR = REPO / ".claude" / "skills"
REPORT_DIR = REPO / "output" / "goal-watch"

EVIDENCE_TIMEOUT = 30
EVIDENCE_CAP = 3000

# ponytail: the only KeepAlive (kind=launchd, needs a live pid) job in the
# registry today is the trading desk; a single constant beats adding a
# launchd "mode" field to every registry entry for one exception.
KEEPALIVE_LABELS = {"com.olivetree.trading-desk"}

SYSTEM_PROMPT = """You are a plain-English goal auditor for Brian Norton's AI operating system.
For each TARGET output one line:
VERDICT|<name>|ON GOAL or OFF GOAL or NO DATA|<one-line why>|<one-line fix if OFF GOAL, else ->
Then a section:
IMPROVEMENTS:
- up to 3 concrete, one-line improvement suggestions for skills or routines that ran (best first). None worth making? Write "- none".
Rules: judge pace goals on pace, not a single day. Weekends/mid-week timing per each goal's own terms -> NO DATA, not OFF GOAL. Never invent evidence. No jargon."""


def load_registry(target_filter: str | None = None) -> list[dict]:
    try:
        data = json.loads(REGISTRY.read_text())
        targets = [t for t in data["targets"] if t.get("enabled", True)]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as e:
        sys.exit(f"goal-registry unreadable ({e}) — fix {REGISTRY} and re-run")
    if target_filter:
        targets = [t for t in targets if t["name"] == target_filter]
        if not targets:
            sys.exit(f"no enabled target named {target_filter!r} in {REGISTRY}")
    return targets


def run_evidence(cmd: str) -> str:
    try:
        r = subprocess.run(cmd, shell=True, cwd=REPO, capture_output=True,
                            text=True, timeout=EVIDENCE_TIMEOUT)
        out = (r.stdout or "") + (r.stderr or "")
        if not out.strip():
            out = "(no output)"
    except Exception as e:
        out = f"evidence failed: {e}"
    return out[:EVIDENCE_CAP]


_launchd_rows: dict[str, tuple[str, str]] | None = None
_launchctl_failed = False


def _launchctl_rows() -> dict[str, tuple[str, str]]:
    """One `launchctl list` call cached for every launchd target this run —
    ponytail: avoids N subprocess calls for N launchd targets."""
    global _launchd_rows, _launchctl_failed
    if _launchd_rows is not None:
        return _launchd_rows
    rows: dict[str, tuple[str, str]] = {}
    try:
        out = subprocess.run(["launchctl", "list"], capture_output=True,
                              text=True, timeout=15).stdout
        for line in out.splitlines()[1:]:
            parts = line.split("\t")
            if len(parts) == 3:
                rows[parts[2]] = (parts[0], parts[1])  # (pid, last exit status)
    except Exception:
        _launchctl_failed = True
    _launchd_rows = rows
    return rows


def check_launchd_target(label: str) -> str:
    """Deterministic status string for one launchd label — same read as
    heartbeat.check_launchd(), scoped to a single job."""
    rows = _launchctl_rows()
    if _launchctl_failed:
        return "UNKNOWN — launchctl list failed; do not treat as missing"
    if label not in rows:
        return "NOT SCHEDULED — job missing from launchctl list"
    pid, exit_status = rows[label]
    if label in KEEPALIVE_LABELS:
        return f"running now (pid {pid})" if pid != "-" else f"DOWN — not running, last exit {exit_status}"
    ok = exit_status == "0"
    return "scheduled, last run finished clean" if ok else f"scheduled, but last run FAILED (exit {exit_status})"


def mine_skill_runs() -> dict[str, dict]:
    """Skill/command invocations from session transcripts touched in the
    last 24h. ponytail: file-mtime cutoff, not per-line timestamp filtering —
    a long-running session's older lines can leak in if the file itself was
    touched in the last 24h; good enough for a midday activity pulse."""
    cutoff = datetime.now().timestamp() - 24 * 3600
    runs: dict[str, dict] = {}
    if not SESSIONS_DIR.exists():
        return runs

    cmd_re = re.compile(r"<command-name>/?([^<\s]+)</command-name>")

    def _bump(name: str, ts: str):
        r = runs.setdefault(name, {"count": 0, "last_ts": ""})
        r["count"] += 1
        if ts > r["last_ts"]:
            r["last_ts"] = ts

    for f in SESSIONS_DIR.glob("*.jsonl"):
        try:
            if f.stat().st_mtime < cutoff:
                continue
        except OSError:
            continue
        try:
            fh = f.open(errors="ignore")
        except OSError:
            continue
        with fh:
            for line in fh:
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = obj.get("timestamp", "")
                content = obj.get("message", {}).get("content")
                blocks = content if isinstance(content, list) else [content]
                for block in blocks:
                    if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") == "Skill":
                        skill = block.get("input", {}).get("skill")
                        if skill:
                            _bump(skill, ts)
                    elif isinstance(block, dict) and block.get("type") == "text":
                        for m in cmd_re.finditer(block.get("text") or ""):
                            _bump(m.group(1), ts)
                    elif isinstance(block, str):
                        for m in cmd_re.finditer(block):
                            _bump(m.group(1), ts)
    return runs


def skill_goal(name: str) -> str | None:
    """First description: line from a skill's SKILL.md frontmatter, first
    300 chars. Missing SKILL.md -> None, skip silently (built-ins)."""
    p = SKILLS_DIR / name / "SKILL.md"
    if not p.exists():
        return None
    try:
        head = "\n".join(p.read_text(errors="ignore").splitlines()[:40])
    except OSError:
        return None
    m = re.search(r"^description:\s*(.+)$", head, re.MULTILINE)
    if m:
        return m.group(1).strip()[:300]
    # ponytail: ~9 skills in this repo (code-review, deal-analysis, ...)
    # predate the frontmatter convention and use a plain "# Title" +
    # "**Trigger:**" header instead — fall back to that instead of dropping
    # them from judge context entirely.
    h1 = re.search(r"^#\s+(.+)$", head, re.MULTILINE)
    if not h1:
        return None
    goal = h1.group(1).strip()
    trig = re.search(r"^\*\*Trigger:\*\*\s*(.+)$", head, re.MULTILINE)
    if trig:
        goal += " — " + trig.group(1).strip()
    return goal[:300]


def collect(targets: list[dict]) -> list[dict]:
    out = []
    for t in targets:
        status = check_launchd_target(t["label"]) if t["kind"] == "launchd" and "label" in t else ""
        evidence = [(cmd, run_evidence(cmd)) for cmd in t.get("evidence", [])]
        out.append({**t, "status": status, "results": evidence})
    return out


def build_prompt(collected: list[dict], skills: dict[str, dict]) -> str:
    parts = []
    for t in collected:
        block = [f"TARGET: {t['name']} ({t['kind']})", f"GOAL: {t['goal']}"]
        if t["status"]:
            block.append(f"STATUS: {t['status']}")
        if t["results"]:
            block.append("EVIDENCE:")
            for cmd, output in t["results"]:
                block.append(f"  $ {cmd}\n{output}")
        parts.append("\n".join(block))

    skill_lines = ["SKILL RUNS (last 24h):"]
    if not skills:
        skill_lines.append("  (none)")
    else:
        for name, info in sorted(skills.items(), key=lambda kv: -kv[1]["count"]):
            goal = skill_goal(name)
            if goal is None:
                continue  # built-in / no SKILL.md — skip silently, per spec
            skill_lines.append(f"  - {name} ({info['count']}x, last {info['last_ts']}): {goal}")

    return "\n\n".join(parts) + "\n\n" + "\n".join(skill_lines)


def judge(prompt: str) -> tuple[list[tuple], list[str]] | None:
    try:
        r = subprocess.run(
            ["claude", "-p", prompt, "--system-prompt", SYSTEM_PROMPT, "--model", "claude-sonnet-5"],
            capture_output=True, text=True, timeout=300,
        )
    except Exception as e:
        print(f"  judge call failed: {e}", file=sys.stderr)
        return None
    out = (r.stdout or "").strip()
    if not out:
        print(f"  judge returned no output; stderr: {(r.stderr or '')[:300]}", file=sys.stderr)
        return None

    verdicts = []
    improvements = []
    in_improvements = False
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("VERDICT|"):
            fields = line.split("|", 4)
            if len(fields) == 5:
                _, name, verdict, why, fix = fields
                verdicts.append((name.strip(), verdict.strip(), why.strip(), fix.strip()))
        elif line.upper().startswith("IMPROVEMENTS"):
            in_improvements = True
        elif in_improvements and line.startswith("-"):
            improvements.append(line.lstrip("- ").strip())

    return (verdicts, improvements) if verdicts else None


def notify(offenders: list[tuple]):
    body = "; ".join(f"{name}: {why} — fix: {fix}" for name, _, why, fix in offenders)
    body = body[:600]
    try:
        subprocess.run(["/bin/sh", str(REPO / "scripts" / "notify.sh"), "Goal Watch", body], timeout=30)
    except Exception as e:
        print(f"  notify failed: {e}")


def write_report(collected: list[dict], verdicts: list[tuple], improvements: list[str]) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORT_DIR / f"{date.today():%Y-%m-%d}.md"
    lines = [f"# Goal Watch — {date.today():%Y-%m-%d}", ""]
    if verdicts:
        lines += ["| Target | Verdict | Why | Fix |", "|---|---|---|---|"]
        for name, verdict, why, fix in verdicts:
            lines.append(f"| {name} | {verdict} | {why} | {fix} |")
    else:
        lines.append("Judge unavailable — no verdicts parsed. Deterministic launchd status only:")
        for t in collected:
            if t["status"]:
                lines.append(f"- {t['name']}: {t['status']}")
    lines += ["", "## Improvements", ""]
    lines += [f"- {i}" for i in improvements] if improvements else ["- none"]
    # ponytail: evidence appendix shows lengths, not full text — full text
    # already went to the judge and is reproducible by re-running the command.
    lines += ["", "## Evidence (lengths, for audit trail)", ""]
    for t in collected:
        for cmd, output in t["results"]:
            lines.append(f"- [{t['name']}] `{cmd}` — {len(output)} chars")
    out.write_text("\n".join(lines) + "\n")
    return out


def print_summary(collected: list[dict], verdicts: list[tuple], improvements: list[str]):
    today = datetime.now()
    print(f"GOAL WATCH — {today:%a %b %d %H:%M}\n")
    if not verdicts:
        print("  judge unavailable — showing launchd status only\n")
        for t in collected:
            if t["status"]:
                print(f"  {t['name']:<22} {t['status']}")
        return

    on_goal = [v for v in verdicts if v[1] == "ON GOAL"]
    off_goal = [v for v in verdicts if v[1] == "OFF GOAL"]
    no_data = [v for v in verdicts if v[1] not in ("ON GOAL", "OFF GOAL")]

    for name, verdict, why, _ in on_goal:
        print(f"  ON GOAL   {name:<22} {why}")
    for name, verdict, why, _ in no_data:
        print(f"  NO DATA   {name:<22} {why}")
    if off_goal:
        print("\n  OFF GOAL:")
        for name, verdict, why, fix in off_goal:
            print(f"    {name}: {why} — fix: {fix}")

    print("\n  IMPROVEMENTS:")
    for i in (improvements or ["none"]):
        print(f"    - {i}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="print the judge prompt, skip claude + notify")
    ap.add_argument("--no-notify", action="store_true", help="judge + print, never push")
    ap.add_argument("--notify", action="store_true", help="push ntfy if anything is OFF GOAL")
    ap.add_argument("--target", help="only run this target by name")
    args = ap.parse_args()

    targets = load_registry(args.target)
    collected = collect(targets)
    skills = mine_skill_runs()
    prompt = build_prompt(collected, skills)

    if args.dry:
        print(prompt)
        return

    result = judge(prompt)
    verdicts, improvements = result if result else ([], [])

    print_summary(collected, verdicts, improvements)
    report_path = write_report(collected, verdicts, improvements)
    print(f"\n  report: {report_path}")

    if args.notify:
        offenders = [v for v in verdicts if v[1] == "OFF GOAL"]
        if offenders:
            notify(offenders)


if __name__ == "__main__":
    main()
