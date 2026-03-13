"""
Contract Intelligence — text extraction, clause parsing, deviation analysis.
"""
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

MODEL_QUALITY = "claude-sonnet-4-5-20250929"
MAX_TEXT_CHARS = 12000  # safe context window slice


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
            pages = []
            for page in reader.pages:
                pages.append(page.extract_text() or "")
            return "\n".join(pages)
        except ImportError:
            logger.warning("pypdf not installed — returning raw text placeholder")
            return file_bytes.decode("utf-8", errors="replace")
    elif ext == "docx":
        try:
            import docx
            import io
            doc = docx.Document(io.BytesIO(file_bytes))
            return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        except ImportError:
            logger.warning("python-docx not installed — returning raw text placeholder")
            return file_bytes.decode("utf-8", errors="replace")
    elif ext == "txt":
        return file_bytes.decode("utf-8", errors="replace")
    else:
        return file_bytes.decode("utf-8", errors="replace")


async def extract_clauses(raw_text: str) -> list[dict]:
    """Use Groq LLM to extract structured clauses from contract text."""
    sliced = raw_text[:MAX_TEXT_CHARS]
    prompt = f"""You are a contract analysis AI. Extract all contractual clauses from the following document into a structured JSON array. For each clause identify:

{{
  "category": "payment_terms|liability|sla|termination|ip_ownership|indemnity|confidentiality|warranty|discount_pricing|data_protection|force_majeure|dispute_resolution|renewal|support_response|other",
  "clause_name": "Human-readable clause title",
  "clause_text": "Exact text or close paraphrase from the contract",
  "key_values": {{}}
}}

Extract between 5 and 20 clauses. Skip preambles, recitals, definitions, and signature blocks.
Return ONLY a valid JSON array. No markdown, no explanation, no backticks.

CONTRACT TEXT:
{sliced}"""

    try:
        resp = await _get_client().chat.completions.create(
            model=MODEL_QUALITY,
            max_tokens=3000,
            temperature=0.1,
            messages=[{"role": "user", "content": prompt}],
        )
        result = _extract_json(resp.choices[0].message.content)
        return result if isinstance(result, list) else []
    except Exception as e:
        logger.warning("extract_clauses failed: %s", e)
        return []


async def compare_contracts(
    standard_clauses: list[dict],
    prospect_clauses: list[dict],
    deal_context: dict,
) -> list[dict]:
    """Use Groq LLM to compare clause sets and generate deviations with severity + counter-suggestions."""
    deal_amount = deal_context.get("amount", 0) or 0
    region = deal_context.get("region", "Unknown")
    stage = deal_context.get("stage", "Unknown")
    deal_name = deal_context.get("name", "Unknown Deal")

    std_json = json.dumps(standard_clauses, indent=2)[:4000]
    pro_json = json.dumps(prospect_clauses, indent=2)[:4000]

    prompt = f"""You are a contract negotiation expert. Compare these two contract clause sets and identify every meaningful deviation.

The STANDARD contract is the seller's baseline.
The PROSPECT contract is the buyer's modified/redlined version.

For each deviation found, return a JSON object:
{{
  "clause_category": "payment_terms",
  "clause_name": "Payment terms",
  "standard_value": "Brief description of standard position",
  "prospect_value": "Brief description of prospect's modified position",
  "deviation_type": "modified",
  "severity": "critical",
  "risk_score": 85,
  "explanation": "Why this matters for the seller",
  "counter_suggestion": "Specific counter-proposal",
  "is_discount_related": false,
  "discount_standard_pct": null,
  "discount_prospect_pct": null
}}

deviation_type: modified | removed | added
severity: critical | major | minor | acceptable
risk_score: 0-100 (how risky this is for the seller)

Severity guide:
- critical: Deal-breaking (liability removal, unlimited indemnity, >30% discount, missing data protection)
- major: Significant risk (payment >60 days, SLA below 99%, discount 15-30%, asymmetric termination)
- minor: Manageable (small timeline shifts, minor wording changes, 5-15% discount)
- acceptable: Normal negotiation (clarifications, reasonable adjustments, <5% discount)

Context: Deal "{deal_name}", worth ${deal_amount:,}, region: {region}, stage: {stage}. Factor deal size into severity.

For discount deviations, set is_discount_related=true and populate discount_standard_pct and discount_prospect_pct as numbers.

STANDARD CLAUSES:
{std_json}

PROSPECT CLAUSES:
{pro_json}

Return ONLY a valid JSON array of deviations. No markdown, no explanation, no backticks."""

    try:
        resp = await _get_client().chat.completions.create(
            model=MODEL_QUALITY,
            max_tokens=4000,
            temperature=0.1,
            messages=[{"role": "user", "content": prompt}],
        )
        result = _extract_json(resp.choices[0].message.content)
        return result if isinstance(result, list) else []
    except Exception as e:
        logger.warning("compare_contracts failed: %s", e)
        return []
