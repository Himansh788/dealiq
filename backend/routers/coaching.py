from fastapi import APIRouter, HTTPException

from models.coaching_schemas import (
    TranscriptAnalysisRequest,
    ConversationMetrics,
    CoachingBenchmarks,
)
from services.transcript_analyzer import analyzer_service
from services.demo_data import COACHING_DEMO_TRANSCRIPT

router = APIRouter()

BENCHMARKS = CoachingBenchmarks(
    ideal_talk_ratio_rep=43.0,
    ideal_talk_ratio_rep_label="43% — top performers talk less and listen more (Google, 2021)",
    ideal_question_count_min=11,
    ideal_question_count_max=14,
    ideal_longest_monologue_seconds=76,
    filler_threshold_per_minute=5.0,
    source="Google Research — The Science of the Perfect Sales Call (2021)",
    notes=[
        "Top reps ask 21.6% more questions than average reps",
        "Best calls feature 4 pricing discussions, not just one",
        "Calls where reps name competitors close 24% less often — let the prospect raise it",
        "Question clusters (3+ in a row) reduce close rates — space them out",
        "Ideal question-to-answer ratio: roughly 1 question per 8–10 minutes of call time",
    ],
)


@router.post("/analyze", response_model=ConversationMetrics)
async def analyze_transcript(body: TranscriptAnalysisRequest):
    """
    Full transcript analysis — talk ratio, question counts, filler words,
    monologue length, topic segments, key moments, and coaching tips.
    """
    if not body.transcript.strip():
        raise HTTPException(status_code=422, detail="transcript must not be empty")
    if len(body.transcript.split()) < 50:
        raise HTTPException(status_code=422, detail="transcript too short for meaningful analysis (minimum ~50 words)")
    try:
        return await analyzer_service.analyze_conversation(
            transcript=body.transcript,
            rep_name=body.rep_name,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@router.get("/analyze/demo", response_model=ConversationMetrics)
async def demo_analysis():
    """Demo coaching analysis — no auth required."""
    try:
        return await analyzer_service.analyze_conversation(COACHING_DEMO_TRANSCRIPT)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Demo analysis failed: {str(e)}")


@router.get("/benchmarks", response_model=CoachingBenchmarks)
async def get_benchmarks():
    """Return Vervotech-research benchmarks for conversation quality."""
    return BENCHMARKS
