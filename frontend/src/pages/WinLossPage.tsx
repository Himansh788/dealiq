import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  RadialBarChart,
  RadialBar,
} from "recharts";
import {
  Trophy,
  XCircle,
  TrendingUp,
  TrendingDown,
  ChevronDown,
  Brain,
  MousePointer,
  CheckSquare,
  HelpCircle,
  ArrowRight,
  X,
  Wifi,
  WifiOff,
  AlertTriangle,
  CheckCircle,
  Loader2,
  Lightbulb,
  Eye,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { api, friendlyError } from "@/lib/api";

// ── Custom CSS keyframes ──────────────────────────────────────────────────────

const KEYFRAMES = `
@keyframes wl-slide-up {
  from { opacity: 0; transform: translateY(16px); }
  to   { opacity: 1; transform: translateY(0);    }
}
@keyframes wl-shimmer {
  0%   { background-position: -400% center; }
  100% { background-position:  400% center; }
}
@keyframes wl-badge-pulse {
  0%, 85%, 100% { transform: scale(1);    }
  92%           { transform: scale(1.04); }
}
`;

// ── Types ─────────────────────────────────────────────────────────────────────

interface WinLossEntry {
  deal_id: string;
  deal_name: string;
  amount: number;
  outcome: "won" | "lost";
  analyzed_at: string;
  primary_reason: string;
  contributing_factors?: string[];
  success_signals?: string[];
  warning_signs_missed?: string[];
  deal_pattern: string;
  lesson: string;
  grade?: string;
  auto_detected?: boolean;
}

interface BoardSummary {
  count: number;
  avg_amount: number;
  top_pattern: string;
  pattern_counts: Record<string, number>;
}

interface Board {
  summary: { won: BoardSummary; lost: BoardSummary };
  deals: WinLossEntry[];
  auto_analyzed_count?: number;
}

// ── Demo data (shown when board is empty and user hasn't dismissed) ───────────

const DEMO_DEALS: WinLossEntry[] = [
  {
    deal_id: "demo_1",
    deal_name: "Acme Corp",
    amount: 48000,
    outcome: "won",
    analyzed_at: new Date(Date.now() - 1000 * 60 * 60 * 2).toISOString(),
    primary_reason: "Strong champion + executive alignment secured before procurement",
    contributing_factors: [
      "Champion had budget authority and board visibility",
      "Ran multi-threaded executive alignment in week 2",
      "Tied close date to their Q1 deployment deadline",
    ],
    success_signals: [
      "Champion introduced us to CFO unprompted",
      "Legal engaged 3 weeks before expected",
      "Security review completed without blockers",
    ],
    deal_pattern: "strong_champion",
    lesson: "Always identify your champion in week 1 and test their influence early.",
    grade: "A",
  },
  {
    deal_id: "demo_2",
    deal_name: "FinanceFlow",
    amount: 92000,
    outcome: "lost",
    analyzed_at: new Date(Date.now() - 1000 * 60 * 60 * 5).toISOString(),
    primary_reason: "Single-threaded — lost access to decision maker after reorg",
    contributing_factors: [
      "Only one contact maintained throughout the cycle",
      "Champion changed roles and lost budget ownership",
      "No relationship with economic buyer before evaluation",
    ],
    warning_signs_missed: [
      "Champion stopped scheduling calls in week 6",
      "Emails went unread for 11 days before reorg announcement",
      "No visibility into internal champion communication",
    ],
    deal_pattern: "single_threaded",
    lesson: "Multi-thread above the champion by week 3 — one contact is a single point of failure.",
    grade: "D",
  },
  {
    deal_id: "demo_3",
    deal_name: "TechNova",
    amount: 31000,
    outcome: "won",
    analyzed_at: new Date(Date.now() - 1000 * 60 * 60 * 24).toISOString(),
    primary_reason: "Created urgency around Q1 budget deadline with concrete ROI model",
    contributing_factors: [
      "Mapped close date to buyer's fiscal calendar expiry",
      "Delivered ROI model showing $180K first-year savings",
      "Offered implementation support as limited-time incentive",
    ],
    success_signals: [
      "Buyer referenced our close date in their board deck",
      "Legal fast-tracked review to hit Q1",
      "Champion asked for onboarding timeline before signing",
    ],
    deal_pattern: "urgency_created",
    lesson: "Tie your close date to the buyer's fiscal calendar and quantify the cost of delay.",
    grade: "B",
  },
  {
    deal_id: "demo_4",
    deal_name: "GlobalRetail",
    amount: 67000,
    outcome: "lost",
    analyzed_at: new Date(Date.now() - 1000 * 60 * 60 * 36).toISOString(),
    primary_reason: "Competitor undercut on price at final stage before we established differentiation",
    contributing_factors: [
      "Value conversation never landed with economic buyer",
      "Procurement drove final evaluation on price only",
      "Differentiation framing came too late in the cycle",
    ],
    warning_signs_missed: [
      "Procurement entered the conversation in week 7",
      "Champion stopped advocating internally after pricing call",
      "No multi-year TCO comparison prepared before final call",
    ],
    deal_pattern: "competitor_win",
    lesson: "Establish differentiation with the economic buyer before procurement gets involved.",
    grade: "C",
  },
];

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatCurrency(val: number): string {
  if (val >= 1_000_000) return `$${(val / 1_000_000).toFixed(1)}M`;
  if (val >= 1_000) return `$${Math.round(val / 1_000)}K`;
  return `$${val}`;
}

function humanPattern(p: string): string {
  return p.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function buildChartData(
  wonCounts: Record<string, number>,
  lostCounts: Record<string, number>
): { pattern: string; Won: number; Lost: number }[] {
  const allPatterns = new Set([...Object.keys(wonCounts), ...Object.keys(lostCounts)]);
  return Array.from(allPatterns).map((p) => ({
    pattern: humanPattern(p),
    Won: wonCounts[p] ?? 0,
    Lost: lostCounts[p] ?? 0,
  }));
}

function computeSummary(deals: WinLossEntry[]): BoardSummary {
  const counts: Record<string, number> = {};
  for (const d of deals) counts[d.deal_pattern] = (counts[d.deal_pattern] ?? 0) + 1;
  const topPattern =
    Object.entries(counts).sort((a, b) => b[1] - a[1])[0]?.[0] ?? "";
  const avgAmount = deals.length
    ? Math.round(deals.reduce((s, d) => s + d.amount, 0) / deals.length)
    : 0;
  return { count: deals.length, avg_amount: avgAmount, top_pattern: topPattern, pattern_counts: counts };
}

// ── useCountUp hook ───────────────────────────────────────────────────────────

function useCountUp(target: number, durationMs = 1200, active = true): number {
  const [value, setValue] = useState(0);
  useEffect(() => {
    if (!active) return;
    if (target === 0) { setValue(0); return; }
    const steps = 40;
    const stepDuration = durationMs / steps;
    let current = 0;
    const id = setInterval(() => {
      current += 1;
      const eased = 1 - Math.pow(1 - current / steps, 3);
      setValue(Math.round(eased * target));
      if (current >= steps) clearInterval(id);
    }, stepDuration);
    return () => clearInterval(id);
  }, [target, durationMs, active]);
  return value;
}

// ── Grade badge ───────────────────────────────────────────────────────────────

function GradeBadge({ grade }: { grade: string }) {
  const colors: Record<string, string> = {
    A: "border-emerald-400/30 bg-emerald-400/10 text-emerald-400",
    B: "border-sky-400/30 bg-sky-400/10 text-sky-400",
    C: "border-amber-400/30 bg-amber-400/10 text-amber-400",
    D: "border-orange-400/30 bg-orange-400/10 text-orange-400",
    F: "border-health-red/30 bg-health-red/10 text-health-red",
  };
  return (
    <span className={cn(
      "inline-flex h-9 w-9 items-center justify-center rounded-lg border text-base font-bold shrink-0",
      colors[grade.toUpperCase()] ?? colors.C
    )}>
      {grade}
    </span>
  );
}

// ── Animated metric card ──────────────────────────────────────────────────────

function AnimatedMetricCard({
  outcome,
  summary,
  delay = 0,
  animated = true,
}: {
  outcome: "won" | "lost";
  summary: BoardSummary;
  delay?: number;
  animated?: boolean;
}) {
  const isWon = outcome === "won";
  const animCount = useCountUp(summary.count, 1200, animated);
  const animAvg = useCountUp(summary.avg_amount, 1200, animated);
  const displayCount = animated ? animCount : summary.count;
  const displayAvg = animated ? animAvg : summary.avg_amount;

  const wonBorderColor = "border-l-[#10b981]";
  const lostBorderColor = "border-l-[#F26A4F]";

  return (
    <div
      className={cn(
        "flex flex-col gap-3 rounded-xl border bg-card p-5 cursor-default",
        "transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md",
        "border-l-4 border-border/40",
        isWon ? wonBorderColor : lostBorderColor
      )}
      style={{ animation: `wl-slide-up 0.4s ease both`, animationDelay: `${delay}ms` }}
    >
      <div className="flex items-center gap-2">
        {isWon
          ? <Trophy className="h-5 w-5 text-emerald-500" />
          : <XCircle className="h-5 w-5" style={{ color: "#F26A4F" }} />}
        <span className={cn("text-sm font-semibold", isWon ? "text-emerald-600 dark:text-emerald-400" : "text-foreground")}>
          {isWon ? "Deals Won" : "Deals Lost"}
        </span>
      </div>
      <div className="flex items-end gap-6">
        <div>
          <p className="text-3xl font-bold tabular-nums text-foreground">
            {displayCount}
          </p>
          <p className="text-xs text-muted-foreground">deals</p>
        </div>
        {summary.avg_amount > 0 && (
          <div>
            <p className="text-xl font-semibold text-foreground tabular-nums">{formatCurrency(displayAvg)}</p>
            <p className="text-xs text-muted-foreground">avg deal size</p>
          </div>
        )}
      </div>
      {summary.top_pattern && (
        <div className="flex items-center gap-1.5">
          {isWon
            ? <TrendingUp className="h-3.5 w-3.5 text-muted-foreground/50" />
            : <TrendingDown className="h-3.5 w-3.5 text-muted-foreground/50" />}
          <span className="text-xs text-muted-foreground">
            Top pattern:{" "}
            <span className="font-medium text-foreground/80">{humanPattern(summary.top_pattern)}</span>
          </span>
        </div>
      )}
    </div>
  );
}

// ── Deal card ─────────────────────────────────────────────────────────────────

function DealCard({ entry, index = 0 }: { entry: WinLossEntry; index?: number }) {
  const [expanded, setExpanded] = useState(false);
  const isWon = entry.outcome === "won";
  const signals = entry.success_signals ?? entry.warning_signs_missed ?? [];

  return (
    <div
      className={cn(
        "rounded-lg border bg-card transition-all duration-150 hover:bg-muted/20",
        isWon
          ? "border-l-[3px] border-l-emerald-500 border-border/30"
          : "border-l-[3px] border-border/30"
      )}
      style={{
        animation: `wl-slide-up 0.35s ease both`,
        animationDelay: `${index * 80}ms`,
        ...(!isWon ? { borderLeftColor: "#F26A4F" } : {}),
      }}
    >
      {/* Card header */}
      <button
        className="flex w-full items-start gap-3 px-4 py-3 text-left"
        onClick={() => setExpanded((v) => !v)}
      >
        <div className="mt-0.5 shrink-0">
          {isWon
            ? <Trophy className="h-4 w-4 text-emerald-400" />
            : <XCircle className="h-4 w-4 text-rose-400" />}
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-semibold text-foreground">{entry.deal_name}</span>

            {/* Outcome badge */}
            <span
              className={cn(
                "inline-flex items-center rounded-md border px-2 py-0.5 text-[10px] font-bold tracking-wide",
                isWon
                  ? "border-emerald-500/25 bg-emerald-500/8 text-emerald-600 dark:text-emerald-400"
                  : "border-orange-400/25 bg-orange-400/8 text-orange-600 dark:text-orange-400"
              )}
              style={isWon ? { animation: "wl-badge-pulse 3s ease infinite" } : undefined}
            >
              {isWon ? "WON" : "LOST"}
            </span>

            {entry.amount > 0 && (
              <span className="text-xs text-muted-foreground tabular-nums">{formatCurrency(entry.amount)}</span>
            )}

            <span className="text-[10px] text-muted-foreground/40 ml-auto">{humanPattern(entry.deal_pattern)}</span>
          </div>

          <p className="mt-1 text-xs text-muted-foreground">{entry.primary_reason}</p>

          {/* Auto-detected label */}
          {entry.auto_detected && (
            <p className="mt-0.5 text-[10px] italic text-muted-foreground/40">
              Auto-detected from Zoho
            </p>
          )}
        </div>

        {/* Rotating chevron */}
        <ChevronDown
          className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground/40 transition-transform duration-200"
          style={{ transform: expanded ? "rotate(180deg)" : "rotate(0deg)" }}
        />
      </button>

      {/* Expanded detail — max-height transition */}
      <div
        style={{
          maxHeight: expanded ? "520px" : "0",
          overflow: "hidden",
          transition: "max-height 0.3s ease",
        }}
      >
        <div className="border-t border-border/20 px-4 py-3 space-y-3">
          {/* Grade + lesson */}
          <div className="flex items-start gap-3">
            {entry.grade && <GradeBadge grade={entry.grade} />}
            {entry.lesson && (
              <div className="flex-1 rounded-md border border-amber-500/15 bg-amber-500/5 px-3 py-2">
                <p className="text-[10px] font-semibold uppercase tracking-wider text-amber-400/60 mb-0.5 flex items-center gap-1">
                  <Lightbulb className="h-3 w-3" />
                  Lesson
                </p>
                <p className="text-xs text-foreground/80 italic">{entry.lesson}</p>
              </div>
            )}
          </div>

          {/* Contributing factors */}
          {(entry.contributing_factors?.length ?? 0) > 0 && (
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/50 mb-1.5">
                Contributing Factors
              </p>
              <ul className="space-y-1">
                {entry.contributing_factors!.map((f, i) => (
                  <li key={i} className="flex items-start gap-1.5 text-xs text-foreground/75">
                    <span className="mt-1 h-1 w-1 shrink-0 rounded-full bg-muted-foreground/30" />
                    {f}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Signals */}
          {signals.length > 0 && (
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/50 mb-1.5">
                {isWon ? "Success Signals" : "Warning Signs Missed"}
              </p>
              <ul className="space-y-1">
                {signals.map((s, i) => (
                  <li key={i} className={cn("flex items-start gap-1.5 text-xs", isWon ? "text-emerald-400/80" : "text-rose-400/80")}>
                    <span className={cn("mt-1 h-1 w-1 shrink-0 rounded-full", isWon ? "bg-emerald-400/50" : "bg-rose-400/50")} />
                    {s}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Skeleton loader ───────────────────────────────────────────────────────────

function SkeletonLoader() {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {[0, 1].map((i) => (
          <div key={i} className="rounded-xl border border-border/30 bg-muted/40 p-5 animate-pulse">
            <div className="flex items-center gap-2 mb-4">
              <div className="h-5 w-5 rounded bg-muted" />
              <div className="h-4 w-24 rounded bg-muted" />
            </div>
            <div className="flex gap-6 mb-3">
              <div className="h-9 w-12 rounded bg-muted" />
              <div className="h-7 w-20 rounded bg-muted" />
            </div>
            <div className="h-3 w-40 rounded bg-muted" />
          </div>
        ))}
      </div>
      <div className="rounded-xl border border-border/30 bg-muted/40 p-5 animate-pulse">
        <div className="h-4 w-40 rounded bg-muted mb-4" />
        <div className="h-[220px] rounded-lg bg-muted" />
      </div>
      <div className="space-y-2">
        <div className="h-4 w-28 rounded bg-muted animate-pulse mb-2" />
        {[0, 1, 2].map((i) => (
          <div key={i} className="rounded-lg border border-border/30 bg-muted/40 px-4 py-3 animate-pulse">
            <div className="flex items-center gap-3">
              <div className="h-4 w-4 rounded bg-muted shrink-0" />
              <div className="flex-1 space-y-2">
                <div className="flex gap-2">
                  <div className="h-4 w-28 rounded bg-muted" />
                  <div className="h-4 w-12 rounded-full bg-muted" />
                  <div className="h-4 w-16 rounded bg-muted" />
                </div>
                <div className="h-3 w-3/4 rounded bg-muted" />
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Actionable empty state ────────────────────────────────────────────────────

function ActionableEmptyState() {
  const navigate = useNavigate();
  const steps = [
    { icon: MousePointer, label: "Open a deal", sub: "From the Deals pipeline", color: "text-sky-400", bg: "bg-sky-400/10", border: "border-sky-400/20" },
    { icon: CheckSquare, label: "Scroll to Mark Outcome", sub: "At the bottom of the Deal Panel", color: "text-emerald-400", bg: "bg-emerald-400/10", border: "border-emerald-400/20" },
    { icon: Brain, label: "AI analyzes the pattern", sub: "Groq surfaces what drove the outcome", color: "text-violet-400", bg: "bg-violet-400/10", border: "border-violet-400/20" },
  ];

  return (
    <div className="flex flex-col items-center py-16 text-center">
      <p className="text-sm font-semibold text-foreground mb-1">No outcomes recorded yet</p>
      <p className="text-xs text-muted-foreground mb-10 max-w-sm">
        Every outcome you log makes DealIQ smarter. Start with your most recent closed deal.
      </p>
      <div className="flex items-start gap-0 mb-10">
        {steps.map((step, i) => (
          <div key={i} className="flex items-start">
            <div className="flex flex-col items-center w-36 text-center">
              <div className={cn("flex h-10 w-10 items-center justify-center rounded-xl border mb-3", step.bg, step.border)}>
                <step.icon className={cn("h-5 w-5", step.color)} />
              </div>
              <p className="text-xs font-semibold text-foreground mb-1">{step.label}</p>
              <p className="text-[11px] text-muted-foreground/60 leading-snug">{step.sub}</p>
            </div>
            {i < steps.length - 1 && <div className="mt-5 mx-1 h-px w-8 bg-border/40 shrink-0" />}
          </div>
        ))}
      </div>
      <Button size="sm" onClick={() => navigate("/dashboard")} className="gap-1.5 bg-primary/15 text-primary border border-primary/30 hover:bg-primary/25" variant="outline">
        Go to Pipeline
        <ArrowRight className="h-3.5 w-3.5" />
      </Button>
    </div>
  );
}

// ── Zoho check modal ──────────────────────────────────────────────────────────

function ZohoCheckModal({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);

  useEffect(() => {
    if (!open) return;
    setResult(null);
    setLoading(true);
    api.debugZohoTest()
      .then(setResult)
      .catch((err) => setResult({ error: friendlyError(err) }))
      .finally(() => setLoading(false));
  }, [open]);

  function renderResult() {
    if (loading) return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" /> Checking connection…
      </div>
    );
    if (!result) return null;

    if (result.mode === "demo") return (
      <div className="flex items-start gap-2 text-sm text-amber-400">
        <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
        <span>You're in demo mode. Connect Zoho CRM to see real data.</span>
      </div>
    );

    if (result.error) return (
      <div className="flex items-start gap-2 text-sm text-rose-400">
        <WifiOff className="h-4 w-4 mt-0.5 shrink-0" />
        <span>Zoho connection failed: {result.error}</span>
      </div>
    );

    if (result.deals_fetched > 0) return (
      <div className="flex items-start gap-2 text-sm text-emerald-400">
        <CheckCircle className="h-4 w-4 mt-0.5 shrink-0" />
        <span>
          Zoho connected ✓ — {result.deals_fetched} deal{result.deals_fetched !== 1 ? "s" : ""} found.
          {" "}None are marked Closed Won/Lost yet, or they're already analyzed.
        </span>
      </div>
    );

    return (
      <div className="flex items-start gap-2 text-sm text-amber-400">
        <Wifi className="h-4 w-4 mt-0.5 shrink-0" />
        <span>Zoho connected but returned 0 deals. Check your Zoho CRM has deals in the Deals module.</span>
      </div>
    );
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="border-border/50 bg-card sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-foreground">
            <Wifi className="h-4 w-4 text-sky-400" />
            Zoho Connection Check
          </DialogTitle>
          <DialogDescription className="text-muted-foreground">
            Diagnosing your CRM data connection.
          </DialogDescription>
        </DialogHeader>
        <div className="py-2">{renderResult()}</div>
        <div className="flex gap-2 pt-1">
          <Button size="sm" variant="ghost" onClick={onClose}>Close</Button>
          <Button
            size="sm"
            variant="outline"
            className="ml-auto gap-1.5 border-border/40"
            onClick={() => { onClose(); navigate("/dashboard"); }}
          >
            View Active Deals
            <ArrowRight className="h-3.5 w-3.5" />
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ── Diagnostic card (truly empty, no demo) ────────────────────────────────────

function DiagnosticCard({ onCheckZoho }: { onCheckZoho: () => void }) {
  const navigate = useNavigate();
  return (
    <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 px-5 py-4">
      <div className="flex items-start gap-3">
        <AlertTriangle className="h-4 w-4 text-amber-400 mt-0.5 shrink-0" />
        <div className="flex-1">
          <p className="text-sm font-semibold text-amber-300 mb-1">No analyzed deals found</p>
          <p className="text-xs text-muted-foreground mb-3">
            This could mean your Zoho CRM has no Closed Won/Lost deals yet, or the connection needs checking.
          </p>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="outline" className="h-7 text-xs border-amber-500/30 text-amber-400 hover:bg-amber-500/10" onClick={onCheckZoho}>
              <Wifi className="mr-1.5 h-3 w-3" />
              Check Zoho Connection
            </Button>
            <Button size="sm" variant="outline" className="h-7 text-xs border-border/40" onClick={() => navigate("/dashboard")}>
              View Active Deals →
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Demo CTA (shimmer button) ─────────────────────────────────────────────────

function DemoCTA() {
  const navigate = useNavigate();
  return (
    <div className="flex items-center justify-center py-4">
      <button
        onClick={() => navigate("/dashboard")}
        className="relative overflow-hidden rounded-lg border border-primary/30 bg-primary/10 px-5 py-2.5 text-sm font-medium text-primary transition-colors hover:bg-primary/20"
      >
        <span
          aria-hidden
          className="pointer-events-none absolute inset-0 rounded-lg"
          style={{
            background: "linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.07) 50%, transparent 100%)",
            backgroundSize: "400% auto",
            animation: "wl-shimmer 4s linear infinite",
          }}
        />
        <span className="relative flex items-center gap-2">
          <Trophy className="h-4 w-4" />
          Mark your first outcome →
        </span>
      </button>
    </div>
  );
}

// ── Custom chart bar shape with gradient ─────────────────────────────────────

function CustomBar(props: any) {
  const { x, y, width, height, fill, gradientId } = props;
  if (!height || height <= 0) return null;
  return (
    <g>
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={fill} stopOpacity={0.9} />
          <stop offset="100%" stopColor={fill} stopOpacity={0.45} />
        </linearGradient>
      </defs>
      <rect
        x={x}
        y={y}
        width={width}
        height={height}
        rx={6}
        ry={6}
        fill={`url(#${gradientId})`}
      />
    </g>
  );
}

function WonBar(props: any) {
  return <CustomBar {...props} fill="#020887" gradientId="grad-won" />;
}

function LostBar(props: any) {
  return <CustomBar {...props} fill="#F26A4F" gradientId="grad-lost" />;
}

// ── Custom chart tooltip ──────────────────────────────────────────────────────

function CustomTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-xl border border-border bg-card px-3.5 py-2.5 text-xs shadow-md">
      <p className="font-semibold text-foreground mb-2">{label}</p>
      {payload.map((p: any) => (
        <div key={p.name} className="flex items-center gap-2 mb-1 last:mb-0">
          <span className="h-2 w-2 rounded-full shrink-0" style={{ backgroundColor: p.fill ?? p.color }} />
          <span className="text-muted-foreground">{p.name}:</span>
          <span className="font-bold text-foreground">{p.value}</span>
        </div>
      ))}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function WinLossPage() {
  const [board, setBoard] = useState<Board | null>(null);
  const [loading, setLoading] = useState(true);
  const [minDelayDone, setMinDelayDone] = useState(false);
  const [userDismissedDemo, setUserDismissedDemo] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [zohoModalOpen, setZohoModalOpen] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  // Minimum 400ms skeleton to prevent jarring flash
  useEffect(() => {
    const t = setTimeout(() => setMinDelayDone(true), 400);
    return () => clearTimeout(t);
  }, []);

  useEffect(() => {
    abortRef.current = new AbortController();
    api
      .getWinLossBoard(abortRef.current.signal)
      .then((data) => { setBoard(data); setError(null); })
      .catch((err) => { const msg = friendlyError(err); if (msg) setError(msg); })
      .finally(() => setLoading(false));
    return () => abortRef.current?.abort();
  }, []);

  const showSkeleton = loading || !minDelayDone;
  const hasRealDeals = (board?.deals.length ?? 0) > 0;
  const isDemo = !showSkeleton && !hasRealDeals && !userDismissedDemo;
  const showDiagnostic = !showSkeleton && !hasRealDeals && userDismissedDemo;

  const displayDeals = isDemo ? DEMO_DEALS : (board?.deals ?? []);
  const wonDeals = displayDeals.filter((d) => d.outcome === "won");
  const lostDeals = displayDeals.filter((d) => d.outcome === "lost");
  const wonSummary = isDemo ? computeSummary(wonDeals) : (board?.summary.won ?? computeSummary(wonDeals));
  const lostSummary = isDemo ? computeSummary(lostDeals) : (board?.summary.lost ?? computeSummary(lostDeals));
  const chartData = buildChartData(wonSummary.pattern_counts, lostSummary.pattern_counts);
  const showFullContent = !showSkeleton && (hasRealDeals || isDemo);

  // Win rate computed at component level so hooks can be called safely
  const total = wonSummary.count + lostSummary.count;
  const winRatePercent = total > 0 ? Math.round((wonSummary.count / total) * 100) : (isDemo ? 50 : 0);
  const animatedWinRate = useCountUp(winRatePercent, 1200, showFullContent);

  return (
    <>
      <style>{KEYFRAMES}</style>
      <ZohoCheckModal open={zohoModalOpen} onClose={() => setZohoModalOpen(false)} />

      {/* ── Page wrapper — matches AlertsPage / other pages ─────────────── */}
      <div className="min-h-screen bg-background">

        {/* ── Header ──────────────────────────────────────────────────────── */}
        <div className="border-b border-border/40 bg-background/95 px-6 py-5 backdrop-blur-sm">
          <div className="flex items-center gap-2.5">
            <Trophy className="h-5 w-5 text-amber-400" />
            <h1 className="text-lg font-bold text-foreground">Win / Loss Intelligence</h1>

            {/* Status pill */}
            {!showSkeleton && (
              isDemo ? (
                <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-500/30 bg-amber-500/10 px-2.5 py-0.5 text-[11px] font-medium text-amber-400">
                  <span className="h-1.5 w-1.5 rounded-full bg-amber-400" />
                  Demo Mode
                </span>
              ) : hasRealDeals ? (
                <span className="inline-flex items-center gap-1.5 rounded-full border border-border/40 bg-secondary/50 px-2.5 py-0.5 text-[11px] font-medium text-muted-foreground">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
                  {displayDeals.length} deal{displayDeals.length !== 1 ? "s" : ""} analyzed
                  {(board?.auto_analyzed_count ?? 0) > 0 && (
                    <span className="text-muted-foreground/50">· {board!.auto_analyzed_count} auto-detected</span>
                  )}
                </span>
              ) : null
            )}

            {/* How it works tooltip */}
            <Tooltip>
              <TooltipTrigger asChild>
                <button className="ml-auto text-muted-foreground/40 hover:text-muted-foreground transition-colors">
                  <HelpCircle className="h-4 w-4" />
                </button>
              </TooltipTrigger>
              <TooltipContent side="bottom" className="max-w-xs text-xs leading-relaxed">
                Mark deals as Won or Lost from the Deal Panel. AI analyzes each outcome and
                surfaces patterns to help your team repeat wins. Closed Won/Lost deals from Zoho
                are auto-detected and analyzed.
              </TooltipContent>
            </Tooltip>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            AI-powered analysis of your deal outcomes — identify patterns to win more.
          </p>
        </div>

        {/* ── Body — left-aligned, full width, matches other pages ────────── */}
        <div className="px-6 py-6 space-y-6">

          {/* Error */}
          {!showSkeleton && error && (
            <div className="rounded-lg border border-rose-500/20 bg-rose-500/5 px-4 py-3 text-sm text-rose-400">
              {error}
            </div>
          )}

          {/* Skeleton */}
          {showSkeleton && <SkeletonLoader />}

          {/* Demo banner */}
          {isDemo && (
            <div className="flex items-center justify-between rounded-lg border border-amber-500/20 bg-amber-500/5 px-4 py-2.5">
              <p className="text-xs text-amber-300/80 flex items-center gap-1.5">
                <Eye className="h-3.5 w-3.5 shrink-0" />
                <span><span className="font-semibold">Showing sample data</span> — mark a deal outcome to see your real intelligence</span>
              </p>
              <button
                onClick={() => setUserDismissedDemo(true)}
                className="ml-4 flex items-center gap-1 text-[11px] text-amber-400/60 hover:text-amber-400 transition-colors shrink-0"
              >
                <X className="h-3 w-3" />
                Dismiss
              </button>
            </div>
          )}

          {/* Diagnostic card (after demo dismissed, still empty) */}
          {showDiagnostic && <DiagnosticCard onCheckZoho={() => setZohoModalOpen(true)} />}

          {/* Actionable empty state */}
          {showDiagnostic && <ActionableEmptyState />}

          {/* Main content */}
          {showFullContent && (
            <>
              {/* Metric cards + Win Rate donut */}
              {(() => {
                return (
                  <div className="grid gap-4 grid-cols-1 sm:grid-cols-[1fr_1fr_180px]">
                    <AnimatedMetricCard outcome="won" summary={wonSummary} delay={0} animated />
                    <AnimatedMetricCard outcome="lost" summary={lostSummary} delay={150} animated />

                    {/* Win Rate donut */}
                    <div
                      className="flex flex-col items-center justify-center rounded-xl border border-border/40 bg-card/40 py-5"
                      style={{ animation: "wl-slide-up 0.4s ease both", animationDelay: "300ms" }}
                    >
                      <p className="text-xs font-semibold text-muted-foreground mb-2">Win Rate</p>
                      <div className="relative">
                        <RadialBarChart
                          width={100}
                          height={100}
                          cx={50}
                          cy={50}
                          innerRadius={32}
                          outerRadius={46}
                          startAngle={90}
                          endAngle={-270}
                          data={[{ name: "Win Rate", value: animatedWinRate, fill: "#020887" }]}
                          barSize={10}
                        >
                          <RadialBar
                            background={{ fill: "rgba(100,116,139,0.12)" }}
                            dataKey="value"
                            cornerRadius={5}
                          />
                        </RadialBarChart>
                        <span className="absolute inset-0 flex items-center justify-center text-lg font-bold text-primary tabular-nums">
                          {animatedWinRate}%
                        </span>
                      </div>
                      <p className="mt-2 text-[11px] text-muted-foreground/60">
                        {wonSummary.count}W / {lostSummary.count}L
                      </p>
                    </div>
                  </div>
                );
              })()}

              {/* Pattern bar chart */}
              {chartData.length > 0 && (
                <div
                  className="rounded-2xl border border-border bg-card p-7"
                  style={{ animation: "wl-slide-up 0.4s ease both", animationDelay: "250ms" }}
                >
                  {/* Chart header + custom legend */}
                  <div className="flex items-center justify-between mb-5">
                    <h2 className="text-sm font-semibold text-foreground">Deal Pattern Breakdown</h2>
                    <div className="flex items-center gap-4 text-xs text-muted-foreground">
                      <span className="flex items-center gap-1.5">
                        <span className="h-2 w-2 rounded-full" style={{ backgroundColor: "#020887" }} />
                        Won
                      </span>
                      <span className="flex items-center gap-1.5">
                        <span className="h-2 w-2 rounded-full" style={{ backgroundColor: "#F26A4F" }} />
                        Lost
                      </span>
                    </div>
                  </div>

                  <ResponsiveContainer width="100%" height={290}>
                    <BarChart
                      data={chartData}
                      margin={{ top: 10, right: 10, left: -20, bottom: 65 }}
                      barCategoryGap="32%"
                      barGap={5}
                    >
                      <CartesianGrid vertical={false} stroke="rgba(100,116,139,0.12)" />
                      <XAxis
                        dataKey="pattern"
                        tick={{ fill: "rgb(100 116 139)", fontSize: 11 }}
                        angle={-30}
                        textAnchor="end"
                        interval={0}
                        height={65}
                        tickLine={false}
                        axisLine={false}
                        dy={6}
                      />
                      <YAxis
                        allowDecimals={false}
                        tick={{ fill: "rgb(100 116 139)", fontSize: 11 }}
                        tickLine={false}
                        axisLine={false}
                      />
                      <RechartsTooltip
                        content={<CustomTooltip />}
                        cursor={{ fill: "rgba(255,255,255,0.04)" }}
                      />
                      <Bar
                        dataKey="Won"
                        shape={<WonBar />}
                        maxBarSize={44}
                        isAnimationActive
                        animationBegin={300}
                        animationDuration={1200}
                      />
                      <Bar
                        dataKey="Lost"
                        shape={<LostBar />}
                        maxBarSize={44}
                        isAnimationActive
                        animationBegin={400}
                        animationDuration={1200}
                      />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}

              {/* Pattern insight strips */}
              {(() => {
                const patternTips: Record<string, string> = {
                  strong_champion: "Close rates jump when a champion has budget authority and board access.",
                  multi_threaded: "Multi-threaded deals are 2× less likely to stall after org changes.",
                  urgency_created: "Tying close date to buyer's fiscal calendar shortens cycles by 18%.",
                  good_execution: "Clean execution: discovery → POC → legal → close with no gaps.",
                  single_threaded: "One contact = one point of failure. Multi-thread above the champion by week 3.",
                  champion_lost: "Champion change is the #1 cause of late-stage loss. Map power early.",
                  no_urgency: "No urgency = no close. Always quantify the cost of delay.",
                  competitor_win: "Establish differentiation with the economic buyer before procurement arrives.",
                  pricing_issue: "Price objections in the final stage signal value wasn't landed earlier.",
                  budget_cut: "Budget risk is detectable — watch for delayed approvals and sponsor silence.",
                };
                const topWonPatterns = Object.entries(wonSummary.pattern_counts)
                  .sort((a, b) => b[1] - a[1])
                  .slice(0, 2);
                const topLostPatterns = Object.entries(lostSummary.pattern_counts)
                  .sort((a, b) => b[1] - a[1])
                  .slice(0, 2);
                const strips = [
                  ...topWonPatterns.map(([p, c]) => ({ pattern: p, count: c, outcome: "won" as const })),
                  ...topLostPatterns.map(([p, c]) => ({ pattern: p, count: c, outcome: "lost" as const })),
                ];
                if (!strips.length) return null;
                return (
                  <div
                    className="grid grid-cols-1 sm:grid-cols-2 gap-3"
                    style={{ animation: "wl-slide-up 0.4s ease both", animationDelay: "350ms" }}
                  >
                    {strips.map(({ pattern, count, outcome }) => {
                      const isWon = outcome === "won";
                      const tip = patternTips[pattern] ?? `Pattern: ${humanPattern(pattern)}`;
                      return (
                        <div
                          key={`${outcome}-${pattern}`}
                          className={cn(
                            "rounded-xl border px-4 py-3",
                            isWon
                              ? "border-emerald-500/20 bg-emerald-500/5 border-l-[3px] border-l-emerald-500"
                              : "border-rose-500/20 bg-rose-500/5 border-l-[3px] border-l-rose-500"
                          )}
                        >
                          <div className="flex items-center gap-2 mb-1.5">
                            <span className={cn("text-xs font-bold", isWon ? "text-emerald-400" : "text-rose-400")}>
                              {humanPattern(pattern)}
                            </span>
                            <span className={cn(
                              "ml-auto text-[10px] font-semibold rounded-full px-2 py-0.5 border",
                              isWon
                                ? "text-emerald-400 border-emerald-500/20 bg-emerald-500/10"
                                : "text-rose-400 border-rose-500/20 bg-rose-500/10"
                            )}>
                              {count}× {isWon ? "WON" : "LOST"}
                            </span>
                          </div>
                          <p className="text-[11px] text-muted-foreground leading-relaxed">{tip}</p>
                        </div>
                      );
                    })}
                  </div>
                );
              })()}

              {/* Deal cards */}
              {displayDeals.length > 0 && (
                <div className="space-y-2">
                  <div className="flex items-center gap-2 mb-1">
                    <h2 className="text-sm font-semibold text-foreground">Analyzed Deals</h2>
                    {isDemo && <span className="text-[10px] text-amber-400/60 font-medium">sample data</span>}
                  </div>
                  <div className="space-y-2">
                    {[...displayDeals]
                      .sort((a, b) => new Date(b.analyzed_at).getTime() - new Date(a.analyzed_at).getTime())
                      .map((entry, i) => (
                        <DealCard key={entry.deal_id} entry={entry} index={i} />
                      ))}
                  </div>
                </div>
              )}

              {/* Demo CTA */}
              {isDemo && <DemoCTA />}
            </>
          )}
        </div>
      </div>
    </>
  );
}
