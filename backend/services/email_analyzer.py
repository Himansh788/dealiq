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

from services.ai_client import AsyncAnthropicCompat as AsyncGroq
import os
import json
import re
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

_client: AsyncGroq | None = None


def _get_client() -> AsyncGroq:
    global _client
    if _client is None:
        _client = AsyncGroq(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _client


MODEL = "claude-sonnet-4-5-20250929"


def _strip_html(text: str) -> str:
    """Strip HTML tags and decode common entities to plain text."""
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    text = text.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
    return re.sub(r"\s+", " ", text).strip()


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

        # Prefer plain-text summary over raw HTML content
        raw_content = (
            e.get("summary") or          # Zoho plain-text preview — best option
            e.get("content") or          # may be HTML
            e.get("Content") or
            e.get("description") or
            e.get("mail_description") or
            ""
        )
        content = _strip_html(raw_content)

        sent_time = (
            e.get("sent_time") or e.get("date") or
            e.get("Date") or e.get("Created_Time") or ""
        )

        from_field = e.get("from") or e.get("From")
        if isinstance(from_field, dict):
            from_addr = from_field.get("user_name") or from_field.get("email") or "Unknown"
        else:
            from_addr = str(from_field) if from_field else "Unknown"

        # Zoho sets type = "sent" | "received" directly
        direction = e.get("type") or e.get("direction") or (
            "sent" if e.get("source") == "CRM" else "received"
        )

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
            messages=[
                {"role": "system", "content": "You are a B2B sales email analyst. Return ONLY valid JSON — no markdown, no explanation outside the JSON object."},
                {"role": "user", "content": prompt},
            ],
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
