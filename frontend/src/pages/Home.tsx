import { useEffect, useState, useMemo } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { useSession } from "@/contexts/SessionContext";
import { useToast } from "@/hooks/use-toast";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import EmailComposer from "@/components/email/EmailComposer";
import {
  Mail,
  Sparkles,
  AlertTriangle,
  CheckCircle,
  Clock,
  Zap,
  ChevronRight,
  X,
  AlarmClockOff,
  Database,
  Search,
  Filter,
  ChevronDown,
  Flame,
  RefreshCw,
  Send,
  MessageSquare,
  Phone,
  Eye,
  SkipForward,
  PartyPopper,
} from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

// ── Types ─────────────────────────────────────────────────────────────────────

interface Action {
  id: string;
  type: string;
  deal_id: string;
  deal_name: string;
  company: string;
  amount: number;
  stage: string;
  urgency_score: number;
  health_label?: string;
  days_since_contact?: number;
  context: string;
  suggested_action: string;
  draft?: string;
}

interface PendingUpdate {
  id: string;
  deal_id: string;
  deal_name?: string;
  field_name: string;
  old_value?: string;
  new_value: string;
  confidence: string;
  context?: string;
}

type FilterType = "all" | "email" | "call" | "zombie" | "follow_up";

// ── Helpers ───────────────────────────────────────────────────────────────────

function greeting(name: string): string {
  const h = new Date().getHours();
  const salutation = h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
  return `${salutation}, ${name.split(" ")[0]}`;
}

function formatCurrency(val: number): string {
  if (val >= 1_000_000) return `$${(val / 1_000_000).toFixed(1)}M`;
  if (val >= 1_000) return `$${Math.round(val / 1_000)}K`;
  return `$${val}`;
}

/** Time-ago with color tier based on days */
function timeAgoLabel(days?: number): { text: string; className: string } | null {
  if (days == null) return null;
  if (days > 60)  return { text: `${days}d ago`, className: "text-health-red" };
  if (days > 14)  return { text: `${days}d ago`, className: "text-health-yellow" };
  return { text: `${days}d ago`, className: "text-muted-foreground/50" };
}

/** Card border + bg based on health_label (real deal health, not just urgency score) */
function cardStyle(action: Action): string {
  const label = action.health_label;
  if (label === "critical" || action.urgency_score >= 90)
    return "border-health-red/30 bg-health-red/5";
  if (label === "at_risk" || action.urgency_score >= 60)
    return "border-health-orange/25 bg-health-orange/4";
  if (label === "watching")
    return "border-health-yellow/25 bg-health-yellow/4";
  return "border-border/40 bg-card/40";
}

/** Dot color for section headers */
function sectionDot(group: "critical" | "at_risk" | "opportunity"): string {
  if (group === "critical")   return "bg-health-red";
  if (group === "at_risk")    return "bg-health-orange";
  return "bg-health-green";
}

/** Dynamic CTA label + icon based on deal type/context */
function ctaConfig(action: Action): { label: string; icon: React.ElementType } {
  const type = action.type?.toLowerCase() ?? "";
  const days = action.days_since_contact ?? 0;

  if (type.includes("zombie") || days > 90)
    return { label: "Revive Deal", icon: Flame };
  if (type.includes("follow_up") || type.includes("no_response") || days > 30)
    return { label: "Send Follow-up", icon: Send };
  if (type.includes("call"))
    return { label: "Prep Call Brief", icon: Phone };
  if (type.includes("proposal") || type.includes("price"))
    return { label: "Send Proposal", icon: Send };
  if (action.draft)
    return { label: "Review Draft", icon: Eye };
  return { label: "Draft Email", icon: Mail };
}

const SNOOZE_OPTIONS = [
  { label: "Tomorrow",  hours: 24 },
  { label: "3 Days",    hours: 72 },
  { label: "1 Week",    hours: 168 },
];

const SECTION_LABELS: Record<string, string> = {
  critical:    "Critical — Needs Immediate Attention",
  at_risk:     "At Risk — Follow Up Soon",
  opportunity: "On Track — Proactive Actions",
};

// localStorage key for collapsed sections
const LS_COLLAPSED = "home_collapsed_sections";

// ── Component ─────────────────────────────────────────────────────────────────

