import asyncio
import hashlib
import json
import sqlite3
from datetime import datetime, timedelta
from typing import Optional

import httpx

SAM_BASE_URL = "https://api.sam.gov/prod/opportunities/v2/search"
CACHE_DB     = "cache.db"
CACHE_TTL    = timedelta(hours=6)


class SAMClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(CACHE_DB) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS search_cache (
                    key           TEXT PRIMARY KEY,
                    response_json TEXT,
                    cached_at     TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS doc_cache (
                    url           TEXT PRIMARY KEY,
                    content       BLOB,
                    analyzed_json TEXT,
                    cached_at     TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS opportunity_store (
                    notice_id  TEXT PRIMARY KEY,
                    data_json  TEXT,
                    stored_at  TIMESTAMP
                );
            """)

    # ── Cache helpers ──────────────────────────────────────────────────────────

    def _cache_key(self, params: dict) -> str:
        return hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()

    def _get_cached_search(self, key: str, ignore_ttl: bool = False) -> Optional[dict]:
        with sqlite3.connect(CACHE_DB) as conn:
            row = conn.execute(
                "SELECT response_json, cached_at FROM search_cache WHERE key = ?", (key,)
            ).fetchone()
        if not row:
            return None
        if not ignore_ttl and datetime.utcnow() - datetime.fromisoformat(row[1]) >= CACHE_TTL:
            return None
        return json.loads(row[0])

    def get_all_cached_opportunities(self, states: list) -> list[dict]:
        """Return all stored opportunities for given states — used as quota fallback."""
        with sqlite3.connect(CACHE_DB) as conn:
            rows = conn.execute(
                "SELECT data_json FROM opportunity_store ORDER BY stored_at DESC LIMIT 500"
            ).fetchall()
        opps = [json.loads(r[0]) for r in rows]
        if not states or states == [None]:
            return opps
        state_set = {s.upper() for s in states if s}
        return [
            o for o in opps
            if (
                isinstance(o.get("placeOfPerformance"), dict) and
                (o["placeOfPerformance"].get("state", {}) or {}).get("code", "").upper() in state_set
            ) or not o.get("placeOfPerformance")
        ]

    def _set_cached_search(self, key: str, data: dict):
        with sqlite3.connect(CACHE_DB) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO search_cache VALUES (?, ?, ?)",
                (key, json.dumps(data), datetime.utcnow().isoformat()),
            )

    # ── Opportunity store ──────────────────────────────────────────────────────

    def store_opportunity(self, opp: dict):
        notice_id = opp.get("noticeId") or opp.get("opportunityId")
        if not notice_id:
            return
        with sqlite3.connect(CACHE_DB) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO opportunity_store VALUES (?, ?, ?)",
                (notice_id, json.dumps(opp), datetime.utcnow().isoformat()),
            )

    def get_opportunity(self, notice_id: str) -> Optional[dict]:
        with sqlite3.connect(CACHE_DB) as conn:
            row = conn.execute(
                "SELECT data_json FROM opportunity_store WHERE notice_id = ?", (notice_id,)
            ).fetchone()
        return json.loads(row[0]) if row else None

    # ── Fetching ───────────────────────────────────────────────────────────────

    async def _fetch_page(self, params: dict) -> dict:
        _skip = {"api_key", "limit", "offset"}
        cache_params = {k: v for k, v in params.items() if k not in _skip and v is not None}
        key = self._cache_key(cache_params)

        if cached := self._get_cached_search(key):
            return cached

        clean = {k: v for k, v in params.items() if v is not None}
        async with httpx.AsyncClient(timeout=30.0) as client:
            for attempt in range(3):
                resp = await client.get(SAM_BASE_URL, params=clean)
                if resp.status_code == 429:
                    # Quota hit — try serving stale cache before giving up
                    stale = self._get_cached_search(key, ignore_ttl=True)
                    if stale:
                        return stale
                    if attempt < 2:
                        await asyncio.sleep(2 ** attempt)
                        continue
                resp.raise_for_status()
                break
            data = resp.json()

        self._set_cached_search(key, data)
        return data

    async def search_opportunities(
        self,
        state: Optional[str] = "GA",
        posted_from: Optional[str] = None,
        posted_to: Optional[str] = None,
    ) -> list[dict]:
        seen_ids: set[str] = set()
        all_results: list[dict] = []

        for ptype in ("k", "o"):
            params = {
                "api_key":     self.api_key,
                "limit":       100,
                "offset":      0,
                "ptype":       ptype,
                "postedFrom":  posted_from,
                "postedTo":    posted_to,
                "state":       state or None,
            }
            data = await self._fetch_page(params)
            for opp in data.get("opportunitiesData") or []:
                nid = opp.get("noticeId") or opp.get("opportunityId")
                if nid and nid not in seen_ids:
                    seen_ids.add(nid)
                    all_results.append(opp)

        for opp in all_results:
            self.store_opportunity(opp)

        return all_results
