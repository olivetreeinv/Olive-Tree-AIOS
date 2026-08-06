#!/usr/bin/env python3
"""
aios_index.py — Build and refresh the unified AIOS hybrid retrieval index.

Indexes all three knowledge corpuses into data/olive.db:
  wiki/          → layer "wiki"
  references/ context/ decisions/ → layer "reference"
  ~/.claude/.../memory/ → layer "memory"

Each markdown file is split on ## / ### headings into chunks.
Chunks are stored in:
  chunks      — plain table (content + metadata)
  chunks_fts  — SQLite FTS5 virtual table (keyword / BM25)
  chunk_vec   — sqlite-vec vec0 virtual table (semantic / KNN)

Uses apsw instead of stdlib sqlite3 because macOS Python disables
extension loading in the stdlib build.

Usage:
  python scripts/aios_index.py             # incremental (skip unchanged files)
  python scripts/aios_index.py --rebuild   # drop + rebuild everything
  python scripts/aios_index.py --dry-run   # print what would change, no writes
"""

import argparse
import hashlib
import json
import re
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path

import apsw
import yaml

REPO_ROOT = Path(__file__).parent.parent
MEMORY_ROOT = (
    Path.home()
    / ".claude"
    / "projects"
    / "-Users-olivetree-Documents-Olive-AIOS"
    / "memory"
)

SOURCES: list[tuple[Path, str]] = [
    (REPO_ROOT / "wiki",        "wiki"),
    (REPO_ROOT / "references",  "reference"),
    (REPO_ROOT / "context",     "reference"),
    (REPO_ROOT / "decisions",   "reference"),
    (MEMORY_ROOT,               "memory"),
]

SKIP_DIRS  = {".obsidian", "__pycache__", "raw", "_transcripts"}
SKIP_FILES = {"MEMORY.md"}
EMBED_DIM  = 384   # all-MiniLM-L6-v2

DB_PATH = REPO_ROOT / "data" / "olive.db"


# ---------------------------------------------------------------------------
# Markdown helpers
# ---------------------------------------------------------------------------

def _parse_frontmatter(text: str) -> tuple[dict, str]:
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            try:
                fm = yaml.safe_load(text[3:end]) or {}
            except yaml.YAMLError:
                fm = {}
            return fm, text[end + 4:].lstrip()
    return {}, text


def _chunk_markdown(path: Path, layer: str) -> list[dict]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    fm, body = _parse_frontmatter(text)
    # YAML may parse date fields as datetime.date objects — coerce to str for JSON
    fm_json  = json.dumps(fm, default=str) if fm else None

    category = None
    try:
        rel   = path.relative_to(REPO_ROOT / "wiki")
        parts = rel.parts
        if len(parts) > 1:
            category = parts[0]
    except ValueError:
        pass

    heading_re = re.compile(r"^(#{2,3})\s+(.+)$", re.MULTILINE)
    splits     = list(heading_re.finditer(body))

    def _make_chunk(heading: str | None, content: str) -> dict | None:
        content = content.strip()
        if len(content) < 30:
            return None
        h = hashlib.sha256(content.encode()).hexdigest()
        return {
            "path":         str(path),
            "layer":        layer,
            "category":     category,
            "heading":      heading,
            "frontmatter":  fm_json,
            "content":      content,
            "content_hash": h,
            "last_indexed": datetime.now(timezone.utc).isoformat(),
        }

    chunks: list[dict] = []
    if not splits:
        c = _make_chunk(None, body)
        if c:
            chunks.append(c)
        return chunks

    preamble = body[: splits[0].start()]
    c = _make_chunk(None, preamble)
    if c:
        chunks.append(c)

    for i, m in enumerate(splits):
        heading_text = m.group(2).strip()
        start = m.end()
        end   = splits[i + 1].start() if i + 1 < len(splits) else len(body)
        c = _make_chunk(heading_text, body[start:end])
        if c:
            chunks.append(c)

    return chunks


def _collect_files(root: Path, layer: str) -> list[tuple[Path, str]]:
    files: list[tuple[Path, str]] = []
    if not root.exists():
        return files
    for p in sorted(root.rglob("*.md")):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if p.name.startswith("_"):
            continue
        if p.name in SKIP_FILES:
            continue
        files.append((p, layer))
    return files


# ---------------------------------------------------------------------------
# DB setup
# ---------------------------------------------------------------------------

def _open_conn() -> apsw.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = apsw.Connection(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    _load_vec(conn)
    return conn


def _load_vec(conn: apsw.Connection) -> None:
    import sqlite_vec
    conn.enableloadextension(True)
    conn.loadextension(sqlite_vec.loadable_path())
    conn.enableloadextension(False)


def _ensure_tables(conn: apsw.Connection) -> None:
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                path         TEXT NOT NULL,
                layer        TEXT NOT NULL,
                category     TEXT,
                heading      TEXT,
                frontmatter  TEXT,
                content      TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                last_indexed TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_path  ON chunks(path)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_layer ON chunks(layer)")
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts
            USING fts5(
                content,
                heading   UNINDEXED,
                path      UNINDEXED,
                layer     UNINDEXED,
                category  UNINDEXED,
                content=chunks,
                content_rowid=id,
                tokenize='porter unicode61'
            )
        """)
        conn.execute(f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS chunk_vec
            USING vec0(
                chunk_id INTEGER PRIMARY KEY,
                embedding FLOAT[{EMBED_DIM}]
            )
        """)


