#!/usr/bin/env python3
"""
aios_recall.py — Unified hybrid retrieval over the AIOS knowledge base.

Searches all three corpuses (wiki, references, memory) using:
  1. SQLite FTS5 BM25 keyword matching
  2. sqlite-vec KNN semantic similarity (fastembed local embeddings)
  3. Reciprocal Rank Fusion to merge and dedupe the two ranked lists

Returns top-k cited chunks. No LLM call — pure retrieval. Callers decide
whether to synthesize. Intended to replace hand-rolled word-overlap search
in wiki_query.py and act as the shared recall primitive for skills.

Library usage:
    from scripts.aios_recall import recall
    hits = recall("Huntsville rent upside", k=8)
    for h in hits:
        print(h.citation, h.snippet)

CLI usage:
    python scripts/aios_recall.py "Huntsville rent upside"
    python scripts/aios_recall.py "cap rate compression" --layer reference
    python scripts/aios_recall.py "expense sourcing rule" --k 5 --json
"""

import argparse
import json
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import apsw

REPO_ROOT = Path(__file__).parent.parent
DB_PATH   = REPO_ROOT / "data" / "olive.db"

RRF_K   = 60    # RRF constant — larger = smoother, less weight to top ranks
TOP_K   = 8     # default results returned
SNIPPET = 300   # chars of content to include in snippet


@dataclass
class Hit:
    chunk_id: int
    path:     str
    layer:    str
    category: Optional[str]
    heading:  Optional[str]
    content:  str
    score:    float

    @property
    def citation(self) -> str:
        try:
            rel = Path(self.path).relative_to(REPO_ROOT)
        except ValueError:
            rel = Path(self.path)
        base = str(rel).replace("\\", "/")
        if self.heading:
            return f"[[{base}#{self.heading}]]"
        return f"[[{base}]]"

    @property
    def snippet(self) -> str:
        return self.content[:SNIPPET].rstrip() + ("…" if len(self.content) > SNIPPET else "")

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "citation": self.citation,
            "path":     self.path,
            "layer":    self.layer,
            "category": self.category,
            "heading":  self.heading,
            "snippet":  self.snippet,
            "score":    round(self.score, 4),
        }


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _open_conn() -> apsw.Connection:
    if not DB_PATH.exists():
        sys.exit(
            f"Index not found at {DB_PATH}.\n"
            "Run: python scripts/aios_index.py --rebuild"
        )
    import sqlite_vec
    conn = apsw.Connection(str(DB_PATH))
    conn.enableloadextension(True)
    conn.loadextension(sqlite_vec.loadable_path())
    conn.enableloadextension(False)
    return conn


# ---------------------------------------------------------------------------
# Embedding (lazy-loaded, same model as aios_index.py)
# ---------------------------------------------------------------------------

_embed_model = None


def _embed_query(text: str) -> list[float]:
    global _embed_model
    if _embed_model is None:
        from fastembed import TextEmbedding
        _embed_model = TextEmbedding("sentence-transformers/all-MiniLM-L6-v2")
    return list(next(_embed_model.embed([text])))


# ---------------------------------------------------------------------------
# Search methods
# ---------------------------------------------------------------------------

def _fts_search(
    conn: apsw.Connection,
    query: str,
    layer: Optional[str],
    category: Optional[str],
    k: int,
) -> list[tuple[int, float]]:
    """Return [(chunk_id, bm25_score), ...] ordered by relevance (descending)."""
    try:
        if layer or category:
            extra_clauses: list[str] = []
            params: list = [query]
            if layer:
                extra_clauses.append("c.layer = ?")
                params.append(layer)
            if category:
                extra_clauses.append("c.category = ?")
                params.append(category)
            and_extra = " AND ".join(extra_clauses)
            sql = f"""
                SELECT f.rowid, -bm25(chunks_fts) AS score
                FROM chunks_fts f
                JOIN chunks c ON c.id = f.rowid
                WHERE chunks_fts MATCH ?
                  AND {and_extra}
                ORDER BY score DESC
                LIMIT ?
            """
            params.append(k * 2)
            rows = conn.execute(sql, params).fetchall()
        else:
            rows = conn.execute(
                """SELECT rowid, -bm25(chunks_fts) AS score
                   FROM chunks_fts
                   WHERE chunks_fts MATCH ?
                   ORDER BY score DESC
                   LIMIT ?""",
                (query, k * 2),
            ).fetchall()
        return [(r[0], r[1]) for r in rows]
    except apsw.Error:
        return []


