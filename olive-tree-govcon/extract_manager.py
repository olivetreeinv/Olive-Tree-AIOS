"""
extract_manager.py — Download and parse SAM.gov bulk-data extracts.

Supports:
  Entity Management  SAM_PUBLIC_MONTHLY_V2_{YYYYMMDD}.ZIP  (pipe-delimited, monthly)
  Exclusions         SAM_Exclusions_Public_Extract_{YYYYMMDD}.ZIP  (comma-delimited, daily)

Column aliases are used so the importer keeps working if SAM.gov changes header names.
"""

import csv
import io
import sqlite3
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterator, Optional

import httpx

from entity_db import init_db, log_extract

# ── Constants ──────────────────────────────────────────────────────────────────

EXTRACT_BASE   = "https://api.sam.gov/data-services/v1/extracts"
DOWNLOADS_DIR  = Path("sam_downloads")
ENTITY_TMPL    = "SAM_PUBLIC_MONTHLY_V2_{date}.ZIP"
EXCL_TMPL      = "SAM_Exclusions_Public_Extract_{date}.ZIP"
BATCH_SIZE     = 5_000

# ── Column aliases (tolerates SAM.gov header renames) ─────────────────────────

_ENTITY_COLS: dict[str, list[str]] = {
    "uei":         ["UEI_SAM", "UEI", "UNIQUE_ENTITY_ID"],
    "cage_code":   ["CAGE_CODE", "CAGE"],
    "legal_name":  ["LEGAL_BUSINESS_NAME", "LEGAL_NAME", "ENTITY_NAME"],
    "dba_name":    ["DBA_NAME", "DBA"],
    "addr_line1":  ["PHYSICAL_ADDRESS_LINE_1", "ADDRESS_LINE_1"],
    "city":        ["PHYSICAL_ADDRESS_CITY", "CITY"],
    "state":       ["PHYSICAL_ADDRESS_PROVINCE_OR_STATE", "STATE"],
    "zip":         ["PHYSICAL_ADDRESS_ZIP_POSTAL_CODE", "ZIP", "ZIP_POSTAL_CODE"],
    "country":     ["PHYSICAL_ADDRESS_COUNTRY_CODE", "COUNTRY", "COUNTRY_CODE"],
    "reg_status":  ["REGISTRATION_STATUS", "REG_STATUS", "ENTITY_STATUS"],
    "expiry_date": ["EXPIRATION_DATE", "REGISTRATION_EXPIRATION_DATE"],
    "entity_type": ["ENTITY_TYPE", "ENTITY_STRUCTURE"],
}

_EXCL_COLS: dict[str, list[str]] = {
    "exclusion_name":    ["EXCLUSION_NAME", "NAME"],
    "uei":               ["UEI_SAM", "UEI", "UNIQUE_ENTITY_ID"],
    "cage_code":         ["CAGE_CODE", "CAGE"],
    "exclusion_type":    ["EXCLUSION_TYPE"],
    "exclusion_program": ["EXCLUSION_PROGRAM"],
    "excluding_agency":  ["EXCLUDING_AGENCY_NAME", "EXCLUDING_AGENCY"],
    "exclusion_date":    ["EXCLUSION_DATE"],
    "termination_date":  ["TERMINATION_DATE"],
    "ct_code":           ["CT_CODE", "CLASSIFICATION"],
}

# ── Column-mapping helpers ─────────────────────────────────────────────────────

def _col_idx(headers: list[str], aliases: list[str]) -> int:
    upper = [h.upper().strip() for h in headers]
    for a in aliases:
        try:
            return upper.index(a.upper())
        except ValueError:
            continue
    return -1


def _make_mapper(headers: list[str], spec: dict[str, list[str]]) -> dict[str, int]:
    return {field: _col_idx(headers, alts) for field, alts in spec.items()}


def _map_row(row: list[str], mapper: dict[str, int], extra: dict) -> dict:
    out: dict = {}
    for field, idx in mapper.items():
        out[field] = (row[idx].strip() or None) if (0 <= idx < len(row)) else None
    out.update(extra)
    return out


