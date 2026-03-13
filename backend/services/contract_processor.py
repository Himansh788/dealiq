"""
Contract Intelligence — text extraction, clause parsing, deviation analysis.
"""
import asyncio
import json
import logging
import os
import re
from typing import Any

from services.ai_client import AsyncAnthropicCompat as AsyncGroq

logger = logging.getLogger(__name__)

_client: AsyncGroq | None = None

def _get_client() -> AsyncGroq:
    global _client
    if _client is None:
        _client = AsyncGroq(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _client

MODEL_QUALITY = "claude-sonnet-4-6"
MAX_TEXT_CHARS = 14000   # prospect contract text slice
MAX_STD_CHARS  = 6000    # standard clauses JSON slice
AI_TIMEOUT_S   = 70      # hard timeout per AI call — stays under 90s frontend timeout


def _extract_json(text: str) -> Any:
    clean = re.sub(r"```json\s*|\s*```", "", text).strip()
    match = re.search(r"\[.*\]|\{.*\}", clean, re.DOTALL)
    if match:
        return json.loads(match.group())
    raise ValueError(f"No JSON found in LLM response: {text[:200]}")


async def extract_text_from_bytes(file_bytes: bytes, filename: str) -> str:
    """Extract plain text from PDF or DOCX file bytes."""
    ext = filename.lower().rsplit(".", 1)[-1]
    if ext == "pdf":
        try:
            import pypdf
            import io
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except ImportError:
            raise RuntimeError("pypdf not installed. Run: pip install pypdf>=4.0")
    elif ext == "docx":
        try:
            import docx
            import io
            doc = docx.Document(io.BytesIO(file_bytes))
            return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        except ImportError:
            raise RuntimeError("python-docx not installed. Run: pip install python-docx>=1.1")
    elif ext == "txt":
        return file_bytes.decode("utf-8", errors="replace")
    else:
        return file_bytes.decode("utf-8", errors="replace")


async def extract_clauses(raw_text: str) -> list[dict]:
    """Extract structured clauses from a contract (used for standard template upload)."""
    sliced = raw_text[:MAX_TEXT_CHARS]
    prompt = f"""You are a contract analysis AI. Extract all contractual clauses from the following document.

Return a JSON array. Each item:
{{
  "category": "payment_terms|liability|sla|termination|ip_ownership|indemnity|confidentiality|warranty|discount_pricing|data_protection|force_majeure|dispute_resolution|renewal|support_response|jurisdiction|auto_renewal|audit_rights|non_compete|warranty|other",
  "clause_name": "Human-readable title",
  "clause_text": "Exact or close paraphrase of the clause",
  "key_values": {{}}
}}

Extract 5–25 clauses. Skip preamble, recitals, definitions, and signature blocks.
Return ONLY a valid JSON array. No markdown.

CONTRACT TEXT:
{sliced}"""

    try:
        resp = await asyncio.wait_for(
            _get_client().chat.completions.create(
                model=MODEL_QUALITY,
                max_tokens=3000,
                temperature=0.1,
                messages=[{"role": "user", "content": prompt}],
            ),
            timeout=AI_TIMEOUT_S,
        )
        result = _extract_json(resp.choices[0].message.content)
        return result if isinstance(result, list) else []
    except asyncio.TimeoutError:
        logger.warning("extract_clauses timed out after %ss", AI_TIMEOUT_S)
        return []
    except Exception as e:
        logger.warning("extract_clauses failed: %s", e)
        return []


async def analyze_redline(
    standard_clauses: list[dict],
    prospect_raw_text: str,
    deal_context: dict,
) -> list[dict]:
    """
    Single-pass analysis: reads the prospect's raw contract text, compares every clause
    against the standard template, and returns deviations with severity + counter-proposals.

    This replaces the old two-call pattern (extract_clauses → compare_contracts) with a
    single Claude call, cutting latency in half and avoiding timeout on prospect upload.
    """
    deal_amount = deal_context.get("amount", 0) or 0
    region      = deal_context.get("region", "Unknown")
    stage       = deal_context.get("stage", "Unknown")
    deal_name   = deal_context.get("name", "Unknown Deal")

    std_json   = json.dumps(standard_clauses, indent=2)[:MAX_STD_CHARS]
    pro_text   = prospect_raw_text[:MAX_TEXT_CHARS]

    leniency_rules = """\
Vervotech Leniency Matrix (apply when scoring severity):
- Jurisdiction / Governing Law: HIGH leniency — prospect's preferred jurisdiction is acceptable
- Communication Language: HIGH leniency — bilingual correspondence acceptable
- Auto-Renewal → Opt-in: HIGH leniency — acceptable
- Audit Rights (annual): HIGH leniency — generally acceptable
- Force Majeure (expanded): HIGH leniency — usually acceptable
- Invoice Payment Terms: MEDIUM — Net-30 standard; Net-45 acceptable; Net-60+ needs CFO approval
- Liability Cap: MEDIUM — 12-month standard; 6-month needs review; unlimited = critical
- Data Hosting Location: MEDIUM — specific region acceptable if infra supports it
- Confidentiality Period extension: MEDIUM — usually acceptable beyond 2 years
- Termination for Convenience <30 days: MEDIUM — financial risk, review needed
- Non-Compete / Exclusivity added by prospect: LOW leniency — flag as critical
- IP Ownership of custom/Vervotech-built work claimed by prospect: LOW — unacceptable
- Indemnification scope broadened: MEDIUM — needs legal review
- Uncapped SLA penalties: LOW — critical financial risk"""

    prompt = f"""You are a contract negotiation expert for Vervotech, a B2B SaaS company.

Your task: read the prospect's FULL contract text and compare it clause-by-clause against Vervotech's STANDARD CLAUSES below. Identify every meaningful deviation.

{leniency_rules}

For each deviation return a JSON object:
{{
  "clause_category": "payment_terms",
  "clause_name": "Payment terms",
  "standard_value": "One-sentence description of Vervotech's standard position",
  "prospect_value": "One-sentence description of what the prospect is asking for",
  "deviation_type": "modified | removed | added",
  "severity": "critical | major | minor | acceptable",
  "risk_score": 85,
  "explanation": "Why this matters for Vervotech — financial, legal, or operational impact",
  "counter_suggestion": "Specific counter-proposal Vervotech should offer",
  "is_discount_related": false,
  "discount_standard_pct": null,
  "discount_prospect_pct": null
}}

Severity:
- critical: deal-breaker (IP grab, unlimited liability, uncapped SLA penalties, exclusivity, >30% discount)
- major: significant risk (payment >60 days, asymmetric termination, broadened indemnity, 15–30% discount)
- minor: manageable (small shifts, 5–15% discount, minor wording)
- acceptable: normal negotiation per leniency matrix above

Deal context: "{deal_name}", ${deal_amount:,}, region: {region}, stage: {stage}.

If no deviation is found for a category, do not include it.
Return ONLY a valid JSON array. No markdown, no explanation.

--- VERVOTECH STANDARD CLAUSES (JSON) ---
{std_json}

--- PROSPECT CONTRACT TEXT ---
{pro_text}"""

    try:
        resp = await asyncio.wait_for(
            _get_client().chat.completions.create(
                model=MODEL_QUALITY,
                max_tokens=4000,
                temperature=0.1,
                messages=[{"role": "user", "content": prompt}],
            ),
            timeout=AI_TIMEOUT_S,
        )
        result = _extract_json(resp.choices[0].message.content)
        return result if isinstance(result, list) else []
    except asyncio.TimeoutError:
        logger.warning("analyze_redline timed out after %ss", AI_TIMEOUT_S)
        return []
    except Exception as e:
        logger.warning("analyze_redline failed: %s", e)
        return []


# ── Backwards-compat shim — kept so the seed path still works ─────────────────
async def compare_contracts(
    standard_clauses: list[dict],
    prospect_clauses: list[dict],
    deal_context: dict,
) -> list[dict]:
    """Legacy two-arg compare. Converts prospect_clauses back to text and delegates to analyze_redline."""
    prospect_text = "\n\n".join(
        f"{c.get('clause_name', '')}: {c.get('clause_text', '')}"
        for c in prospect_clauses
    )
    return await analyze_redline(standard_clauses, prospect_text, deal_context)
