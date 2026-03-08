"""
Smart Trackers
==============
Detects CONCEPTS in sales call transcripts — not keywords but underlying intent.
Each tracker has a concept description that
tells the LLM what to look for semantically, so "Is that your best price?" fires
the discount_pressure tracker even though "discount" was never said.

All 6 default trackers + support for custom trackers created at runtime.
Single Groq prompt per analysis — all trackers evaluated in one call.
"""

from groq import AsyncGroq
import os
import json
import re
from typing import Any

from models.tracker_schemas import TrackerMatch, TrackerResponse

_client: AsyncGroq | None = None

MODEL = "llama-3.3-70b-versatile"


def _get_client() -> AsyncGroq:
    global _client
    if _client is None:
        _client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))
    return _client


# ── Default tracker definitions ───────────────────────────────────────────────

DEFAULT_TRACKERS: list[dict[str, str]] = [
    {
        "id": "discount_pressure",
        "name": "Discount Pressure",
        "concept_description": (
            "The buyer is applying pressure on price — directly or indirectly. "
            "Includes: asking for a discount, asking if the price is negotiable, "
            "comparing price unfavourably to a competitor, asking 'is that your best price?', "
            "'can you do better?', 'what flexibility do you have?', or any signal that "
            "the buyer wants a lower price even if the word 'discount' is never used."
        ),
        "severity": "warning",
    },
    {
        "id": "competitor_mention",
        "name": "Competitor Mention",
        "concept_description": (
            "A competing product, vendor, or alternative solution is referenced. "
            "Includes: naming a specific competitor, saying 'another vendor', "
            "'the other tool we're evaluating', 'our current solution', "
            "or any reference that implies the buyer is considering alternatives."
        ),
        "severity": "warning",
    },
    {
        "id": "timeline_urgency",
        "name": "Timeline Urgency",
        "concept_description": (
            "There is urgency or a hard deadline driving the buyer's decision. "
            "Includes: a board meeting, quarter-end deadline, contract renewal, "
            "executive mandate, launch date, budget freeze, or any forcing function "
            "that makes the buyer need a solution by a specific time."
        ),
        "severity": "info",
    },
    {
        "id": "budget_objection",
        "name": "Budget Objection",
        "concept_description": (
            "The buyer raises concern about cost, budget, or financial fit. "
            "Includes: 'this is over our budget', 'we didn't expect it to be this expensive', "
            "'we have limited budget', 'need to get budget approved', "
            "or any signal that money is a blocker or constraint — even indirect ones."
        ),
        "severity": "critical",
    },
    {
        "id": "decision_maker_absent",
        "name": "Decision Maker Absent",
        "concept_description": (
            "The person on the call does not have final authority to buy and "
            "needs someone else's approval. Includes: 'I need to run this by my CFO/CEO/boss', "
            "'my manager will need to sign off', 'I'm not the final decision maker', "
            "'I'll need to loop in legal/procurement', or any reference to an approver "
            "who is not present on this call."
        ),
        "severity": "critical",
    },
    {
        "id": "next_steps_vague",
        "name": "Next Steps Vague",
        "concept_description": (
            "The conversation ends or a meeting closes without a clear, concrete next step "
            "that has an owner, a specific action, and ideally a date. "
            "Includes: vague closings like 'we'll be in touch', 'let's reconnect soon', "
            "'I'll think about it and get back to you', or any moment where the path "
            "forward is undefined or non-committal."
        ),
        "severity": "warning",
    },
]

# ── In-memory custom tracker store (keyed by id) ──────────────────────────────

_custom_trackers: dict[str, dict[str, str]] = {}


# ── Prompt ────────────────────────────────────────────────────────────────────

TRACKER_SYSTEM = """You are a sales call intelligence analyst. Your job is to detect CONCEPTS
in sales call transcripts — not exact keywords but the underlying intent or situation.

You will receive a transcript and a list of tracker definitions. Each tracker has an id,
name, and a concept_description that explains the IDEA to look for regardless of the
exact words used.

For every tracker, scan the entire transcript and identify every moment where that concept
appears. A single statement can match multiple trackers.

Return ONLY valid JSON with no markdown fences and no text outside the JSON object:
{
  "matches": [
    {
      "tracker_id": "<exact id from the tracker list>",
      "matched_text": "<the verbatim phrase or sentence from the transcript that triggered this>",
      "timestamp_hint": "<timestamp like [00:12:34] if present in transcript, otherwise null>",
      "confidence_score": <float between 0.0 and 1.0>,
      "context_snippet": "<1 sentence explaining WHY this phrase matches the concept>"
    }
  ]
}

Rules:
- Only include matches with confidence_score >= 0.6
- Use the exact tracker_id values provided — do not invent new ones
- matched_text must be a verbatim excerpt from the transcript, not a paraphrase
- If a tracker has no matches in the transcript, do not include any entry for it
- If the transcript has no matches at all, return {"matches": []}"""


