# Olive Tree — Land Wholesaling Scripts

Call/letter scripts for the land vertical. Used by `/land-builders`, `/land-call`, `/land-mail`. Adapt the bracketed fields. Nothing auto-sends.

---

## 1. Builder / developer outreach (get the buy box)

The buy box is the anchor for everything — one confirmed $/acre = green light to mass-offer that zip. Get it three ways; capture every answer in the **Land Builders** tab.

**Who to hit first.** Lead with **Tier-A regional "build-on-your-lot" / scattered-spec builders** (Adams, DSLD, Stone Martin, True Homes, Sedgewick, Taylor) — they take a *single* 1–10 ac assigned lot and close fast. Nationals (DR Horton, LGI, Smith Douglas) want 50+ lot subdivisions and route through slow land-acquisition portals — work them too, but they're not your fast yes.

**Find them where they're already building.** Zillow / Realtor.com "new construction" in the target zip shows which builder names recur — that's your call list (`/land-builders` logs it). Those same listings give you the retail $/acre for the **Avg $/Acre (Comp)** column.

**The four questions (every channel):** price/acre · lot-size range · deal-killers (slope, wetlands, utilities, road frontage) · close speed on clean title.

**a) Call** (Tier-A, when you have a phone):
> "Hi [name] — I see you've been building around [exact zip/subdivision]. I bring builders off-market vacant land before it hits the MLS. What would you pay per acre for a buildable 1–10 ac lot in [zip], what sizes do you want, and what kills a deal — slope, wetlands, utilities, road frontage? How fast can you close on clean title?"

**b) Email** (no phone, or a warm-up — staged, never auto-sent):
> Subject: Off-market land for your [county] pipeline
> Builder-to-builder, ~6 lines: who you are, that you tie up vacant 1–10 ac lots in their exact zips *before MLS*, the four questions, offer a 10-min call. (See the DSLD draft pattern.)

**c) Intake portal** (nationals with "sell your land" forms — Fischer, DR Horton, Smith Douglas, True Homes, DSLD): submit a real or representative parcel to get routed to the local land-acquisition manager; log their reply.

Capture into the **Land Builders** tab: price/lot or price/acre, size range, zips, conditions, volume/month, close timeline, tier, intake-portal URL.

---

## 2. Seller cold call (the core)

You're offering money, not selling anything. Keep it to 90–120 seconds.

> **Open:** "Hey [name], is this the owner of [situs address]? … I'll be quick — would you be open to selling that lot if the price was right?"
>
> **Offer:** "I can do a full cash offer, you pay no realtor fees and no closing costs, so it's net to you. I can close in 2–3 weeks. I can get you [offer] plus all closing costs."
>
> **If they name a higher comp:** "Got it — that one was listed in [month] and took ~6 months to close, and after the ~8% agent fee and ~$1,500 closing costs they really walked with about [net]. I'm transparent: I work with builders in the area and have one ready. I can do [offer] — about the same in your pocket, but done in 3 weeks instead of 6 months."
>
> **Counter-offer move:** never say yes instantly. "Let me check with my partner…" [pause 60–90s] "…yeah, we can make [number] work." (Reduces remorse, raises close rate.)
>
> **If no:** "No worries — save my number as [name] Land Guy. If you ever decide to sell, that's me. Have a good one."

---

## 3. Neighbor first-look call (before closing with a builder)

> "Hi [name] — courtesy call. I'm about to sell the vacant lot right next to you at [address] to a builder. Before it goes, I wanted to give you first look — any interest in extending your yard, a buffer, or picking it up yourself?"

Neighbors routinely pay above market (the lot has unique value to them).

---

## 4. Mass-offer mail (letter + pre-filled contract)

**Letter (one page):** who you are; that you work with [N] builders in [area]; that you buy vacant land for cash, no fees, ~3-week close; the offer for *their* parcel is enclosed; sign and return, or call/text [number].

**Enclosure:** pre-filled offer at [offer] with assignability + feasibility clauses, 21–30 day close, signature line, return envelope/instructions.

Template lives in `templates/land-mail-offer.md`; `/land-mail` merges per parcel from the Land Sellers tab.

---

## 5. "Save my number" follow-up

Tag every no with a callback. Many deals close months later. `/land-call` schedules the callback and re-surfaces it.
