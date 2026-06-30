import asyncio
import os
from datetime import datetime, timedelta
from typing import Optional as Opt

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from bid_tracker import STATUSES, create_bid, list_bids, pipeline_summary, update_bid
from doc_analyzer import analyze_opportunity
from entity_db import SAM_DB, db_stats, search_entities
from proposal_builder import generate_proposal
from sam_client import SAMClient
from usaspending_client import fetch_past_awards, pricing_summary

load_dotenv()

# Region → state code mappings (must mirror the frontend REGIONS array)
REGIONS: dict[str, list[str]] = {
    "NORTHEAST":    ["CT", "ME", "MA", "NH", "NJ", "NY", "PA", "RI", "VT"],
    "SOUTHEAST":    ["AL", "AR", "DC", "DE", "FL", "GA",
                     "KY", "LA", "MD", "MS", "NC", "SC", "TN", "VA", "WV"],
    "MIDWEST":      ["IL", "IN", "IA", "KS", "MI", "MN",
                     "MO", "NE", "ND", "OH", "SD", "WI"],
    "SOUTHWEST":    ["AZ", "NM", "OK", "TX"],
    "MOUNTAIN_WEST":["CO", "ID", "MT", "NV", "UT", "WY"],
    "PACIFIC":      ["AK", "CA", "HI", "OR", "WA"],
}

NAICS_LABELS: dict[str, str] = {
    "236118": "Residential Remodelers",
    "236220": "Commercial Building Construction",
    "238110": "Poured Concrete",
    "238130": "Framing",
    "238140": "Masonry",
    "238160": "Roofing",
    "238170": "Siding",
    "238190": "Exterior Trades (Other)",
    "238210": "Electrical",
    "238220": "Plumbing & HVAC",
    "238290": "Other Building Equipment",
    "238310": "Drywall & Insulation",
    "238320": "Painting & Wall Covering",
    "238330": "Flooring",
    "238340": "Tile & Terrazzo",
    "238350": "Finish Carpentry",
    "238390": "Other Finishing Trades",
    "238990": "Specialty Trades (Other)",
    "561730": "Landscaping",
    "561710": "Pest Control",
    "238910": "Site Prep & Excavation",
    "561720": "Janitorial & Cleaning",
    "561740": "Carpet & Upholstery Cleaning",
    "561790": "Other Building Services",
    # Real estate / property background
    "531311": "Residential Property Management",
    "531312": "Nonresidential Property Management",
    "561210": "Facilities Support Services",
    "541350": "Building Inspection Services",
    # High-win / Natalie model
    "484210": "Household & Office Moving",
    "812990": "All Other Personal Services",
    "562112": "Hazardous Waste Collection",
    "562910": "Remediation Services",
}


def _enrich(opp: dict) -> dict:
    code = str(opp.get("naicsCode") or "")
    return {**opp, "naics_label": NAICS_LABELS.get(code, code)}


