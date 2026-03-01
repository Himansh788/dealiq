import { useEffect, useState } from "react";
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
  TrendingUp,
  DollarSign,
  Activity,
  CheckCircle,
  Clock,
  Zap,
} from "lucide-react";

// ── Types ─────────────────────────────────────────────────────────────────────

interface Deal {
  id: string;
  deal_name: string;
  company: string;
  stage: string;
  amount: number;
  health_score: number;
  health_label: string;
  owner?: string;
}

interface Metrics {
  total_deals: number;
  total_value: number;
  average_health_score: number;
  at_risk_count: number;
  critical_count: number;
  deals_needing_action: number;
}

interface Todo {
  dealId: string;
  dealName: string;
  company: string;
  health: string;
  score: number;
  amount: number;
  action: string;
  priority: "high" | "medium" | "low";
}

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

function scoreColor(score: number) {
  if (score >= 75) return "text-health-green";
  if (score >= 50) return "text-health-yellow";
  if (score >= 25) return "text-health-orange";
  return "text-health-red";
}

const ACTION_MAP: Record<string, string> = {
  critical: "Urgent: send a recovery email to re-engage stakeholders",
  at_risk:  "Re-engage the champion before this goes quiet",
  watching: "Confirm next step and keep momentum",
  healthy:  "Keep momentum — prepare for stage advancement",
};

const PRIORITY_MAP: Record<string, "high" | "medium" | "low"> = {
  critical: "high",
  at_risk:  "medium",
  watching: "low",
  healthy:  "low",
};

function buildTodos(deals: Deal[]): Todo[] {
  return deals
    .filter((d) => d.health_label === "critical" || d.health_label === "at_risk" || d.health_label === "watching")
    .map((d) => ({
      dealId:   d.id,
      dealName: d.deal_name,
      company:  d.company,
      health:   d.health_label,
      score:    d.health_score,
      amount:   d.amount,
      action:   ACTION_MAP[d.health_label] ?? "Review deal status",
      priority: PRIORITY_MAP[d.health_label] ?? "low",
    }))
    .sort((a, b) => {
      const prio: Record<string, number> = { high: 0, medium: 1, low: 2 };
      return (prio[a.priority] ?? 3) - (prio[b.priority] ?? 3);
    })
    .slice(0, 12);
}

const PRIORITY_STYLE: Record<string, string> = {
  high:   "border-health-red/30 bg-health-red/5",
  medium: "border-health-orange/30 bg-health-orange/5",
  low:    "border-border/30 bg-card/60",
};

const HEALTH_BADGE: Record<string, string> = {
  critical: "border-health-red/30 text-health-red bg-health-red/10",
  at_risk:  "border-health-orange/30 text-health-orange bg-health-orange/10",
  watching: "border-health-yellow/30 text-health-yellow bg-health-yellow/10",
  healthy:  "border-health-green/30 text-health-green bg-health-green/10",
};

const QUICK_LINKS = [
  { href: "/dashboard", icon: TrendingUp,    label: "Pipeline",   desc: "All deals" },
  { href: "/ask",       icon: Sparkles,      label: "Ask DealIQ", desc: "Q&A engine" },
  { href: "/alerts",    icon: AlertTriangle, label: "Alerts",     desc: "Digest feed" },
  { href: "/forecast",  icon: Clock,         label: "Forecast",   desc: "Revenue view" },
] as const;

// ── Component ─────────────────────────────────────────────────────────────────

