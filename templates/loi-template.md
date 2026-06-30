# Olive Tree Investments — LOI Template (preview)
**Source:** LOI Example (641 Powder Springs) — Google Doc renders the final formatting.
**Fields, defaults, formulas, and Google-Doc token map:** `templates/loi-fields.json` — the single source of truth. This file is the **in-chat preview body only**; `scripts/loi.py` produces the actual Doc + PDF from the JSON.
**Use:** Show this filled in for Brian's approval. `{{KEY}}` tokens match the keys in `loi-fields.json`. All deposits auto-calculate from offer price. Nothing auto-sends.

---

## Template

```
[LOGO — height no more than 1 inch. Omit this line if no logo provided.]

# LETTER OF INTENT

# From: {{COMPANY_NAME}}  {{OWNER_NAME}}, Owner

To: {{BROKER_NAME}} | {{BROKERAGE}}

RE: Purchase of {{PROPERTY_ADDRESS}}

This non-binding Letter of Intent ("LOI") sets forth the general terms upon which **{{COMPANY_NAME}} or assignee** ("Buyer") will purchase **{{PROPERTY_ADDRESS}}** ("The Property") from Selling Entity ("Seller"). Buyer and Seller will not be legally bound to transact unless and until the execution and delivery of a Purchase and Sale Agreement ("PSA") by Buyer and Seller. The purpose of this LOI is to provide the basis and general terms for which a transaction will be contemplated and negotiated, and to outline the main terms for which a PSA will eventually be documented.

| PROPERTY             | {{PROPERTY_ADDRESS}}                                                                                                                                                                                                                                                                               |
|:---------------------|:-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| PRICE                | **${{OFFER_PRICE}} / ${{PRICE_PER_UNIT}}/unit**                                                                                                                                                                                                                                                     |
| DEPOSIT              | **${{TOTAL_DEPOSIT}}** delivered within five (5) days of mutual execution of the PSA and placed in escrow with **First American, Chicago or Fidelity Title**. Following the expiration of the due diligence period, the Deposit shall be non-refundable to Buyer. **${{HARD_DEPOSIT}} is hard from day 1, non-refundable.** |
| FINANCING            | **{{FINANCING_TYPE}}**                                                                                                                                                                                                                                                                             |
| DOWNPAYMENT          | **{{DOWNPAYMENT}}**                                                                                                                                                                                                                                                                                |
| DUE DILIGENCE        | **{{DD_DAYS}} Day Due Diligence** beginning at the execution date of the PSA to inspect and perform Due Diligence as Buyer deems reasonably necessary to further evaluate the Purchase of the Property(s). Upon execution of LOI, Buyer shall have access to the property/units and all financial, legal, title, survey and other pertinent documents needed to evaluate the purchase of the Property. |
| CLOSING              | **{{CLOSING_DAYS}} Day Total Closing.** In the event an extension is needed it shall be granted for 30 days with an additional **${{EXTENSION_DEPOSIT}}** non-refundable deposit applicable to purchase price.                                                                                        |
| CLOSING COSTS/TITLE  | Customary. The Property to be sold and conveyed free of liens and encumbrances, and title is to be deemed clean and marketable.                                                                                                                                                                   |
| BROKERS & COMMISSIONS | Seller shall pay all brokerage commissions.                                                                                                                                                                                                                                                      |
| CONTINUED OPERATIONS | Unless otherwise stated in the PSA, Seller will continue to operate the Property in a consistent manner as prior to this LOI. Major property decisions which might significantly affect the value of Property or nature of the contemplated transaction, should be brought to Buyer for discussion and review. |
| SPECIAL CONDITIONS   | {{SPECIAL_CONDITIONS}}                                                                                                                                                                                                                                                                             |
| OTHER TERMS          | Insurance shall be selected by purchaser.                                                                                                                                                                                                                                                        |
| CONFIDENTIALITY      | The content of this LOI shall be confidential in nature and shall not be disclosed to other buyers.                                                                                                                                                                                               |
| ABOUT SPONSOR (Resume) | {{COMPANY_NAME}} is a {{COMPANY_CITY}} based private investment firm focused on offering retail, accredited, family funds, and institutional investors access to emerging real-estate opportunities. In collaboration with partners with over 11 years of corporate experience in land acquisition, multi-unit development and value-add apartment rehabilitation & management, we actively manage end-to-end operations. {{COMPANY_NAME}} & our co-GP partners have acquired over 1,000 units and have a history of thousands of multifamily units developed over the years. |

| SIGNATURES  Buyer: {{COMPANY_NAME}} or its assignee.  Date: {{DATE}}  {{OWNER_NAME}} | SIGNATURES  Seller:  Date: |
|:---|:---|

{{OWNER_EMAIL}} | {{OWNER_PHONE}} | {{COMPANY_WEBSITE}}
```

---

## Deposit Quick Reference

| Item | Formula | Example ($950K deal) |
|---|---|---|
| Total earnest deposit | price × 1% (round to nearest $500) | $9,500 |
| Hard from day 1 | price × 0.5% (round to nearest $250) | $4,750 |
| Extension deposit | price × 0.15% (round to nearest $100) | $1,400 |

> Formulas + rounding live in `templates/loi-fields.json` — change them there, not here.

---

## Negotiation Notes (Stage 7 of pipeline)

- **Price** — anchor below asking; the DSCR max defensible offer is the ceiling. Never draft above it without Brian's explicit override logged in `decisions/log.md`.
- **DD period** — 28 days is standard; push for 30–45 on complex deals.
- **Hard deposit** — keep it low; push for a longer soft period.
- **Key broker question:** *"What terms matter most to the seller?"* and *"Where are competitive offers landing?"*
- **Non-binding, always** — LOI must state it's non-binding and subject to PSA.
- **If the LOI loses** — draft a gracious note to keep the broker relationship warm.
