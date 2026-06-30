# Olive Tree — Land Wholesaling Scripts

Call/letter scripts for the land vertical. Used by `/land-builders`, `/land-call`, `/land-mail`. Adapt the bracketed fields. Nothing auto-sends.

---

## 1. Builder / developer first call (get the buy box)

Goal: learn price, sizes, zips, conditions, close timeline.

> "Hi [name] — I see you've been building around [area/zip]. I bring builders off-market land deals. Quick question: what would you pay for a buildable lot in [zip], and what lot sizes are you looking for? … Any conditions that kill it for you — slope, wetlands, utilities? … And how fast can you close on clean title?"

Capture into the **Land Builders** tab: price/lot or price/acre, size range, zips, conditions, volume/month, close timeline.

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