export default function Home() {
  const { session } = useSession();
  const { toast } = useToast();

  const [actions, setActions]               = useState<Action[]>([]);
  const [pendingUpdates, setPendingUpdates] = useState<PendingUpdate[]>([]);
  const [loading, setLoading]               = useState(true);
  const [dismissed, setDismissed]           = useState<Set<string>>(new Set());
  const [snoozed, setSnoozed]               = useState<Set<string>>(new Set());
  const [composer, setComposer]             = useState<{ dealId: string; dealName: string; draft?: string } | null>(null);
  const [search, setSearch]                 = useState("");
  const [filterType, setFilterType]         = useState<FilterType>("all");
  const [collapsed, setCollapsed]           = useState<Set<string>>(() => {
    try {
      const stored = localStorage.getItem(LS_COLLAPSED);
      return stored ? new Set(JSON.parse(stored)) : new Set();
    } catch { return new Set(); }
  });

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;

    Promise.all([
      api.getTodayActions(controller.signal),
      api.getPendingCrmUpdates(controller.signal),
    ])
      .then(([actionsData, updatesData]) => {
        if (cancelled) return;
        setActions(actionsData.actions ?? []);
        setPendingUpdates(updatesData.updates ?? []);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof DOMException && err.name === "AbortError") return;
        if (err instanceof Error && err.name === "AbortError") return;
        toast({ title: "Couldn't load your day", description: "Please refresh to try again.", variant: "destructive" });
      })
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; controller.abort(); };
  }, []);

  // Persist collapsed state to localStorage
  function toggleCollapse(group: string) {
    setCollapsed((prev) => {
      const next = new Set(prev);
      next.has(group) ? next.delete(group) : next.add(group);
      try { localStorage.setItem(LS_COLLAPSED, JSON.stringify([...next])); } catch {}
      return next;
    });
  }

  const visibleActions = useMemo(() => {
    let list = actions.filter((a) => !dismissed.has(a.id) && !snoozed.has(a.id));

    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter(
        (a) =>
          a.deal_name.toLowerCase().includes(q) ||
          a.company?.toLowerCase().includes(q) ||
          a.context.toLowerCase().includes(q)
      );
    }

    if (filterType !== "all") {
      list = list.filter((a) => {
        const t = a.type?.toLowerCase() ?? "";
        if (filterType === "email")      return t.includes("email") || t.includes("draft");
        if (filterType === "call")       return t.includes("call");
        if (filterType === "zombie")     return t.includes("zombie") || (a.days_since_contact ?? 0) > 90;
        if (filterType === "follow_up")  return t.includes("follow") || t.includes("no_response");
        return true;
      });
    }

    return list;
  }, [actions, dismissed, snoozed, search, filterType]);

  const snoozedActions = useMemo(
    () => actions.filter((a) => snoozed.has(a.id)),
    [actions, snoozed]
  );

  // Grouping: critical (score≥80 or health_label=critical), at_risk, opportunity
  const groups = useMemo(() => {
    const critical    = visibleActions.filter((a) => a.health_label === "critical" || a.urgency_score >= 80);
    const at_risk     = visibleActions.filter((a) => !critical.includes(a) && (a.health_label === "at_risk" || a.urgency_score >= 50));
    const opportunity = visibleActions.filter((a) => !critical.includes(a) && !at_risk.includes(a));
    return { critical, at_risk, opportunity };
  }, [visibleActions]);

  const atRiskValue = visibleActions.reduce((sum, a) => sum + (a.amount || 0), 0);
  const displayName = session?.display_name ?? "there";

  async function handleDismiss(id: string) {
    setDismissed((prev) => new Set([...prev, id]));
    await api.dismissAction(id).catch(() => null);
  }

  async function handleSnooze(id: string, hours: number) {
    setSnoozed((prev) => new Set([...prev, id]));
    await api.snoozeAction(id).catch(() => null);
    const label = hours <= 24 ? "tomorrow" : hours <= 72 ? "in 3 days" : "in a week";
    toast({ title: `Snoozed — reappears ${label}` });
  }

  async function handleApproveUpdate(id: string) {
    await api.approveCrmUpdate(id).catch(() => null);
    setPendingUpdates((prev) => prev.filter((u) => u.id !== id));
    toast({ title: "CRM updated", description: "Field update applied to Zoho." });
  }

  async function handleRejectUpdate(id: string) {
    await api.rejectCrmUpdate(id).catch(() => null);
    setPendingUpdates((prev) => prev.filter((u) => u.id !== id));
  }

  return (
    <>
      <div className="min-h-screen bg-background">

        {/* ── Hero Header ── */}
        <div className="relative overflow-hidden border-b border-border/40 bg-gradient-to-r from-primary/5 via-background to-accent/5 px-6 py-5">
          <div className="max-w-5xl mx-auto">
            <div className="flex items-center justify-between gap-4">
              <div>
                <h1 className="text-lg font-semibold text-foreground">{greeting(displayName)}</h1>
                <p className="text-xs text-muted-foreground mt-0.5">
                  {loading ? "Loading your day…" : "Here's what needs your attention today."}
                </p>
              </div>

              {/* Stat pills */}
              {!loading && (
                <div className="hidden sm:flex items-center gap-2 flex-wrap justify-end">
                  {groups.critical.length > 0 && (
                    <span className="inline-flex items-center gap-1.5 rounded-full border border-health-red/30 bg-health-red/10 px-3 py-1 text-[11px] font-semibold text-health-red">
                      <span className="h-1.5 w-1.5 rounded-full bg-health-red animate-pulse" />
                      {groups.critical.length} Critical
                    </span>
                  )}
                  {groups.at_risk.length > 0 && (
                    <span className="inline-flex items-center gap-1.5 rounded-full border border-health-orange/30 bg-health-orange/10 px-3 py-1 text-[11px] font-semibold text-health-orange">
                      {groups.at_risk.length} At Risk
                    </span>
                  )}
                  {atRiskValue > 0 && (
                    <span className="inline-flex items-center gap-1.5 rounded-full border border-border/40 bg-secondary/50 px-3 py-1 text-[11px] font-semibold text-foreground/70">
                      {formatCurrency(atRiskValue)} at risk
                    </span>
                  )}
                  {pendingUpdates.length > 0 && (
                    <span className="inline-flex items-center gap-1.5 rounded-full border border-blue-400/30 bg-blue-400/10 px-3 py-1 text-[11px] font-semibold text-blue-400">
                      {pendingUpdates.length} CRM updates
                    </span>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="max-w-5xl mx-auto px-6 py-5 space-y-5">

          {/* ── Search + Filter bar ── */}
          {!loading && visibleActions.length > 0 && (
            <div className="flex items-center gap-2">
              <div className="relative flex-1 max-w-xs">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground/50" />
                <input
                  type="text"
                  placeholder="Search deals…"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="h-8 w-full rounded-lg border border-border/40 bg-secondary/30 pl-8 pr-3 text-xs text-foreground placeholder:text-muted-foreground/40 focus:border-border/70 focus:outline-none focus:ring-0"
                />
              </div>

              <div className="flex items-center gap-1.5">
                {(["all", "email", "call", "zombie", "follow_up"] as FilterType[]).map((f) => (
                  <button
                    key={f}
                    onClick={() => setFilterType(f)}
                    className={cn(
                      "h-7 rounded-md px-2.5 text-[11px] font-medium transition-colors",
                      filterType === f
                        ? "bg-primary/15 text-primary"
                        : "text-muted-foreground/60 hover:text-foreground hover:bg-secondary/50"
                    )}
                  >
                    {f === "all" ? "All" : f === "follow_up" ? "Follow-up" : f.charAt(0).toUpperCase() + f.slice(1)}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* ── Pending CRM Updates Banner ── */}
          {!loading && pendingUpdates.length > 0 && (
            <section>
              <div className="flex items-center gap-2 mb-2">
                <Database className="h-4 w-4 text-blue-400" />
                <h2 className="text-sm font-semibold text-foreground">CRM Updates Awaiting Approval</h2>
                <Badge variant="outline" className="ml-auto text-[10px] h-4 px-1.5 text-blue-400 border-blue-400/30 bg-blue-400/10">
                  {pendingUpdates.length} pending
                </Badge>
              </div>
              <div className="space-y-2">
                {pendingUpdates.map((u) => (
                  <div
                    key={u.id}
                    className="flex items-center gap-3 rounded-xl border border-blue-400/20 bg-blue-400/5 px-4 py-3"
                  >
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-semibold text-foreground">
                        {u.deal_name || u.deal_id} — <span className="font-normal text-muted-foreground">{u.field_name}</span>
                      </p>
                      <p className="text-[11px] text-muted-foreground mt-0.5">
                        {u.old_value ? <><span className="line-through">{u.old_value}</span> → </> : ""}{u.new_value}
                      </p>
                      {u.context && <p className="text-[10px] text-muted-foreground/60 mt-0.5">{u.context}</p>}
                    </div>
                    <Badge variant="outline" className="text-[10px] h-4 px-1.5 shrink-0 capitalize text-muted-foreground">
                      {u.confidence}
                    </Badge>
                    <Button
                      size="sm"
                      variant="outline"
                      className="shrink-0 h-6 px-2 text-[11px] border-health-green/40 text-health-green hover:bg-health-green/10"
                      onClick={() => handleApproveUpdate(u.id)}
                    >
                      Apply
                    </Button>
                    <button
                      className="text-muted-foreground/40 hover:text-muted-foreground shrink-0"
                      onClick={() => handleRejectUpdate(u.id)}
                      aria-label="Reject update"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* ── Main Content ── */}
          {loading ? (
            <div className="space-y-2">
              {[...Array(4)].map((_, i) => (
                <div key={i} className="rounded-xl border border-border/30 bg-card/30 px-4 py-3 space-y-2 animate-pulse">
                  <Skeleton className="h-4 w-48" />
                  <Skeleton className="h-3 w-full" />
                  <Skeleton className="h-3 w-3/4" />
                  <div className="flex gap-2 pt-1">
                    <Skeleton className="h-7 w-28 rounded-md" />
                    <Skeleton className="h-7 w-16 rounded-md" />
                  </div>
                </div>
              ))}
            </div>
          ) : visibleActions.length === 0 && !search && filterType === "all" ? (
            /* All clear empty state */
            <div className="flex flex-col items-center gap-3 rounded-xl border border-border/30 bg-card/40 px-6 py-14">
              <PartyPopper className="h-10 w-10 text-health-green/60" />
              <p className="text-sm font-semibold text-foreground">All caught up!</p>
              <p className="text-xs text-muted-foreground text-center max-w-xs">
                No critical or at-risk deals need your attention right now. Check back later or explore your pipeline.
              </p>
              <Link
                to="/dashboard"
                className="mt-1 inline-flex items-center gap-1.5 text-xs text-primary hover:underline"
              >
                View full pipeline <ChevronRight className="h-3 w-3" />
              </Link>
            </div>
          ) : visibleActions.length === 0 ? (
            /* No search results */
            <div className="flex flex-col items-center gap-2 rounded-xl border border-border/30 bg-card/40 px-6 py-10">
              <Search className="h-7 w-7 text-muted-foreground/30" />
              <p className="text-sm text-muted-foreground">No actions match your filter.</p>
              <button
                className="text-xs text-primary hover:underline"
                onClick={() => { setSearch(""); setFilterType("all"); }}
              >
                Clear filters
              </button>
            </div>
          ) : (
            <div className="space-y-4">
              {(["critical", "at_risk", "opportunity"] as const).map((group) => {
                const list = groups[group];
                if (list.length === 0) return null;
                const isCollapsed = collapsed.has(group);

                return (
                  <section key={group}>
                    {/* Sticky section header */}
                    <button
                      onClick={() => toggleCollapse(group)}
                      className="sticky top-0 z-10 w-full flex items-center gap-2 rounded-lg bg-background/90 px-2 py-1.5 backdrop-blur-sm mb-2 hover:bg-secondary/30 transition-colors"
                    >
                      <span className={cn("h-1.5 w-1.5 rounded-full shrink-0", sectionDot(group))} />
                      <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground/60 flex-1 text-left">
                        {SECTION_LABELS[group]} · {list.length}
                      </span>
                      <ChevronDown className={cn("h-3.5 w-3.5 text-muted-foreground/40 transition-transform", isCollapsed && "-rotate-90")} />
                    </button>

                    {!isCollapsed && (
                      <div className="space-y-2">
                        {list.map((action) => (
                          <ActionCard
                            key={action.id}
                            action={action}
                            onEmail={() => setComposer({ dealId: action.deal_id, dealName: action.deal_name, draft: action.draft })}
                            onDismiss={() => handleDismiss(action.id)}
                            onSnooze={(hours) => handleSnooze(action.id, hours)}
                          />
                        ))}
                      </div>
                    )}
                  </section>
                );
              })}
            </div>
          )}

          {/* ── Snoozed Section ── */}
          {snoozedActions.length > 0 && (
            <section>
              <div className="flex items-center gap-2 mb-2">
                <AlarmClockOff className="h-3.5 w-3.5 text-muted-foreground/40" />
                <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground/40">
                  Snoozed · {snoozedActions.length}
                </span>
              </div>
              <div className="space-y-1.5">
                {snoozedActions.map((a) => (
                  <div key={a.id} className="flex items-center gap-3 rounded-lg border border-border/20 bg-secondary/20 px-3 py-2 opacity-60">
                    <p className="text-xs text-muted-foreground flex-1 truncate">{a.deal_name}</p>
                    <button
                      className="text-[11px] text-primary hover:underline shrink-0"
                      onClick={() => setSnoozed((prev) => { const n = new Set(prev); n.delete(a.id); return n; })}
                    >
                      Unsnooze
                    </button>
                  </div>
                ))}
              </div>
            </section>
          )}

        </div>
      </div>

      {/* Email Composer */}
      {composer && (
        <EmailComposer
          open
          dealId={composer.dealId}
          dealName={composer.dealName}
          onClose={() => setComposer(null)}
        />
      )}
    </>
  );
}

// ── ActionCard ────────────────────────────────────────────────────────────────

function ActionCard({
  action,
  onEmail,
  onDismiss,
  onSnooze,
}: {
  action: Action;
  onEmail: () => void;
  onDismiss: () => void;
  onSnooze: (hours: number) => void;
}) {
  const cta = ctaConfig(action);
  const CtaIcon = cta.icon;
  const timeAgo = timeAgoLabel(action.days_since_contact);

  return (
    <div className={cn("rounded-xl border px-4 py-3 transition-colors hover:border-border/70", cardStyle(action))}>

      {/* Row 1: deal name + badges + dismiss */}
      <div className="flex items-center gap-2 min-w-0">
        <p className="text-sm font-semibold text-foreground truncate flex-1">{action.deal_name}</p>

        <div className="flex items-center gap-1.5 shrink-0">
          {action.stage && (
            <Badge variant="outline" className="text-[10px] h-4 px-1.5 border-border/40 text-muted-foreground">
              {action.stage}
            </Badge>
          )}
          {action.amount > 0 && (
            <span className="text-[10px] text-muted-foreground/50 font-medium tabular-nums">
              {formatCurrency(action.amount)}
            </span>
          )}
          {timeAgo && (
            <span className={cn("text-[10px] font-medium shrink-0", timeAgo.className)}>
              {timeAgo.text}
            </span>
          )}
        </div>

        <button
          className="text-muted-foreground/30 hover:text-muted-foreground shrink-0 ml-1"
          onClick={onDismiss}
          aria-label="Dismiss"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* Row 2: insight text */}
      <p className="text-xs text-muted-foreground mt-1.5 leading-relaxed">{action.context}</p>

      {/* Row 3: action buttons */}
      <div className="flex items-center gap-2 mt-2.5">
        <Button
          size="sm"
          variant="outline"
          className="h-7 px-3 text-xs border-border/50 hover:border-primary/40 hover:text-primary"
          onClick={onEmail}
        >
          <CtaIcon className="mr-1.5 h-3 w-3" />
          {cta.label}
        </Button>

        {/* Snooze dropdown */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button className="flex items-center gap-1 text-[11px] text-muted-foreground/50 hover:text-muted-foreground transition-colors">
              <AlarmClockOff className="h-3 w-3" />
              Snooze
              <ChevronDown className="h-2.5 w-2.5" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-32 border-border/40 bg-card shadow-xl">
            {SNOOZE_OPTIONS.map((opt) => (
              <DropdownMenuItem
                key={opt.label}
                className="text-xs cursor-pointer"
                onClick={() => onSnooze(opt.hours)}
              >
                {opt.label}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>
  );
}
