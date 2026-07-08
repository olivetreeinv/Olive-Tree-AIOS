<!-- Exact copy from GHL workflow "Deal Funnel Pitch Deck" (v11), step 0. Recovered 2026-07-07 via ghl_workflow_export.py.
     GHL fired this on the pitch-deck funnel opt-in: 1 delivery email + SMS + adds `pitchdeck` tag + internal notification to Brian.
     GHL step 1 was an SMS (dropped in local v1, email-only): "{{first_name}}, a copy of the pitch deck has been sent to your email."
     GHL step 2 added tag `pitchdeck`; step 3 sent Brian an internal notification (not reproduced — no internal-notify channel in v1; tag applied at enroll).
     The prior local 3-step cadence (steps 02/03) was invented, not from GHL — removed to match GHL exactly (recoverable from git history). -->
---
delay_days: 0
subject: Here Is Your Pitch Deck
---
Hello {{first_name}}, Here's your copy of the pitch deck you requested. We will reach out and discuss shortly

Brian Norton
Olive Tree Investments
