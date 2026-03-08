import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import {
  Plus, FileText, Phone, Mail, CheckSquare, MailOpen,
  Activity, Flag, AlertTriangle, Sparkles, Brain,
  GitMerge, TrendingUp, TrendingDown, Bot, User,
  ChevronDown, ChevronUp, Calendar, ExternalLink,
} from "lucide-react";

// ── Types ─────────────────────────────────────────────────────────────────────

interface TimelineEvent {
  type: string;
  label: string;
  detail: string;
  datetime: string;
  days_ago: number;
  icon: string;
  is_future?: boolean;
  is_warning?: boolean;
  is_automation?: boolean;
  stage_from?: string;
  stage_to?: string;
  stage_from_colour?: string;
  stage_to_colour?: string;
  direction?: "forward" | "backward";
  revenue_direction?: "up" | "down";
  old_value?: number;
  new_value?: number;
  email_subject?: string;
}

interface Signal {
  severity: "critical" | "warning" | "good";
  text: string;
}

interface TimelineIntelligence {
  stage_progression: Array<{
    old_stage: string;
    new_stage: string;
    old_colour: string;
    new_colour: string;
    direction: string;
    changed_by: string;
    days_ago: number;
  }>;
  last_email_sent?: string;
  last_email_subject?: string;
  days_since_last_email?: number;
  revenue_changes: Array<{
    direction: string;
    old_value: number;
    new_value: number;
    changed_by?: string;
    days_ago?: number;
  }>;
  automation_count: number;
  human_count: number;
  deal_health_signals: {
    has_recent_email: boolean;
    stage_moving_forward: boolean;
    revenue_growing: boolean;
    human_activity_ratio: number;
  };
}

