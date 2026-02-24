import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Plus, FileText, Phone, Mail, CheckSquare,
  Activity, Flag, AlertTriangle, Sparkles, Brain
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
}

interface Signal {
  severity: "critical" | "warning" | "good";
  text: string;
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
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function getIcon(iconName: string, isFuture?: boolean, isWarning?: boolean) {
  const cls = `h-3.5 w-3.5 ${isFuture ? "text-primary" : isWarning ? "text-health-red" : "text-muted-foreground"}`;
  switch (iconName) {
    case "plus":          return <Plus className={cls} />;
    case "file-text":     return <FileText className={cls} />;
    case "phone":         return <Phone className={cls} />;
    case "mail":          return <Mail className={cls} />;
    case "check-square":  return <CheckSquare className={cls} />;
    case "activity":      return <Activity className={cls} />;
    case "flag":          return <Flag className={`${cls} text-primary`} />;
    case "alert-triangle": return <AlertTriangle className={`${cls} text-health-red`} />;
    default:              return <Activity className={cls} />;
  }
}

function formatDaysAgo(days: number, isFuture?: boolean): string {
  if (isFuture) {
    if (days === 0) return "today";
    if (days === 1) return "tomorrow";
    return `in ${Math.abs(days)} days`;
  }
  if (days === 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 0) return `${Math.abs(days)}d overdue`;
  return `${days}d ago`;
}

function silenceColor(days: number | null): string {
  if (days === null) return "text-muted-foreground";
  if (days >= 30) return "text-health-red";
  if (days >= 14) return "text-health-orange";
  if (days >= 7)  return "text-health-yellow";
  return "text-health-green";
}

// ── Main Component ────────────────────────────────────────────────────────────

export default function DealTimeline({ dealId }: { dealId: string }) {
  const [data, setData] = useState<TimelineData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!dealId) return;
    setLoading(true);
    setError(null);
    api.getDealTimeline(dealId)
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [dealId]);

  if (loading) return (
    <div className="space-y-4 py-2">
      <div className="space-y-2">
        <Skeleton className="h-3 w-2/3" />
        <Skeleton className="h-3 w-full" />
        <Skeleton className="h-3 w-1/2" />
      </div>
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
  );

  if (error) return (
    <p className="text-xs text-muted-foreground py-3">Could not load timeline: {error}</p>
  );

  if (!data || data.events.length === 0) return (
    <p className="text-xs text-muted-foreground py-3">No timeline events found for this deal.</p>
  );

  return (
    <div className="space-y-4">

      {/* ── Signal pills ── */}
      {data.signals.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {data.signals.map((sig, i) => (
            <span key={i} className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium border
              ${sig.severity === "critical" ? "bg-health-red/10 text-health-red border-health-red/30" :
                sig.severity === "warning"  ? "bg-health-yellow/10 text-health-yellow border-health-yellow/30" :
                "bg-health-green/10 text-health-green border-health-green/30"}`}>
              {sig.severity === "critical" ? "⚠" : sig.severity === "warning" ? "○" : "✓"}
              {sig.text}
            </span>
          ))}
        </div>
      )}

      {/* ── AI Narrative ── */}
      {data.narrative && (
        <div className="rounded-lg border border-primary/20 bg-primary/5 p-3 space-y-1.5">
          <div className="flex items-center gap-1.5">
            <Brain className="h-3.5 w-3.5 text-primary" />
            <span className="text-xs font-semibold text-primary uppercase tracking-wider">AI Timeline Analysis</span>
            <span className="inline-flex items-center gap-1 rounded-full border border-primary/30 bg-primary/10 px-1.5 py-0.5 text-xs font-medium text-primary">
              <Sparkles className="h-2.5 w-2.5" /> AI
            </span>
          </div>
          <p className="text-xs text-foreground/90 leading-relaxed">{data.narrative}</p>
        </div>
      )}

      {/* ── Silence indicator ── */}
      {data.silence_days !== null && (
        <div className="flex items-center justify-between rounded-lg bg-secondary/50 px-3 py-2">
          <span className="text-xs text-muted-foreground">Last activity</span>
          <span className={`text-xs font-bold ${silenceColor(data.silence_days)}`}>
            {data.silence_days === 0 ? "Today" :
             data.silence_days === 1 ? "Yesterday" :
             `${data.silence_days} days ago`}
            {data.silence_days >= 14 ? " ⚠" : ""}
          </span>
        </div>
      )}

      {/* ── Timeline ── */}
      <div className="relative">
        {/* Vertical line */}
        <div className="absolute left-[13px] top-3 bottom-3 w-px bg-border/50" />

        <div className="space-y-1">
          {data.events.map((event, i) => {
            const isLast = i === data.events.length - 1;
            const isPast = !event.is_future;
            const isNow = event.days_ago === 0;

            return (
              <div key={i} className={`relative flex gap-3 group ${event.is_future ? "opacity-70" : ""}`}>
                {/* Dot */}
                <div className={`relative z-10 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border
                  ${event.is_warning  ? "border-health-red/40 bg-health-red/10" :
                    event.is_future   ? "border-primary/40 bg-primary/10 border-dashed" :
                    isNow             ? "border-primary bg-primary/20" :
                    "border-border/60 bg-secondary/80"}`}>
                  {getIcon(event.icon, event.is_future, event.is_warning)}
                </div>

                {/* Content */}
                <div className={`flex-1 min-w-0 pb-4 ${isLast ? "pb-0" : ""}`}>
                  <div className="flex items-start justify-between gap-2 pt-0.5">
                    <p className={`text-xs font-medium leading-tight ${
                      event.is_warning ? "text-health-red" :
                      event.is_future  ? "text-primary" :
                      "text-foreground"
                    }`}>
                      {event.label}
                    </p>
                    <span className={`shrink-0 text-xs tabular-nums ${
                      event.is_warning ? "text-health-red font-medium" :
                      event.is_future  ? "text-primary" :
                      "text-muted-foreground"
                    }`}>
                      {formatDaysAgo(event.days_ago ?? 0, event.is_future)}
                    </span>
                  </div>

                  {event.detail && (
                    <p className="mt-0.5 text-xs text-muted-foreground leading-relaxed line-clamp-2">
                      {event.detail}
                    </p>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* ── Footer summary ── */}
      <div className="flex items-center justify-between border-t border-border/30 pt-3 text-xs text-muted-foreground">
        <span>{data.total_events} recorded events</span>
        {data.closing_date && (
          <span className={data.days_to_close !== null && data.days_to_close < 0 ? "text-health-red font-medium" : ""}>
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
