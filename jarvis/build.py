#!/usr/bin/env python3
"""
build.py — scan the AIOS markdown corpus into a 3D graph for the Jarvis viewer.

Corpus: wiki/, references/, context/, decisions/, and the Claude Code memory
directory. Each note becomes a node (id, label, group, excerpt, path). Notes
that mention each other's title or share a [[wikilink]] get linked.

Output: jarvis/viewer/graph-data.js — `window.GRAPH = {nodes, links}`.

Incremental: only rescans if any source .md is newer than graph-data.js (or
it doesn't exist yet). Import `ensure_fresh()` from server.py to reuse this
check without shelling out.

Usage: python3 jarvis/build.py
"""

import json
import os
import re
from pathlib import Path

REPO = Path(__file__).parent.parent
OUT = Path(__file__).parent / "viewer" / "graph-data.js"

CORPUS_DIRS = [
    REPO / "wiki",
    REPO / "references",
    REPO / "context",
    REPO / "decisions",
    Path(os.path.expanduser(
        "~/.claude/projects/-Users-olivetree-Documents-Olive-AIOS/memory"
    )),
]

EXCERPT_LEN = 700
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)")


def _find_notes() -> list[Path]:
    notes = []
    for d in CORPUS_DIRS:
        if d.exists():
            notes.extend(sorted(d.rglob("*.md")))
    return notes


def is_stale() -> bool:
    """True if any source note is newer than graph-data.js, or it's missing."""
    if not OUT.exists():
        return True
    out_mtime = OUT.stat().st_mtime
    for note in _find_notes():
        try:
            if note.stat().st_mtime > out_mtime:
                return True
        except OSError:
            continue
    return False


def _group_for(path: Path) -> str:
    try:
        rel = path.relative_to(REPO)
        return rel.parts[0]
    except ValueError:
        # memory dir, outside repo
        return "memory"


def _title_for(path: Path, text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#"):
            return line.lstrip("#").strip()
    return path.stem


def build() -> dict:
    notes = _find_notes()
    parsed = []
    for path in notes:
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        title = _title_for(path, text)
        excerpt = text.strip()[:EXCERPT_LEN]
        parsed.append({
            "path": str(path),
            "label": path.stem,
            "title": title,
            "group": _group_for(path),
            "excerpt": excerpt,
            "text": text,
        })

    nodes = []
    for i, p in enumerate(parsed):
        nodes.append({
            "id": i,
            "label": p["label"],
            "group": p["group"],
            "excerpt": p["excerpt"],
            "path": p["path"],
        })

    # Link notes that mention each other's title, or share a [[wikilink]] target.
    links = []
    seen_pairs = set()
    wikilinks = [set(m.lower() for m in WIKILINK_RE.findall(p["text"])) for p in parsed]

    for i, p in enumerate(parsed):
        title_lc = p["title"].lower()
        label_lc = p["label"].lower()
        for j, q in enumerate(parsed):
            if i == j:
                continue
            pair = (min(i, j), max(i, j))
            if pair in seen_pairs:
                continue
            hit = False
            # q mentions p's title/filename
            qtext_lc = q["text"].lower()
            if title_lc and len(title_lc) > 3 and title_lc in qtext_lc:
                hit = True
            elif label_lc and len(label_lc) > 3 and label_lc in qtext_lc:
                hit = True
            # shared wikilink target
            elif wikilinks[i] & wikilinks[j]:
                hit = True
            if hit:
                links.append({"source": i, "target": j})
                seen_pairs.add(pair)

    return {"nodes": nodes, "links": links}


def rebuild_if_stale() -> int:
    """Rebuild graph-data.js if stale. Returns node count either way."""
    if is_stale():
        graph = build()
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text("window.GRAPH = " + json.dumps(graph, indent=1) + ";\n")
        return len(graph["nodes"])
    else:
        text = OUT.read_text()
        return text.count('"id":')


if __name__ == "__main__":
    n = rebuild_if_stale()
    print(f"Indexed {n} notes -> {OUT}")