interface TimelineData {
  events: TimelineEvent[];
  signals: Signal[];
  narrative: string;
  silence_days: number | null;
  days_to_close: number | null;
  stage_age_days: number | null;
  total_events: number;
  deal_name: string;
  stage: string;
  closing_date: string;
  timeline_intelligence?: TimelineIntelligence;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatTs(days: number, isFuture?: boolean): string {
  if (isFuture) {
    if (days === 0) return "today";
    if (days === 1) return "tomorrow";
    return `in ${Math.abs(days)}d`;
  }
  if (days === 0) return "Today";
  if (days === 1) return "Yesterday";
  if (days < 0) return `${Math.abs(days)}d overdue`;
  if (days > 30) return `${days}d ago`;
  return `${days}d ago`;
}

function fmtCurrency(v: number) {
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `$${Math.round(v / 1_000)}K`;
  return `$${v}`;
}

/** Node colour + size for the vertical connector line */
function nodeCfg(event: TimelineEvent): { dot: string; ring: string; size: string } {
  switch (event.type) {
    case "task":           return { dot: "bg-blue-500",    ring: "ring-blue-500/30",   size: "w-3 h-3" };
    case "email":          return { dot: "bg-purple-500",  ring: "ring-purple-500/30", size: "w-3 h-3" };
    case "stage_change":   return { dot: "bg-yellow-400",  ring: "ring-yellow-400/30", size: "w-4 h-4" };
    case "closing_overdue":return { dot: "bg-red-500 animate-pulse", ring: "ring-red-500/30", size: "w-3 h-3" };
    case "created":        return { dot: "bg-green-500",   ring: "ring-green-500/30",  size: "w-3 h-3" };
    case "last_activity":  return { dot: "bg-muted-foreground/50",   ring: "ring-slate-500/20",  size: "w-2.5 h-2.5" };
    case "revenue_change": return {
      dot: event.revenue_direction === "up" ? "bg-green-500" : "bg-orange-500",
      ring: event.revenue_direction === "up" ? "ring-green-500/30" : "ring-orange-500/30",
      size: "w-3 h-3",
    };
    default: return { dot: "bg-muted-foreground/40", ring: "ring-slate-500/20", size: "w-3 h-3" };
  }
}

/** Coloured stage pill using Zoho colour_code */
function StagePill({ label, colour }: { label: string; colour?: string }) {
  const style = colour
    ? { borderColor: `${colour}60`, backgroundColor: `${colour}22`, color: colour }
    : undefined;
  return (
    <span
      className="inline-flex items-center rounded-full border border-border/50 bg-muted/50 text-muted-foreground px-3.5 text-[10px] font-semibold whitespace-nowrap leading-[1.4]"
      style={{ ...style, padding: "5px 14px" }}
    >
      {label}
    </span>
  );
}

// ── 1. Summary Bar — stat chips ───────────────────────────────────────────────

function SummaryBar({ intel, totalEvents }: { intel?: TimelineIntelligence; totalEvents: number }) {
  if (!intel) return null;
  const { days_since_last_email, stage_progression, automation_count, human_count } = intel;
  const forwardMoves = stage_progression.filter(s => s.direction === "forward").length;
  const backMoves    = stage_progression.filter(s => s.direction === "backward").length;
  const emailLate    = days_since_last_email != null && days_since_last_email > 30;

  return (
    <div className="flex flex-wrap items-center gap-2">
      {/* Activities */}
      <span className="inline-flex items-center gap-1.5 rounded-full bg-muted/50 px-3 py-1 text-[11px] text-foreground/80">
        <Calendar className="h-3 w-3 text-muted-foreground" />
        {totalEvents} activities
      </span>

      {/* Last email */}
      {days_since_last_email != null && (
        <span className={cn(
          "inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-[11px]",
          emailLate
            ? "bg-red-500/10 text-red-600 border border-red-500/30"
            : "bg-muted/50 text-foreground/80"
        )}>
          <Mail className="h-3 w-3" />
          Last email: {days_since_last_email === 0 ? "today" : `${days_since_last_email}d ago`}
          {emailLate && " ⚠"}
        </span>
      )}

      {/* Stage moves */}
      {forwardMoves > 0 && (
        <span className="inline-flex items-center gap-1.5 rounded-full bg-green-950 px-3 py-1 text-[11px] text-green-400 border border-green-800/50">
          ↑ Stage: +{forwardMoves} forward
        </span>
      )}
      {backMoves > 0 && (
        <span className="inline-flex items-center gap-1.5 rounded-full bg-red-950 px-3 py-1 text-[11px] text-red-400 border border-red-800/50">
          ↓ Stage: {backMoves} backward
        </span>
      )}
    </div>
  );
}

// ── 8. Human vs automation ratio bar ─────────────────────────────────────────

function EngagementBar({ intel }: { intel: TimelineIntelligence }) {
  const { human_count, automation_count } = intel;
  const total = human_count + automation_count;
  if (total === 0) return null;
  const ratio = Math.round((human_count / total) * 100);

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-[11px]">
        <span className="flex items-center gap-1 text-muted-foreground">
          <User className="h-3 w-3" />
          {ratio}% human activity
          <span className="text-muted-foreground/50">({human_count} human / {automation_count} automated)</span>
        </span>
        <Bot className="h-3 w-3 text-muted-foreground/50" />
      </div>
      <div className="h-1.5 w-full rounded-full bg-muted/50 overflow-hidden">
        <div
          className="h-full rounded-full bg-green-500 transition-all duration-500"
          style={{ width: `${ratio}%` }}
        />
      </div>
    </div>
  );
}

// ── 3. Signal pills sorted + critical banner ──────────────────────────────────

function SignalPills({ signals }: { signals: Signal[] }) {
  if (signals.length === 0) return null;
  const sorted = [...signals].sort((a, b) => {
    const order = { critical: 0, warning: 1, good: 2 };
    return order[a.severity] - order[b.severity];
  });
  const critCount = sorted.filter(s => s.severity === "critical").length;

  return (
    <div className="space-y-2">
      {critCount >= 3 && (
        <div className="flex items-center gap-2 rounded-lg bg-red-950 border border-red-800/60 px-3 py-2">
          <span className="text-base">⚠️</span>
          <span className="text-xs font-semibold text-red-400">This deal needs immediate attention</span>
        </div>
      )}
      <div className="flex flex-wrap gap-1.5">
        {sorted.map((sig, i) => (
          <span key={i} className={cn(
            "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium",
            sig.severity === "critical"
              ? "bg-red-900/50 text-red-400 border-red-700"
              : sig.severity === "warning"
              ? "bg-yellow-900/50 text-yellow-400 border-yellow-700"
              : "bg-green-900/50 text-green-400 border-green-700"
          )}>
            {sig.severity === "critical"
              ? <span className="h-1.5 w-1.5 rounded-full bg-red-500 animate-pulse" />
              : sig.severity === "warning"
              ? <span className="text-xs">⚠</span>
              : <span className="text-xs">✓</span>
            }
            {sig.text}
          </span>
        ))}
      </div>
    </div>
  );
}

