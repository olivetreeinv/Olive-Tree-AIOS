import json
import sqlite3
from datetime import datetime, timedelta
from typing import Optional

import httpx

CACHE_DB  = "cache.db"
USA_BASE  = "https://api.usaspending.gov/api/v2"
CACHE_TTL = timedelta(hours=24)


def _init_db():
    with sqlite3.connect(CACHE_DB) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS usaspending_cache (
                key           TEXT PRIMARY KEY,
                response_json TEXT,
                cached_at     TIMESTAMP
            )
        """)


_init_db()


def _cache_key(naics: str, state: Optional[str]) -> str:
    return f"usa:{naics}:{state or 'ALL'}"


def _get_cached(key: str) -> Optional[list]:
    with sqlite3.connect(CACHE_DB) as conn:
        row = conn.execute(
            "SELECT response_json, cached_at FROM usaspending_cache WHERE key = ?", (key,)
        ).fetchone()
    if not row:
        return None
    if datetime.utcnow() - datetime.fromisoformat(row[1]) > CACHE_TTL:
        return None
    return json.loads(row[0])


def _set_cached(key: str, data: list):
    with sqlite3.connect(CACHE_DB) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO usaspending_cache VALUES (?, ?, ?)",
            (key, json.dumps(data), datetime.utcnow().isoformat()),
        )


async def fetch_past_awards(naics: str, state: Optional[str] = None, limit: int = 10) -> list[dict]:
    key = _cache_key(naics, state)
    if (cached := _get_cached(key)) is not None:
        return cached

    filters: dict = {"award_type_codes": ["A", "B", "C", "D"], "naics_codes": [naics]}
    if state:
        filters["place_of_performance_locations"] = [{"country": "USA", "state": state}]

    payload = {
        "filters": filters,
        "fields": [
            "Award ID", "Recipient Name", "Start Date", "End Date",
            "Award Amount", "Description", "Awarding Agency",
            "Place of Performance State Code", "Contract Award Type", "NAICS Code",
        ],
        "page": 1, "limit": limit,
        "sort": "Award Amount", "order": "desc",
        "subawards": False,
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                f"{USA_BASE}/search/spending_by_award/",
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            results = resp.json().get("results") or []
    except Exception as exc:
        return [{"error": str(exc)}]

    awards = [
        {
            "award_id":      r.get("Award ID", ""),
            "recipient":     r.get("Recipient Name", "Unknown"),
            "amount":        r.get("Award Amount") or 0,
            "start_date":    r.get("Start Date", ""),
            "end_date":      r.get("End Date", ""),
            "description":   r.get("Description", ""),
            "agency":        r.get("Awarding Agency", ""),
            "state":         r.get("Place of Performance State Code", ""),
            "contract_type": r.get("Contract Award Type", ""),
        }
        for r in results
    ]

    _set_cached(key, awards)
    return awards


def pricing_summary(awards: list[dict]) -> dict:
    amounts = sorted(
        a["amount"] for a in awards
        if isinstance(a.get("amount"), (int, float)) and a["amount"] > 0
    )
    if not amounts:
        return {"ceiling": None, "floor": None, "median": None, "recommendation": "No past pricing data found."}

    n       = len(amounts)
    ceiling = amounts[-1]
    floor   = amounts[0]
    median  = amounts[n // 2] if n % 2 else (amounts[n // 2 - 1] + amounts[n // 2]) / 2
    rec_low, rec_high = ceiling * 0.75, ceiling * 0.85

    return {
        "ceiling":        ceiling,
        "floor":          floor,
        "median":         median,
        "rec_low":        rec_low,
        "rec_high":       rec_high,
        "sample_size":    n,
        "recommendation": (
            f"Past ceiling: ${ceiling:,.0f}. "
            f"Bid between ${rec_low:,.0f}–${rec_high:,.0f} to be competitive while maintaining margin."
        ),
    }