def _build_user_prompt(transcript: str, trackers: list[dict]) -> str:
    tracker_block = "\n".join(
        f'- id: "{t["id"]}"\n  name: "{t["name"]}"\n  concept: {t["concept_description"]}'
        for t in trackers
    )
    return (
        f"TRACKERS TO DETECT:\n{tracker_block}\n\n"
        f"TRANSCRIPT:\n{transcript[:10000]}"
    )


def _extract_json(text: str) -> dict[str, Any]:
    clean = re.sub(r"```json\s*|\s*```", "", text).strip()
    match = re.search(r"\{.*\}", clean, re.DOTALL)
    if match:
        candidate = match.group()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            # Model truncated mid-output — salvage complete match objects before the cut
            complete_matches = re.findall(
                r'\{\s*"tracker_id".*?"context_snippet"\s*:\s*"[^"]*"\s*\}',
                candidate,
                re.DOTALL,
            )
            salvaged = []
            for m in complete_matches:
                try:
                    salvaged.append(json.loads(m))
                except json.JSONDecodeError:
                    continue
            return {"matches": salvaged}
    raise ValueError(f"No JSON found in response: {text[:200]}")


# ── SmartTracker class ─────────────────────────────────────────────────────────

class SmartTracker:

    def get_all_trackers(self) -> list[TrackerResponse]:
        result = [
            TrackerResponse(**t, is_default=True)
            for t in DEFAULT_TRACKERS
        ]
        result += [
            TrackerResponse(**t, is_default=False)
            for t in _custom_trackers.values()
        ]
        return result

    def add_custom_tracker(self, tracker_id: str, name: str, concept_description: str, severity: str) -> TrackerResponse:
        entry = {
            "id": tracker_id,
            "name": name,
            "concept_description": concept_description,
            "severity": severity,
        }
        _custom_trackers[tracker_id] = entry
        return TrackerResponse(**entry, is_default=False)

    def _resolve_trackers(self, tracker_ids: list[str] | None) -> list[dict]:
        """Return tracker dicts to run — all if tracker_ids is None."""
        all_defs = {t["id"]: t for t in DEFAULT_TRACKERS}
        all_defs.update(_custom_trackers)

        if tracker_ids is None:
            return list(all_defs.values())

        return [all_defs[tid] for tid in tracker_ids if tid in all_defs]

    async def analyze_transcript(
        self,
        transcript: str,
        tracker_ids: list[str] | None = None,
    ) -> list[TrackerMatch]:
        trackers = self._resolve_trackers(tracker_ids)
        if not trackers:
            return []

        # Build a lookup so we can fill in tracker_name and severity from the match
        tracker_meta = {t["id"]: t for t in trackers}

        prompt = _build_user_prompt(transcript, trackers)

        response = await _get_client().chat.completions.create(
            model=MODEL,
            max_tokens=4000,
            temperature=0.1,
            messages=[
                {"role": "system", "content": TRACKER_SYSTEM},
                {"role": "user", "content": prompt},
            ],
        )

        raw = response.choices[0].message.content
        parsed = _extract_json(raw)

        matches: list[TrackerMatch] = []
        for item in parsed.get("matches", []):
            tid = item.get("tracker_id", "")
            meta = tracker_meta.get(tid)
            if meta is None:
                continue   # model hallucinated an unknown tracker id — skip
            matches.append(TrackerMatch(
                tracker_id=tid,
                tracker_name=meta["name"],
                severity=meta["severity"],
                matched_text=item.get("matched_text", ""),
                timestamp_hint=item.get("timestamp_hint"),
                confidence_score=float(item.get("confidence_score", 0.0)),
                context_snippet=item.get("context_snippet", ""),
            ))

        return matches


# Module-level singleton — import and use directly in the router
tracker_service = SmartTracker()
