import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import {
  ChevronDown, ChevronUp, AlertTriangle, Zap, Shield, BarChart3,
  Target, CheckCircle2, TrendingUp, TrendingDown, ArrowRight, Plus,
} from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { useSession } from "@/contexts/SessionContext";
import { useToast } from "@/hooks/use-toast";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

// ── Types ─────────────────────────────────────────────────────────────────────

interface ForecastDeal {
  id: string;
  name: string;
  company: string;
  amount: number;
  stage: string;
  health_score: number;
  effective_category: "commit" | "best_case" | "pipeline" | "omit";
  has_critical_warning: boolean;
}

interface ForecastCategory {
  deals: ForecastDeal[];
  total: number;
}

interface ForecastBoard {
  quota: number;
  period_label: string;
  categories: {
    commit: ForecastCategory;
    best_case: ForecastCategory;
    pipeline: ForecastCategory;
  };
  last_submission: ForecastSubmissionRecord | null;
  ai_risk_count: number;
  coverage_ratio: number;
}

interface ForecastSubmissionRecord {
  week_of: string;
  commit_amount: number;
  best_case_amount: number;
  pipeline_amount: number;
  notes: string;
  submitted_at: string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatK(amount: number): string {
  if (amount >= 1_000_000) return `$${(amount / 1_000_000).toFixed(1)}M`;
  if (amount >= 1_000) return `$${Math.round(amount / 1_000)}K`;
  return `$${amount}`;
}


function coverageColor(ratio: number): string {
  if (ratio >= 3) return "text-emerald-400";
  if (ratio >= 2) return "text-amber-400";
  return "text-rose-400";
}

function coverageBarColor(ratio: number): string {
  if (ratio >= 3) return "bg-emerald-500";
  if (ratio >= 2) return "bg-amber-500";
  return "bg-rose-500";
}

function healthBarColor(score: number): string {
  if (score >= 75) return "bg-emerald-400";
  if (score >= 50) return "bg-amber-400";
  if (score >= 25) return "bg-orange-500";
  return "bg-rose-500";
}

function healthTextColor(score: number): string {
  if (score >= 75) return "text-emerald-400";
  if (score >= 50) return "text-amber-400";
  if (score >= 25) return "text-orange-400";
  return "text-rose-400";
}

function coverageStatusText(ratio: number): string {
  if (ratio >= 3) return "healthy";
  if (ratio >= 2) return "below target";
  return "critical";
}

function formatWeekOf(weekOf: string): string {
  try {
    const d = new Date(weekOf + "T00:00:00");
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  } catch {
    return weekOf;
  }
}

function currentWeekLabel(): string {
  const today = new Date();
  const monday = new Date(today);
  monday.setDate(today.getDate() - today.getDay() + (today.getDay() === 0 ? -6 : 1));
  return `Week of ${monday.toLocaleDateString("en-US", { month: "short", day: "numeric" })}`;
}

// ── Deal Card ─────────────────────────────────────────────────────────────────

function DealCard({
  deal,
  onCategorize,
}: {
  deal: ForecastDeal;
  onCategorize: (id: string, category: string) => void;
}) {
  const navigate = useNavigate();
  return (
    <div className="bg-card hover:bg-muted/40 transition-all duration-300 hover:-translate-y-[2px] hover:shadow-md rounded-xl p-3 cursor-default group border border-border/60 relative overflow-hidden">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          {deal.has_critical_warning && (
            <AlertTriangle size={13} className="text-rose-400 flex-shrink-0" strokeWidth={2.5} />
          )}
          <span className="text-foreground font-medium text-sm truncate">{deal.name}</span>
        </div>
        <span className="text-foreground/80 font-semibold text-sm flex-shrink-0">{formatK(deal.amount)}</span>
      </div>
      <div className="flex items-center justify-between mt-2 gap-2">
        <span className="text-muted-foreground text-xs truncate">{deal.company}</span>
        <div className="flex items-center gap-2 flex-shrink-0">
          <div className="flex items-center gap-1.5">
            <div className="w-12 h-1.5 bg-border rounded-full overflow-hidden">
              <div
                className={cn("h-full rounded-full transition-all", healthBarColor(deal.health_score))}
                style={{ width: `${deal.health_score}%` }}
              />
            </div>
            <span className={cn("text-xs font-semibold tabular-nums", healthTextColor(deal.health_score))}>
              {deal.health_score}
            </span>
          </div>
          <select
            className="text-xs bg-background text-foreground border border-border rounded-lg px-2 py-1 cursor-pointer opacity-0 group-hover:opacity-100 transition-opacity focus:opacity-100"
            value={deal.effective_category}
            onChange={(e) => onCategorize(deal.id, e.target.value)}
            onClick={(e) => e.stopPropagation()}
          >
            <option value="commit">→ Commit</option>
            <option value="best_case">→ Best Case</option>
            <option value="pipeline">→ Pipeline</option>
            <option value="omit">→ Omit</option>
          </select>
          <button
            onClick={(e) => {
              e.stopPropagation();
              navigate(`/dashboard?deal=${deal.id}&tab=battlecard`);
            }}
            className="opacity-0 group-hover:opacity-100 transition-opacity text-xs text-sky-400 hover:text-sky-300 bg-sky-500/10 rounded-lg px-2 py-1"
            title="Open Battle Card"
          >
            <Zap size={10} className="inline mr-0.5" strokeWidth={2.5} />
            Brief
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Column ────────────────────────────────────────────────────────────────────

function DealColumn({
  title,
  colorClass,
  textClass,
  deals,
  total,
  onCategorize,
  promoteCandidates,
}: {
  title: string;
  colorClass: string;
  textClass: string;
  deals: ForecastDeal[];
  total: number;
  onCategorize: (id: string, category: string) => void;
  promoteCandidates?: ForecastDeal[];
}) {
  const candidates = promoteCandidates?.filter(d => d.health_score >= 65).slice(0, 3) ?? [];
  const isEmptyCommit = title === "Commit" && deals.length === 0;

  return (
    <div className="flex flex-col min-w-0">
      <div className={cn("border-t-[3px] rounded-t-xl bg-card px-4 py-3 flex justify-between items-center", colorClass)}>
        <div className="flex items-center gap-2">
          {title === "Commit" && <Zap size={14} className={textClass} strokeWidth={2.5} />}
          {title === "Best Case" && <Shield size={14} className={textClass} strokeWidth={2.5} />}
          {title === "Pipeline" && <BarChart3 size={14} className={textClass} strokeWidth={2.5} />}
          <span className={cn("font-semibold text-sm uppercase tracking-wider", textClass)}>{title}</span>
        </div>
        <span className={cn("font-bold text-sm", isEmptyCommit ? "text-rose-500" : "text-foreground/70")}>
          {isEmptyCommit ? "$0" : formatK(total)} · {deals.length} deal{deals.length !== 1 ? "s" : ""}
        </span>
      </div>
      <div className={cn(
        "bg-muted/20 border border-t-0 border-border rounded-b-xl p-3 min-h-[320px] space-y-2 flex-1",
        isEmptyCommit && "bg-rose-500/10 border-rose-500/20"
      )}>
        {deals.length === 0 ? (
          isEmptyCommit ? (
            <div className="flex flex-col items-center justify-center h-32 gap-2">
              <AlertTriangle className="h-6 w-6 text-rose-500/70" />
              <span className="text-rose-500/80 text-xs font-semibold">No committed deals</span>
            </div>
          ) : (
            <>
              <div className="flex flex-col items-center justify-center h-32 gap-2">
                <div className="w-8 h-8 rounded-full border-2 border-dashed border-border/50 flex items-center justify-center">
                  <Plus size={14} className="text-muted-foreground/40" />
                </div>
                <span className="text-muted-foreground/50 text-xs">Move deals here</span>
              </div>
              {promoteCandidates !== undefined && (
                <div className="mt-3 px-1">
                  <p className="text-xs text-muted-foreground/60 mb-2 uppercase tracking-wider">Promote to Commit?</p>
                  {candidates.length > 0 ? candidates.map(deal => (
                    <button
                      key={deal.id}
                      onClick={() => onCategorize(deal.id, "commit")}
                      className="w-full text-left mb-1.5 px-3 py-2 rounded-lg bg-muted/30 hover:bg-emerald-500/10 hover:border-emerald-500/30 border border-border/50 transition-all group/suggest"
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-muted-foreground group-hover/suggest:text-foreground text-xs truncate transition-colors">
                          {deal.name}
                        </span>
                        <span className="text-emerald-500/60 group-hover/suggest:text-emerald-400 text-xs ml-2 flex-shrink-0 transition-colors">
                          {deal.health_score} ↑
                        </span>
                      </div>
                    </button>
                  )) : (
                    <p className="text-xs text-muted-foreground/50 italic">No high-health deals in Best Case yet</p>
                  )}
                </div>
              )}
            </>
          )
        ) : (
          deals.map((deal) => (
            <DealCard key={deal.id} deal={deal} onCategorize={onCategorize} />
          ))
        )}
      </div>
    </div>
  );
}

// ── Skeleton ──────────────────────────────────────────────────────────────────

function BoardSkeleton() {
  return (
    <div className="space-y-6">
      <div className="bg-card border border-border rounded-2xl p-6 space-y-4">
        <Skeleton className="h-7 w-48" />
        <div className="grid grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => <Skeleton key={i} className="h-20 rounded-xl" />)}
        </div>
        <Skeleton className="h-3 w-full rounded-full" />
      </div>
      <div className="grid grid-cols-3 gap-4">
        {[...Array(3)].map((_, i) => <Skeleton key={i} className="h-80 rounded-xl" />)}
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function ForecastBoard() {
  const { session } = useSession();
  const navigate = useNavigate();
  const { toast } = useToast();

  const [board, setBoard] = useState<ForecastBoard | null>(null);
  const [localDeals, setLocalDeals] = useState<Record<string, "commit" | "best_case" | "pipeline" | "omit">>({});
  const [loading, setLoading] = useState(true);

  // Quota form
  const [quotaFormOpen, setQuotaFormOpen] = useState(false);
  const [quotaInput, setQuotaInput] = useState("");
  const [periodInput, setPeriodInput] = useState("Q1 2025");
  const [savingQuota, setSavingQuota] = useState(false);

  // Submit forecast
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitSuccess, setSubmitSuccess] = useState<ForecastSubmissionRecord | null>(null);

  // History
  const [historyOpen, setHistoryOpen] = useState(false);
  const [submissions, setSubmissions] = useState<ForecastSubmissionRecord[]>([]);

  // ── Load board ─────────────────────────────────────────────────────────────

  const loadBoard = useCallback((signal?: AbortSignal) => {
    setLoading(true);
    api.getForecastBoard(signal)
      .then((data: ForecastBoard) => {
        setBoard(data);
        // Seed local overrides from effective_category
        const overrides: Record<string, "commit" | "best_case" | "pipeline" | "omit"> = {};
        const allDeals = [
          ...data.categories.commit.deals,
          ...data.categories.best_case.deals,
          ...data.categories.pipeline.deals,
        ];
        allDeals.forEach((d) => { overrides[d.id] = d.effective_category; });
        setLocalDeals(overrides);
      })
      .catch((err: unknown) => {
        if (err instanceof DOMException && err.name === "AbortError") return;
        if (err instanceof Error && err.name === "AbortError") return;
        toast({ title: "Failed to load forecast board", variant: "destructive" });
      })
      .finally(() => setLoading(false));
  }, [toast]);

  useEffect(() => {
    if (!session) { navigate("/", { replace: true }); return; }
    const controller = new AbortController();
    loadBoard(controller.signal);
    return () => controller.abort();
  }, [session, navigate, loadBoard]);

  // ── Categorize ─────────────────────────────────────────────────────────────

  function handleCategorize(dealId: string, category: string) {
    const prev = localDeals[dealId];
    // Optimistic update
    setLocalDeals((d) => ({ ...d, [dealId]: category as ForecastDeal["effective_category"] }));
    setBoard((b) => {
      if (!b) return b;
      // Move deal across buckets in local board state
      const allDeals = [
        ...b.categories.commit.deals,
        ...b.categories.best_case.deals,
        ...b.categories.pipeline.deals,
      ];
      const deal = allDeals.find((d) => d.id === dealId);
      if (!deal) return b;
      const updated = { ...deal, effective_category: category as ForecastDeal["effective_category"] };
      const categories = { commit: [] as ForecastDeal[], best_case: [] as ForecastDeal[], pipeline: [] as ForecastDeal[] };
      allDeals.forEach((d) => {
        const cat = d.id === dealId ? category : d.effective_category;
        if (cat === "omit") return;
        const bucket = cat as keyof typeof categories;
        if (bucket in categories) categories[bucket].push(d.id === dealId ? updated : d);
      });
      return {
        ...b,
        categories: {
          commit: { deals: categories.commit, total: categories.commit.reduce((s, d) => s + d.amount, 0) },
          best_case: { deals: categories.best_case, total: categories.best_case.reduce((s, d) => s + d.amount, 0) },
          pipeline: { deals: categories.pipeline, total: categories.pipeline.reduce((s, d) => s + d.amount, 0) },
        },
      };
    });

    api.categorizeDeal(dealId, category).catch(() => {
      // Revert on error
      setLocalDeals((d) => ({ ...d, [dealId]: prev as ForecastDeal["effective_category"] }));
      loadBoard();
      toast({ title: "Failed to save category — reverted", variant: "destructive" });
    });
  }

  // ── Save quota ─────────────────────────────────────────────────────────────

  async function handleSaveQuota() {
    const amount = parseFloat(quotaInput.replace(/[^0-9.]/g, ""));
    if (!amount || amount <= 0) {
      toast({ title: "Enter a valid quota amount", variant: "destructive" });
      return;
    }
    setSavingQuota(true);
    try {
      await api.setForecastQuota(amount, periodInput || "Q1 2025");
      setQuotaFormOpen(false);
      loadBoard();
    } catch {
      toast({ title: "Failed to save quota", variant: "destructive" });
    } finally {
      setSavingQuota(false);
    }
  }

  // ── Submit forecast ────────────────────────────────────────────────────────

  async function handleSubmit() {
    if (!board) return;
    setSubmitting(true);
    try {
      await api.submitForecast({
        commit_amount: board.categories.commit.total,
        best_case_amount: board.categories.best_case.total,
        pipeline_amount: board.categories.pipeline.total,
        notes,
      });
      const record: ForecastSubmissionRecord = {
        week_of: new Date().toISOString().slice(0, 10),
        commit_amount: board.categories.commit.total,
        best_case_amount: board.categories.best_case.total,
        pipeline_amount: board.categories.pipeline.total,
        notes,
        submitted_at: new Date().toISOString(),
      };
      setSubmitSuccess(record);
      setNotes("");
      // Reload submissions for history
      api.getForecastSubmissions().then((d: { submissions: ForecastSubmissionRecord[] }) => {
        setSubmissions(d.submissions ?? []);
      }).catch(() => { });
    } catch {
      toast({ title: "Failed to submit forecast", variant: "destructive" });
    } finally {
      setSubmitting(false);
    }
  }

  // ── Load history ───────────────────────────────────────────────────────────

  function handleToggleHistory() {
    if (!historyOpen && submissions.length === 0) {
      api.getForecastSubmissions()
        .then((d: { submissions: ForecastSubmissionRecord[] }) => setSubmissions(d.submissions ?? []))
        .catch(() => { });
    }
    setHistoryOpen((v) => !v);
  }

  // ── Render ─────────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="min-h-screen bg-background">
        <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
          <div className="mb-6 flex items-center justify-between">
            <div>
              <Skeleton className="h-7 w-48 mb-2" />
              <Skeleton className="h-4 w-72" />
            </div>
          </div>
          <BoardSkeleton />
        </div>
      </div>
    );
  }

  if (!board) return null;

  const { quota, period_label, categories, last_submission, ai_risk_count, coverage_ratio } = board;
  const commitTotal = categories.commit.total;
  const bestCaseTotal = categories.best_case.total;
  const pipelineTotal = categories.pipeline.total;
  const totalPipeline = commitTotal + bestCaseTotal + pipelineTotal;

  const commitPct = quota > 0 ? Math.min((commitTotal / quota) * 100, 100) : 0;
  const bestCasePct = quota > 0 ? Math.min(((bestCaseTotal) / quota) * 100, 100 - commitPct) : 0;
  const quotaReachedPct = quota > 0 ? Math.min((totalPipeline / quota) * 100, 100) : 0;

  return (
    <div className="min-h-screen bg-background">
      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 space-y-6">

        {/* Page title */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-foreground">Forecast Board</h1>
            <p className="text-sm text-muted-foreground/60 mt-0.5">
              Categorize deals and submit your weekly forecast
            </p>
          </div>
        </div>

        {/* ── SECTION A: Quota Progress ────────────────────────────────────── */}
        <div className="bg-card border border-border rounded-2xl p-6 space-y-5">

          {/* Header row */}
          <div className="flex items-center justify-between flex-wrap gap-3">
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-2">
                <div className="w-6 h-6 rounded-md bg-sky-500/20 flex items-center justify-center">
                  <Target size={13} className="text-sky-400" strokeWidth={2} />
                </div>
                <span className="text-base font-semibold text-foreground">{period_label} Forecast</span>
              </div>
              {quota > 0 && (
                <span className={cn(
                  "text-xs font-semibold px-2.5 py-0.5 rounded-full border",
                  coverage_ratio >= 3
                    ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30"
                    : coverage_ratio >= 2
                      ? "bg-amber-500/10 text-amber-400 border-amber-500/30"
                      : "bg-rose-500/10 text-rose-400 border-rose-500/30"
                )}>
                  {coverage_ratio.toFixed(1)}x pipeline coverage
                </span>
              )}
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setQuotaFormOpen((v) => !v)}
                className="text-xs px-3 py-1.5 rounded-lg border border-border bg-muted/50 text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
              >
                {quotaFormOpen ? "Cancel" : "Set Quota"}
              </button>
            </div>
          </div>

          {/* Quota form */}
          {quotaFormOpen && (
            <div className="flex flex-wrap items-end gap-3 bg-muted/40 rounded-xl p-4 border border-border">
              <div className="flex flex-col gap-1">
                <label className="text-xs text-muted-foreground/70 uppercase tracking-wider">Quarterly Quota</label>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground text-sm">$</span>
                  <input
                    type="number"
                    value={quotaInput}
                    onChange={(e) => setQuotaInput(e.target.value)}
                    placeholder="150000"
                    className="bg-background border border-border rounded-lg pl-7 pr-3 py-2 text-sm text-foreground placeholder:text-muted-foreground/40 focus:outline-none focus:ring-1 focus:ring-primary w-40"
                  />
                </div>
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-xs text-muted-foreground/70 uppercase tracking-wider">Period</label>
                <input
                  type="text"
                  value={periodInput}
                  onChange={(e) => setPeriodInput(e.target.value)}
                  placeholder="Q1 2025"
                  className="bg-background border border-border rounded-lg px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground/40 focus:outline-none focus:ring-1 focus:ring-primary w-28"
                />
              </div>
              <button
                onClick={handleSaveQuota}
                disabled={savingQuota}
                className="px-4 py-2 rounded-lg bg-sky-600 hover:bg-sky-500 disabled:opacity-50 text-white text-sm font-medium transition-colors"
              >
                {savingQuota ? "Saving…" : "Save"}
              </button>
            </div>
          )}

          {/* Stat chips */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[
              { label: "Commit", value: formatK(commitTotal), color: "text-emerald-400" },
              { label: "Best Case", value: formatK(bestCaseTotal), color: "text-amber-400" },
              { label: "Pipeline", value: formatK(pipelineTotal), color: "text-sky-400" },
              { label: "Quota", value: quota > 0 ? formatK(quota) : "Not set", color: "text-foreground/70" },
            ].map(({ label, value, color }) => (
              <div key={label} className="bg-muted/40 border border-border/50 rounded-xl px-5 py-3 text-center">
                <div className={cn("text-2xl font-bold", color)}>{value}</div>
                <div className="text-xs text-muted-foreground/60 mt-1 uppercase tracking-wider">{label}</div>
              </div>
            ))}
          </div>

          {/* Progress bar */}
          {quota > 0 ? (
            <div className="space-y-2">
              <div className="h-3 bg-border/60 rounded-full overflow-hidden flex">
                <div
                  className="bg-emerald-500 h-full transition-all duration-500"
                  style={{ width: `${commitPct}%` }}
                />
                <div
                  className="bg-amber-500/70 h-full transition-all duration-500"
                  style={{ width: `${bestCasePct}%` }}
                />
              </div>
              <div className="flex justify-between items-center text-xs text-muted-foreground/70">
                <div className="flex items-center gap-3">
                  <span className="flex items-center gap-1"><span className="inline-block w-2.5 h-2.5 rounded-full bg-emerald-500" /> Commit</span>
                  <span className="flex items-center gap-1"><span className="inline-block w-2.5 h-2.5 rounded-full bg-amber-500/70" /> Best Case</span>
                </div>
                <span className={cn("font-semibold", coverageColor(coverage_ratio))}>
                  {Math.round(quotaReachedPct)}% to quota
                </span>
              </div>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground/60 italic">Set a quota to see coverage</p>
          )}

          {ai_risk_count > 0 && (
            <div className="flex items-center gap-2 text-xs text-rose-400">
              <AlertTriangle size={13} strokeWidth={2.5} />
              <span>{ai_risk_count} deal{ai_risk_count > 1 ? "s" : ""} in Commit with health score below 60</span>
            </div>
          )}
        </div>

        {/* ── SECTION B: Three-column board ────────────────────────────────── */}
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <DealColumn
            title="Commit"
            colorClass="border-emerald-500"
            textClass="text-emerald-400"
            deals={categories.commit.deals}
            total={categories.commit.total}
            onCategorize={handleCategorize}
            promoteCandidates={categories.best_case.deals}
          />
          <DealColumn
            title="Best Case"
            colorClass="border-amber-500"
            textClass="text-amber-400"
            deals={categories.best_case.deals}
            total={categories.best_case.total}
            onCategorize={handleCategorize}
          />
          <DealColumn
            title="Pipeline"
            colorClass="border-sky-500"
            textClass="text-sky-400"
            deals={categories.pipeline.deals}
            total={categories.pipeline.total}
            onCategorize={handleCategorize}
          />
        </div>

        {/* ── SECTION C: Submit Forecast ───────────────────────────────────── */}
        <div className="bg-card border border-border rounded-2xl p-6 space-y-4">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <h2 className="text-sm font-semibold text-foreground">Submit This Week's Forecast</h2>
            <span className="text-xs text-muted-foreground/60">{currentWeekLabel()}</span>
          </div>

          {/* Auto-calculated amounts */}
          <div className="flex flex-wrap gap-4 text-sm">
            {[
              { label: "Commit", value: formatK(commitTotal), color: "text-emerald-400" },
              { label: "Best Case", value: formatK(bestCaseTotal), color: "text-amber-400" },
              { label: "Pipeline", value: formatK(pipelineTotal), color: "text-sky-400" },
            ].map(({ label, value, color }) => (
              <div key={label} className="flex items-center gap-1.5">
                <span className="text-muted-foreground/70">{label}:</span>
                <span className={cn("font-semibold", color)}>{value}</span>
              </div>
            ))}
          </div>
          <p className="text-xs text-muted-foreground/50">Auto-calculated from your board above</p>

          {/* Notes */}
          <div className="space-y-1.5">
            <label className="text-xs text-muted-foreground/70 uppercase tracking-wider">Notes for manager (optional)</label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value.slice(0, 300))}
              placeholder="Any context or updates for your manager…"
              rows={3}
              className="w-full bg-background border border-border rounded-xl px-4 py-3 text-sm text-foreground placeholder:text-muted-foreground/40 focus:outline-none focus:ring-1 focus:ring-primary resize-none"
            />
            <p className="text-right text-xs text-muted-foreground/50">{notes.length}/300</p>
          </div>

          {/* Submit + last submission line */}
          <div className="flex items-center justify-between flex-wrap gap-3">
            <button
              onClick={handleSubmit}
              disabled={submitting}
              className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-sm font-semibold transition-colors"
            >
              {submitting ? "Submitting…" : <><CheckCircle2 size={15} strokeWidth={2.5} />Submit Forecast</>}
            </button>
            {last_submission && !submitSuccess && (
              <span className="text-xs text-muted-foreground/60">
                Last submitted: {formatWeekOf(last_submission.week_of)} · {formatK(last_submission.commit_amount)} commit
              </span>
            )}
          </div>

          {/* Success state */}
          {submitSuccess && (
            <div className="bg-emerald-500/10 border border-emerald-500/30 rounded-xl px-4 py-3 space-y-1">
              <div className="flex items-center gap-2">
                <CheckCircle2 size={15} className="text-emerald-400" strokeWidth={2.5} />
                <p className="text-sm font-semibold text-emerald-400">Forecast submitted — {currentWeekLabel()}</p>
              </div>
              <p className="text-xs text-muted-foreground">
                Commit {formatK(submitSuccess.commit_amount)} · Best Case {formatK(submitSuccess.best_case_amount)} · Pipeline {formatK(submitSuccess.pipeline_amount)}
              </p>
              <button
                onClick={handleToggleHistory}
                className="text-xs text-primary hover:text-primary/80 underline"
              >
                {historyOpen ? "Hide" : "View"} submission history
              </button>
            </div>
          )}

          {/* History toggle (always visible after first load) */}
          {!submitSuccess && (
            <button
              onClick={handleToggleHistory}
              className="flex items-center gap-1 text-xs text-muted-foreground/60 hover:text-foreground transition-colors"
            >
              {historyOpen ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
              {historyOpen ? "Hide" : "Show"} submission history
            </button>
          )}

          {/* History table */}
          {historyOpen && submissions.length > 0 && (
            <div className="overflow-x-auto rounded-xl border border-border">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-border bg-muted/40">
                    {["Week", "Commit", "Best Case", "Pipeline", "Notes"].map((h) => (
                      <th key={h} className="px-4 py-2.5 text-left text-muted-foreground/70 uppercase tracking-wider font-semibold">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {submissions.slice(-6).reverse().map((s, i, arr) => {
                    const prev = arr[i + 1];
                    const trendDir = prev
                      ? s.commit_amount > prev.commit_amount ? "up"
                        : s.commit_amount < prev.commit_amount ? "down" : "flat"
                      : null;
                    return (
                      <tr
                        key={s.week_of}
                        className={cn(
                          "border-b border-border/50 last:border-0",
                          i === 0 ? "bg-muted/50" : "hover:bg-muted/30"
                        )}
                      >
                        <td className="px-4 py-2.5 text-muted-foreground">{formatWeekOf(s.week_of)}</td>
                        <td className="px-4 py-2.5 text-emerald-400 font-semibold">
                          <span className="flex items-center gap-1">
                            {formatK(s.commit_amount)}
                            {trendDir === "up" && <TrendingUp size={13} className="text-emerald-400" />}
                            {trendDir === "down" && <TrendingDown size={13} className="text-rose-400" />}
                            {trendDir === "flat" && <ArrowRight size={13} className="text-muted-foreground/50" />}
                          </span>
                        </td>
                        <td className="px-4 py-2.5 text-amber-400">{formatK(s.best_case_amount)}</td>
                        <td className="px-4 py-2.5 text-sky-400">{formatK(s.pipeline_amount)}</td>
                        <td className="px-4 py-2.5 text-muted-foreground/60 max-w-[200px] truncate">{s.notes || "—"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {historyOpen && submissions.length === 0 && (
            <p className="text-xs text-muted-foreground/50 text-center py-4">No submissions yet this quarter</p>
          )}
        </div>

      </div>
    </div>
  );
}
