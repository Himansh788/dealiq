"""
Transcript Analyzer — Conversation Quality & Coaching Metrics
=============================================================
Two-layer architecture:

Layer 1 — Python (fast, free, deterministic):
  talk_ratio, question counts, filler words, longest monologue

Layer 2 — Groq (single prompt):
  topic_segments, key_moments, coaching_tips, overall_score

Speaker detection: parses "Speaker: text" labels. Falls back to
first-speaker-is-rep heuristic when role words are absent.
"""

from groq import AsyncGroq
import os
import json
import re
from typing import Any
from datetime import datetime, timezone

from models.coaching_schemas import ConversationMetrics, TopicSegment, KeyMoment

_client: AsyncGroq | None = None
MODEL = "llama-3.3-70b-versatile"
WORDS_PER_MINUTE = 130  # average speaking rate used for duration estimates

REP_ROLE_WORDS    = {"rep", "sales", "ae", "sdr", "bdr", "se", "csm", "executive", "manager", "account"}
PROSPECT_ROLE_WORDS = {"prospect", "customer", "buyer", "client"}

FILLER_PATTERNS: list[tuple[str, str]] = [
    ("um",        r"\bum+\b"),
    ("uh",        r"\buh+\b"),
    ("you know",  r"\byou know\b"),
    ("basically", r"\bbasically\b"),
    ("actually",  r"\bactually\b"),
    ("right",     r"\bright\b"),
    ("like",      r"\blike\b"),
]

# Matches "Speaker Name: text" — 1-3 word speaker label
SPEAKER_RE  = re.compile(r"^([A-Za-z][A-Za-z]{0,14}(?:\s[A-Za-z]{1,14}){0,2}):\s+(.*)")
METADATA_RE = re.compile(r"^\[.*\]$")
TIMESTAMP_RE = re.compile(r"^\[\d{2}:\d{2}(?::\d{2})?\]$")


def _get_client() -> AsyncGroq:
    global _client
    if _client is None:
        _client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))
    return _client


def _extract_json(text: str) -> dict[str, Any]:
    clean = re.sub(r"```json\s*|\s*```", "", text).strip()
    match = re.search(r"\{.*\}", clean, re.DOTALL)
    if match:
        return json.loads(match.group())
    raise ValueError(f"No JSON found in response: {text[:200]}")


# ── Parsing ───────────────────────────────────────────────────────────────────

def _parse_turns(transcript: str) -> list[dict[str, Any]]:
    """
    Parse transcript into turns: [{speaker, text, word_count}].
    Handles multi-line speaker turns. Skips blank lines and metadata.
    """
    turns: list[dict[str, Any]] = []
    current_speaker: str | None = None
    current_lines: list[str] = []

    def _flush():
        if current_speaker and current_lines:
            text = " ".join(current_lines).strip()
            if text:
                turns.append({
                    "speaker":    current_speaker,
                    "text":       text,
                    "word_count": len(text.split()),
                })

    for line in transcript.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if METADATA_RE.match(stripped) or TIMESTAMP_RE.match(stripped):
            continue

        m = SPEAKER_RE.match(stripped)
        if m:
            _flush()
            current_speaker = m.group(1).strip()
            rest = m.group(2).strip()
            current_lines = [rest] if rest else []
        elif current_speaker:
            current_lines.append(stripped)

    _flush()
    return turns


def _identify_speakers(
    turns: list[dict],
    rep_name_hint: str | None = None,
) -> tuple[str | None, str | None]:
    """
    Return (rep_label, prospect_label).
    Priority: role-word match → rep_name_hint → first-speaker fallback.
    """
    # ordered unique speakers
    speakers = list(dict.fromkeys(t["speaker"] for t in turns))
    rep_label: str | None = None
    prospect_label: str | None = None

    for spk in speakers:
        words = set(spk.lower().split())
        if words & REP_ROLE_WORDS and not rep_label:
            rep_label = spk
        elif words & PROSPECT_ROLE_WORDS and not prospect_label:
            prospect_label = spk

    if rep_name_hint and not rep_label:
        hint = rep_name_hint.lower()
        for spk in speakers:
            if hint in spk.lower():
                rep_label = spk
                break

    # fallback: first speaker = rep
    if not rep_label and speakers:
        rep_label = speakers[0]
    if not prospect_label:
        others = [s for s in speakers if s != rep_label]
        prospect_label = others[0] if others else None

    return rep_label, prospect_label


# ── Python metrics ────────────────────────────────────────────────────────────

def _count_questions(text: str) -> int:
    return len(re.findall(r"\?", text))


def _count_fillers(text: str) -> tuple[int, dict[str, int]]:
    text_lower = text.lower()
    breakdown: dict[str, int] = {}
    for name, pattern in FILLER_PATTERNS:
        count = len(re.findall(pattern, text_lower))
        if count:
            breakdown[name] = count
    return sum(breakdown.values()), breakdown


def _longest_monologue_seconds(turns: list[dict], rep_label: str | None) -> int:
    """Longest consecutive rep-only speech block (uninterrupted by prospect)."""
    if not rep_label:
        return 0
    max_words = current_words = 0
    for turn in turns:
        if turn["speaker"] == rep_label:
            current_words += turn["word_count"]
        else:
            max_words = max(max_words, current_words)
            current_words = 0
    max_words = max(max_words, current_words)
    return int((max_words / WORDS_PER_MINUTE) * 60)


