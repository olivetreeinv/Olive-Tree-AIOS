#!/usr/bin/env python3
"""
server.py — Jarvis brain. Serves the 3D knowledge galaxy viewer and answers
questions (voice or text) grounded in Brian's AIOS notes.

Endpoints:
  GET  /            -> jarvis/viewer/index.html (+ static assets)
  GET  /boot         -> {"greeting": "..."} spoken opener, ops status + new drops
  POST /chat         -> {"question": "...", "history": [{"question","answer"}, ...]}
                         returns {"answer": "...", "nodes": [ids], "action": "..."}

Intent router (checked before any LLM call):
  1. "remember (that)? ..."      -> capture a new note, live-append to the galaxy
  2. status / running / systems  -> scripts/heartbeat.py, summarized
  3. new deals / downloads       -> scripts/deal_intake.py, summarized
  4. everything else             -> aios_recall + claude -p (butler persona)

stdlib http.server only, port 4700. No pip installs, no API keys.
"""

import json
import re
import subprocess
import sys
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).parent.parent
VIEWER = Path(__file__).parent / "viewer"
CAPTURES = REPO / "wiki" / "captures"
PORT = 4700

sys.path.insert(0, str(REPO))
import jarvis.build as build  # noqa: E402
from scripts.aios_recall import recall  # noqa: E402

SYSTEM_PROMPT = (
    "You are Jarvis, a dry British butler AI serving Brian Norton, founder of "
    "Olive Tree Investments (multifamily real estate). You answer ONLY using "
    "the note excerpts provided in the user message -- never invent facts. "
    "Answer in 2-3 sentences, razor wit, occasional 'sir'. If the notes don't "
    "cover it, say so plainly instead of guessing. You are aware his mission "
    "this quarter is one 15-50 door multifamily deal under contract and $400K "
    "in LP commitments."
)

REMEMBER_RE = re.compile(r"^\s*remember\s+(?:that\s+)?(.+)$", re.IGNORECASE | re.DOTALL)
STATUS_RE = re.compile(
    r"\b(status|everything up|all systems|systems? (up|green|running)|is (everything|\w+) running)\b",
    re.IGNORECASE,
)
DEALS_RE = re.compile(r"\b(new deals?|downloads?|deal intake)\b", re.IGNORECASE)

# Short in-memory history of prior exchanges (per-process, single user -> no sessions needed)
_HISTORY: list[dict] = []
_GRAPH: dict = {}


def _env(name: str) -> str | None:
    """Return env var, falling back to a line in the project .env."""
    import os
    if os.environ.get(name):
        return os.environ[name]
    env = REPO / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line.startswith(f"{name}=") and not line.startswith("#"):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def _model_name() -> str:
    try:
        settings = json.loads((Path.home() / ".claude" / "settings.json").read_text())
        v = settings["model"]
        v = re.sub(r"\[.*\]$", "", v)
        if v.startswith("claude-"):
            v = v[len("claude-"):]
        return v.replace("-", " ").upper()
    except Exception:
        return "SONNET 5"


def _load_graph() -> dict:
    global _GRAPH
    n = build.rebuild_if_stale()
    text = (VIEWER / "graph-data.js").read_text()
    _GRAPH = json.loads(text[len("window.GRAPH = "):-2])
    return _GRAPH


def _run(cmd: list[str], timeout: int = 30) -> str:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return out.stdout.strip() or out.stderr.strip()
    except Exception as e:
        return f"(failed to run {cmd[1]}: {e})"


def _summarize_heartbeat(raw: str) -> str:
    lines = [l.strip() for l in raw.splitlines() if l.strip()]
    summary_line = next((l for l in lines if l.upper().startswith("SUMMARY:")), None)
    reds = [l for l in lines if l.upper().startswith("[RED]") or " RED " in l.upper()]
    parts = []
    if summary_line:
        parts.append(summary_line.split(":", 1)[1].strip())
    if reds and not summary_line:
        parts.append("; ".join(reds[:2]))
    if not parts:
        parts.append(lines[-1] if lines else "no report produced")
    return "Ops check, sir: " + " ".join(parts) + "."