export default function Home() {
  const { session } = useSession();
  const { toast } = useToast();
  const [deals,    setDeals]    = useState<Deal[]>([]);
  const [metrics,  setMetrics]  = useState<Metrics | null>(null);
  const [loading,  setLoading]  = useState(true);
  const [composer, setComposer] = useState<{ dealId: string; dealName: string } | null>(null);

  const todos = buildTodos(deals);

  useEffect(() => {
    Promise.all([api.getAllDeals(), api.getMetrics()])
      .then(([dealsData, metricsData]) => {
        setDeals(Array.isArray(dealsData) ? dealsData : []);
        setMetrics(metricsData);
      })
      .catch((err: Error) =>
        toast({ title: "Failed to load pipeline", description: err.message, variant: "destructive" })
      )
      .finally(() => setLoading(false));
  }, []);

  const displayName = session?.display_name ?? "there";

  return (
    <>
      <div className="min-h-screen bg-background">

        {/* ── Header ── */}
        <div className="border-b border-border/40 bg-background/95 backdrop-blur-sm px-6 py-4">
          <div className="flex items-center justify-between max-w-5xl mx-auto">
            <div>
              <h1 className="text-lg font-semibold text-foreground">{greeting(displayName)}</h1>
              <p className="text-xs text-muted-foreground mt-0.5">
                {loading
                  ? "Loading pipeline…"
                  : todos.length > 0
                    ? `${todos.length} action${todos.length !== 1 ? "s" : ""} need your attention today`
                    : "Pipeline looks healthy — no urgent actions"}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-violet-500/20">
                <Sparkles className="h-3.5 w-3.5 text-violet-400" />
              </div>
              <span className="text-xs text-muted-foreground">AI-prioritised</span>
            </div>
          </div>
        </div>

        <div className="max-w-5xl mx-auto px-6 py-6 space-y-6">

          {/* ── Metrics strip ── */}
          {loading ? (
            <div className="grid grid-cols-3 gap-3">
              {[0, 1, 2].map((i) => <Skeleton key={i} className="h-16 rounded-xl" />)}
            </div>
          ) : metrics && (
            <div className="grid grid-cols-3 gap-3">
              <MetricCard
                icon={DollarSign}
                label="Pipeline value"
                value={formatCurrency(metrics.total_value)}
                iconClass="text-primary bg-primary/10"
              />
              <MetricCard
                icon={AlertTriangle}
                label="At risk / Critical"
                value={`${(metrics.at_risk_count ?? 0) + (metrics.critical_count ?? 0)} deals`}
                iconClass="text-health-orange bg-health-orange/10"
              />
              <MetricCard
                icon={Activity}
                label="Needs action"
                value={`${metrics.deals_needing_action ?? 0} deals`}
                iconClass="text-health-yellow bg-health-yellow/10"
              />
            </div>
          )}

          {/* ── To-do list ── */}
          <section>
            <div className="flex items-center gap-2 mb-3">
              <Zap className="h-4 w-4 text-violet-400" />
              <h2 className="text-sm font-semibold text-foreground">Today's Actions</h2>
              {!loading && (
                <span className="ml-auto text-[10px] text-muted-foreground/60">
                  Sorted by urgency
                </span>
              )}
            </div>

            {loading ? (
              <div className="space-y-2">
                {[...Array(5)].map((_, i) => <Skeleton key={i} className="h-16 w-full rounded-xl" />)}
              </div>
            ) : todos.length === 0 ? (
              <div className="flex flex-col items-center gap-2 rounded-xl border border-border/30 bg-card/40 px-6 py-10">
                <CheckCircle className="h-8 w-8 text-health-green" />
                <p className="text-sm font-medium text-foreground">All clear — pipeline looks healthy!</p>
                <p className="text-xs text-muted-foreground">No critical or at-risk deals need attention right now.</p>
              </div>
            ) : (
              <div className="space-y-2">
                {todos.map((todo) => (
                  <TodoRow
                    key={todo.dealId}
                    todo={todo}
                    onEmail={() => setComposer({ dealId: todo.dealId, dealName: todo.dealName })}
                  />
                ))}
              </div>
            )}
          </section>

          {/* ── Quick links ── */}
          <section className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {QUICK_LINKS.map(({ href, icon: Icon, label, desc }) => (
              <Link
                key={href}
                to={href}
                className="flex flex-col gap-1.5 rounded-xl border border-border/30 bg-card/40 px-3 py-3 transition-colors hover:border-primary/30 hover:bg-primary/5"
              >
                <Icon className="h-4 w-4 text-muted-foreground" />
                <div>
                  <p className="text-xs font-semibold text-foreground">{label}</p>
                  <p className="text-[10px] text-muted-foreground">{desc}</p>
                </div>
              </Link>
            ))}
          </section>

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

// ── Sub-components ─────────────────────────────────────────────────────────────

function MetricCard({
  icon: Icon,
  label,
  value,
  iconClass,
}: {
  icon: React.ElementType;
  label: string;
  value: string;
  iconClass: string;
}) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-border/30 bg-card/60 px-4 py-3">
      <div className={cn("flex h-8 w-8 items-center justify-center rounded-lg shrink-0", iconClass)}>
        <Icon className="h-4 w-4" />
      </div>
      <div className="min-w-0">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/60 truncate">{label}</p>
        <p className="text-sm font-bold text-foreground">{value}</p>
      </div>
    </div>
  );
}

function TodoRow({ todo, onEmail }: { todo: Todo; onEmail: () => void }) {
  return (
    <div className={cn(
      "flex items-center gap-4 rounded-xl border px-4 py-3 transition-colors",
      PRIORITY_STYLE[todo.priority]
    )}>
      {/* Score ring */}
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border-2 border-border/30 bg-background">
        <span className={cn("text-[11px] font-bold tabular-nums", scoreColor(todo.score))}>
          {todo.score}
        </span>
      </div>

      {/* Deal info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <p className="text-sm font-semibold text-foreground truncate">{todo.dealName}</p>
          <Badge
            variant="outline"
            className={cn("text-[10px] h-4 px-1.5 capitalize shrink-0", HEALTH_BADGE[todo.health])}
          >
            {todo.health.replace("_", " ")}
          </Badge>
          <span className="text-[10px] text-muted-foreground/50 shrink-0">{formatCurrency(todo.amount)}</span>
        </div>
        <p className="text-xs text-muted-foreground mt-0.5">{todo.action}</p>
      </div>

      {/* Action button */}
      <Button
        size="sm"
        variant="outline"
        className="shrink-0 h-7 px-3 text-xs border-border/50 hover:border-primary/40 hover:text-primary"
        onClick={onEmail}
      >
        <Mail className="mr-1.5 h-3 w-3" />
        Write email
      </Button>
    </div>
  );
}
