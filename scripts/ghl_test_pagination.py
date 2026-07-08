#!/usr/bin/env python3
"""Test GHL pagination mechanism."""
import json
import subprocess
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

GHL_KEY = os.getenv("GHL_API_KEY")
GHL_LOC = os.getenv("GHL_LOCATION_ID")
BASE_URL = "https://services.leadconnectorhq.com"

def ghl_get(path, version="2021-04-15", params=None):
    """Call GHL API via curl with headers on stdin."""
    url = BASE_URL + path
    if params:
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        url += f"?{qs}"

    cfg = f'header = "Authorization: Bearer {GHL_KEY}"\nheader = "Version: {version}"\nheader = "Accept: application/json"\n'
    try:
        r = subprocess.run(
            ["curl", "-s", "-K", "-", url],
            input=cfg,
            capture_output=True,
            text=True,
            timeout=60
        )
        return json.loads(r.stdout, strict=False) if r.stdout else None
    except Exception as e:
        print(f"Error: {e}")
        return None

# Fetch first page
print("Testing pagination...\n")
print("=" * 70)
print("PAGE 1 (offset=0)")
print("=" * 70)

resp1 = ghl_get("/conversations/search", params={"locationId": GHL_LOC, "limit": 50, "offset": 0})
print(f"\nResponse keys: {list(resp1.keys())}")

convs1 = resp1.get("conversations", [])
print(f"Conversations returned: {len(convs1)}")

if convs1:
    first_conv = convs1[0]
    last_conv = convs1[-1]

    print(f"\nFirst conversation:")
    print(f"  ID: {first_conv.get('id')}")
    print(f"  Keys: {list(first_conv.keys())[:10]}")

    print(f"\nLast conversation:")
    print(f"  ID: {last_conv.get('id')}")
    print(f"  lastMessageDate: {last_conv.get('lastMessageDate')}")
    print(f"  sort: {last_conv.get('sort')}")
    print(f"  dateAdded: {last_conv.get('dateAdded')}")

# Try offset-based pagination
print("\n" + "=" * 70)
print("PAGE 2 (offset=50)")
print("=" * 70)

resp2 = ghl_get("/conversations/search", params={"locationId": GHL_LOC, "limit": 50, "offset": 50})
convs2 = resp2.get("conversations", [])
print(f"Conversations returned: {len(convs2)}")

if convs2:
    first_conv2 = convs2[0]
    print(f"First conversation on page 2: {first_conv2.get('id')}")
    if convs1:
        print(f"First conversation on page 1: {convs1[0].get('id')}")
        print(f"Same? {convs2[0].get('id') == convs1[0].get('id')}")

# Try cursor-based with lastMessageDate
print("\n" + "=" * 70)
print("Testing cursor-based with lastMessageDate")
print("=" * 70)

if convs1:
    last_conv = convs1[-1]
    last_date = last_conv.get('lastMessageDate')
    print(f"Last conversation date from page 1: {last_date}")

    resp3 = ghl_get("/conversations/search", params={
        "locationId": GHL_LOC,
        "limit": 50,
        "startAfterDate": last_date
    })
    convs3 = resp3.get("conversations", [])
    print(f"Conversations with startAfterDate: {len(convs3)}")
    if convs3:
        print(f"First ID: {convs3[0].get('id')}")

# Try other cursor params
print("\n" + "=" * 70)
print("Testing other potential cursor params")
print("=" * 70)

for param_name in ["startAfter", "after", "page", "pageNumber", "skip"]:
    resp = ghl_get("/conversations/search", params={
        "locationId": GHL_LOC,
        "limit": 50,
        param_name: "1"
    })
    if resp and resp.get("conversations"):
        print(f"  {param_name}: returned {len(resp.get('conversations', []))} conversations")
