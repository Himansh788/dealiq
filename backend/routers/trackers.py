from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone
import uuid

from models.tracker_schemas import (
    TrackerCreate,
    TrackerResponse,
    TrackerAnalysisRequest,
    TrackerAnalysisResult,
)
from services.smart_tracker import tracker_service
from services.demo_data import TRACKER_DEMO_TRANSCRIPT

router = APIRouter()


# ── CRUD ──────────────────────────────────────────────────────────────────────

@router.post("/", response_model=TrackerResponse, status_code=201)
async def create_tracker(body: TrackerCreate):
    """Create a custom concept tracker."""
    if body.severity not in ("info", "warning", "critical"):
        raise HTTPException(status_code=422, detail="severity must be info, warning, or critical")
    tracker_id = body.name.lower().replace(" ", "_") + "_" + uuid.uuid4().hex[:6]
    return tracker_service.add_custom_tracker(
        tracker_id=tracker_id,
        name=body.name,
        concept_description=body.concept_description,
        severity=body.severity,
    )


@router.get("/", response_model=list[TrackerResponse])
async def list_trackers():
    """List all trackers — default built-ins plus any custom ones."""
    return tracker_service.get_all_trackers()


# ── Analysis ──────────────────────────────────────────────────────────────────

@router.post("/analyze", response_model=TrackerAnalysisResult)
async def analyze_transcript(body: TrackerAnalysisRequest):
    """
    Run trackers against a transcript.
    Pass tracker_ids to run a subset, or omit to run all trackers.
    """
    if not body.transcript.strip():
        raise HTTPException(status_code=422, detail="transcript must not be empty")

    try:
        matches = await tracker_service.analyze_transcript(
            transcript=body.transcript,
            tracker_ids=body.tracker_ids,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Tracker analysis failed: {str(e)}")

    all_trackers = tracker_service.get_all_trackers()
    trackers_run = len(body.tracker_ids) if body.tracker_ids else len(all_trackers)

    return TrackerAnalysisResult(
        matches=matches,
        total_matches=len(matches),
        trackers_run=trackers_run,
        critical_count=sum(1 for m in matches if m.severity == "critical"),
        warning_count=sum(1 for m in matches if m.severity == "warning"),
        info_count=sum(1 for m in matches if m.severity == "info"),
        analysed_at=datetime.now(timezone.utc).isoformat(),
    )


@router.get("/analyze/demo", response_model=TrackerAnalysisResult)
async def demo_tracker_analysis():
    """
    Demo endpoint — runs all default trackers against a sample transcript.
    No auth required.
    """
    try:
        matches = await tracker_service.analyze_transcript(TRACKER_DEMO_TRANSCRIPT)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Demo analysis failed: {str(e)}")

    all_trackers = tracker_service.get_all_trackers()

    return TrackerAnalysisResult(
        matches=matches,
        total_matches=len(matches),
        trackers_run=len(all_trackers),
        critical_count=sum(1 for m in matches if m.severity == "critical"),
        warning_count=sum(1 for m in matches if m.severity == "warning"),
        info_count=sum(1 for m in matches if m.severity == "info"),
        analysed_at=datetime.now(timezone.utc).isoformat(),
    )
