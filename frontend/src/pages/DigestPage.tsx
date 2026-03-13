import { useEffect, useState, useCallback } from "react";
import { CheckCircle2, Circle, Mail, Phone, MessageSquare, BookOpen, Calendar, FileText, Clock, AlertTriangle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

// --------------------------------------------------------------------------- //
// Types
// --------------------------------------------------------------------------- //

interface DigestTask {
  id: string;
  deal_id: string;
  deal_name: string;
  company: string;
  stage: string;
  amount: number | null;
  amount_fmt: string;
  task_type: string;
  task_type_label: string;
  task_text: string;
  reason: string;
  is_completed: boolean;
  completed_at: string | null;
  sort_order: number;
}

interface UntouchedDeal {
  deal_id: string;
  deal_name: string;
  company: string;
  stage: string;
  amount: number | null;
  amount_fmt: string;
  owner: string;
  days_since_contact: number;
  suggested_action: string;
}

interface Digest {
  date: string;
  tasks: DigestTask[];
  untouched_deals: UntouchedDeal[];
  progress: { completed: number; total: number };
  simulated?: boolean;
}

// --------------------------------------------------------------------------- //
// Task type icons & colours
// --------------------------------------------------------------------------- //

const TASK_ICON: Record<string, React.ElementType> = {
  email:      Mail,
  call:       Phone,
  whatsapp:   MessageSquare,
  case_study: BookOpen,
  meeting:    Calendar,
  contract:   FileText,
};

const TASK_COLOR: Record<string, string> = {
  email:      "text-blue-400 bg-blue-500/10",
  call:       "text-emerald-400 bg-emerald-500/10",
  whatsapp:   "text-green-400 bg-green-500/10",
  case_study: "text-violet-400 bg-violet-500/10",
  meeting:    "text-amber-400 bg-amber-500/10",
  contract:   "text-orange-400 bg-orange-500/10",
};

// --------------------------------------------------------------------------- //
// Task row
// --------------------------------------------------------------------------- //

function TaskRow({ task, onToggle }: { task: DigestTask; onToggle: (id: string) => void }) {
  const Icon = TASK_ICON[task.task_type] ?? Circle;
  const colorClass = TASK_COLOR[task.task_type] ?? "text-muted-foreground bg-secondary/50";

  return (
    <div
      className={cn(
        "flex items-start gap-3 rounded-xl border p-4 transition-all duration-200",
        task.is_completed
          ? "border-border/20 bg-card/20 opacity-60"
          : "border-border/30 bg-card/60 hover:border-border/50"
      )}
    >
      {/* Complete button */}
      <button
        onClick={() => onToggle(task.id)}
        className="mt-0.5 shrink-0 transition-colors"
        aria-label={task.is_completed ? "Mark as incomplete" : "Mark as done"}
      >
        {task.is_completed
          ? <CheckCircle2 className="h-5 w-5 text-health-green" />
          : <Circle className="h-5 w-5 text-muted-foreground/40 hover:text-muted-foreground" />
        }
      </button>

      {/* Task type badge */}
      <div className={cn("mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg", colorClass)}>
        <Icon className="h-3.5 w-3.5" />
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap mb-1">
          <span className={cn(
            "text-[11px] font-semibold uppercase tracking-wide",
            task.is_completed ? "text-muted-foreground/50" : colorClass.split(" ")[0]
          )}>
            {task.task_type_label}
          </span>
          <span className="text-[11px] text-muted-foreground/60">{task.company}</span>
          {task.amount_fmt && (
            <Badge variant="outline" className="text-[10px] h-4 px-1.5 border-border/30 text-muted-foreground/60">
              {task.amount_fmt}
            </Badge>
          )}
          {task.stage && (
            <Badge variant="outline" className="text-[10px] h-4 px-1.5 border-border/30 text-muted-foreground/40">
              {task.stage}
            </Badge>
          )}
        </div>
        <p className={cn(
          "text-sm leading-relaxed",
          task.is_completed ? "line-through text-muted-foreground/40" : "text-foreground"
        )}>
          {task.task_text}
        </p>
        {task.is_completed && task.completed_at && (
          <p className="text-[11px] text-muted-foreground/40 mt-1">
            Completed {new Date(task.completed_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
          </p>
        )}
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Untouched deal row
// --------------------------------------------------------------------------- //

function UntouchedRow({ deal }: { deal: UntouchedDeal }) {
  const urgency = deal.days_since_contact >= 60 ? "text-health-red" : "text-amber-400";

  return (
    <div className="flex items-start gap-3 rounded-xl border border-border/20 bg-card/30 p-4">
      <AlertTriangle className={cn("mt-0.5 h-4 w-4 shrink-0", urgency)} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap mb-1">
          <span className="text-sm font-semibold text-foreground">{deal.deal_name}</span>
          {deal.amount_fmt && (
            <Badge variant="outline" className="text-[10px] h-4 px-1.5 border-border/30 text-muted-foreground/60">
              {deal.amount_fmt}
            </Badge>
          )}
          <Badge variant="outline" className="text-[10px] h-4 px-1.5 border-border/30 text-muted-foreground/40">
            {deal.stage}
          </Badge>
        </div>
        <div className="flex items-center gap-2 mb-1.5 flex-wrap">
          <span className="text-xs text-muted-foreground">{deal.company}</span>
          {deal.owner && <span className="text-xs text-muted-foreground/50">· {deal.owner}</span>}
          <span className={cn("text-xs font-semibold", urgency)}>
            {deal.days_since_contact} days silent
          </span>
        </div>
        <p className="text-xs text-muted-foreground/70">{deal.suggested_action}</p>
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Progress bar
// --------------------------------------------------------------------------- //

function ProgressBar({ completed, total }: { completed: number; total: number }) {
  const pct = total > 0 ? Math.round((completed / total) * 100) : 0;
  return (
    <div className="flex items-center gap-3">
      <span className="text-sm text-muted-foreground">
        <span className="font-semibold text-foreground">{completed}</span> of{" "}
        <span className="font-semibold text-foreground">{total}</span> tasks completed today
      </span>
      <div className="flex-1 max-w-48 h-1.5 rounded-full bg-secondary/60 overflow-hidden">
        <div
          className="h-full rounded-full bg-primary transition-all duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs text-muted-foreground">{pct}%</span>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Skeleton
// --------------------------------------------------------------------------- //

function SkeletonRow() {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-border/20 bg-card/40 p-4 animate-pulse">
      <div className="mt-0.5 h-5 w-5 rounded-full bg-secondary/60 shrink-0" />
      <div className="mt-0.5 h-7 w-7 rounded-lg bg-secondary/60 shrink-0" />
      <div className="flex-1 space-y-2">
        <div className="h-3 w-32 rounded bg-secondary/60" />
        <div className="h-4 w-3/4 rounded bg-secondary/40" />
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Page
// --------------------------------------------------------------------------- //

export default function DigestPage() {
  const [digest, setDigest] = useState<Digest | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getTodayDigest();
      setDigest(data);
    } catch (e: any) {
      setError(e?.message || "Failed to load digest");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleToggle = useCallback(async (taskId: string) => {
    if (!digest) return;

    // Optimistic update
    setDigest(prev => {
      if (!prev) return prev;
      const tasks = prev.tasks.map(t =>
        t.id === taskId
          ? { ...t, is_completed: !t.is_completed, completed_at: !t.is_completed ? new Date().toISOString() : null }
          : t
      );
      const completed = tasks.filter(t => t.is_completed).length;
      return { ...prev, tasks, progress: { ...prev.progress, completed } };
    });

    try {
      await api.completeDigestTask(taskId);
    } catch {
      // Revert on failure
      setDigest(prev => {
        if (!prev) return prev;
        const tasks = prev.tasks.map(t =>
          t.id === taskId
            ? { ...t, is_completed: !t.is_completed, completed_at: t.is_completed ? null : t.completed_at }
            : t
        );
        const completed = tasks.filter(t => t.is_completed).length;
        return { ...prev, tasks, progress: { ...prev.progress, completed } };
      });
      toast.error("Could not save — try again");
    }
  }, [digest]);

  const todayLabel = new Date().toLocaleDateString("en-GB", {
    weekday: "long", day: "numeric", month: "long", year: "numeric",
  });

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <div className="border-b border-border/40 px-6 py-4">
        <div className="max-w-3xl mx-auto flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <Clock className="h-4 w-4 text-primary" />
              <span className="text-xs font-semibold text-primary uppercase tracking-wide">Daily Digest</span>
            </div>
            <h1 className="text-xl font-bold text-foreground">{todayLabel}</h1>
            {digest && !loading && (
              <div className="mt-2">
                <ProgressBar completed={digest.progress.completed} total={digest.progress.total} />
              </div>
            )}
          </div>
          {digest?.simulated && (
            <Badge variant="outline" className="text-[10px] border-amber-500/30 text-amber-400/70 shrink-0">
              Demo data
            </Badge>
          )}
        </div>
      </div>

      <div className="max-w-3xl mx-auto px-6 py-6 space-y-8">
        {error && (
          <div className="rounded-xl border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {error} — <button className="underline" onClick={load}>retry</button>
          </div>
        )}

        {/* Section 1 — Tasks */}
        <section>
          <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">
            Today's Tasks
          </h2>
          <div className="space-y-2">
            {loading
              ? Array.from({ length: 5 }).map((_, i) => <SkeletonRow key={i} />)
              : digest?.tasks.length
                ? digest.tasks.map(t => (
                    <TaskRow key={t.id} task={t} onToggle={handleToggle} />
                  ))
                : (
                    <div className="rounded-xl border border-border/20 bg-card/30 p-6 text-center">
                      <CheckCircle2 className="h-8 w-8 text-health-green mx-auto mb-2" />
                      <p className="text-sm text-muted-foreground">No tasks generated — your pipeline looks healthy.</p>
                    </div>
                  )
            }
          </div>
        </section>

        {/* Section 2 — Untouched deals */}
        {(loading || (digest?.untouched_deals?.length ?? 0) > 0) && (
          <section>
            <div className="flex items-center gap-2 mb-3">
              <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                Deals needing attention — no contact in 30+ days
              </h2>
              {!loading && digest && (
                <Badge variant="outline" className="text-[10px] h-4 px-1.5 border-amber-500/30 text-amber-400/70">
                  {digest.untouched_deals.length}
                </Badge>
              )}
            </div>
            <div className="space-y-2">
              {loading
                ? Array.from({ length: 4 }).map((_, i) => <SkeletonRow key={i} />)
                : digest?.untouched_deals.map(d => (
                    <UntouchedRow key={d.deal_id} deal={d} />
                  ))
              }
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
