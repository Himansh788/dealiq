from pydantic import BaseModel
from typing import Optional


class ActivityItem(BaseModel):
    id: str
    type: str           # email | call | meeting | note | task
    direction: str      # outbound | inbound | internal
    date: str           # ISO 8601
    subject: Optional[str] = None
    participants: list[str] = []
    summary: Optional[str] = None
    duration_minutes: Optional[int] = None  # calls/meetings only


class GhostStakeholder(BaseModel):
    name: str
    role: Optional[str] = None
    email: Optional[str] = None
    days_silent: int
    last_seen_date: Optional[str] = None
    alert: str


class EngagementVelocityScore(BaseModel):
    score: int              # 0-15
    touchpoints_14d: int
    unique_contacts_14d: int
    days_since_two_way: int
    meeting_trend: str      # increasing | stable | declining | none
    stage_benchmark: Optional[str] = None  # e.g. "Won deals at this stage average 3.2 meetings/week. This deal: 0.8."


class ActivityFeedResponse(BaseModel):
    deal_id: str
    activities: list[ActivityItem]
    total_count: int
    engagement_score: EngagementVelocityScore
    ghost_stakeholders: list[GhostStakeholder]
    simulated: bool


class RepActivity(BaseModel):
    rep_name: str
    deals_active: int
    deals_touched_7d: int       # deals with last_activity in last 7 days
    avg_health_score: float
    total_pipeline_value: float
    activity_trend: str         # active | slowing | inactive


class TeamActivitySummary(BaseModel):
    reps: list[RepActivity]
    team_avg_deals_touched_7d: float
    team_avg_health_score: float
    generated_at: str
    simulated: bool