def _summarize_deal_intake(raw: str) -> str:
    if "No new deal-doc folders" in raw:
        return "Nothing new in Downloads, sir. Quiet on the deal front."
    lines = [l.strip() for l in raw.splitlines() if l.strip()]
    header = next((l for l in lines if l.startswith("DEAL INTAKE")), lines[0] if lines else "")
    names = [l.lstrip("- ").split("(")[0].strip() for l in lines if l and not l.startswith(("DEAL INTAKE", "  ", "→", "After"))]
    if names:
        return f"{header}. Top of the pile: {', '.join(names[:3])}."
    return header or "Deal intake produced no readable output."


def _claude_answer(question: str, history: list[dict]) -> tuple[str, list[int]]:
    hits = recall(question, k=6)
    if not hits:
        return ("I've nothing on that in your notes, sir. Perhaps ask me something else, or teach me with 'remember that...'.", [])

    context = "\n\n".join(f"{h.citation}\n{h.snippet}" for h in hits)
    convo = ""
    for turn in history[-2:]:
        convo += f"Earlier -- Q: {turn.get('question','')}\nA: {turn.get('answer','')}\n\n"

    prompt = f"{convo}NOTES:\n{context}\n\nQUESTION: {question}"
    result = subprocess.run(
        ["claude", "-p", prompt, "--system-prompt", SYSTEM_PROMPT],
        capture_output=True, text=True, timeout=60,
    )
    answer = (result.stdout or result.stderr or "").strip() or "I seem to be at a loss for words, sir."

    # Map cited note paths back to graph node ids.
    citation_paths = {h.path for h in hits}
    node_ids = [n["id"] for n in _GRAPH.get("nodes", []) if n["path"] in citation_paths]
    return answer, node_ids


def _remember(text: str) -> tuple[str, list[int]]:
    CAPTURES.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    note_path = CAPTURES / f"{ts}.md"
    note_path.write_text(f"# Capture {ts}\n\n{text.strip()}\n")

    graph = build.build()
    (VIEWER / "graph-data.js").write_text("window.GRAPH = " + json.dumps(graph, indent=1) + ";\n")
    global _GRAPH
    _GRAPH = graph

    new_id = next((n["id"] for n in graph["nodes"] if n["path"] == str(note_path)), None)
    node_ids = [new_id] if new_id is not None else []
    return ("Noted, sir. Filed away for posterity.", node_ids)


def _handle_chat(question: str, history: list[dict]) -> dict:
    m = REMEMBER_RE.match(question)
    if m:
        answer, node_ids = _remember(m.group(1))
        return {"answer": answer, "nodes": node_ids, "action": "remember"}

    if STATUS_RE.search(question):
        raw = _run(["python3", str(REPO / "scripts" / "heartbeat.py")], timeout=60)
        return {"answer": _summarize_heartbeat(raw), "nodes": [], "action": "status"}

    if DEALS_RE.search(question):
        raw = _run(["python3", str(REPO / "scripts" / "deal_intake.py")], timeout=30)
        return {"answer": _summarize_deal_intake(raw), "nodes": [], "action": "deals"}

    answer, node_ids = _claude_answer(question, history)
    return {"answer": answer, "nodes": node_ids, "action": "recall"}


