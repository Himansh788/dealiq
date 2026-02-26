from pydantic import BaseModel
from typing import Optional, List


class TrackerCreate(BaseModel):
    name: str
    concept_description: str
    severity: str = "info"  # info | warning | critical


class TrackerResponse(BaseModel):
    id: str
    name: str
    concept_description: str
    severity: str
    is_default: bool = False


class TrackerMatch(BaseModel):
    tracker_id: str
    tracker_name: str
    severity: str
    matched_text: str
    timestamp_hint: Optional[str] = None
    confidence_score: float   # 0.0 – 1.0
    context_snippet: str


class TrackerAnalysisRequest(BaseModel):
    transcript: str
    tracker_ids: Optional[List[str]] = None   # None = run all trackers


class TrackerAnalysisResult(BaseModel):
    matches: List[TrackerMatch]
    total_matches: int
    trackers_run: int
    critical_count: int
    warning_count: int
    info_count: int
    analysed_at: str
