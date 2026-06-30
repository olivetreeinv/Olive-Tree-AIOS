# Government Contracting — Workflow Reference

## The Model in One Sentence
Find a federal service contract on SAM.gov → get a subcontractor quote → mark it up → submit the bid → collect from the government → pay the sub → keep the spread.

---

## One-Time Setup (Do This First)

### 1. Form your LLC
- Register at your state's Secretary of State website
- Get your EIN free at IRS.gov (10 minutes)
- Open a business checking account in the LLC name

### 2. Register on SAM.gov
- Go to sam.gov → Create account → Register Entity
- You'll need: LLC name, EIN, NAICS codes, bank account for EFT payments
- Full activation takes 1–3 weeks — start immediately
- **You cannot submit bids until SAM.gov is active**

### 3. Pick your NAICS codes
Codes already loaded in the app. Start with these highest-win plays:
- **562112** — Hazardous Waste Collection (Natalie's #1 earner)
- **484210** — Household & Office Moving (relocation contracts, low competition)
- **531311** — Residential Property Management (you know this business)
- **561730** — Landscaping (Natalie's $962K contract)
- **561720** — Janitorial & Cleaning (recurring, easy to sub)
- **812990** — All Other Personal Services (Natalie's Dismal Swamp play)

---

## The Weekly Workflow (Every Monday)

```
Top 20 Picks → Analyze → Pricing → Find Sub → Proposal → Submit → Track
```

### Step 1 — Open the app
Start the GovCon app:
```
http://localhost:8000
```
If it's not running, open Terminal and run:
```bash
cd "/Users/olivetree/Documents/Olive AIOS/olive-tree-govcon"
.venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

---

### Step 2 — Find your best bids
Click **Top 20 Picks** tab.

The app scores every opportunity from the last 30 days across all your NAICS codes. Look for:
- ✅ Green score (70+)
- ✅ Notice type: RFQ or IFB (not Sources Sought or Pre-Sol)
- ✅ 14+ days until deadline
- ✅ Small business set-aside badge (means less competition)

**Notice type guide:**
| Type | What it means | Bid it? |
|---|---|---|
| RFQ | Request for Quote — under $350K, price only, no past performance | ✅ Best |
| IFB | Invitation for Bid — sealed bid, lowest price wins | ✅ Great |
| Combined | Combined synopsis + solicitation | ✅ Good |
| RFP | Request for Proposal — may need past performance | ⚠️ Review first |
| Sources Sought | Market research only — not a real bid | ❌ Skip |
| Pre-Sol | Presolicitation — not ready yet | ❌ Skip |
| Award | Already awarded | ❌ Skip |

---

### Step 3 — Analyze the bid
Click **Analyze** on any card that looks promising.

Wait 10–15 seconds. You'll get:
- **GO / NO-GO / NEEDS REVIEW** — Claude's verdict
- **Scope summary** — plain English: what the work actually is
- **Submission checklist** — exactly what you need to submit
- **FAR clauses** — legal references (don't need to understand these)

**GO criteria:** Services contract, subcontracting allowed, no security clearance needed, straightforward scope.

**NO-GO criteria:** Self-performance required, security clearance needed, products/manufacturing.

If it says GO → continue. NO-GO → skip it, move to the next one.

---

### Step 4 — Research the pricing
Click **Pricing** on the same card.

This pulls what the government has actually paid for this work before from USASpending.gov.

**How to use it:**
- **Ceiling** = the highest the government has paid. This is your upper limit.
- **Recommended range** = 75–85% of the ceiling. This is your target bid.
- Example: ceiling $80K → bid between $60K–$68K

**The golden rule:** Never bid blind. Always check the ceiling before picking your number.

---

### Step 5 — Find a subcontractor
This is your job — the app can't make phone calls.

**How to find subs:**
1. Google: `[service type] company [city where work is]`
2. Check Yelp, Angi, or Google Maps for local businesses
3. Look for small teams (3–15 people), 4+ star reviews, active website

**Call script (60 seconds):**
> "Hey [Name], my name's Brian Norton with Olive Tree Investments. I have a federal government contract opportunity in [city] for [service]. The government pays net 30 after the work is done. I need a quote by [deadline minus 5 days]. Would you be interested and can you get me a price for [scope in one sentence]? Best way to reach me is brian@olivetreeinv.io."

**What to look for in a sub:**
- Responds same day or next day (hunger signal)
- Asks smart questions about the scope
- Small enough to care about your contract
- Not so busy they'll deprioritize you

**Get at least 2 quotes.** This gives you options and competitive data.

**Key thing to tell subs:** They get paid after the government pays you (net 30). Some will push back — find ones who accept these terms.

---

### Step 6 — Generate your proposal
Once you have a sub quote, click **Proposal** on the card.

Enter:
- **Sub name** (optional but helps personalize the output)
- **Sub quote** — what they'll charge you
- **Our bid price** — your markup (use the pricing ceiling from Step 4 as your guide)
- **Past price ceiling** — auto-fills if you clicked Pricing first

Click **Generate Proposal**. Claude writes four things in ~30 seconds:

| Tab | What it is | When to use it |
|---|---|---|
| Proposal | Full proposal text ready to submit | Copy and paste into SAM.gov |
| Phone Script | What to say when calling subs | Before you've locked in a sub |
| Email Template | Follow-up email if sub didn't answer | Day after the call |
| Pricing Notes | Why your bid price makes sense | Internal reference |

**The math:**
```
Gross Profit = Our Bid - Sub Quote
Margin %     = Gross Profit ÷ Our Bid × 100
Target:        Bid at 75–85% of pricing ceiling
```

---

### Step 7 — Submit on SAM.gov (manual)
This step cannot be automated. SAM.gov requires a logged-in account.

1. Click **SAM.gov ↗** on the card — takes you directly to the opportunity
2. Log into your SAM.gov account
3. Find the "Submit Offer" or "Submit Quote" button
4. Paste your proposal text from the app
5. Attach any required documents from the submission checklist
6. Hit submit before the deadline

**After submitting:** Update the bid status in the app to `submitted`.

---

### Step 8 — Track it
Click **Track** on the card to add it to the Bid Pipeline.

Click the **Bid Pipeline** tab to see everything in flight.

**Status flow:**
```
researching → sub_contacted → quoted → submitted → won / lost
```

Update status as you go. Your hit rate calculates automatically once you start winning.

---

## Key Numbers to Know

| Metric | What it means |
|---|---|
| Net 30 | Government pays you 30 days after work completion + invoice submitted |
| $350K threshold | Below = RFQ (no past performance needed). Above = RFP (past performance required) |
| 8–9% | Percent of contracts that receive zero bids — look for niche/unusual ones |
| 50% rule | You must perform at least 50% of the work yourself OR use certified small business subs |
| Pass-through | Illegal — you must add real value (coordination, oversight, invoicing, accountability) |

---

## What "Net 30" Means in Practice

1. Contract awarded to you
2. Sub does the work
3. You submit invoice to the government
4. Government pays **you** within 30 days
5. You pay your sub after receiving payment

Your sub works first, gets paid after. This is standard — find subs who accept it.

---

## The Scoring System (Top 20)

| Factor | Max Points | What earns it |
|---|---|---|
| Notice type | 25 | RFQ = 25, IFB = 22, Combined/Solicitation = 15, RFP = 8 |
| Deadline | 20 | 21+ days = 20, 14–20 days = 16, 7–13 days = 10 |
| Set-aside | 20 | Any small business set-aside = 20 |
| Has documents | 15 | Docs available to analyze = 15 |
| Service contract | 20 | Service NAICS (56xxxx, 48xxxx, 81xxxx) = 20 |

**Score guide:** 70+ = pursue. 45–69 = review. Below 45 = low priority.

---

## Subcontractor Vetting Checklist

Before locking in a sub:
- [ ] Responded within 24 hours
- [ ] Seems genuinely interested (asks questions about scope)
- [ ] Has a real website and Google presence
- [ ] 4+ star reviews mentioning reliability and showing up on time
- [ ] Small enough to prioritize your contract
- [ ] Has done this type of work before
- [ ] Accepts net-30 payment terms
- [ ] Check SAM.gov that they're not debarred (search their name at sam.gov)

---

## Run the Skill Anytime

Say **"govcon"** in Claude Code to check your pipeline and get next steps.

The skill will:
- Pull your live bid status
- Surface the most urgent action per bid
- Draft subcontractor outreach if needed
- Update bid status after you take action
