# GHL Workflow — Tag "Agent/Wholesaler">> send text/email

- **Status:** published
- **Version:** 4
- **Created:** 2025-05-13T18:08:11.790Z
- **Updated:** 2025-05-13T18:18:13.362Z
- **Trigger data file:** `location/SLq7B2pldVzfQLKjGpvw/workflow-triggers/b1dc85ce-f80f-4189-bde6-ef38c3aa89d2/3` (triggers stored separately in Firebase; see raw fileUrl)

## Steps (workflowData.templates)

### 0. Email  _(email)_
- **Subject:** Do you have anything in my buy box?
- **Body:**

```
Hi {{contact.first_name}}, this is Brian Norton. How's your day going? Do you have anything cooking? My buy box is 3/2+, 1500sqft+, with a price range of 350-450k.

The ARV needs to be 200k above purchase price or more. Here are the counties I'm interested in: Cobb, Cherokee, Bartow, Fulton (Alpharetta, Roswell, John's Creek).

Looking forward to hearing from you.
Thank you!

Regards,
{{location_owner.first_name}} {{location_owner.last_name}}
```

### 1. SMS  _(sms)_
- **Message:**

```
Hi {{contact.first_name}}, this is Brian Norton. How's your day going? Do you have anything cooking? My buy box is 3/2+, 1500sqft+, with a price range of 350-450k. The ARV needs to be 200k above purchase price or more. Here are the counties I'm interested in: Cobb, Cherokee, Bartow, Fulton (Alpharetta, Roswell, John's Creek). Looking forward to hearing from you. Thank you!
```
