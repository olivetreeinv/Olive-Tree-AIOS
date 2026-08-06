<!-- Exact copy from GHL workflow "Contact added>> send text/email" (v7), step 3. Recovered 2026-07-07 via ghl_workflow_export.py.
     Fires after a 12hr wait in GHL; the day-granularity local drip rounds to 1 day.
     GHL step 4 was an SMS (dropped in local v1, email-only): "750+ investors trust Olive Tree for smart multifamily investments. Join our newsletter to stay ahead of the curve 📈 ➡️ [Your Link]"
     GHL step 5 was a 15-min reply-branch that added the `newsletter` tag on reply. Local reproduction applies the newsletter tag at enrollment/audience sync instead of via reply detection. -->
---
delay_days: 1
subject: {{first_name}}, Why 750+ Investors Trust Olive Tree (And You Can Too)
---
Hi {{first_name}},

Over 750 investors have partnered with us on a shared mission: to unlock long-term wealth through intelligent real estate investing.
When you join our newsletter, you're not just getting emails.

You're gaining access to:
- Real-time market insights
- New deal alerts before the public
- A network of forward-thinking investors

Whether you're curious, cautious, or ready to scale your portfolio, our newsletter helps you stay informed, confident, and connected.

👉 Don't miss out. [Join our investor community today]

To your success,
The Olive Tree Investments Team