# ── Date discovery ─────────────────────────────────────────────────────────────

def _recent_dates(days_back: int = 45) -> list[str]:
    today = datetime.now(timezone.utc)
    return [(today - timedelta(days=d)).strftime("%Y%m%d") for d in range(days_back)]


async def find_latest_filename(
    api_key: str,
    template: str,
    days_back: int = 45,
    log: Callable[[str], None] = print,
) -> Optional[str]:
    """
    Probe SAM.gov with HEAD requests for recent dates and return the first
    filename that exists. Falls back to GET if HEAD is not supported.
    """
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        for date_str in _recent_dates(days_back):
            fname  = template.format(date=date_str)
            params = {"api_key": api_key, "fileName": fname}
            try:
                resp = await client.head(EXTRACT_BASE, params=params)
                if resp.status_code == 200:
                    return fname
                # 302 redirect to the file = it exists
                if resp.status_code in (301, 302, 303, 307, 308):
                    return fname
            except httpx.HTTPError:
                pass
    return None


# ── Download ───────────────────────────────────────────────────────────────────

async def download_extract(
    api_key: str,
    filename: str,
    log: Callable[[str], None] = print,
) -> Path:
    """
    Stream-download a SAM.gov extract ZIP into sam_downloads/.
    Skips if the file already exists locally (re-run safe).
    """
    DOWNLOADS_DIR.mkdir(exist_ok=True)
    dest = DOWNLOADS_DIR / filename

    if dest.exists():
        log(f"  ↩  Already downloaded: {dest.name}  (delete to re-fetch)")
        return dest

    log(f"  ↓  Downloading {filename} …")
    params = {"api_key": api_key, "fileName": filename}

    async with httpx.AsyncClient(timeout=None, follow_redirects=True) as client:
        async with client.stream("GET", EXTRACT_BASE, params=params) as resp:
            resp.raise_for_status()
            total    = int(resp.headers.get("content-length", 0))
            received = 0
            with open(dest, "wb") as fout:
                async for chunk in resp.aiter_bytes(65_536):
                    fout.write(chunk)
                    received += len(chunk)
                    if total:
                        pct = received * 100 // total
                        print(f"\r  ↓  {pct:3d}%  {received:>12,} / {total:,} bytes", end="", flush=True)
    print()
    log(f"  ✓  Saved → {dest}")
    return dest


# ── CSV iterators ──────────────────────────────────────────────────────────────

def _iter_entity_rows(zip_path: Path) -> Iterator[dict]:
    now = datetime.now(timezone.utc).isoformat()
    with zipfile.ZipFile(zip_path) as zf:
        targets = [n for n in zf.namelist() if n.lower().endswith((".dat", ".csv"))]
        if not targets:
            raise RuntimeError(f"No .dat or .csv files found inside {zip_path.name}")
        for name in targets:
            with zf.open(name) as raw:
                text   = io.TextIOWrapper(raw, encoding="utf-8", errors="replace")
                reader = csv.reader(text, delimiter="|")
                headers = next(reader, None)
                if headers is None:
                    continue
                mapper = _make_mapper(headers, _ENTITY_COLS)
                for row in reader:
                    if row:
                        yield _map_row(row, mapper, {"imported_at": now})


def _iter_exclusion_rows(zip_path: Path) -> Iterator[dict]:
    now = datetime.now(timezone.utc).isoformat()
    with zipfile.ZipFile(zip_path) as zf:
        targets = [n for n in zf.namelist() if n.lower().endswith((".dat", ".csv"))]
        if not targets:
            raise RuntimeError(f"No .dat or .csv files found inside {zip_path.name}")
        for name in targets:
            with zf.open(name) as raw:
                text   = io.TextIOWrapper(raw, encoding="utf-8", errors="replace")
                reader = csv.reader(text, delimiter=",")
                headers = next(reader, None)
                if headers is None:
                    continue
                mapper = _make_mapper(headers, _EXCL_COLS)
                for row in reader:
                    if row:
                        yield _map_row(row, mapper, {"imported_at": now})


# ── Batch insert helpers (bypass entity_db for streaming performance) ──────────