def _compute_python_metrics(
    turns: list[dict],
    rep_label: str | None,
    prospect_label: str | None,
) -> dict[str, Any]:
    rep_turns      = [t for t in turns if t["speaker"] == rep_label]
    prospect_turns = [t for t in turns if t["speaker"] == prospect_label]

    rep_words      = sum(t["word_count"] for t in rep_turns)
    prospect_words = sum(t["word_count"] for t in prospect_turns)
    total_words    = rep_words + prospect_words or 1  # guard div/0

    rep_ratio      = round((rep_words / total_words) * 100, 1)
    rep_text       = " ".join(t["text"] for t in rep_turns)
    prospect_text  = " ".join(t["text"] for t in prospect_turns)

    filler_count, filler_breakdown = _count_fillers(rep_text)
    rep_speaking_minutes = (rep_words / WORDS_PER_MINUTE) or 1
    filler_per_min = round(filler_count / rep_speaking_minutes, 2)

    return {
        "rep_word_count":            rep_words,
        "prospect_word_count":       prospect_words,
        "talk_ratio_rep":            rep_ratio,
        "talk_ratio_prospect":       round(100 - rep_ratio, 1),
        "estimated_duration_minutes": round(total_words / WORDS_PER_MINUTE, 1),
        "longest_monologue_seconds": _longest_monologue_seconds(turns, rep_label),
        "question_count_rep":        _count_questions(rep_text),
        "question_count_prospect":   _count_questions(prospect_text),
        "filler_word_count":         filler_count,
        "filler_words_per_minute":   filler_per_min,
        "filler_breakdown":          filler_breakdown,
    }


# ── Groq prompt ───────────────────────────────────────────────────────────────

COACHING_SYSTEM = """You are a world-class B2B sales coaching analyst.
You analyse sales call transcripts and return structured, actionable coaching feedback.

Return ONLY valid JSON — no markdown fences, no text outside the JSON object:
{
  "topic_segments": [
    {"topic": "...", "start_position_pct": 0, "duration_estimate": "~N min"}
  ],
  "key_moments": [
    {"type": "objection|commitment|question|pricing|competitor", "text": "verbatim quote max 20 words", "position_pct": 0}
  ],
  "coaching_tips": ["specific actionable tip 1", "tip 2", "tip 3"],
  "overall_score": 0,
  "score_rationale": "1-2 sentence explanation referencing specific metrics and moments from the call"
}

Rules:
- topic_segments: 3-6 segments covering the full call, start_position_pct 0-100
- key_moments: max 8, only the most impactful moments, position_pct 0-100
- coaching_tips: 3-5 bullets. Be specific — reference actual quotes or moments. Include at least 1 positive. Compare metrics to benchmarks where relevant.
- overall_score: 0-100. Weight: talk ratio (25%), question count (20%), longest monologue (20%), filler rate (15%), conversation quality (20%). 70+ = strong call, 40-69 = needs work, <40 = serious issues.
- score_rationale: translate the numbers into a human-readable verdict — don't just list the metrics."""

COACHING_PROMPT = """COMPUTED METRICS:
- Rep talk ratio: {talk_ratio_rep}% (benchmark: 43%)
- Prospect talk ratio: {talk_ratio_prospect}%
- Rep questions asked: {question_count_rep} (benchmark: 11–14)
- Prospect questions asked: {question_count_prospect}
- Longest rep monologue: {longest_monologue_seconds}s (benchmark: <76s)
- Filler words (rep): {filler_word_count} total at {filler_words_per_minute}/min of speaking time (benchmark: <5/min)
- Filler breakdown: {filler_breakdown}
- Estimated call duration: {estimated_duration_minutes} min
- Rep speaker label: "{rep_label}"
- Prospect speaker label: "{prospect_label}"

TRANSCRIPT:
{transcript}

Analyse and return the JSON coaching report."""


# ── Analyzer class ────────────────────────────────────────────────────────────

class TranscriptAnalyzer:

    async def analyze_conversation(
        self,
        transcript: str,
        rep_name: str | None = None,
    ) -> ConversationMetrics:
        turns = _parse_turns(transcript)
        rep_label, prospect_label = _identify_speakers(turns, rep_name)
        pm = _compute_python_metrics(turns, rep_label, prospect_label)

        prompt = COACHING_PROMPT.format(
            **pm,
            rep_label=rep_label or "Unknown",
            prospect_label=prospect_label or "Unknown",
            transcript=transcript[:8000],
        )

        response = await _get_client().chat.completions.create(
            model=MODEL,
            max_tokens=1800,
            temperature=0.2,
            messages=[
                {"role": "system", "content": COACHING_SYSTEM},
                {"role": "user",   "content": prompt},
            ],
        )

        raw = response.choices[0].message.content
        try:
            ai = _extract_json(raw)
        except (ValueError, json.JSONDecodeError):
            ai = {
                "topic_segments":  [],
                "key_moments":     [],
                "coaching_tips":   ["AI analysis unavailable — could not parse response. Python metrics above are accurate."],
                "overall_score":   50,
                "score_rationale": "AI analysis unavailable.",
            }

        topic_segments = [
            TopicSegment(
                topic=s.get("topic", ""),
                start_position_pct=float(s.get("start_position_pct", 0)),
                duration_estimate=s.get("duration_estimate", ""),
            )
            for s in ai.get("topic_segments", [])
        ]

        key_moments = [
            KeyMoment(
                type=m.get("type", "question"),
                text=m.get("text", ""),
                position_pct=float(m.get("position_pct", 0)),
            )
            for m in ai.get("key_moments", [])
        ]

        return ConversationMetrics(
            rep_label=rep_label,
            prospect_label=prospect_label,
            speakers_detected=list(dict.fromkeys(t["speaker"] for t in turns)),
            **pm,
            topic_segments=topic_segments,
            key_moments=key_moments,
            coaching_tips=ai.get("coaching_tips", []),
            overall_score=int(ai.get("overall_score", 50)),
            score_rationale=ai.get("score_rationale", ""),
            analysed_at=datetime.now(timezone.utc).isoformat(),
        )


analyzer_service = TranscriptAnalyzer()
