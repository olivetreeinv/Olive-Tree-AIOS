# GHL Workflow — Contact added>> send text/email

- **Status:** published
- **Version:** 7
- **Created:** 2025-05-13T17:12:30.350Z
- **Updated:** 2026-02-17T18:59:59.930Z
- **Trigger data file:** `location/SLq7B2pldVzfQLKjGpvw/workflow-triggers/73b9a479-c833-4cb4-ac6e-26cbe4bacced/6` (triggers stored separately in Firebase; see raw fileUrl)

## Steps (workflowData.templates)

### 0. Email  _(email)_
- **Subject:** {{contact.first_name}},
- **Body:**

```
Hi {{contact.first_name}},

At Olive Tree Investments, we believe that building wealth through real estate should be accessible, strategic, and community-driven.

That’s why we invite you to subscribe to our exclusive newsletter—your front-row seat to real estate intelligence, expert strategies, and curated opportunities in multifamily investing.

Here’s what you’ll get:
•⁠  ⁠🏢 Early access to new investment opportunities  
•⁠  ⁠📈 Market trends & performance insights  
•⁠  ⁠💡 Wealth-building strategies from seasoned pros  
•⁠  ⁠🤝 Real-time project updates & partnership news  

👉 Subscribe Now and take your investment game to the next level. Subscribe by responding with "Yes".

We’re not just growing properties—we’re growing people.

Warm regards,  
The Olive Tree Team
```

### 1. SMS  _(sms)_
- **Message:**

```
⁠Hi {{contact.first_name}}, welcome to Olive Tree Investments! Want early access to top real estate insights & investment deals? Tap here to subscribe ➡️ [Your Link]
```

### 2. Wait 12 hrs  _(wait)_
- **Wait:** {"type": "time", "startAfter": {"type": "hour", "value": 12, "when": "after"}, "name": "Wait 12 hrs", "cat": "", "isHybridAction": true, "hybridActionType": "wait", "convertToMultipath": false, "transitions": []}

### 3. Email  _(email)_
- **Subject:** {{contact.first_name}}, Why 750+ Investors Trust Olive Tree (And You Can Too)
- **Body:**

```
Hi {{contact.first_name}},

Over 750 investors have partnered with us on a shared mission: to unlock long-term wealth through intelligent real estate investing.
When you join our newsletter, you're not just getting emails.

You're gaining access to:
•⁠  ⁠Real-time market insights  
•⁠  ⁠New deal alerts before the public  
•⁠  ⁠A network of forward-thinking investors  
Whether you’re curious, cautious, or ready to scale your portfolio, our newsletter helps you stay informed, confident, and connected.

👉 Don’t miss out. [Join our investor community today]
To your success,  
The Olive Tree Investments Team
```

### 4. SMS- social proof  _(sms)_
- **Message:**

```
750+ investors trust Olive Tree for smart multifamily investments. Join our newsletter to stay ahead of the curve 📈 ➡️ [Your Link]
```

### 5. wait  _(wait)_
- **Wait:** {"type": "reply", "startAfter": {"type": "minutes", "value": 15, "when": "after"}, "name": "Wait", "cat": "multi-path", "isHybridAction": true, "hybridActionType": "wait", "convertToMultipath": true, "transitions": [{"id": "6a7b65c9-cafb-4ada-bb2b-b150d41546f7", "name": "wait", "condition": "primary", "conditionType": "user-defined", "isPrimaryBranch": true, "description": "", "attributes": {"type": "wait_reply", "description": "What will happen when a contact replies on Email or Email or SMS or SMS- social proof"}}, {"id": "8e6e6901-89d5-47c0-80f9-50e2b491ff27", "name": "timeout", "condition": "timeout", "conditionType": "user-defined", "isPrimaryBranch": false, "description": "", "attributes": {"type": "wait_timeout", "description": "What will happen after 15 minutes"}}], "reply": ["92f0d648-627d-48f3-92d3-2b64d278a3f4", "23c66793-aba2-44e5-847c-253b9cc17554", "181c3077-e64d-42ca-b136-494a0b6c8e78", "ac0d5993-93c6-4995-9df8-0450715479a6"], "replyLabel": ["Email", "Email", "SMS", "SMS- social proof"]}

### 6. wait  _(transition)_
- attributes: `{"type": "wait_reply", "description": "What will happen when a contact replies on Email or Email or SMS or SMS- social proof"}`

### 0. Add Tag  _(add_contact_tag)_
- attributes: `{"tags": ["newsletter"]}`

### 6. timeout  _(transition)_
- attributes: `{"type": "wait_timeout", "description": "What will happen after 15 minutes"}`