// ── 5. AI Narrative with expand/collapse ──────────────────────────────────────

function NarrativeBox({ text }: { text: string }) {
  const [expanded, setExpanded] = useState(false);
  const sentences = text.match(/[^.!?]+[.!?]+/g) ?? [text];
  const preview = sentences.slice(0, 2).join(" ").trim();
  const hasMore = sentences.length > 2;

  return (
    <div className="rounded-lg border border-blue-900/60 bg-blue-950/30 p-3 space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <Brain className="h-3.5 w-3.5 text-blue-400" />
          <span className="text-[11px] font-semibold text-blue-400 uppercase tracking-wider">AI Analysis</span>
        </div>
        <span className="inline-flex items-center gap-1 rounded-full border border-blue-700/50 bg-blue-900/50 px-1.5 py-0.5 text-[10px] font-medium text-blue-400">
          <Sparkles className="h-2.5 w-2.5" /> AI
        </span>
      </div>
      <div className="border-l-2 border-blue-500 pl-3">
        <p className="text-xs text-foreground/80 leading-relaxed">
          {expanded ? text : preview}
        </p>
        {hasMore && (
          <button
            onClick={() => setExpanded(v => !v)}
            className="mt-1.5 flex items-center gap-1 text-[11px] text-blue-400 hover:text-blue-300 transition-colors"
          >
            {expanded
              ? <><ChevronUp className="h-3 w-3" /> Show less</>
              : <><ChevronDown className="h-3 w-3" /> Read more</>
            }
          </button>
        )}
      </div>
    </div>
  );
}

// ── 6. Revenue change banner ──────────────────────────────────────────────────

