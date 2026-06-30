import json
import os
import re
import sqlite3
from datetime import datetime
from io import BytesIO
from typing import Optional

import anthropic
import httpx
from pypdf import PdfReader

CACHE_DB = "cache.db"

# Module-level client — instantiated once, reused across all requests
_anthropic: Optional[anthropic.AsyncAnthropic] = None

def _get_anthropic() -> Optional[anthropic.AsyncAnthropic]:
    global _anthropic
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return None
    if _anthropic is None:
        _anthropic = anthropic.AsyncAnthropic(api_key=api_key)
    return _anthropic


# ── Regex fallback patterns ────────────────────────────────────────────────────

_POSITIVE = [
    r"FAR\s*52\.244-2", r"FAR\s*52\.219-9", r"subcontracting\s+plan",
    r"may\s+subcontract", r"subcontractor[s]?\s+shall", r"consent\s+to\s+subcontract",
]
_NEGATIVE = [
    r"no\s+subcontracting", r"shall\s+not\s+subcontract",
    r"prime\s+contractor\s+shall\s+perform", r"self[-\s]performance\s+required",
]
_FAR_RE = re.compile(r"FAR\s+\d{2}\.\d{3}-\d+", re.IGNORECASE)

_EMPTY_RESULT = {
    "subcontractors_allowed": "unclear",
    "evidence": [],
    "far_clauses_found": [],
    "small_business_subk_plan_required": False,
    "scope_summary": None,
    "go_no_go": "NEEDS-REVIEW",
    "go_no_go_reason": "",
    "submission_checklist": [],
    "key_requirements": [],
    "contract_type": "unknown",
    "analyzed_by": "none",
}


# ── SQLite helpers ─────────────────────────────────────────────────────────────

def _get_cached_content(url: str) -> Optional[bytes]:
    with sqlite3.connect(CACHE_DB) as conn:
        row = conn.execute("SELECT content FROM doc_cache WHERE url = ?", (url,)).fetchone()
    return row[0] if row else None


def _get_cached_analysis(url: str) -> Optional[dict]:
    with sqlite3.connect(CACHE_DB) as conn:
        row = conn.execute(
            "SELECT analyzed_json FROM doc_cache WHERE url = ? AND analyzed_json IS NOT NULL",
            (url,),
        ).fetchone()
    return json.loads(row[0]) if row else None


def _cache_content(url: str, content: bytes):
    with sqlite3.connect(CACHE_DB) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO doc_cache (url, content, cached_at) VALUES (?, ?, ?)",
            (url, content, datetime.utcnow().isoformat()),
        )


def _cache_analysis(url: str, analysis: dict):
    with sqlite3.connect(CACHE_DB) as conn:
        conn.execute(
            "UPDATE doc_cache SET analyzed_json = ? WHERE url = ?",
            (json.dumps(analysis), url),
        )


# ── PDF handling ───────────────────────────────────────────────────────────────

async def _download(url: str) -> bytes:
    cached = _get_cached_content(url)
    if cached:
        return cached
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        resp = await client.get(url, headers={"User-Agent": "OliveTreeGovCon/1.0"})
        resp.raise_for_status()
    _cache_content(url, resp.content)
    return resp.content


def _extract_text(content: bytes) -> str:
    try:
        reader = PdfReader(BytesIO(content))
        return "\n".join(
            t for page in reader.pages[:50] if (t := page.extract_text())
        )
    except Exception:
        return ""


def _smart_truncate(text: str, total: int = 10_000) -> str:
    """Keep the first 8K chars (requirements) and last 2K (closing conditions)."""
    if len(text) <= total:
        return text
    head, tail = 8_000, 2_000
    return text[:head] + "\n...[truncated]...\n" + text[-tail:]


# ── Regex fallback ─────────────────────────────────────────────────────────────

def _snippet(text: str, match: re.Match) -> str:
    start = max(0, match.start() - 60)
    end   = min(len(text), match.end() + 160)
    raw   = text[start:end].strip().replace("\n", " ")
    return raw[:200] + ("…" if len(raw) > 200 else "")


def _regex_analyze(text: str) -> dict:
    evidence: list[str] = []
    seen_far: set[str]  = set()
    far_clauses: list[str] = []

    for m in _FAR_RE.finditer(text):
        clause = m.group(0).strip()
        if clause not in seen_far:
            seen_far.add(clause)
            far_clauses.append(clause)

    positive_hits, negative_hits = [], []
    for pattern in _POSITIVE:
        if m := re.search(pattern, text, re.IGNORECASE):
            positive_hits.append(m.group(0))
            if len(evidence) < 3:
                evidence.append(_snippet(text, m))
    for pattern in _NEGATIVE:
        if m := re.search(pattern, text, re.IGNORECASE):
            negative_hits.append(m.group(0))
            if len(evidence) < 3:
                evidence.append(_snippet(text, m))

    status = "yes" if positive_hits else ("no" if negative_hits else "unclear")
    sbk_plan = bool(re.search(r"FAR\s*52\.219-9|subcontracting\s+plan", text, re.IGNORECASE))

    return {
        **_EMPTY_RESULT,
        "subcontractors_allowed": status,
        "evidence": evidence,
        "far_clauses_found": far_clauses[:10],
        "small_business_subk_plan_required": sbk_plan,
        "go_no_go": "NEEDS-REVIEW",
        "go_no_go_reason": "Analyzed via regex fallback — set ANTHROPIC_API_KEY for full AI analysis.",
        "analyzed_by": "regex",
    }


# ── Claude analysis ────────────────────────────────────────────────────────────

async def _claude_analyze(text: str) -> Optional[dict]:
    client = _get_anthropic()
    if not client:
        return None

    prompt = f"""Analyze this federal government solicitation and return ONLY valid JSON.

{_smart_truncate(text)}

Return this exact JSON structure:
{{
  "subcontractors_allowed": "yes"|"no"|"unclear",
  "evidence": ["up to 3 short quotes from the doc"],
  "far_clauses_found": ["FAR XX.XXX-X"],
  "small_business_subk_plan_required": true|false,
  "scope_summary": "2-3 sentence plain English summary of the work",
  "go_no_go": "GO"|"NO-GO"|"NEEDS-REVIEW",
  "go_no_go_reason": "one sentence",
  "submission_checklist": ["item 1", "item 2"],
  "key_requirements": ["requirement 1"],
  "contract_type": "RFQ"|"RFP"|"IFB"|"unknown"
}}

GO = services contract, subcontracting allowed/unclear, no clearance required.
NO-GO = self-performance required, security clearance needed, or products/manufacturing.
Return only the JSON object."""

    try:
        msg = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
        result = json.loads(raw)
        result["analyzed_by"] = "claude"
        return result
    except Exception:
        return None


# ── Public interface ───────────────────────────────────────────────────────────

async def analyze_opportunity(opportunity: dict) -> dict:
    resource_links = [u for u in (opportunity.get("resourceLinks") or []) if isinstance(u, str)]

    if not resource_links:
        return {**_EMPTY_RESULT, "evidence": ["No documents attached to this opportunity."]}

    pdf_links = ([u for u in resource_links if ".pdf" in u.lower()] or resource_links)[:3]

    if cached := _get_cached_analysis(pdf_links[0]):
        return cached

    combined = ""
    for url in pdf_links:
        try:
            combined += _extract_text(await _download(url)) + "\n"
        except Exception:
            continue

    if not combined.strip():
        return {**_EMPTY_RESULT, "evidence": ["Could not extract text from attached documents."]}

    result = await _claude_analyze(combined) or _regex_analyze(combined)
    _cache_analysis(pdf_links[0], result)
    return result
