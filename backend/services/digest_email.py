"""
Digest Email Service — sends daily digest via Resend.
Falls back gracefully if RESEND_API_KEY is not set.
"""

import os
import logging
from datetime import date
from typing import Optional

logger = logging.getLogger(__name__)

_APP_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

TASK_TYPE_ICONS = {
    "email":      "✉️",
    "call":       "📞",
    "whatsapp":   "💬",
    "case_study": "📋",
    "meeting":    "📅",
    "contract":   "📝",
}


def _build_html(digest: dict, rep_name: str = "") -> str:
    today_str = date.today().strftime("%A, %B %-d")
    tasks = digest.get("tasks", [])
    untouched = digest.get("untouched_deals", [])
    progress = digest.get("progress", {})

    tasks_html = ""
    for t in tasks:
        icon = TASK_TYPE_ICONS.get(t["task_type"], "•")
        type_label = t.get("task_type_label", t["task_type"])
        amount_str = f" · {t['amount_fmt']}" if t.get("amount_fmt") else ""
        tasks_html += f"""
        <tr>
          <td style="padding:12px 0;border-bottom:1px solid #1e2a3a;">
            <span style="font-size:18px;margin-right:10px;">{icon}</span>
            <strong style="color:#e2e8f0;font-size:13px;">{type_label}</strong>
            <span style="color:#64748b;font-size:11px;margin-left:8px;">{t.get('company','')}{amount_str}</span><br>
            <span style="color:#94a3b8;font-size:13px;padding-left:28px;">{t['task_text']}</span>
          </td>
        </tr>"""

    untouched_html = ""
    for u in untouched:
        amount_str = u.get("amount_fmt", "")
        untouched_html += f"""
        <tr>
          <td style="padding:10px 0;border-bottom:1px solid #1e2a3a;">
            <strong style="color:#e2e8f0;font-size:13px;">{u['deal_name']}</strong>
            <span style="color:#64748b;font-size:11px;margin-left:8px;">{u.get('company','')} · {u.get('stage','')} · {amount_str}</span><br>
            <span style="color:#ef4444;font-size:12px;">{u['days_since_contact']} days silent</span>
            <span style="color:#64748b;font-size:12px;margin-left:8px;">— {u['suggested_action']}</span>
          </td>
        </tr>"""

    greeting = f"Hi {rep_name}," if rep_name else "Hi,"

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#0f1923;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#0f1923;padding:32px 0;">
    <tr><td align="center">
      <table width="580" cellpadding="0" cellspacing="0" style="background:#1a2332;border-radius:12px;overflow:hidden;border:1px solid #2d3b4e;">
        <!-- Header -->
        <tr>
          <td style="background:#020887;padding:24px 32px;">
            <p style="margin:0;color:#93c5fd;font-size:11px;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;">DealIQ · Daily Digest</p>
            <h1 style="margin:4px 0 0;color:#ffffff;font-size:22px;font-weight:700;">{today_str}</h1>
            <p style="margin:6px 0 0;color:#93c5fd;font-size:13px;">{progress.get('completed',0)} of {progress.get('total',0)} tasks completed</p>
          </td>
        </tr>

        <!-- Body -->
        <tr><td style="padding:28px 32px;">
          <p style="margin:0 0 20px;color:#94a3b8;font-size:14px;">{greeting} Here's your focus for today.</p>

          <!-- Tasks -->
          <h2 style="margin:0 0 12px;color:#e2e8f0;font-size:14px;font-weight:700;letter-spacing:0.04em;text-transform:uppercase;">Today's Tasks</h2>
          <table width="100%" cellpadding="0" cellspacing="0">
            {tasks_html}
          </table>

          <!-- Untouched Deals -->
          <h2 style="margin:28px 0 12px;color:#e2e8f0;font-size:14px;font-weight:700;letter-spacing:0.04em;text-transform:uppercase;">Deals needing attention — 30+ days silent</h2>
          <table width="100%" cellpadding="0" cellspacing="0">
            {untouched_html}
          </table>

          <!-- CTA -->
          <div style="text-align:center;margin-top:32px;">
            <a href="{_APP_URL}/digest" style="display:inline-block;background:#020887;color:#ffffff;text-decoration:none;font-size:14px;font-weight:600;padding:12px 28px;border-radius:8px;">Open DealIQ</a>
          </div>
        </td></tr>

        <!-- Footer -->
        <tr>
          <td style="padding:16px 32px;border-top:1px solid #2d3b4e;">
            <p style="margin:0;color:#475569;font-size:11px;text-align:center;">
              DealIQ Daily Digest · <a href="{_APP_URL}/settings" style="color:#475569;">Manage preferences</a>
            </p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


async def send_digest_email(to_email: str, digest: dict, rep_name: str = "") -> bool:
    """Send the daily digest email via Resend. Returns True on success."""
    api_key = os.getenv("RESEND_API_KEY", "")
    from_email = os.getenv("DIGEST_FROM_EMAIL", "DealIQ <onboarding@resend.dev>")

    if not api_key:
        logger.warning("RESEND_API_KEY not set — skipping digest email to %s", to_email)
        return False

    try:
        import httpx
        today_str = date.today().strftime("%A, %B %-d")
        payload = {
            "from": from_email,
            "to": [to_email],
            "subject": f"Your DealIQ digest — {today_str}",
            "html": _build_html(digest, rep_name),
        }
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        if resp.status_code in (200, 201):
            logger.info("Digest email sent to %s (id=%s)", to_email, resp.json().get("id"))
            return True
        logger.error("Resend error %s — from=%s to=%s body=%s", resp.status_code, from_email, to_email, resp.text)
        return False
    except Exception as e:
        logger.exception("Failed to send digest email to %s: %s", to_email, e)
        return False
