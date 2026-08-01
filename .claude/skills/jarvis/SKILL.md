---
name: jarvis
description: Voice-driven 3D knowledge galaxy over the AIOS corpus (wiki, references, context, decisions, memory) — ask questions out loud, get spoken answers with a fly-to-source camera dive to the exact note. Trigger on "/jarvis", "start jarvis", "open the galaxy", "talk to my notes".
---

## What this skill does

A local web app (`jarvis/` in the repo root, port 4700) that renders every AIOS
markdown note as a star in a 3D force graph. Brian asks a question by voice or
text; an intent router checks for "remember...", "status/running", or "new
deals/downloads" first — otherwise it retrieves the best chunks via
`scripts/aios_recall.py` and answers through `claude -p` (free on the Claude
Code subscription — no API key), speaks the answer aloud, and flies the camera
to the source note(s).

Adapted from Zubair Trabzada's "Build Your Own JARVIS" prompt pack
(6 prompts: galaxy → brain → voice → fly-to-source → personality → remember).

## How to run

```bash
python3 jarvis/build.py     # rescan notes → viewer/graph-data.js (also runs automatically on server start if stale)
python3 jarvis/server.py    # serve on http://localhost:4700 — open in Chrome (mic/voice need it)
```

If `jarvis/` doesn't exist yet, rebuild it per the spec below, then start the
server and give Brian the URL + 3 example questions from his actual notes.

## Build spec

**Corpus** — scan `.md` files in: `wiki/`, `references/`, `context/`,
`decisions/`, and `~/.claude/projects/-Users-olivetree-Documents-Olive-AIOS/memory/`.

1. **Galaxy** — `jarvis/build.py` (stdlib only): each note → node with label
   (filename), group (top-level folder → color), ~700-char excerpt, numeric id
   (index in the nodes array), and full path. Links notes that mention each
   other's title/filename or share a `[[wikilink]]` target. Writes
   `jarvis/viewer/graph-data.js` as `const GRAPH = {nodes, links}`.
   `is_stale()` / `rebuild_if_stale()` skip the rescan unless a source `.md` is
   newer than `graph-data.js` — printed either way is the indexed note count.
   Viewer: single `viewer/index.html` using 3d-force-graph from CDN — black
   starfield, glowing group-colored nodes, slow idle camera drift; click a node
   = fly to it, flash it white briefly, open a side panel with its excerpt.
2. **Brain** — `jarvis/server.py` (stdlib `http.server`, `ThreadingHTTPServer`,
   port 4700, serves only `viewer/` as static files). Imports `build.py`
   directly at startup (no subprocess) so the galaxy is never stale.
   - `POST /chat` — body `{"question", "history"}` (history = last 3
     question/answer pairs, kept server-side too, since it's single-user
     local). Intent router, in order:
     1. `remember (that)? ...` → writes `wiki/captures/YYYY-MM-DD-HHMMSS.md`,
        rebuilds the graph in-process, returns the new node id + a short
        confirmation line. `action: "remember"`.
     2. status / running / systems → shells out to `scripts/heartbeat.py`,
        pulls the `SUMMARY:` line, no LLM call. `action: "status"`.
     3. new deals / downloads / deal intake → shells out to
        `scripts/deal_intake.py`, truncates to the top 3 candidates, no LLM
        call. `action: "deals"`.
     4. otherwise → `recall(question, k=6)` from `scripts/aios_recall.py`,
        prepends the last 2 history turns for follow-up context, calls
        `claude -p "<notes+question>" --system-prompt "<butler persona>"`,
        maps cited note paths back to graph node ids. `action: "recall"`.
   - `GET /boot` — runs `heartbeat.py` + `deal_intake.find_candidates()`
     directly (no LLM call) and composes a 1–2 sentence spoken opener.
   - Responses are plain synchronous JSON, not streamed — `claude -p` answers
     are capped at 2–3 sentences so the round trip is already short; streaming
     would have meant chunked/SSE plumbing in a stdlib handler for no real
     latency win at this response size.
3. **Voice** — speechSynthesis (prefers an en-GB voice if present) + a
   push-to-talk button (hold to talk) via webkitSpeechRecognition, NOT
   continuous/wake-word listening (unreliable in Chrome, out of scope);
   "● listening…" / "● thinking…" status line.
4. **Fly-to-source** — on answer, fly to the top cited node (or flash the
   whole cluster white if 4+ sources), open its panel. Spoken answer stays
   short — the note is on screen.
5. **Personality** — dry British butler, razor wit, "sir" occasionally. Knows
   the mission: one 15–50 door deal under contract, $400K in LP commitments.
   Boot greeting speaks the real ops summary + new-drop count, not a canned line.
6. **Remember** — "remember that…" is handled inside `POST /chat` (not a
   separate endpoint) since the router already has to inspect every question;
   a second endpoint would just be another place for the client to get it
   wrong. Writes the note, calls `build.build()` directly to regenerate
   `graph-data.js` (no separate `aios_index.py` reindex step — `aios_recall`'s
   DB index and the galaxy's `graph-data.js` are independent stores; run
   `python3 scripts/aios_index.py` separately if the capture should also
   surface through `/aios_recall` elsewhere).

## Rules

- No API keys, no pip installs, no npm — stdlib + CDN + `claude -p` only.
- Port 4700 (8000 = govcon, 8765 = Canva OAuth — don't touch).
- Chrome only for mic/voice; that's a browser limitation, not a bug.
- Troubleshooting: mic dead → Chrome lock icon → allow Microphone; no sound →
  click the page once first; stale page → Cmd+Shift+R; generic answers →
  re-run `build.py` and check the corpus paths.
