# Olive Tree Investments — LOI Template
**Source:** 641 Powder Springs St LOI (Brian Norton, 04/21/26)
**Use:** Fill placeholders below. Review every draft before sending — nothing auto-sends.

---

## Template

```
OLIVE TREE INVESTMENTS
LETTER OF INTENT

From: Olive Tree Investments LLC
      Brian Norton, Owner

To:   [BROKER_NAME] | [BROKERAGE]

RE:   Purchase of [PROPERTY_ADDRESS]

This non-binding Letter of Intent ("LOI") sets forth the general terms upon which
Olive Tree Investments, LLC or assignee ("Buyer") will purchase [PROPERTY_ADDRESS]
("The Property") from Selling Entity ("Seller"). Buyer and Seller will not be
legally bound to transact unless and until the execution and delivery of a Purchase
and Sale Agreement ("PSA") by Buyer and Seller. The purpose of this LOI is to
provide the basis and general terms for which a transaction will be contemplated
and negotiated, and to outline the main terms for which a PSA will eventually be
documented.

PROPERTY            [PROPERTY_ADDRESS]

PRICE               $[OFFER_PRICE] / $[PRICE_PER_UNIT]/unit

DEPOSIT             $[TOTAL_DEPOSIT] delivered within five (5) days of mutual
                    execution of the PSA and placed in escrow with First American,
                    Chicago or Fidelity Title. Following the expiration of the due
                    diligence period, the Deposit shall be non-refundable to Buyer.
                    $[HARD_DEPOSIT] is hard from day 1, non-refundable.

FINANCING           [FINANCING_TYPE]. No Financing Contingency.

DOWNPAYMENT         [DOWNPAYMENT_PCT]% Down Payment Equity ([EQUITY_SOURCE]).

DUE DILIGENCE       [DD_DAYS] Day Due Diligence beginning at the execution date of
                    the PSA to inspect and perform Due Diligence as Buyer deems
                    reasonably necessary to further evaluate the purchase of the
                    Property. Upon execution of LOI, Buyer shall have access to the
                    property/units and all financial, legal, title, survey, and other
                    pertinent documents needed to evaluate the purchase of the Property.

CLOSING             [CLOSING_DAYS] Day Total Closing. In the event an extension is
                    needed it shall be granted for [EXTENSION_DAYS] days with an
                    additional $[EXTENSION_DEPOSIT] non-refundable deposit applicable
                    to purchase price.

CLOSING COSTS/TITLE Customary. The Property to be sold and conveyed free of liens
                    and encumbrances, and title is to be deemed clean and marketable.

BROKER(S) &         Seller shall pay all brokerage commissions.
COMMISSIONS

CONTINUED           Unless otherwise stated in the PSA, Seller will continue to
OPERATIONS          operate the Property in a consistent manner as prior to this LOI.
                    Major property decisions which might significantly affect the
                    value of the Property or nature of the contemplated transaction
                    should be brought to Buyer for discussion and review.

SPECIAL CONDITIONS  [SPECIAL_CONDITIONS]

OTHER TERMS         Insurance shall be selected by purchaser.

CONFIDENTIALITY     The content of this LOI shall be confidential in nature and
                    shall not be disclosed to other buyers.

ABOUT SPONSOR       Olive Tree Investments is an Atlanta-based private investment
                    firm focused on offering retail, accredited, family fund, and
                    institutional investors access to emerging real estate
                    opportunities. In collaboration with partners with over 11 years
                    of experience in land acquisition, multi-unit development, and
                    value-add apartment rehabilitation & management, we actively
                    manage end-to-end operations. Olive Tree Investments & our co-GP
                    partners have acquired over 1,000 units and have a history of
                    thousands of multifamily units developed over the years.

SIGNATURES

Buyer: Olive Tree Investments LLC or its assignee          Date: [DATE]

_________________________________
Brian Norton, Owner
brian@olivetreeinv.io | 404-643-2356 | www.OliveTreeInv.io

Seller:                                                    Date:

_________________________________
```

---

## Field Guide

| Placeholder | What to fill | Default / Guidance |
|---|---|---|
| `[BROKER_NAME]` | Broker's full name | From Brokers List or email |
| `[BROKERAGE]` | Brokerage firm name | From Brokers List or email |
| `[PROPERTY_ADDRESS]` | Full street address, city, state, zip | From OM or listing |
| `[OFFER_PRICE]` | Dollar amount of offer | From deal analysis output |
| `[PRICE_PER_UNIT]` | Offer price ÷ units | Auto-calc |
| `[TOTAL_DEPOSIT]` | Total earnest money | ~1% of offer price |
| `[HARD_DEPOSIT]` | Hard day-1 non-refundable portion | ~50% of total deposit |
| `[FINANCING_TYPE]` | Loan type and LTV | Default: `70% LTC Bridge Financing` |
| `[DOWNPAYMENT_PCT]` | Equity % | Default: `30` |
| `[EQUITY_SOURCE]` | Where equity comes from | Default: `equity sourced from our funds & partners` |
| `[DD_DAYS]` | Due diligence period length | Default: `28` (range: 21–45) |
| `[CLOSING_DAYS]` | Total closing timeline | Default: `60` (range: 45–75) |
| `[EXTENSION_DAYS]` | Extension window if needed | Default: `30` |
| `[EXTENSION_DEPOSIT]` | Additional deposit for extension | Default: `$1,300` (adjust to ~0.1% of price) |
| `[SPECIAL_CONDITIONS]` | Any deal-specific terms | Default: `N/A` |
| `[DATE]` | Date LOI is submitted | Today's date |

---

## Standard Defaults (from knowledge-base.md)

```
Financing:      Bridge loan, non-recourse, 70–75% LTC, 36-month I/O
                1% lender fee, 0.5% broker fee, 6-month extension option
Deposit:        1–2% of offer price total
                50% hard from day 1
DD Period:      28–30 days (ask for 45 on complex deals)
Closing:        60 days from LOI execution
Extension:      30 days / $1,300 (adjust to ~0.1% of purchase price)
Commissions:    Seller pays — always
Contingency:    No financing contingency (signals strength)
```

---

## Negotiation Targets (from knowledge-base.md, Stage 7)

When countering or adjusting:
- **Price** — primary lever; anchor below asking, leave room to negotiate up
- **Earnest money** — keep hard deposit low; push for longer soft period
- **DD period** — longer is better; 30+ days gives time for physical inspection
- **Closing timeline** — 60 days is standard; can extend for complex deals
- **Ask broker:** *"What terms matter most to the seller?"* and *"Where do competitive offers usually land?"*

---

## When used by /lets-get-to-work and /deal-analysis

The LOI draft step pulls:
1. `OFFER_PRICE` and `PRICE_PER_UNIT` → from deal analysis recommendation
2. `BROKER_NAME` + `BROKERAGE` → from Deal Sourcing tab or inbound email
3. `PROPERTY_ADDRESS` → from deal sourcing log
4. All other fields → defaults above unless Brian specifies otherwise

Draft is shown to Brian before any send. He confirms price, deposit, and DD period before it goes out.