def _drop_index_tables(conn: apsw.Connection) -> None:
    with conn:
        conn.execute("DROP TABLE IF EXISTS chunk_vec")
        conn.execute("DROP TABLE IF EXISTS chunks_fts")
        conn.execute("DROP TABLE IF EXISTS chunks")


# ---------------------------------------------------------------------------
# Embedding model (lazy)
# ---------------------------------------------------------------------------

_embed_model = None


def _get_embed_model():
    global _embed_model
    if _embed_model is None:
        from fastembed import TextEmbedding
        # persistent cache: the default /var/folders temp cache gets purged by macOS
        _embed_model = TextEmbedding(
            "sentence-transformers/all-MiniLM-L6-v2",
            cache_dir=str(Path.home() / ".cache" / "fastembed"),
        )
    return _embed_model


def _embed_texts(texts: list[str]) -> list[list[float]]:
    return [v.tolist() for v in _get_embed_model().embed(texts)]


# ---------------------------------------------------------------------------
# Index operations
# ---------------------------------------------------------------------------

def _existing_hashes(conn: apsw.Connection) -> dict[str, set[str]]:
    rows = conn.execute("SELECT path, content_hash FROM chunks").fetchall()
    result: dict[str, set[str]] = {}
    for path, h in rows:
        result.setdefault(path, set()).add(h)
    return result


def _delete_path(conn: apsw.Connection, path: str) -> None:
    ids = [r[0] for r in conn.execute(
        "SELECT id FROM chunks WHERE path=?", (path,)
    ).fetchall()]
    if not ids:
        return
    placeholders = ",".join("?" * len(ids))
    conn.execute(f"DELETE FROM chunks_fts WHERE rowid IN ({placeholders})", ids)
    conn.execute(f"DELETE FROM chunk_vec WHERE chunk_id IN ({placeholders})", ids)
    conn.execute("DELETE FROM chunks WHERE path=?", (path,))


def _insert_chunks(conn: apsw.Connection, chunks: list[dict]) -> None:
    if not chunks:
        return

    conn.executemany(
        """INSERT INTO chunks
           (path,layer,category,heading,frontmatter,content,content_hash,last_indexed)
           VALUES (:path,:layer,:category,:heading,:frontmatter,:content,:content_hash,:last_indexed)""",
        chunks,
    )

    ids: list[int] = []
    for c in chunks:
        row = conn.execute(
            "SELECT id FROM chunks WHERE path=? AND content_hash=?",
            (c["path"], c["content_hash"]),
        ).fetchone()
        if row:
            ids.append(row[0])

    for chunk_id, c in zip(ids, chunks):
        conn.execute(
            "INSERT INTO chunks_fts(rowid,content,heading,path,layer,category) VALUES(?,?,?,?,?,?)",
            (chunk_id, c["content"], c["heading"] or "", c["path"], c["layer"], c["category"] or ""),
        )

    vectors = _embed_texts([c["content"] for c in chunks])
    for chunk_id, vec in zip(ids, vectors):
        blob = struct.pack(f"{len(vec)}f", *vec)
        conn.execute(
            "INSERT INTO chunk_vec(chunk_id, embedding) VALUES(?,?)",
            (chunk_id, blob),
        )


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------

def run(rebuild: bool = False, dry_run: bool = False) -> None:
    conn = _open_conn()

    if rebuild:
        print("Rebuilding index from scratch…")
        _drop_index_tables(conn)

    _ensure_tables(conn)

    existing  = _existing_hashes(conn)
    all_files: list[tuple[Path, str]] = []
    for root, layer in SOURCES:
        all_files.extend(_collect_files(root, layer))

    seen_paths: set[str] = set()
    added = changed = skipped = 0

    for path, layer in all_files:
        path_str = str(path)
        seen_paths.add(path_str)
        chunks = _chunk_markdown(path, layer)
        if not chunks:
            continue

        new_hashes = {c["content_hash"] for c in chunks}
        old_hashes = existing.get(path_str, set())

        if new_hashes == old_hashes:
            skipped += 1
            continue

        if dry_run:
            action = "ADD" if path_str not in existing else "UPDATE"
            print(f"  [{action}] {path_str} ({len(chunks)} chunks)")
            added += path_str not in existing
            changed += path_str in existing
            continue

        with conn:
            _delete_path(conn, path_str)
            _insert_chunks(conn, chunks)

        if path_str not in existing:
            added += 1
        else:
            changed += 1

    deleted = 0
    for path_str in list(existing.keys()):
        if path_str not in seen_paths:
            if not dry_run:
                with conn:
                    _delete_path(conn, path_str)
            deleted += 1
            print(f"  [REMOVE] {path_str}")

    total = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] if not dry_run else "?"
    print(
        f"\nIndex {'(dry-run) ' if dry_run else ''}complete: "
        f"+{added} added, ~{changed} updated, {skipped} unchanged, -{deleted} removed "
        f"| total chunks: {total}"
    )
    conn.close()


def refresh() -> None:
    """Convenience hook for ingest scripts: incremental re-index."""
    run(rebuild=False, dry_run=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build/refresh the AIOS unified retrieval index")
    parser.add_argument("--rebuild",  action="store_true", help="Drop and rebuild from scratch")
    parser.add_argument("--dry-run",  action="store_true", help="Show what would change without writing")
    args = parser.parse_args()
    run(rebuild=args.rebuild, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
