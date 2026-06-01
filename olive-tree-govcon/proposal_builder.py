import os
from typing import Optional

import anthropic

_client: Optional[anthropic.AsyncAnthropic] = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
    return _client


def _fmt(val) -> str:
    if val is None:
        return "TBD"
    try:
        return f"${float(val):,.2f}"
    except (TypeError, ValueError):
        return str(val)


_SECTIONS = ["PROPOSAL", "SUB OUTREACH SCRIPT", "SUB EMAIL TEMPLATE", "PRICING RATIONALE"]


def _extract(raw: str, section: str) -> str:
    marker = f"=== {section} ==="
    if marker not in raw:
        return ""
    start = raw.index(marker) + len(marker)
    end = len(raw)
    for s in _SECTIONS:
        other = f"=== {s} ==="
        if other != marker and other in raw:
            idx = raw.index(other)
            if idx > start:
                end = min(end, idx)
    return raw[start:end].strip()


async def generate_proposal(
    opportunity: dict,
    sub_quote: float,
    our_bid: float,
    past_price_ceiling: Optional[float],
    sub_name: Optional[str] = None,
) -> dict:
    client = _get_client()

    title      = opportunity.get("title", "Federal Service Contract")
    agency     = (opportunity.get("fullParentPathName") or "").split(">")[0].strip() or "Federal Agency"
    naics_code = opportunity.get("naicsCode", "")
    state      = ""
    if isinstance(opportunity.get("placeOfPerformance"), dict):
        state = opportunity["placeOfPerformance"].get("state", {}).get("code", "") or ""
    deadline   = opportunity.get("responseDeadLine", "See solicitation")
    notice_id  = opportunity.get("noticeId", "")
    sam_link   = opportunity.get("uiLink", "")
    description = (opportunity.get("description") or "")[:600]

    gross_profit = our_bid - sub_quote
    margin_pct   = (gross_profit / our_bid * 100) if our_bid else 0

    pricing_line = ""
    if past_price_ceiling:
        pct_below = (1 - our_bid / past_price_ceiling) * 100
        pricing_line = f"Past ceiling: {_fmt(past_price_ceiling)}. Our bid is {pct_below:.0f}% below historical ceiling."

    user_prompt = f"""Write a federal RFQ proposal package. Separate sections with === SECTION NAME ===.

CONTRACT: {title} | {agency} | NAICS {naics_code} | {state} | Due: {deadline} | Notice: {notice_id}
DESCRIPTION: {description or 'See solicitation documents.'}
PRICING: Sub quote {_fmt(sub_quote)}{f' ({sub_name})' if sub_name else ''} | Our bid {_fmt(our_bid)} | Profit {_fmt(gross_profit)} ({margin_pct:.1f}%) | {pricing_line}
COMPANY: Olive Tree Investments LLC — registered small business, SAM.gov active. Owner: Brian Norton, brian@olivetreeinv.io

=== PROPOSAL ===
Professional proposal covering: executive summary (2-3 sentences), technical approach, price table, subcontractor info (name: {sub_name or '[SUBCONTRACTOR NAME]'}), capability statement (generic), POC: Brian Norton brian@olivetreeinv.io. Plain text only.

=== SUB OUTREACH SCRIPT ===
60-second phone script: what the contract is, where, net-30 payment, need a quote by [deadline minus 5 days]. Natural tone.

=== SUB EMAIL TEMPLATE ===
Under 150 words. Subject line + body. Sign off: -Brian, brian@olivetreeinv.io

=== PRICING RATIONALE ===
3-4 bullet points: why {_fmt(our_bid)} is the right bid given the sub quote and pricing context."""

    msg = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2500,
        messages=[{"role": "user", "content": user_prompt}],
    )

    raw = msg.content[0].text if msg.content else ""

    return {
        "proposal_text":       _extract(raw, "PROPOSAL"),
        "sub_outreach_script": _extract(raw, "SUB OUTREACH SCRIPT"),
        "sub_email_template":  _extract(raw, "SUB EMAIL TEMPLATE"),
        "pricing_rationale":   _extract(raw, "PRICING RATIONALE"),
        "our_bid":             our_bid,
        "sub_quote":           sub_quote,
        "gross_profit":        gross_profit,
        "margin_pct":          round(margin_pct, 1),
    }
