import asyncio
import httpx
import json
import base64
import os
from dotenv import load_dotenv

load_dotenv()

# 🔥 Paste your session token here
SESSION = "PASTE_YOUR_dealiq_session_VALUE_HERE"

# 🔥 Paste any deal ID here
DEAL_ID = "PASTE_ANY_DEAL_ID_HERE"

decoded = json.loads(base64.b64decode(SESSION).decode())
access_token = decoded["access_token"]

async def test():
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"https://www.zohoapis.in/crm/v2/Deals/{DEAL_ID}/Emails",
            headers={"Authorization": f"Zoho-oauthtoken {access_token}"}
        )

        print("EMAIL STATUS:", r.status_code)
        print(json.dumps(r.json(), indent=2))

asyncio.run(test())