def _boot_greeting() -> str:
    raw = _run(["python3", str(REPO / "scripts" / "heartbeat.py")], timeout=60)
    lines = [l.strip() for l in raw.splitlines() if l.strip()]
    summary_line = next((l for l in lines if l.upper().startswith("SUMMARY:")), None)
    status = summary_line.split(":", 1)[1].strip() if summary_line else "all systems nominal"

    try:
        from scripts.deal_intake import find_candidates, _seen
        cands = find_candidates()
        seen = _seen()
        new = [c for c in cands if c["path"] not in seen]
    except Exception:
        new = []

    opener = f"Morning, sir. {status}."
    if new:
        opener += f" And {len(new)} new deal drop(s) waiting in Downloads."
    return opener


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # ponytail: quiet server, heartbeat/deal_intake logs are enough

    def _send_json(self, payload: dict, status: int = 200):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_static(self):
        rel = self.path.lstrip("/") or "index.html"
        rel = rel.split("?")[0]
        fpath = (VIEWER / rel).resolve()
        if VIEWER.resolve() not in fpath.parents and fpath != VIEWER.resolve():
            self.send_error(403)
            return
        if not fpath.exists() or fpath.is_dir():
            fpath = VIEWER / "index.html"
        ctype = "text/html"
        if fpath.suffix == ".js":
            ctype = "application/javascript"
        elif fpath.suffix == ".css":
            ctype = "text/css"
        elif fpath.suffix in (".jpg", ".jpeg"):
            ctype = "image/jpeg"
        elif fpath.suffix == ".png":
            ctype = "image/png"
        elif fpath.suffix == ".mp4":
            ctype = "video/mp4"

        size = fpath.stat().st_size
        rng = self.headers.get("Range") if fpath.suffix == ".mp4" else None
        if rng:
            m = re.match(r"bytes=(\d*)-(\d*)", rng)
            if m:
                start = int(m.group(1) or 0)
                end = min(int(m.group(2) or size - 1), size - 1)
                if start > end:
                    self.send_error(416)
                    return
                with fpath.open("rb") as f:
                    f.seek(start)
                    chunk = f.read(end - start + 1)
                self.send_response(206)
                self.send_header("Content-Type", ctype)
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                self.send_header("Content-Length", str(len(chunk)))
                self.end_headers()
                self.wfile.write(chunk)
                return

        data = fpath.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        if fpath.suffix == ".mp4":
            self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.startswith("/boot"):
            self._send_json({"greeting": _boot_greeting()})
            return
        if self.path.startswith("/meta"):
            self._send_json({
                "model": _model_name(),
                "tts": bool(_env("ELEVENLABS_API_KEY")),
                "nodes": len(_GRAPH.get("nodes", [])),
                "links": len(_GRAPH.get("links", [])),
            })
            return
        self._serve_static()

    def _handle_tts(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            body = {}
        text = (body.get("text") or "").strip()
        if not text:
            self._send_json({"error": "no text"}, 400)
            return

        key = _env("ELEVENLABS_API_KEY")
        if not key:
            self._send_json({"error": "no key"}, 503)
            return

        voice = _env("ELEVENLABS_VOICE_ID") or "onwK4e9ZLuTAKqWW03F9"
        req = urllib.request.Request(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format=mp3_44100_128",
            data=json.dumps({"text": text, "model_id": "eleven_multilingual_v2"}).encode(),
            headers={"xi-api-key": key, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                audio = resp.read()
        except Exception as e:
            upstream = ""
            if hasattr(e, "read"):
                try:
                    upstream = e.read().decode(errors="replace")
                except Exception:
                    upstream = ""
            self._send_json({"error": f"tts upstream failed: {e}", "upstream": upstream}, 502)
            return

        self.send_response(200)
        self.send_header("Content-Type", "audio/mpeg")
        self.send_header("Content-Length", str(len(audio)))
        self.end_headers()
        self.wfile.write(audio)

    def do_POST(self):
        if self.path.startswith("/tts"):
            self._handle_tts()
            return
        if not self.path.startswith("/chat"):
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            body = {}
        question = (body.get("question") or "").strip()
        history = body.get("history") or []
        if not question:
            self._send_json({"answer": "I didn't quite catch that, sir.", "nodes": [], "action": "none"})
            return

        result = _handle_chat(question, history)
        _HISTORY.append({"question": question, "answer": result["answer"]})
        del _HISTORY[:-3]
        self._send_json(result)


def main():
    _load_graph()
    print(f"Jarvis serving http://localhost:{PORT}  ({len(_GRAPH.get('nodes', []))} notes indexed)")
    server = ThreadingHTTPServer(("localhost", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