_ENTITY_INSERT = """
    INSERT OR REPLACE INTO entities
        (uei,cage_code,legal_name,dba_name,addr_line1,city,state,
         zip,country,reg_status,expiry_date,entity_type,imported_at)
    VALUES
        (:uei,:cage_code,:legal_name,:dba_name,:addr_line1,:city,:state,
         :zip,:country,:reg_status,:expiry_date,:entity_type,:imported_at)
"""

_EXCL_INSERT = """
    INSERT INTO exclusions
        (exclusion_name,uei,cage_code,exclusion_type,exclusion_program,
         excluding_agency,exclusion_date,termination_date,ct_code,imported_at)
    VALUES
        (:exclusion_name,:uei,:cage_code,:exclusion_type,:exclusion_program,
         :excluding_agency,:exclusion_date,:termination_date,:ct_code,:imported_at)
"""


def _stream_insert(
    db_path: str,
    rows: Iterator[dict],
    delete_sql: str,
    insert_sql: str,
    log: Callable[[str], None],
) -> int:
    """
    Single-transaction delete-then-insert with periodic progress logging.
    Uses one large transaction for maximum SQLite throughput.
    """
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA cache_size  = -65536")   # 64 MB page cache
    conn.execute("BEGIN")
    conn.execute(delete_sql)

    batch: list[dict] = []
    total = 0

    for row in rows:
        batch.append(row)
        if len(batch) >= BATCH_SIZE:
            conn.executemany(insert_sql, batch)
            total += len(batch)
            batch.clear()
            if total % 100_000 == 0:
                log(f"  … {total:,} rows imported")

    if batch:
        conn.executemany(insert_sql, batch)
        total += len(batch)

    conn.execute("COMMIT")
    conn.close()
    return total


# ── High-level refresh API ─────────────────────────────────────────────────────

async def refresh_entities(
    api_key: str,
    db_path: str,
    date_str: Optional[str] = None,
    log: Callable[[str], None] = print,
) -> int:
    """Download + import the monthly Entity Management extract. Returns row count."""
    if date_str:
        filename = ENTITY_TMPL.format(date=date_str)
    else:
        log("  🔍 Finding latest Entity Management extract …")
        filename = await find_latest_filename(api_key, ENTITY_TMPL, days_back=45, log=log)
        if not filename:
            raise RuntimeError(
                "No recent Entity Management extract found on SAM.gov.\n"
                "Try: python refresh.py entities --date YYYYMMDD"
            )

    log(f"  📦 {filename}")
    zip_path = await download_extract(api_key, filename, log)

    init_db(db_path)
    log("  📥 Parsing & importing …")

    total = _stream_insert(
        db_path,
        _iter_entity_rows(zip_path),
        delete_sql="DELETE FROM entities",
        insert_sql=_ENTITY_INSERT,
        log=log,
    )

    log_extract(db_path, "entities", filename, total)
    log(f"  ✅ {total:,} entity records imported.")
    return total


async def refresh_exclusions(
    api_key: str,
    db_path: str,
    date_str: Optional[str] = None,
    log: Callable[[str], None] = print,
) -> int:
    """Download + import the daily Exclusions extract. Returns row count."""
    if date_str:
        filename = EXCL_TMPL.format(date=date_str)
    else:
        log("  🔍 Finding latest Exclusions extract …")
        filename = await find_latest_filename(api_key, EXCL_TMPL, days_back=7, log=log)
        if not filename:
            raise RuntimeError(
                "No recent Exclusions extract found on SAM.gov.\n"
                "Try: python refresh.py exclusions --date YYYYMMDD"
            )

    log(f"  📦 {filename}")
    zip_path = await download_extract(api_key, filename, log)

    init_db(db_path)
    log("  📥 Parsing & importing …")

    total = _stream_insert(
        db_path,
        _iter_exclusion_rows(zip_path),
        delete_sql="DELETE FROM exclusions",
        insert_sql=_EXCL_INSERT,
        log=log,
    )

    log_extract(db_path, "exclusions", filename, total)
    log(f"  ✅ {total:,} exclusion records imported.")
    return total
