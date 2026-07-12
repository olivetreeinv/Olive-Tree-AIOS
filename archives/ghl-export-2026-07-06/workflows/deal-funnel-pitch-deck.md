# GHL Workflow — Deal Funnel Pitch Deck

- **Status:** published
- **Version:** 11
- **Created:** 2025-02-05T22:22:17.657Z
- **Updated:** 2026-05-21T17:32:07.590Z
- **Trigger data file:** `location/SLq7B2pldVzfQLKjGpvw/workflow-triggers/0f93b671-d649-4836-9cd4-39ce0985c4c1/2` (triggers stored separately in Firebase; see raw fileUrl)

## Steps (workflowData.templates)

### 0. Email  _(email)_
- **Subject:** Here Is Your Pitch Deck
- **Body:**

```
Hello {{contact.first_name}}, Here's your copy of the pitch deck you requested. We will reach out and discuss shortly

Brian Norton
Olive Tree Investments
```

### 1. SMS  _(sms)_
- **Message:**

```
{{contact.first_name}}, a copy of the pitch deck has been sent to your email.
```

### 2. Add Tag  _(add_contact_tag)_
- attributes: `{"tags": ["pitchdeck"]}`

### 3. Internal Notification  _(internal_notification)_
- **Notify:** subject= | 