def _vec_search(
    conn: apsw.Connection,
    query: str,
    layer: Optional[str],
    category: Optional[str],
    k: int,
) -> list[tuple[int, float]]:
    """Return [(chunk_id, distance), ...] ordered by distance (lower = closer)."""
    try:
        vec  = _embed_query(query)
        blob = struct.pack(f"{len(vec)}f", *vec)

        if layer or category:
            extra_clauses: list[str] = []
            params: list = [blob, k * 2]
            if layer:
                extra_clauses.append("c.layer = ?")
                params.append(layer)
            if category:
                extra_clauses.append("c.category = ?")
                params.append(category)
            and_extra = " AND ".join(extra_clauses)
            sql = f"""
                SELECT v.chunk_id, v.distance
                FROM chunk_vec v
                JOIN chunks c ON c.id = v.chunk_id
                WHERE v.embedding MATCH ?
                  AND k = ?
                  AND {and_extra}
                ORDER BY v.distance
            """
            rows = conn.execute(sql, params).fetchall()
        else:
            rows = conn.execute(
                """SELECT chunk_id, distance
                   FROM chunk_vec
                   WHERE embedding MATCH ?
                     AND k = ?
                   ORDER BY distance""",
                (blob, k * 2),
            ).fetchall()
        return [(r[0], r[1]) for r in rows]
    except apsw.Error:
        return []


# ---------------------------------------------------------------------------
# RRF merge
# ---------------------------------------------------------------------------

def _rrf_merge(
    fts_hits: list[tuple[int, float]],
    vec_hits: list[tuple[int, float]],
    k: int,
) -> list[tuple[int, float]]:
    """Reciprocal Rank Fusion — returns [(chunk_id, score), ...] desc."""
    scores: dict[int, float] = {}
    for rank, (chunk_id, _) in enumerate(fts_hits):
        scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (RRF_K + rank + 1)
    for rank, (chunk_id, _) in enumerate(vec_hits):
        scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (RRF_K + rank + 1)
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return ranked[:k]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def recall(
    query: str,
    layer: Optional[str] = None,
    category: Optional[str] = None,
    k: int = TOP_K,
) -> list[Hit]:
    """
    Hybrid keyword + semantic search over all indexed AIOS knowledge.

    Args:
        query:    Natural language question or keyword phrase.
        layer:    Optional filter — "wiki", "reference", or "memory".
        category: Optional wiki category filter — "deals", "markets", etc.
        k:        Number of results to return.

    Returns:
        List of Hit objects, ordered by RRF score (best first).
    """
    conn = _open_conn()
    try:
        fts_hits = _fts_search(conn, query, layer, category, k)
        vec_hits = _vec_search(conn, query, layer, category, k)
        merged   = _rrf_merge(fts_hits, vec_hits, k)

        if not merged:
            return []

        ids    = [cid for cid, _ in merged]
        scores = {cid: score for cid, score in merged}

        placeholders = ",".join("?" * len(ids))
        rows = conn.execute(
            f"SELECT id,path,layer,category,heading,content FROM chunks WHERE id IN ({placeholders})",
            ids,
        ).fetchall()

        row_map = {r[0]: r for r in rows}
        hits: list[Hit] = []
        for cid, score in merged:
            if cid not in row_map:
                continue
            r = row_map[cid]
            hits.append(Hit(
                chunk_id=r[0],
                path=r[1],
                layer=r[2],
                category=r[3],
                heading=r[4],
                content=r[5],
                score=score,
            ))
        return hits
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Hybrid recall over the AIOS knowledge base")
    parser.add_argument("query",   nargs="+",  help="Search query")
    parser.add_argument("--layer", choices=["wiki", "reference", "memory"],
                        help="Limit to one knowledge layer")
    parser.add_argument("--cat",   metavar="CATEGORY",
                        help="Limit to one wiki category (deals, markets, brokers, etc.)")
    parser.add_argument("--k",     type=int, default=TOP_K,
                        help=f"Results to return (default {TOP_K})")
    parser.add_argument("--json",  action="store_true", help="Output as JSON array")
    args = parser.parse_args()

    question = " ".join(args.query)
    hits = recall(question, layer=args.layer, category=args.cat, k=args.k)

    if not hits:
        msg = "No results. Run `python scripts/aios_index.py` to build the index."
        if args.json:
            print(json.dumps({"query": question, "results": []}))
        else:
            print(msg)
        return

    if args.json:
        print(json.dumps({"query": question, "results": [h.to_dict() for h in hits]}, indent=2))
        return

    sep = "─" * 60
    print(f"\nRecall: {len(hits)} hits for '{question}'\n{sep}")
    for i, h in enumerate(hits, 1):
        layer_tag = f"[{h.layer}]" + (f" [{h.category}]" if h.category else "")
        print(f"\n{i}. {h.citation}  {layer_tag}  score={h.score:.4f}")
        print(f"   {h.snippet}")
    print()


if __name__ == "__main__":
    main()
