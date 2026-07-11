# GHL Workflow — Brian's Personal Calendar Booking - DS

- **Status:** published
- **Version:** 9
- **Created:** 2026-02-16T20:48:35.326Z
- **Updated:** 2026-05-28T10:26:42.126Z
- **Trigger data file:** `location/SLq7B2pldVzfQLKjGpvw/workflow-triggers/a2539935-a5d0-4c22-92e9-378ee0319c98/8` (triggers stored separately in Firebase; see raw fileUrl)

## Steps (workflowData.templates)

### 0. Email  _(email)_
- **Subject:** Welcome
- **Body:**

```

```

### 1. SMS  _(sms)_
- **Message:**

```
Welcome
```

### 2. Internal Notification  _(internal_notification)_
- **Notify:** subject= | 

### 3. 24 hours before Wait  _(wait)_
- **Wait:** {"type": "appointment", "name": "24 hours before Wait", "cat": "", "appointmentStartAfter": {"when": "before", "type": "minutes", "value": 1440, "distributed": {"months": 0, "days": 1, "hours": 0, "minutes": 0}}, "appointmentCondition": "skip", "isHybridAction": true, "hybridActionType": "wait", "convertToMultipath": false, "transitions": []}

### 4. 24 hours before reminder Email  _(email)_
- **Subject:** Welcome
- **Body:**

```

```

### 5. 24 hours before reminder SMS  _(sms)_
- **Message:**

```
Welcome
```

### 6. 24 hours before Wait  _(wait)_
- **Wait:** {"type": "appointment", "name": "24 hours before Wait", "cat": "", "appointmentStartAfter": {"when": "before", "type": "minutes", "value": 60, "distributed": {"months": 0, "days": 0, "hours": 1, "minutes": 0}}, "appointmentCondition": "skip", "isHybridAction": true, "hybridActionType": "wait", "convertToMultipath": false, "transitions": []}

### 7. 1 hour before reminder Email  _(email)_
- **Subject:** Welcome
- **Body:**

```

```

### 8. 1 hour before reminder SMS  _(sms)_
- **Message:**

```
Welcome
```