function RevenueBanner({ changes }: { changes: TimelineIntelligence["revenue_changes"] }) {
  if (!changes || changes.length === 0) return null;
  return (
    <div className="space-y-1.5">
      {changes.map((rc, i) => {
        const isUp = rc.direction === "up";
        const diff = Math.abs(rc.new_value - rc.old_value);
        return (
          <div key={i} className={cn(
            "flex items-center gap-2 rounded-lg border px-3 py-2",
            isUp
              ? "bg-green-950/50 border-green-800/50"
              : "bg-orange-950/50 border-orange-800/50"
          )}>
            {isUp
              ? <TrendingUp className="h-4 w-4 text-green-400 shrink-0" />
              : <span className="text-base shrink-0">💸</span>
            }
            <div className="flex-1 min-w-0">
              <p className={cn("text-xs font-semibold", isUp ? "text-green-400" : "text-orange-400")}>
                Revenue {isUp ? "increased" : "reduced"}: {fmtCurrency(rc.old_value)} → {fmtCurrency(rc.new_value)}
                <span className={cn("ml-1.5", isUp ? "text-green-500" : "text-red-400")}>
                  ({isUp ? "+" : "–"}{fmtCurrency(diff)})
                </span>
              </p>
              {rc.changed_by && (
                <p className="text-[10px] text-muted-foreground/70 mt-0.5">
                  by {rc.changed_by}{rc.days_ago != null ? ` · ${rc.days_ago}d ago` : ""}
                </p>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── 2. Stage change row ───────────────────────────────────────────────────────

function StageChangeRow({ event, isLast }: { event: TimelineEvent; isLast: boolean }) {
  const borderColour = event.stage_to_colour || "#facc15";
  return (
    <div
      className={cn("flex-1 min-w-0 rounded-lg px-3 py-2.5 mb-3", !isLast && "mb-3")}
      style={{
        backgroundColor: "rgba(15,15,25,0.8)",
        borderLeft: `3px solid ${borderColour}`,
        borderTop: "1px solid rgba(255,255,255,0.06)",
        borderRight: "1px solid rgba(255,255,255,0.04)",
        borderBottom: "1px solid rgba(255,255,255,0.04)",
      }}
    >
      <div className="flex flex-col gap-1">
        {/* Pill row — all items share the same inline-flex baseline */}
        <div className="inline-flex items-center gap-2">
          <StagePill label={event.stage_from || ""} colour={event.stage_from_colour} />
          <span className="text-muted-foreground/70 text-xs leading-none">→</span>
          <StagePill label={event.stage_to || ""} colour={event.stage_to_colour} />
          <span className="ml-auto text-[10px] text-muted-foreground/70 tabular-nums shrink-0">
            {formatTs(event.days_ago ?? 0)}
          </span>
        </div>

        {/* Meta row — direction badge + detail on their own line */}
        <div className="flex items-center gap-2">
          <span className={cn(
            "inline-flex items-center rounded-full text-[10px] font-bold leading-[1.4]",
            event.direction === "forward"
              ? "bg-green-900/60 text-green-400"
              : "bg-red-900/60 text-red-400"
          )} style={{ padding: "5px 14px" }}>
            {event.direction === "forward" ? "↑ Forward" : "↓ Backward"}
          </span>
          {event.detail && (
            <span className="text-[10px] text-muted-foreground/70">{event.detail}</span>
          )}
        </div>
      </div>
    </div>
  );
}

// ── 7. Closing overdue banner ─────────────────────────────────────────────────

function ClosingOverdueBanner({ event }: { event: TimelineEvent }) {
  const daysOverdue = Math.abs(event.days_ago ?? 0);
  return (
    <div className="flex-1 min-w-0 mb-3">
      <div className="flex items-center gap-3 rounded-lg border border-red-700 bg-red-950 px-3 py-2.5">
        <AlertTriangle className="h-5 w-5 text-red-400 shrink-0" />
        <div className="flex-1 min-w-0">
          <p className="text-xs font-semibold text-red-400">
            Closing Date Passed — {daysOverdue} days overdue
          </p>
          <p className="text-[10px] text-muted-foreground/70 mt-0.5">
            {event.detail || `Original close date has passed`}
          </p>
        </div>
        <a
          href="#"
          className="shrink-0 flex items-center gap-1 rounded-md border border-red-700/60 bg-red-900/40 px-2 py-1 text-[11px] text-red-400 hover:bg-red-900/70 transition-colors"
          onClick={e => e.preventDefault()}
        >
          Update <ExternalLink className="h-2.5 w-2.5" />
        </a>
      </div>
    </div>
  );
}

// ── 10. Task row ──────────────────────────────────────────────────────────────

function TaskRow({ event, isLatest, isLast }: { event: TimelineEvent; isLatest: boolean; isLast: boolean }) {
  return (
    <div className={cn(
      "flex-1 min-w-0 pb-3 border-l-2 pl-2",
      isLast && "pb-0",
      "border-yellow-600/40"
    )}>
      <div className="flex items-start justify-between gap-2 pt-0.5">
        <p className="text-xs font-medium text-foreground flex items-center gap-1.5">
          <CheckSquare className="h-3 w-3 text-yellow-500 shrink-0" />
          {event.label.replace(/^Task:\s*/, "")}
          {isLatest && (
            <span className="ml-1 rounded-full bg-blue-900/60 border border-blue-700/50 px-1.5 py-0.5 text-[9px] font-semibold text-blue-400">
              Latest
            </span>
          )}
        </p>
        <span className="shrink-0 text-[11px] text-muted-foreground/70 tabular-nums">
          {formatTs(event.days_ago ?? 0)}
        </span>
      </div>
      {event.detail && (
        <p className="mt-0.5 text-[11px] text-muted-foreground/70">{event.detail}</p>
      )}
    </div>
  );
}

// ── 11. Last activity row (muted) ─────────────────────────────────────────────

function LastActivityRow({ event, isLast }: { event: TimelineEvent; isLast: boolean }) {
  return (
    <div className={cn("flex-1 min-w-0 pb-3", isLast && "pb-0")}>
      <div className="flex items-center justify-between gap-2 pt-0.5">
        <p className="text-[11px] text-muted-foreground/50 italic">{event.label}</p>
        <span className="text-[11px] text-muted-foreground/40 tabular-nums shrink-0">
          {formatTs(event.days_ago ?? 0)}
        </span>
      </div>
    </div>
  );
}

// ── 12. Ghost / no-reply row ──────────────────────────────────────────────────

function NoReplyGhostRow({ days, onEmail }: { days: number; onEmail?: () => void }) {
  return (
    <div className="flex items-center gap-3 rounded-lg border border-dashed border-border/60 bg-muted/20 px-3 py-2.5">
      <MailOpen className="h-4 w-4 text-muted-foreground/50 shrink-0" />
      <div className="flex-1 min-w-0">
        <p className="text-xs text-muted-foreground/70">No reply received from buyer</p>
        <p className="text-[10px] text-muted-foreground/50">Last email sent {days}d ago</p>
      </div>
      <button
        className="shrink-0 text-[11px] text-primary hover:underline whitespace-nowrap"
        onClick={onEmail}
      >
        Send Follow-up →
      </button>
    </div>
  );
}

// ── Main Component ────────────────────────────────────────────────────────────

export default function DealTimeline({ dealId, onFollowUp }: { dealId: string; onFollowUp?: () => void }) {
  const [data, setData] = useState<TimelineData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Increment to trigger a manual retry without changing dealId
  const [retryKey, setRetryKey] = useState(0);

  useEffect(() => {
    if (!dealId) return;

    // Create a controller so we can cancel the request on cleanup.
    // This fires when: component unmounts, dealId changes, or retryKey changes.
    const controller = new AbortController();
    // Guard against setting state after cleanup (double-safety for StrictMode)
    let cancelled = false;

    setLoading(true);
    setError(null);

    api.getDealTimeline(dealId, controller.signal)
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        // AbortError = intentional cancel (unmount / dealId change) — never show to user
        if (e instanceof DOMException && e.name === "AbortError") return;
        if (e instanceof Error && e.name === "AbortError") return;
        setError(
          e instanceof Error
            ? e.message
            : "Failed to load timeline"
        );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
    // retryKey is intentional — incrementing it re-runs this effect
  }, [dealId, retryKey]);

  if (loading) return (
    <div className="space-y-4 py-2">
      <div className="flex gap-2">
        <Skeleton className="h-6 w-24 rounded-full" />
        <Skeleton className="h-6 w-32 rounded-full" />
        <Skeleton className="h-6 w-28 rounded-full" />
      </div>
      <Skeleton className="h-1.5 w-full rounded-full" />
      {[...Array(5)].map((_, i) => (
        <div key={i} className="flex gap-3">
          <div className="flex flex-col items-center">
            <Skeleton className="h-3 w-3 rounded-full" />
            {i < 4 && <div className="w-px h-8 bg-muted/50 mt-1" />}
          </div>
          <div className="flex-1 space-y-1.5 pb-4">
            <Skeleton className="h-3 w-1/2" />
            <Skeleton className="h-3 w-3/4" />
          </div>
        </div>
      ))}
    </div>
  );

  if (error) return (
    <div className="flex flex-col items-start gap-2 rounded-lg border border-border/50 bg-muted/20 px-4 py-4">
      <p className="text-xs font-medium text-foreground/80">Could not load timeline</p>
      <p className="text-[11px] text-muted-foreground/70">{error}</p>
      <button
        onClick={() => setRetryKey(k => k + 1)}
        className="mt-1 rounded-md border border-border bg-muted/50 px-3 py-1 text-[11px] text-foreground/80 hover:bg-muted transition-colors"
      >
        Try again
      </button>
    </div>
  );
  if (!data || data.events.length === 0) return (
    <p className="text-xs text-muted-foreground/70 py-3">No timeline events found for this deal.</p>
  );

  const intel = data.timeline_intelligence;
  const taskEvents = data.events.filter(e => e.type === "task");
  const latestTaskIdx = taskEvents.length > 0
    ? data.events.findIndex(e => e === taskEvents[taskEvents.length - 1])
    : -1;

  // Show ghost no-reply row when last email was > 30d ago
  const showGhost = intel && !intel.deal_health_signals.has_recent_email
    && intel.days_since_last_email != null && intel.days_since_last_email > 30;

  return (
    <div className="space-y-4">

      {/* 1. Summary stat chips */}
      <SummaryBar intel={intel} totalEvents={data.total_events} />

      {/* 8. Engagement ratio bar */}
      {intel && <EngagementBar intel={intel} />}

      {/* 3. Signal pills */}
      <SignalPills signals={data.signals} />

      {/* 6. Revenue changes */}
      {intel && intel.revenue_changes.length > 0 && (
        <RevenueBanner changes={intel.revenue_changes} />
      )}

      {/* 5. AI Narrative */}
      {data.narrative && <NarrativeBox text={data.narrative} />}

      {/* ── Timeline ── */}
      <div className="relative pl-4">
        {/* 1. Vertical connector line */}
        <div className="absolute left-[7px] top-0 bottom-0 w-px bg-border/60" />

        <div className="space-y-0">
          {data.events.map((event, i) => {
            const isLast     = i === data.events.length - 1;
            const isOverdue  = event.type === "closing_overdue";
            const isStage    = event.type === "stage_change";
            const isLastAct  = event.type === "last_activity";
            const isTask     = event.type === "task";
            const { dot, ring, size } = nodeCfg(event);

            return (
              <div
                key={i}
                className={cn(
                  "relative flex gap-3 group transition-all duration-200",
                  !isStage && !isOverdue && "hover:bg-muted/50/30 rounded-md -mx-1 px-1",
                  event.is_future && "opacity-60"
                )}
              >
                {/* Node on the vertical line */}
                <div className="relative z-10 flex shrink-0 items-center justify-center mt-2"
                  style={{ width: 16, minWidth: 16 }}>
                  <span className={cn(
                    "rounded-full ring-2 ring-offset-1 ring-offset-background block",
                    dot, ring, size
                  )} />
                </div>

                {/* Content */}
                <div className="flex-1 min-w-0">
                  {isOverdue ? (
                    <ClosingOverdueBanner event={event} />
                  ) : isStage ? (
                    <StageChangeRow event={event} isLast={isLast} />
                  ) : isLastAct ? (
                    <LastActivityRow event={event} isLast={isLast} />
                  ) : isTask ? (
                    <TaskRow event={event} isLatest={i === latestTaskIdx} isLast={isLast} />
                  ) : event.type === "revenue_change" ? (
                    <div className={cn("flex-1 min-w-0 pb-3", isLast && "pb-0")}>
                      <div className="flex items-center gap-2 pt-0.5">
                        <span className={cn("text-xs font-medium", event.revenue_direction === "up" ? "text-green-400" : "text-red-400")}>
                          {event.label}
                        </span>
                        <span className="ml-auto text-[11px] text-muted-foreground/70 tabular-nums shrink-0">
                          {formatTs(event.days_ago ?? 0)}
                        </span>
                      </div>
                      {event.detail && <p className="text-[10px] text-muted-foreground/70 mt-0.5">{event.detail}</p>}
                    </div>
                  ) : (
                    /* Default row — created, email, note, activity, etc. */
                    <div className={cn("flex-1 min-w-0 pb-3", isLast && "pb-0")}>
                      <div className="flex items-start justify-between gap-2 pt-0.5">
                        <p className={cn(
                          "text-xs font-medium leading-tight",
                          event.is_warning    ? "text-red-400" :
                          event.is_future     ? "text-primary" :
                          event.is_automation ? "text-muted-foreground/70" :
                          event.type === "email" ? "text-foreground" :
                          event.type === "created" ? "text-foreground" :
                          "text-foreground/80"
                        )}>
                          {event.label}
                          {event.is_automation && (
                            <span className="ml-1.5 text-[9px] font-normal text-muted-foreground/50 uppercase tracking-wider">auto</span>
                          )}
                        </p>
                        <span className={cn(
                          "shrink-0 text-[11px] tabular-nums",
                          event.is_warning ? "text-red-400 font-medium" :
                          event.is_future  ? "text-primary" :
                          "text-muted-foreground/70"
                        )}>
                          {formatTs(event.days_ago ?? 0, event.is_future)}
                        </span>
                      </div>
                      {event.detail && (
                        <p className="mt-0.5 text-[11px] text-muted-foreground/70 leading-relaxed line-clamp-2">
                          {event.detail}
                        </p>
                      )}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* 12. No-reply ghost row */}
      {showGhost && (
        <NoReplyGhostRow
          days={intel!.days_since_last_email!}
          onEmail={onFollowUp}
        />
      )}

      {/* Footer */}
      <div className="flex items-center justify-between border-t border-border/40 pt-3 text-[11px] text-muted-foreground/50">
        <span>{data.total_events} recorded events</span>
        {data.closing_date && (
          <span className={data.days_to_close !== null && data.days_to_close < 0 ? "text-red-500 font-medium" : ""}>
            Close: {data.closing_date}
            {data.days_to_close !== null && (
              <span className="ml-1">
                ({data.days_to_close < 0
                  ? `${Math.abs(data.days_to_close)}d overdue`
                  : `${data.days_to_close}d left`})
              </span>
            )}
          </span>
        )}
      </div>
    </div>
  );
}
