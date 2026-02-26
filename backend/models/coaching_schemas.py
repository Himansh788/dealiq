from pydantic import BaseModel
from typing import Optional, List, Dict


class TopicSegment(BaseModel):
    topic: str
    start_position_pct: float   # 0-100 through the call
    duration_estimate: str      # e.g. "~4 min"


class KeyMoment(BaseModel):
    type: str          # objection | commitment | question | pricing | competitor
    text: str          # verbatim quote (max ~20 words)
    position_pct: float  # 0-100 through the call


class ConversationMetrics(BaseModel):
    # Speaker detection
    rep_label: Optional[str] = None
    prospect_label: Optional[str] = None
    speakers_detected: List[str] = []

    # Python-computed (fast, deterministic)
    talk_ratio_rep: float             # 0-100 %
    talk_ratio_prospect: float        # 0-100 %
    estimated_duration_minutes: float
    rep_word_count: int
    prospect_word_count: int
    longest_monologue_seconds: int
    question_count_rep: int
    question_count_prospect: int
    filler_word_count: int
    filler_words_per_minute: float    # per minute of rep speaking time
    filler_breakdown: Dict[str, int]  # {word: count}

    # Groq-computed (AI analysis)
    topic_segments: List[TopicSegment] = []
    key_moments: List[KeyMoment] = []
    coaching_tips: List[str] = []
    overall_score: int        # 0-100
    score_rationale: str = ""

    analysed_at: str


class TranscriptAnalysisRequest(BaseModel):
    transcript: str
    rep_name: Optional[str] = None   # hint for speaker detection


class CoachingBenchmarks(BaseModel):
    ideal_talk_ratio_rep: float
    ideal_talk_ratio_rep_label: str
    ideal_question_count_min: int
    ideal_question_count_max: int
    ideal_longest_monologue_seconds: int
    filler_threshold_per_minute: float
    source: str
    notes: List[str]
