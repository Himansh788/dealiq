"""
Email Thread Analyzer
======================
Fetches the actual email thread from Zoho and uses Groq to extract
real health signals from the content:

- Buyer sentiment (positive / neutral / negative / no response)
- Objections raised (price, timing, competition, authority)
- Discount mentions (exact count from thread)
- Next steps promised but not confirmed
- Last buyer response date (actual, not CRM approximation)
- Red flags (going dark, CC'd legal, "we're evaluating other options")
- Green flags (asked for contract, introduced new stakeholder, set a date)

This feeds directly into the health score breakdown as a new signal
AND enriches the existing signals with real data instead of approximations.
"""

from groq import Groq
import os
import json
import re
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

client = Groq(api_key=os.getenv("GROQ_API_KEY", ""))
MODEL = "llama-3.3-70b-versatile"


def _extract_json(text: str) -> Any:
    clean = re.sub(r"```json\s*|\s*```", "", text).strip()
    try:
        return json.loads(clean)
    except Exception:
        match = re.search(r"\{.*\}", clean, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise ValueError(f"No JSON found: {text[:200]}")


def parse_emails(raw_emails: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Normalise Zoho email records into a clean format for the AI prompt.
    Zoho emails can come in different shapes depending on API version.
    """
    parsed = []
    for e in raw_emails[:10]:  # cap at 10 most recent
        # Try different Zoho email field names
        subject = (
            e.get("subject") or e.get("Subject") or
            e.get("mail_label") or "No subject"
        )
        content = (
            e.get("content") or e.get("Content") or
            e.get("description") or e.get("summary") or ""
        )
        sent_time = (
            e.get("date") or e.get("Date") or
            e.get("sent_time") or e.get("Created_Time") or ""
        )
        from_addr = (
            e.get("from", {}).get("user_name") if isinstance(e.get("from"), dict)
            else e.get("from") or e.get("From") or "Unknown"
        )
        direction = e.get("type") or ("sent" if "rep" in str(from_addr).lower() else "received")

        if subject or content:
            parsed.append({
                "subject": subject[:100],
                "content": content[:500],  # cap content per email
                "sent_time": sent_time,
                "from": str(from_addr)[:60],
                "direction": direction,
            })

    return parsed


async def analyze_email_thread(
    deal_name: str,
    stage: str,
    emails: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Send the email thread to Groq and get structured health signals back.
    Returns a dict with extracted signals and an AI-written summary.
    """
    if not emails:
        return {
            "generated": False,
            "reason": "no_emails",
            "summary": "No email thread found for this deal.",
            "buyer_sentiment": "unknown",
            "last_buyer_response_days": None,
            "discount_mentions": 0,
            "objections": [],
            "red_flags": [],
            "green_flags": [],
            "next_step_promised": None,
            "email_health_score": 5,  # neutral out of 20
        }

    # Build email thread text for the prompt
    thread_text = "\n\n".join([
        f"[{e.get('direction', '?').upper()}] From: {e['from']}\n"
        f"Subject: {e['subject']}\n"
        f"Date: {e.get('sent_time', 'unknown')}\n"
        f"Content: {e['content']}"
        for e in emails
    ])

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    prompt = f"""You are a sales intelligence analyst reading an email thread for a B2B SaaS deal.

DEAL: {deal_name}
STAGE: {stage}
TODAY: {today}

EMAIL THREAD (most recent first):
{thread_text}

Analyse this email thread and extract health signals. Respond ONLY with this JSON:
{{
  "buyer_sentiment": "positive" | "neutral" | "negative" | "no_response" | "unknown",
  "last_buyer_response_days": <integer days since last buyer email, or null if unknown>,
  "discount_mentions": <count of times discount/price reduction mentioned in thread>,
  "objections": ["list of specific objections raised by buyer, e.g. 'price too high', 'need board approval'"],
  "red_flags": ["specific concerning phrases or patterns, e.g. 'buyer went silent after pricing email'"],
  "green_flags": ["positive signals, e.g. 'buyer asked for contract template', 'introduced CFO to thread'"],
  "next_step_promised": "description of any next step promised in emails but not yet confirmed, or null",
  "email_health_score": <integer 0-20 based on overall email thread health>,
  "summary": "2-3 sentence summary of what the email thread tells us about this deal's health and likely outcome"
}}

Be specific. Use actual content from the emails. Do not make things up."""

    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=800,
        )
        result = _extract_json(resp.choices[0].message.content)
        result["generated"] = True
        result["email_count"] = len(emails)
        return result
    except Exception as e:
        return {
            "generated": False,
            "reason": str(e)[:100],
            "summary": "Email analysis unavailable.",
            "buyer_sentiment": "unknown",
            "last_buyer_response_days": None,
            "discount_mentions": 0,
            "objections": [],
            "red_flags": [],
            "green_flags": [],
            "next_step_promised": None,
            "email_health_score": 5,
        }
