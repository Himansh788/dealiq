import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";
import { Mail, Phone, Users, FileText, AlertTriangle, TrendingUp, TrendingDown, Minus } from "lucide-react";
import { cn } from "@/lib/utils";

// ── Types ──────────────────────────────────────────────────────────────────────

interface ActivityItem {
  id: string;
  type: string;
  direction: string;
  date: string;
  subject?: string;
  participants: string[];
  summary?: string;
  duration_minutes?: number;
}

interface EngagementVelocityScore {
  score: number;
  touchpoints_14d: number;
  unique_contacts_14d: number;
  days_since_two_way: number;
  meeting_trend: string;
  stage_benchmark?: string;
}

interface GhostStakeholder {
  name: string;
  role?: string;
  email?: string;
  days_silent: number;
  last_seen_date?: string;
  alert: string;
}

interface ActivityFeedResponse {
  deal_id: string;
  activities: ActivityItem[];
  total_count: number;
  engagement_score: EngagementVelocityScore;
  ghost_stakeholders: GhostStakeholder[];
  simulated: boolean;
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function daysAgoLabel(dateStr: string): string {
  try {
    const dt = new Date(dateStr);
    const diff = Math.floor((Date.now() - dt.getTime()) / 86_400_000);
    if (diff === 0) return "today";
    if (diff === 1) return "yesterday";
    return `${diff}d ago`;
  } catch {
    return "";
  }
}

function formatDate(dateStr: string): string {
  try {
    return new Date(dateStr).toLocaleDateString("en-GB", {
      day: "numeric",
      month: "short",
    });
  } catch {
    return dateStr;
  }
}

function daysBetween(a: string, b: string): number {
  try {
    return Math.floor((new Date(b).getTime() - new Date(a).getTime()) / 86_400_000);
  } catch {
    return 0;
  }
}

function ActivityIcon({ type }: { type: string }) {
  switch (type) {
    case "email":   return <Mail className="h-3.5 w-3.5 text-blue-400" />;
    case "call":    return <Phone className="h-3.5 w-3.5 text-green-400" />;
    case "meeting": return <Users className="h-3.5 w-3.5 text-purple-400" />;
    default:        return <FileText className="h-3.5 w-3.5 text-slate-400" />;
  }
}

function activityDotClass(type: string): string {
  switch (type) {
    case "email":   return "bg-blue-500/20 border-blue-500/40";
    case "call":    return "bg-green-500/20 border-green-500/40";
    case "meeting": return "bg-purple-500/20 border-purple-500/40";
    default:        return "bg-slate-500/20 border-slate-500/40";
  }
}

function activityTypeLabel(type: string): string {
  switch (type) {
    case "email":   return "Email";
    case "call":    return "Call";
    case "meeting": return "Meeting";
    case "note":    return "Note";
    case "task":    return "Task";
    default:        return type;
  }
}

function directionLabel(direction: string): string {
  switch (direction) {
    case "outbound": return "outbound";
    case "inbound":  return "inbound";
    default:         return "";
  }
}

function scoreRingColor(score: number): string {
  if (score >= 10) return "stroke-health-green";
  if (score >= 6)  return "stroke-health-yellow";
  return "stroke-health-red";
}

function scoreLabelColor(score: number): string {
  if (score >= 10) return "text-health-green";
  if (score >= 6)  return "text-health-yellow";
  return "text-health-red";
}

function MeetingTrendIcon({ trend }: { trend: string }) {
  if (trend === "increasing") return <TrendingUp className="h-3.5 w-3.5 text-health-green" />;
  if (trend === "declining")  return <TrendingDown className="h-3.5 w-3.5 text-health-red" />;
  return <Minus className="h-3.5 w-3.5 text-muted-foreground" />;
}

type ActivityFilter = "all" | "email" | "call" | "meeting";

// ── Score Ring ─────────────────────────────────────────────────────────────────

function ScoreRing({ score, max = 15 }: { score: number; max?: number }) {
  const r = 16;
  const circ = 2 * Math.PI * r;
  const filled = (score / max) * circ;
  return (
    <div className="relative flex items-center justify-center">
      <svg width="44" height="44" viewBox="0 0 36 36" className="-rotate-90" aria-hidden>
        <circle cx="18" cy="18" r={r} fill="none" strokeWidth="3" className="stroke-border/40" />
        <circle
          cx="18" cy="18" r={r} fill="none" strokeWidth="3"
          strokeDasharray={`${filled} ${circ}`} strokeLinecap="round"
          className={scoreRingColor(score)}
        />
      </svg>
      <span className={cn("absolute text-sm font-bold tabular-nums", scoreLabelColor(score))}>
        {score}
      </span>
    </div>
  );
}

// ── Main Component ─────────────────────────────────────────────────────────────

export default function ActivityFeedPanel({
  dealId,
  stage,
}: {
  dealId: string;
  stage?: string;
}) {
  const [data, setData] = useState<ActivityFeedResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<ActivityFilter>("all");

  useEffect(() => {
    if (!dealId) return;
    const controller = new AbortController();
    let cancelled = false;
    setLoading(true);
    setError(null);

    api.getDealActivities(dealId, controller.signal)
      .then(d => { if (!cancelled) setData(d); })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof DOMException && err.name === "AbortError") return;
        if (err instanceof Error && err.name === "AbortError") return;
        setError("Couldn't load activity data. Please try again.");
      })
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; controller.abort(); };
  }, [dealId]);

  if (loading) return (
    <div className="space-y-4 py-2">
      <Skeleton className="h-20 w-full rounded-lg" />
      <div className="space-y-3">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="flex gap-3">
            <Skeleton className="h-7 w-7 rounded-full shrink-0" />
            <div className="flex-1 space-y-1.5 pt-1">
              <Skeleton className="h-3 w-1/2" />
              <Skeleton className="h-3 w-3/4" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );

  if (error) return (
    <p className="py-3 text-xs text-muted-foreground">Could not load activity feed: {error}</p>
  );

  if (!data) return null;

  const ev = data.engagement_score;
  const filtered = filter === "all" ? data.activities : data.activities.filter(a => a.type === filter);

  return (
    <div className="space-y-4">

      {/* ── Engagement Score Card ── */}
      <div className="rounded-lg border border-border/40 bg-secondary/30 p-3">
        <div className="flex items-start gap-4">
          <ScoreRing score={ev.score} />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-xs font-semibold text-foreground">Engagement Velocity</span>
              <span className="rounded-full border border-border/40 bg-secondary/60 px-1.5 py-0.5 text-[10px] text-muted-foreground tabular-nums">
                {ev.score}/15
              </span>
            </div>
            <div className="grid grid-cols-3 gap-2">
              <div className="text-center">
                <p className="text-base font-bold tabular-nums text-foreground">{ev.touchpoints_14d}</p>
                <p className="text-[10px] text-muted-foreground">touches/14d</p>
              </div>
              <div className="text-center">
                <p className="text-base font-bold tabular-nums text-foreground">{ev.unique_contacts_14d}</p>
                <p className="text-[10px] text-muted-foreground">contacts</p>
              </div>
              <div className="text-center">
                <div className="flex items-center justify-center gap-1">
                  <MeetingTrendIcon trend={ev.meeting_trend} />
                  <p className="text-[10px] text-muted-foreground capitalize">{ev.meeting_trend}</p>
                </div>
                <p className="text-[10px] text-muted-foreground">mtg trend</p>
              </div>
            </div>
          </div>
        </div>

        {/* Stage benchmark callout */}
        {ev.stage_benchmark && (
          <div className={cn(
            "mt-3 rounded-md border px-2.5 py-1.5 text-xs",
            ev.stage_benchmark.includes("Below benchmark")
              ? "border-health-orange/30 bg-health-orange/5 text-health-orange"
              : "border-border/30 bg-secondary/40 text-muted-foreground"
          )}>
            {ev.stage_benchmark}
          </div>
        )}
      </div>

      {/* ── Ghost Stakeholder Alerts ── */}
      {data.ghost_stakeholders.length > 0 && (
        <div className="space-y-2">
          {data.ghost_stakeholders.map((ghost, i) => (
            <div key={i} className="flex items-start gap-2.5 rounded-lg border border-health-red/30 bg-health-red/5 p-2.5">
              <AlertTriangle className="h-4 w-4 shrink-0 text-health-red mt-0.5" />
              <div className="min-w-0">
                <p className="text-xs font-semibold text-health-red">Ghost Stakeholder</p>
                <p className="text-xs text-muted-foreground mt-0.5">{ghost.alert}</p>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ── Filter pills ── */}
      {data.activities.length > 0 && (
        <div className="flex items-center gap-1.5">
          {(["all", "email", "call", "meeting"] as const).map(f => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={cn(
                "rounded-full border px-2.5 py-1 text-xs font-medium transition-colors",
                filter === f
                  ? "border-primary/50 bg-primary/15 text-primary"
                  : "border-border/40 bg-secondary/40 text-muted-foreground hover:text-foreground"
              )}
            >
              {f.charAt(0).toUpperCase() + f.slice(1)}
            </button>
          ))}
          <span className="ml-auto text-xs text-muted-foreground">{filtered.length} activities</span>
        </div>
      )}

      {/* ── Activity Timeline ── */}
      {filtered.length === 0 ? (
        <p className="py-3 text-xs text-muted-foreground">No activity recorded for this deal yet.</p>
      ) : (
        <div className="relative">
          <div className="absolute left-[13px] top-3 bottom-3 w-px bg-border/40" />
          <div className="space-y-1">
            {filtered.map((activity, idx) => {
              // Detect gap >7 days between consecutive activities
              const prev = filtered[idx - 1];
              const gap = prev ? daysBetween(activity.date, prev.date) : 0;
              const showGapBand = gap > 7;

              return (
                <div key={activity.id}>
                  {/* Gap band */}
                  {showGapBand && (
                    <div className="relative ml-7 mb-1 mt-1 flex items-center gap-2 rounded-sm border-l-2 border-health-red/40 bg-health-red/5 px-2 py-1">
                      <span className="text-[10px] font-medium text-health-red/80">
                        {gap}-day gap
                      </span>
                    </div>
                  )}

                  <div className="relative flex gap-3 group">
                    {/* Dot */}
                    <div className={cn(
                      "relative z-10 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border",
                      activityDotClass(activity.type)
                    )}>
                      <ActivityIcon type={activity.type} />
                    </div>

                    {/* Content */}
                    <div className="flex-1 min-w-0 pb-3">
                      <div className="flex items-start justify-between gap-2 pt-0.5">
                        <div className="min-w-0">
                          <span className="text-xs font-medium text-foreground">
                            {activityTypeLabel(activity.type)}
                          </span>
                          {activity.direction !== "internal" && (
                            <span className="ml-1.5 text-[10px] text-muted-foreground">
                              ({directionLabel(activity.direction)})
                            </span>
                          )}
                          {activity.duration_minutes && (
                            <span className="ml-1.5 text-[10px] text-muted-foreground">
                              · {activity.duration_minutes} min
                            </span>
                          )}
                        </div>
                        <span className="shrink-0 text-[10px] tabular-nums text-muted-foreground/70">
                          {formatDate(activity.date)} · {daysAgoLabel(activity.date)}
                        </span>
                      </div>

                      {activity.subject && (
                        <p className="mt-0.5 text-xs font-medium text-foreground/80 leading-tight">
                          {activity.subject}
                        </p>
                      )}

                      {activity.participants.length > 0 && (
                        <p className="mt-0.5 text-[10px] text-muted-foreground/70">
                          {activity.participants.slice(0, 3).join(", ")}
                          {activity.participants.length > 3 && ` +${activity.participants.length - 3}`}
                        </p>
                      )}

                      {activity.summary && (
                        <p className="mt-1 text-xs text-muted-foreground leading-relaxed line-clamp-2">
                          {activity.summary}
                        </p>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Footer */}
      <div className="border-t border-border/30 pt-2 text-xs text-muted-foreground">
        {data.total_count} total activities
        {data.simulated && " · Demo data"}
      </div>
    </div>
  );
}