app = FastAPI(title="Olive Tree GovCon", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

_sam = SAMClient(os.getenv("SAM_API_KEY", ""))


async def _prewarm():
    """
    On startup, quietly populate the cache for the most common queries so
    dropdown changes are instant for the user.  Failures are silently swallowed
    (quota may already be exhausted; this is best-effort).
    """
    today = datetime.utcnow()
    posted_to   = today.strftime("%m/%d/%Y")
    posted_from = (today - timedelta(days=30)).strftime("%m/%d/%Y")

    # Warm states in priority order: all SE states first (primary market),
    # then the lead state from every other region so region-level queries
    # always return at least some cached data.
    # Each state = 2 API calls (ptype k + o); already-cached = free.
    warm_states = [
        # Southeast (full)
        "GA", "FL", "AL", "SC", "TN", "NC", "MS", "LA",
        "VA", "KY", "AR", "WV", "MD", "DE", "DC",
        # One lead state per other region
        "NY",   # Northeast
        "TX",   # Southwest
        "IL",   # Midwest
        "CO",   # Mountain West
        "CA",   # Pacific
    ]
    for state in warm_states:
        try:
            await _sam.search_opportunities(
                state=state,
                posted_from=posted_from,
                posted_to=posted_to,
            )
        except Exception:
            break   # quota hit — stop, don't waste retries


@app.on_event("startup")
async def startup_event():
    asyncio.create_task(_prewarm())


@app.get("/", include_in_schema=False)
async def root():
    return FileResponse("static/index.html")


@app.get("/api/opportunities")
async def get_opportunities(
    state: str = Query("SOUTHEAST"),  # "SOUTHEAST" | 2-letter code | "" (national)
    naics: str = Query(None),
    days_back: int = Query(30, ge=1, le=365),
    analyze: bool = Query(False),
    limit: int = Query(25, ge=1, le=100),
):
    today = datetime.utcnow()
    posted_from = (today - timedelta(days=days_back)).strftime("%m/%d/%Y")
    posted_to = today.strftime("%m/%d/%Y")

    # Resolve state(s) to search
    if state in REGIONS:
        states_to_search = REGIONS[state]
    elif state == "":
        states_to_search = [None]   # national — no state filter
    else:
        states_to_search = [state]

    # Fan out to each state in parallel; every individual call is cached by
    # (state, dates, ptype) so NAICS / region changes never burn extra API calls.
    tasks = [
        _sam.search_opportunities(
            state=s,
            posted_from=posted_from,
            posted_to=posted_to,
        )
        for s in states_to_search
    ]
    raw_results = await asyncio.gather(*tasks, return_exceptions=True)

    # Merge results, deduplicate by noticeId, track partial quota failures
    seen_ids: set = set()
    opportunities: list = []
    quota_hit = False

    for res in raw_results:
        if isinstance(res, Exception):
            err_str = str(res)
            if "429" in err_str or "quota" in err_str.lower() or "throttled" in err_str.lower():
                quota_hit = True
            continue
        for opp in res:
            nid = opp.get("noticeId") or opp.get("opportunityId")
            if nid and nid not in seen_ids:
                seen_ids.add(nid)
                opportunities.append(opp)

    # Quota hit with no fresh results — fall back to opportunity_store
    cached_fallback = False
    if not opportunities and quota_hit:
        opportunities = _sam.get_all_cached_opportunities(states_to_search)
        if opportunities:
            cached_fallback = True
        else:
            raise HTTPException(
                status_code=429,
                detail="SAM.gov daily API quota exhausted and no cached data available. Results refresh after midnight UTC.",
            )

    # Apply NAICS filter
    if naics:
        opportunities = [o for o in opportunities if str(o.get("naicsCode") or "") == naics]

    opportunities = opportunities[:limit]

    if analyze and opportunities:
        tasks = [analyze_opportunity(o) for o in opportunities]
        analyses = await asyncio.gather(*tasks, return_exceptions=True)
        enriched = []
        for opp, analysis in zip(opportunities, analyses):
            if isinstance(analysis, Exception):
                analysis = {
                    "subcontractors_allowed": "unclear",
                    "evidence": [str(analysis)],
                    "far_clauses_found": [],
                    "small_business_subk_plan_required": False,
                }
            enriched.append({**_enrich(opp), "analysis": analysis})
        return JSONResponse({"opportunities": enriched, "total": len(enriched), "cached": cached_fallback})

    plain = [_enrich(o) for o in opportunities]
    return JSONResponse({"opportunities": plain, "total": len(plain), "cached": cached_fallback})


@app.get("/api/opportunity/{notice_id}/analyze")
async def analyze_single(notice_id: str):
    opp = _sam.get_opportunity(notice_id)
    if not opp:
        raise HTTPException(
            status_code=404,
            detail="Opportunity not found in cache. Run a search first.",
        )
    try:
        result = await analyze_opportunity(opp)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return JSONResponse(result)


# ── Entity / Exclusion endpoints ───────────────────────────────────────────────

@app.get("/api/entities/stats")
async def entity_stats():
    """Database readiness + row counts — safe to call before first import."""
    return JSONResponse(db_stats(SAM_DB))


@app.get("/api/entities/search")
async def entity_search(
    q: str = Query(..., min_length=2, description="UEI, CAGE code, or partial legal name"),
    limit: int = Query(25, ge=1, le=100),
):
    """
    Search registered entities by UEI (exact), CAGE (exact), or name (LIKE).
    Each result includes an 'exclusions' list and an 'excluded' boolean flag.
    Returns 503 if the entity database has not been populated yet.
    """
    stats = db_stats(SAM_DB)
    if not stats["ready"]:
        raise HTTPException(
            status_code=503,
            detail=(
                "Entity database is empty. "
                "Run 'python refresh.py all' to download the SAM.gov extracts."
            ),
        )
    results = search_entities(SAM_DB, q, limit)
    return JSONResponse({"results": results, "total": len(results), "query": q})


# ── USASpending past pricing ───────────────────────────────────────────────────

@app.get("/api/pricing/{naics}")
async def get_past_pricing(
    naics: str,
    state: str = Query(None, description="2-letter state code, optional"),
    limit: int = Query(10, ge=1, le=25),
):
    """Fetch past federal contract awards for a NAICS code from USASpending.gov."""
    awards = await fetch_past_awards(naics, state or None, limit)
    summary = pricing_summary(awards)
    return JSONResponse({"awards": awards, "summary": summary, "naics": naics, "state": state})


# ── Proposal generation ────────────────────────────────────────────────────────

class ProposalRequest(BaseModel):
    sub_quote: float
    our_bid: float
    past_price_ceiling: Opt[float] = None
    sub_name: Opt[str] = None


@app.post("/api/opportunity/{notice_id}/proposal")
async def build_proposal(notice_id: str, req: ProposalRequest):
    """Generate a full proposal package using Claude."""
    opp = _sam.get_opportunity(notice_id)
    if not opp:
        raise HTTPException(
            status_code=404,
            detail="Opportunity not found in cache. Run a search first.",
        )
    try:
        result = await generate_proposal(
            opportunity=opp,
            sub_quote=req.sub_quote,
            our_bid=req.our_bid,
            past_price_ceiling=req.past_price_ceiling,
            sub_name=req.sub_name,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    # Auto-save to bid tracker
    title  = opp.get("title", "")
    agency = (opp.get("fullParentPathName") or "").split(">")[0].strip()
    naics  = opp.get("naicsCode", "")
    state  = ""
    if isinstance(opp.get("placeOfPerformance"), dict):
        state = opp["placeOfPerformance"].get("state", {}).get("code", "") or ""
    deadline = opp.get("responseDeadLine", "")
    link     = opp.get("uiLink", "")

    create_bid(notice_id, title, agency, naics, state, deadline, link)
    update_bid(
        notice_id,
        status="quoted",
        sub_name=req.sub_name,
        sub_quote=req.sub_quote,
        our_bid=req.our_bid,
        past_price_ceiling=req.past_price_ceiling,
        proposal_text=result.get("proposal_text", ""),
    )

    return JSONResponse(result)


# ── Bid tracker ────────────────────────────────────────────────────────────────

class BidCreate(BaseModel):
    notice_id: str
    title: str
    agency: str
    naics_code: str
    state: Opt[str] = None
    deadline: Opt[str] = None
    sam_link: Opt[str] = None


class BidUpdate(BaseModel):
    status: Opt[str] = None
    sub_name: Opt[str] = None
    sub_contact: Opt[str] = None
    sub_quote: Opt[float] = None
    our_bid: Opt[float] = None
    past_price_ceiling: Opt[float] = None
    notes: Opt[str] = None


@app.get("/api/bids")
async def get_bids(status: str = Query(None)):
    bids = list_bids(status or None)
    summary = pipeline_summary()
    return JSONResponse({"bids": bids, "summary": summary, "statuses": STATUSES})


@app.post("/api/bids")
async def add_bid(req: BidCreate):
    bid = create_bid(
        notice_id=req.notice_id,
        title=req.title,
        agency=req.agency,
        naics_code=req.naics_code,
        state=req.state or "",
        deadline=req.deadline,
        sam_link=req.sam_link,
    )
    return JSONResponse(bid or {})


@app.get("/api/bids/pipeline")
async def get_pipeline():
    return JSONResponse(pipeline_summary())


@app.patch("/api/bids/{notice_id}")
async def patch_bid(notice_id: str, req: BidUpdate):
    updates = req.model_dump(exclude_none=True)
    bid = update_bid(notice_id, **updates)
    if not bid:
        raise HTTPException(status_code=404, detail="Bid not found.")
    return JSONResponse(bid)
