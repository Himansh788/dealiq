"""
Email Thread Analyzer
======================
Fetches the actual email thread from Zoho and extracts real health signals:
- Buyer sentiment (positive / neutral / negative / no response)
- Objections raised (price, timing, competition, authority)
- Discount mentions (exact count from thread)
- Next steps promised but not confirmed
- Last buyer response date
- Red flags (going dark, CC'd legal, "evaluating other options")
- Green flags (asked for contract, introduced new stakeholder, set a date)
"""

from groq import AsyncGroq
import os
import json
import re
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

_client: AsyncGroq | None = None


def _get_client() -> AsyncGroq:
    global _client
    if _client is None:
        _client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))
    return _client


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
    parsed = []
    for e in raw_emails[:10]:
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
                "content": content[:500],
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
            "email_health_score": 5,
        }

    thread_text = "\n\n".join([
        f"[{e.get('direction', '?').upper()}] From: {e['from']}\n"
        f"Subject: {e['subject']}\n"
        f"Date: {e.get('sent_time', 'unknown')}\n"
        f"Content: {e['content']}"
        for e in emails
    ])

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    prompt = f"""You are a senior deal intelligence analyst reading a B2B SaaS email thread.
Extract every meaningful signal about deal health from this email thread.

Be specific — quote actual language from the emails for red flags and green flags.
Calculate buyer response time from the actual dates in the thread.

DEAL: {deal_name} | STAGE: {stage} | TODAY: {today}

EMAIL THREAD (most recent first):
{thread_text}

Return ONLY this JSON:
{{
  "buyer_sentiment": "positive|neutral|negative|no_response|unknown",
  "last_buyer_response_days": null,
  "discount_mentions": 0,
  "objections": ["specific objections raised by buyer — quote their actual language"],
  "red_flags": ["specific concerning phrases or patterns — e.g., 'Buyer used passive language: evaluating our options'"],
  "green_flags": ["specific positive signals — e.g., 'Buyer asked about contract process on [date]'"],
  "next_step_promised": "What was promised as next step, if anything — or null",
  "email_health_score": 10,
  "summary": "2-3 sentence forensic summary of what this email thread reveals about deal health — be direct"
}}"""

    try:
        resp = await _get_client().chat.completions.create(
            model=MODEL,
            max_tokens=900,
            temperature=0.1,
            messages=[{"role": "user", "content": prompt}],
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
