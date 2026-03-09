import { useEffect, useState, useMemo, useRef } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  AlertTriangle, AlertCircle, CheckCircle2, Activity, DollarSign, Users, Search, X, Filter,
  ChevronRight, ChevronDown, Users2, TrendingUp, TrendingDown, Minus, RefreshCw,
  ArrowUpDown, BarChart2, Inbox, ClipboardCheck, Map, Loader2, Zap, BrainCircuit,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import {
  Table, TableBody, TableCell, TableHead,
  TableHeader, TableRow
} from "@/components/ui/table";
import {
  Select, SelectContent, SelectItem,
  SelectTrigger, SelectValue
} from "@/components/ui/select";
import { useSession } from "@/contexts/SessionContext";
import { useToast } from "@/hooks/use-toast";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import DealDetailPanel from "@/components/DealDetailPanel";
import AlertsDigestPanel from "@/components/AlertsDigestPanel";
import BuyingSignalPanel from "@/components/BuyingSignalPanel";
import NavBar from "@/components/NavBar";
import DemoTour from "@/components/DemoTour";
import { useCountUp } from "@/hooks/useCountUp";
import { MetricCardSkeleton, TableRowSkeleton } from "@/components/ui/Skeletons";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

// ── Types ─────────────────────────────────────────────────────────────────────

interface Metrics {
  total_deals: number;
  total_value: number;
  average_health_score: number;
  healthy_count: number;
  at_risk_count: number;
  critical_count: number;
  zombie_count: number;
  deals_needing_action: number;
}

interface Deal {
  id: string;
  deal_name: string;
  company: string;
  stage: string;
  amount: number;
  health_score: number;
  health_label: string;
  score_trend?: string | null;  // "improving" | "declining" | "stable" | null
  owner?: string;
  last_activity_time?: string;
  next_step?: string;
  discount_mention_count?: number;
}

interface DealWarningInfo {
  warning_count: number;
  has_critical: boolean;
  top_warning?: string;
}

interface RepActivity {
  rep_name: string;
  deals_active: number;
  deals_touched_7d: number;
  avg_health_score: number;
  total_pipeline_value: number;
  activity_trend: string;
}

interface TeamActivitySummary {
  reps: RepActivity[];
  team_avg_deals_touched_7d: number;
  team_avg_health_score: number;
  generated_at: string;
  simulated: boolean;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatCurrency(val: number): string {
  if (val >= 1_000_000) return `$${(val / 1_000_000).toFixed(1)}M`;
  if (val >= 1_000) return `$${Math.round(val / 1_000)}K`;
  return `$${val}`;
}

function scoreColor(score: number) {
  if (score >= 75) return "text-health-green";
  if (score >= 50) return "text-health-yellow";
  return "text-health-red";
}

function healthDotColor(score: number) {
  if (score >= 75) return "bg-health-green";
  if (score >= 50) return "bg-health-yellow";
  return "bg-health-red";
}

function healthStatusLabel(score: number) {
  if (score >= 75) return "Healthy pipeline";
  if (score >= 50) return "Good — monitor key deals";
  if (score >= 25) return "At Risk — monitor closely";
  return "Critical — immediate action";
}

function healthColor(label: string) {
  switch (label) {
    case "healthy": return "bg-health-green/15 text-health-green border-health-green/25";
    case "at_risk": return "bg-health-yellow/15 text-health-yellow border-health-yellow/25";
    case "critical": return "bg-health-orange/15 text-health-orange border-health-orange/25";
    case "zombie": return "bg-health-red/15 text-health-red border-health-red/25";
    default: return "bg-muted text-muted-foreground border-border/40";
  }
}

function dealInitialClass(label: string): string {
  switch (label) {
    case "healthy": return "bg-health-green/15 text-health-green";
    case "at_risk": return "bg-health-yellow/15 text-health-yellow";
    case "critical": return "bg-health-orange/15 text-health-orange";
    case "zombie": return "bg-health-red/15 text-health-red";
    default: return "bg-secondary text-muted-foreground";
  }
}

function getDealWhyLine(deal: Deal): { text: string; colorClass: string } | null {
  if (deal.health_label === "healthy") return null;
  const daysSince = deal.last_activity_time
    ? Math.floor((Date.now() - new Date(deal.last_activity_time).getTime()) / 86400000)
    : null;
  if (daysSince !== null && daysSince < 7)
    return { text: "Contacted recently ✓", colorClass: "text-health-green" };
  if (daysSince !== null && daysSince > 90)
    return { text: `No contact in ${daysSince} days ⚠`, colorClass: "text-health-red" };
  if (daysSince !== null && daysSince > 30)
    return { text: `No contact in ${daysSince} days`, colorClass: "text-health-yellow" };
  if (!deal.next_step) return { text: "No next step defined", colorClass: "text-muted-foreground/70" };
  if (daysSince !== null && daysSince > 14) return { text: `${daysSince} days since last touch`, colorClass: "text-muted-foreground/70" };
  if ((deal.discount_mention_count ?? 0) >= 3) return { text: "Discount pressure — multiple requests", colorClass: "text-health-orange" };
  return null;
}

function stagePillClass(stage: string): string {
  const s = stage.toLowerCase();
  if (s.includes("discovery")) return "bg-sky-500/10 text-sky-400 border-sky-500/20";
  if (s.includes("qualif")) return "bg-violet-500/10 text-violet-400 border-violet-500/20";
  if (s.includes("proposal")) return "bg-amber-500/10 text-amber-400 border-amber-500/20";
  if (s.includes("negotiat")) return "bg-orange-500/10 text-orange-400 border-orange-500/20";
  if (s.includes("won")) return "bg-health-green/10 text-health-green border-health-green/20";
  if (s.includes("lost")) return "bg-health-red/10 text-health-red border-health-red/20";
  return "bg-secondary/60 text-muted-foreground border-border/30";
}

// ── Sub-components ────────────────────────────────────────────────────────────

function HealthRing({ score }: { score: number }) {
  const r = 8;
  const circ = 2 * Math.PI * r;
  const filled = (score / 100) * circ;
  const ringColor =
    score >= 75 ? "stroke-health-green" :
      score >= 50 ? "stroke-health-yellow" :
        "stroke-health-red";
  return (
    <div className="flex items-center gap-1.5">
      <svg width="22" height="22" viewBox="0 0 20 20" className="-rotate-90" aria-hidden>
        <circle cx="10" cy="10" r={r} fill="none" strokeWidth="2.5" className="stroke-border/40" />
        <circle
          cx="10" cy="10" r={r} fill="none" strokeWidth="2.5"
          strokeDasharray={`${filled} ${circ}`} strokeLinecap="round"
          className={ringColor}
        />
      </svg>
      <span className={cn("text-sm font-bold tabular-nums", scoreColor(score))}>{score}</span>
    </div>
  );
}

function MetricValue({ value, format, className }: { value: number; format: (v: number) => string; className?: string }) {
  const animatedValue = useCountUp(value, 800);
  return <span className={className}>{format(animatedValue)}</span>;
}

function HealthGauge({ value }: { value: number }) {
  const animatedValue = useCountUp(value, 900);
  const SIZE = 120;
  const STROKE = 9;
  const r = (SIZE - STROKE) / 2;
  const circ = 2 * Math.PI * r;
  const filled = (animatedValue / 100) * circ;
  const strokeColor = animatedValue >= 75 ? "#10b981" : animatedValue >= 50 ? "#f59e0b" : "#f43f5e";
  const textColor = animatedValue >= 75 ? "text-emerald-400" : animatedValue >= 50 ? "text-amber-400" : "text-rose-400";

  return (
    <div className="relative shrink-0" style={{ width: SIZE, height: SIZE }}>
      <svg
        width={SIZE} height={SIZE}
        viewBox={`0 0 ${SIZE} ${SIZE}`}
        style={{ display: "block", transform: "rotate(-90deg)" }}
      >
        <circle
          cx={SIZE / 2} cy={SIZE / 2} r={r}
          fill="none" strokeWidth={STROKE}
          stroke="rgba(148,163,184,0.12)"
          strokeLinecap="round"
        />
        <circle
          cx={SIZE / 2} cy={SIZE / 2} r={r}
          fill="none" strokeWidth={STROKE}
          stroke={strokeColor}
          strokeDasharray={`${filled} ${circ}`}
          strokeLinecap="round"
          style={{ transition: "stroke-dasharray 0.9s cubic-bezier(0.4,0,0.2,1)" }}
        />
      </svg>
      {/* Label overlay — absolutely positioned, NOT rotated */}
      <div
        style={{ position: "absolute", top: 0, left: 0, width: SIZE, height: SIZE }}
        className="flex flex-col items-center justify-center gap-0"
      >
        <span className={cn("font-mono font-bold tabular-nums leading-none", textColor)} style={{ fontSize: 30 }}>
          {animatedValue}
        </span>
        <span className="font-mono text-[11px] text-slate-500 leading-none mt-1">/100</span>
      </div>
    </div>
  );
}

function OwnerAvatar({ name }: { name: string }) {
  const initials = (name ?? "")
    .split(" ")
    .filter(Boolean)
    .map(n => n[0])
    .slice(0, 2)
    .join("")
    .toUpperCase() || "?";
  return (
    <div className="flex items-center gap-2 min-w-0">
      <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/15 text-[10px] font-bold text-primary">
        {initials}
      </div>
      <span className="text-sm text-muted-foreground truncate">{name}</span>
    </div>
  );
}

// Empty state — no deals connected yet
function EmptyDealsState({ onConnectCRM, onTryDemo }: { onConnectCRM: () => void; onTryDemo: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-24 text-center px-6">
      {/* Icon */}
      <div className="mb-6 flex h-20 w-20 items-center justify-center rounded-3xl border border-border/40 bg-secondary/30">
        <Inbox className="h-9 w-9 text-muted-foreground/30" />
      </div>

      <h3 className="text-base font-semibold text-foreground">No deals connected yet</h3>
      <p className="mt-2 max-w-xs text-sm text-muted-foreground/70 leading-relaxed">
        Connect your Zoho CRM to see real deal health scores, or explore with demo data.
      </p>

      <div className="mt-6 flex flex-col sm:flex-row gap-3">
        <Button
          onClick={onConnectCRM}
          className="gap-2"
        >
          <BarChart2 className="h-4 w-4" />
          Connect Zoho CRM →
        </Button>
        <Button
          variant="outline"
          onClick={onTryDemo}
          className="gap-2 border-border/40"
        >
          <Map className="h-4 w-4" />
          Try Demo Mode →
        </Button>
      </div>
    </div>
  );
}

// Health pill config — static class strings for Tailwind JIT
const HEALTH_PILLS = [
  {
    key: "healthy",
    label: "Healthy",
    metricKey: "healthy_count" as keyof Metrics,
    active: "border-health-green/60 bg-health-green/20 text-health-green",
    inactive: "border-health-green/20 bg-health-green/5 text-health-green/80 hover:bg-health-green/15 hover:border-health-green/40",
    dot: "bg-health-green",
  },
  {
    key: "at_risk",
    label: "At Risk",
    metricKey: "at_risk_count" as keyof Metrics,
    active: "border-health-yellow/60 bg-health-yellow/20 text-health-yellow",
    inactive: "border-health-yellow/20 bg-health-yellow/5 text-health-yellow/80 hover:bg-health-yellow/15 hover:border-health-yellow/40",
    dot: "bg-health-yellow",
  },
  {
    key: "critical",
    label: "Critical",
    metricKey: "critical_count" as keyof Metrics,
    active: "border-health-orange/60 bg-health-orange/20 text-health-orange",
    inactive: "border-health-orange/20 bg-health-orange/5 text-health-orange/80 hover:bg-health-orange/15 hover:border-health-orange/40",
    dot: "bg-health-orange",
  },
  {
    key: "zombie",
    label: "Zombie",
    metricKey: "zombie_count" as keyof Metrics,
    active: "border-health-red/60 bg-health-red/20 text-health-red",
    inactive: "border-health-red/20 bg-health-red/5 text-health-red/80 hover:bg-health-red/15 hover:border-health-red/40",
    dot: "bg-health-red",
  },
] as const;

// ── Demo fallbacks ────────────────────────────────────────────────────────────

const DEMO_METRICS: Metrics = {
  total_deals: 24, total_value: 1_840_000, average_health_score: 38,
  healthy_count: 3, at_risk_count: 7, critical_count: 8, zombie_count: 6,
  deals_needing_action: 14,
};

const DEMO_DEALS: Deal[] = [
  { id: "1", deal_name: "Acme Corp Enterprise", company: "Acme Corp", stage: "Negotiation", amount: 450000, health_score: 28, health_label: "zombie", owner: "Sarah Chen" },
  { id: "2", deal_name: "TechFlow Platform", company: "TechFlow Inc", stage: "Proposal", amount: 320000, health_score: 42, health_label: "critical", owner: "James Okafor" },
  { id: "3", deal_name: "DataVault Migration", company: "DataVault", stage: "Discovery", amount: 180000, health_score: 55, health_label: "at_risk", owner: "Maya Patel" },
  { id: "4", deal_name: "CloudSync Annual", company: "CloudSync", stage: "Negotiation", amount: 275000, health_score: 88, health_label: "healthy", owner: "Sarah Chen" },
  { id: "5", deal_name: "Nexus Analytics Suite", company: "Nexus Labs", stage: "Qualification", amount: 195000, health_score: 35, health_label: "critical", owner: "James Okafor" },
  { id: "6", deal_name: "Orbital SaaS Rollout", company: "Orbital Inc", stage: "Negotiation", amount: 420000, health_score: 71, health_label: "at_risk", owner: "Maya Patel" },
];

// ── Component ─────────────────────────────────────────────────────────────────

export default function Dashboard() {
  const { session, isDemo } = useSession();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { toast } = useToast();

  // Data state
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [allDeals, setAllDeals] = useState<Deal[]>([]);
  const [loadingMetrics, setLoadingMetrics] = useState(true);
  const [loadingDeals, setLoadingDeals] = useState(true);
  const [selectedDealId, setSelectedDealId] = useState<string | null>(null);
  const [panelInitialSection, setPanelInitialSection] = useState<string | undefined>(undefined);
  const [panelInitialTab, setPanelInitialTab] = useState<"Overview" | "Battle Card">("Overview");
  const [digestOpen, setDigestOpen] = useState(false);
  const [digestCriticalCount, setDigestCriticalCount] = useState<number | undefined>(undefined);
  const [signalPanelOpen, setSignalPanelOpen] = useState(false);
  const [teamSummary, setTeamSummary] = useState<TeamActivitySummary | null>(null);
  const [loadingTeam, setLoadingTeam] = useState(false);
  const [teamSummaryExpanded, setTeamSummaryExpanded] = useState(false);
  const [teamSummaryFetched, setTeamSummaryFetched] = useState(false);
  const [tourActive, setTourActive] = useState(false);
  const [dealWarnings, setDealWarnings] = useState<Record<string, DealWarningInfo>>({});
  const [pipelineSummary, setPipelineSummary] = useState<string | null>(null);
  const [loadingSummary, setLoadingSummary] = useState(false);
  const [ownerOptions, setOwnerOptions] = useState<string[]>([]);
  const [stageOptions, setStageOptions] = useState<string[]>([]);

  // Inline stage edit
  const [editingStage, setEditingStage] = useState<{ dealId: string; value: string } | null>(null);
  const [savingStage, setSavingStage] = useState<string | null>(null); // dealId being saved

  // Sort
  const [sortAsc, setSortAsc] = useState(false); // false = worst health first (default)

  // Pagination
  const [currentPage, setCurrentPage] = useState(1);
  const [totalDeals, setTotalDeals] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [cacheMeta, setCacheMeta] = useState<{ fresh?: boolean; source?: string; age_seconds?: number; needs_background_sync?: boolean } | null>(null);
  const PER_PAGE = 15;

  // Derived — don't rely solely on API flags; compute locally as reliable fallback
  const hasPrev = currentPage > 1;
  const hasNext = currentPage < totalPages;

  // Ref to scroll the deal table into view on page change
  const dealTableRef = useRef<HTMLDivElement>(null);

  // Filter state
  const [searchName, setSearchName] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [filterOwner, setFilterOwner] = useState("all");
  const [filterStage, setFilterStage] = useState("all");
  const [filterHealth, setFilterHealth] = useState("all");

  // Load metrics + AI summary in one shot (both served from shared server cache)
  useEffect(() => {
    if (!session) { navigate("/", { replace: true }); return; }
    const controller = new AbortController();
    let cancelled = false;

    setLoadingSummary(true);

    api.getMetricsWithSummary(controller.signal)
      .then(({ metrics: data, summary }) => {
        if (cancelled) return;
        setMetrics({
          total_deals: data.total_deals ?? 0,
          total_value: data.total_value ?? data.pipeline_value ?? 0,
          average_health_score: data.average_health_score ?? data.avg_health_score ?? 0,
          healthy_count: data.healthy_count ?? 0,
          at_risk_count: data.at_risk_count ?? 0,
          critical_count: data.critical_count ?? 0,
          zombie_count: data.zombie_count ?? 0,
          deals_needing_action: data.deals_needing_action ?? data.needs_action ?? 0,
        });
        setPipelineSummary(summary || null);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof DOMException && err.name === "AbortError") return;
        if (err instanceof Error && err.name === "AbortError") return;
        setMetrics(DEMO_METRICS);
      })
      .finally(() => {
        if (!cancelled) { setLoadingMetrics(false); setLoadingSummary(false); }
      });

    return () => { cancelled = true; controller.abort(); };
  }, [session, navigate]);

  // Fetch filter options (all owners + stages across all deals) once on mount
  useEffect(() => {
    if (!session) return;
    api.getDealFilterOptions()
      .then(({ owners, stages }) => {
        setOwnerOptions(owners);
        setStageOptions(stages);
      })
      .catch(() => {}); // non-critical — dropdowns fall back to empty
  }, [session]);

  // Debounce search input — 300ms after typing stops, update debouncedSearch and reset to page 1
  const searchDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (searchDebounceRef.current) clearTimeout(searchDebounceRef.current);
    searchDebounceRef.current = setTimeout(() => {
      setDebouncedSearch(searchName);
      setCurrentPage(1);
    }, 300);
    return () => {
      if (searchDebounceRef.current) clearTimeout(searchDebounceRef.current);
    };
  }, [searchName]);

  // Reset to page 1 when server-side filters change
  useEffect(() => {
    setCurrentPage(1);
  }, [filterHealth, filterOwner, filterStage]);

  // Load deals — re-fetches on page change or search change
  useEffect(() => {
    if (!session) return;
    const controller = new AbortController();
    let cancelled = false;
    setLoadingDeals(true);

    api.getDealsPage(currentPage, PER_PAGE, debouncedSearch || undefined, controller.signal, {
      health_label: filterHealth,
      owner: filterOwner,
      stage: filterStage,
    })
      .then((data: any) => {
        if (cancelled) return;
        const list: any[] = data.deals ?? data ?? [];
        const mapped: Deal[] = list.map((d: any) => ({
          id: d.id,
          deal_name: d.name ?? d.deal_name ?? "Unnamed Deal",
          company: d.account_name || d.company || "—",
          stage: d.stage ?? "Unknown",
          amount: d.amount ?? 0,
          health_score: d.health_score ?? 0,
          health_label: d.health_label ?? "critical",
          owner: typeof d.owner === "object" ? d.owner?.name : d.owner || "—",
          last_activity_time: d.last_activity_time,
          next_step: d.next_step ?? undefined,
          score_trend: d.score_trend ?? null,
          discount_mention_count: d.discount_mention_count ?? 0,
        }));
        setAllDeals(mapped);
        const apiTotal = data.total ?? mapped.length;
        const apiPages = data.total_pages ?? (Math.ceil(apiTotal / PER_PAGE) || 1);
        setTotalDeals(apiTotal);
        setTotalPages(apiPages);
        if (data.cache_meta) setCacheMeta(data.cache_meta);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof DOMException && err.name === "AbortError") return;
        if (err instanceof Error && err.name === "AbortError") return;
        setAllDeals(DEMO_DEALS);
        setTotalDeals(DEMO_DEALS.length);
        setTotalPages(Math.ceil(DEMO_DEALS.length / PER_PAGE) || 1);
      })
      .finally(() => { if (!cancelled) setLoadingDeals(false); });

    return () => { cancelled = true; controller.abort(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session, currentPage, debouncedSearch, filterHealth, filterOwner, filterStage]);

  // Batch-fetch warnings for the current page of deals
  useEffect(() => {
    if (!session || allDeals.length === 0) return;
    const controller = new AbortController();
    const ids = allDeals.slice(0, 20).map(d => d.id);
    api.batchDealWarnings(ids, controller.signal)
      .then((data: Record<string, DealWarningInfo>) => {
        setDealWarnings(prev => ({ ...prev, ...data }));
      })
      .catch((err: unknown) => {
        if (err instanceof DOMException && err.name === "AbortError") return;
        if (err instanceof Error && err.name === "AbortError") return;
        // silent — warnings are non-critical
      });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [allDeals]);

  // Fetch team summary — only called when user expands the section or hits Refresh.
  function fetchTeamSummary() {
    if (!session) return;
    setLoadingTeam(true);
    api.getTeamActivitySummary()
      .then((data: TeamActivitySummary) => {
        setTeamSummary(data);
        setTeamSummaryFetched(true);
      })
      .catch((err: unknown) => {
        if (err instanceof DOMException && err.name === "AbortError") return;
        if (err instanceof Error && err.name === "AbortError") return;
        // silent — team summary is non-critical
      })
      .finally(() => setLoadingTeam(false));
  }

  function handleTeamSummaryToggle() {
    const willExpand = !teamSummaryExpanded;
    setTeamSummaryExpanded(willExpand);
    // Only fetch on first expand
    if (willExpand && !teamSummaryFetched && !loadingTeam) {
      fetchTeamSummary();
    }
  }


  async function saveStageEdit(dealId: string, newStage: string, oldStage: string) {
    setSavingStage(dealId);
    setEditingStage(null);
    // Optimistic update
    setAllDeals((prev) => prev.map((d) => d.id === dealId ? { ...d, stage: newStage } : d));
    try {
      const res = await api.updateDealField(dealId, "Stage", newStage);
      if (!res.success) throw new Error(res.error ?? "Save failed");
      toast({ title: "Stage updated in Zoho" });
    } catch {
      // Revert
      setAllDeals((prev) => prev.map((d) => d.id === dealId ? { ...d, stage: oldStage } : d));
      toast({ title: "Failed to update Zoho", variant: "destructive" });
    } finally {
      setSavingStage(null);
    }
  }


  // Filtering is server-side. Client-side: sort only.
  const filteredAndSortedDeals = useMemo(() => {
    if (sortAsc) {
      return [...allDeals].sort((a, b) => b.health_score - a.health_score);
    }
    // Default: warnings-first sort
    const warnTier = (id: string): number => {
      const w = dealWarnings[id];
      if (!w) return 1;
      if (w.has_critical) return 0;
      if (w.warning_count > 0) return 1;
      return 2;
    };
    return [...allDeals].sort((a, b) => {
      const tierDiff = warnTier(a.id) - warnTier(b.id);
      if (tierDiff !== 0) return tierDiff;
      return a.health_score - b.health_score;
    });
  }, [allDeals, sortAsc, dealWarnings]);

  // hasActiveFilters excludes searchName — search is server-side so pagination still shows
  const hasActiveFilters = filterOwner !== "all" || filterStage !== "all" || filterHealth !== "all";

  const clearFilters = () => {
    setSearchName("");
    setDebouncedSearch("");
    setCurrentPage(1);
    setFilterOwner("all");
    setFilterStage("all");
    setFilterHealth("all");
  };

  // Pagination helpers
  const startItem = (currentPage - 1) * PER_PAGE + 1;
  const endItem = Math.min(currentPage * PER_PAGE, totalDeals);

  function goToPage(pg: number) {
    const clamped = Math.max(1, Math.min(pg, totalPages));
    if (clamped === currentPage) return;
    setCurrentPage(clamped);
    // Scroll to the top of the deal table, not the whole page
    requestAnimationFrame(() => {
      dealTableRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  // Build page number array with ellipsis gaps: [1] ... [4][5][6] ... [10]
  function buildPageList(current: number, total: number): (number | "...")[] {
    if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
    const pages: (number | "...")[] = [];
    const addPage = (p: number) => { if (!pages.includes(p)) pages.push(p); };
    addPage(1);
    if (current > 3) pages.push("...");
    for (let p = Math.max(2, current - 2); p <= Math.min(total - 1, current + 2); p++) addPage(p);
    if (current < total - 2) pages.push("...");
    addPage(total);
    return pages;
  }

  const selectedDeal = allDeals.find(d => d.id === selectedDealId);

  // Open deal from ?deal=ID query param (set by command palette / forecast board)
  // Supports optional ?tab=battlecard to open directly on the Battle Card tab
  useEffect(() => {
    const dealParam = searchParams.get("deal");
    const tabParam = searchParams.get("tab");
    if (dealParam && allDeals.length > 0) {
      const found = allDeals.find(d => d.id === dealParam);
      if (found) {
        setPanelInitialTab(tabParam === "battlecard" ? "Battle Card" : "Overview");
        setSelectedDealId(dealParam);
        setSearchParams({}, { replace: true });
      }
    }
  }, [searchParams, allDeals, setSearchParams]);

  // Open most-at-risk deal on the mismatch section (FAB / nav button)
  const openMismatchForMostAtRisk = () => {
    const atRisk = allDeals
      .filter(d => d.health_label !== "healthy")
      .sort((a, b) => a.health_score - b.health_score);
    const target = atRisk[0] ?? allDeals[0];
    if (!target) {
      toast({ title: "No deals loaded yet", description: "Load your pipeline first." });
      return;
    }
    setPanelInitialSection("mismatch");
    setSelectedDealId(target.id);
  };

  // Handle connect CRM — reuse login URL flow
  const handleConnectCRM = async () => {
    try {
      const data = await api.getLoginUrl();
      if (data?.url) window.location.href = data.url;
    } catch {
      toast({ title: "Could not reach auth endpoint", variant: "destructive" });
    }
  };

  // Handle try demo
  const handleTryDemo = async () => {
    try {
      const data = await api.getDemoSession();
      if (data?.session) {
        localStorage.setItem("dealiq_session", data.session);
        window.location.reload();
      }
    } catch {
      toast({ title: "Could not start demo session", variant: "destructive" });
    }
  };

  const avgScore = metrics?.average_health_score ?? 0;

  const summaryCards = [
    {
      label: "Total Deals",
      value: metrics?.total_deals,
      icon: Users,
      format: (v: number) => String(v),
      isAlert: false,
      subtext: metrics ? `${metrics.healthy_count} healthy · ${metrics.at_risk_count + metrics.critical_count + metrics.zombie_count} need attention` : null,
    },
    {
      label: "Pipeline Value",
      value: metrics?.total_value,
      icon: DollarSign,
      format: formatCurrency,
      isAlert: false,
      subtext: "Active current-quarter deals",
    },
    {
      label: "Avg Health",
      value: metrics?.average_health_score,
      icon: Activity,
      format: (v: number) => `${Math.round(v)} / 100`,
      isAlert: false,
      colorFn: (v: number) => scoreColor(v),
      subtext: metrics ? healthStatusLabel(avgScore) : null,
      dot: metrics ? healthDotColor(avgScore) : null,
    },
    {
      label: "Needs Action",
      value: metrics?.deals_needing_action,
      icon: AlertTriangle,
      format: (v: number) => String(v),
      isAlert: true,
      subtext: metrics
        ? `${metrics.deals_needing_action} of ${metrics.total_deals} deals · health < 50 or 30d no activity`
        : null,
    },
  ];

  const noDealsLoaded = !loadingDeals && allDeals.length === 0;

  return (
    <div className="min-h-screen bg-background">
      <style>{`
        @keyframes pulseBorderRed {
          0%, 100% { border-color: rgba(239,68,68,0.15); box-shadow: 0 0 15px rgba(239, 68, 68, 0.1); }
          50% { border-color: rgba(239,68,68,0.3); box-shadow: 0 0 25px rgba(239, 68, 68, 0.25); }
        }
        .pulse-border-red {
          animation: pulseBorderRed 3s infinite;
        }
        @keyframes scaleXIn {
          from { transform: scaleX(0); }
          to { transform: scaleX(1); }
        }
        .deal-row { position: relative; }
        .deal-row::before {
          content: '';
          position: absolute;
          left: 0;
          top: 0;
          bottom: 0;
          width: 3px;
          transform: scaleY(0);
          transition: transform 150ms ease-out;
          background-color: var(--row-health-color);
        }
        .deal-row:hover::before {
          transform: scaleY(1);
        }
        .deal-row:hover {
          background-color: hsl(var(--muted) / 0.4) !important;
        }
      `}</style>

      {/* ── Header ── */}
      <div className="sticky top-0 z-40 bg-background/90 backdrop-blur-[16px] border-b border-border/40">
        <NavBar
          onOpenDigest={() => setDigestOpen(true)}
          onOpenSignal={() => setSignalPanelOpen(true)}
          digestCriticalCount={digestCriticalCount}
          deals={allDeals}
          onSelectDeal={(id) => { setPanelInitialSection(undefined); setSelectedDealId(id); }}
          onOpenMismatch={openMismatchForMostAtRisk}
        />
      </div>

      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 space-y-5">

        {/* ── Demo tour button (demo mode only) ── */}
        {isDemo && (
          <div className="flex items-center justify-between">
            <p className="text-xs text-muted-foreground/60">
              Exploring demo data · Connect Zoho CRM for live metrics
            </p>
            <button
              onClick={() => setTourActive(true)}
              className="flex items-center gap-1.5 rounded-full border border-primary/30 bg-primary/10 px-3 py-1 text-xs font-semibold text-primary transition-colors hover:bg-primary/20"
            >
              <Map className="h-3 w-3" />
              Take a Tour
            </button>
          </div>
        )}

        {/* ── Summary Cards — hero layout ── */}
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3" data-tour="metric-cards">
          {loadingMetrics ? (
            <>
              <div className="lg:col-span-2"><MetricCardSkeleton /></div>
              <div className="space-y-3">
                <MetricCardSkeleton />
                <MetricCardSkeleton />
                <MetricCardSkeleton />
              </div>
            </>
          ) : (
            <>
              {/* Hero: Pipeline Health — 2/3 width */}
              <Card
                className="lg:col-span-2 relative overflow-hidden border-border/30 bg-card/50 animate-slide-up"
                style={{ animationDelay: "0ms" }}
              >
                <CardContent className="px-8 py-6 space-y-4">
                  {/* Row 1: Gauge + status + distribution bar */}
                  <div className="flex items-center gap-6">
                    <HealthGauge value={avgScore} />
                    <div className="min-w-0 flex-1 space-y-2">
                      <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-500">
                        Pipeline Health
                      </p>
                      <p className={cn("text-lg font-semibold leading-snug", scoreColor(avgScore))}>
                        {healthStatusLabel(avgScore)}
                      </p>
                      {metrics && (
                        <p className="text-xs text-slate-500">
                          {metrics.deals_needing_action} of {metrics.total_deals} deals need attention
                          {metrics.healthy_count > 0 && ` · ${metrics.healthy_count} healthy`}
                        </p>
                      )}
                      {metrics && metrics.total_deals > 0 && (
                        <div className="space-y-1.5">
                          <div className="flex h-1.5 rounded-full overflow-hidden bg-slate-200 dark:bg-slate-800 w-full">
                            {metrics.healthy_count > 0 && (
                              <div className="bg-emerald-500 h-full transition-all duration-700"
                                style={{ width: `${(metrics.healthy_count / metrics.total_deals) * 100}%` }} />
                            )}
                            {metrics.at_risk_count > 0 && (
                              <div className="bg-amber-500 h-full transition-all duration-700"
                                style={{ width: `${(metrics.at_risk_count / metrics.total_deals) * 100}%` }} />
                            )}
                            {(metrics.critical_count + metrics.zombie_count) > 0 && (
                              <div className="bg-rose-500 h-full flex-1" />
                            )}
                          </div>
                          <div className="flex gap-5 text-xs text-slate-500">
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <span className="cursor-default underline decoration-dotted decoration-slate-600">
                                  <span className="text-emerald-400 font-semibold">{metrics.healthy_count}</span> healthy
                                </span>
                              </TooltipTrigger>
                              <TooltipContent side="bottom" className="max-w-[230px] text-xs">
                                <strong className="text-emerald-400">Healthy</strong> — score ≥ 75. Progressing well: recent activity, engaged stakeholders, aligned timeline. No action required.
                              </TooltipContent>
                            </Tooltip>
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <span className="cursor-default underline decoration-dotted decoration-slate-600">
                                  <span className="text-amber-400 font-semibold">{metrics.at_risk_count}</span> at risk
                                </span>
                              </TooltipTrigger>
                              <TooltipContent side="bottom" className="max-w-[230px] text-xs">
                                <strong className="text-amber-400">At Risk</strong> — score 50–74. Warning signs: slowing engagement, missed follow-ups, or stalled stage. Take action this week.
                              </TooltipContent>
                            </Tooltip>
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <span className="cursor-default underline decoration-dotted decoration-slate-600">
                                  <span className="text-rose-400 font-semibold">{metrics.critical_count + metrics.zombie_count}</span> critical
                                </span>
                              </TooltipTrigger>
                              <TooltipContent side="bottom" className="max-w-[230px] text-xs">
                                <strong className="text-rose-400">Critical</strong> — score &lt; 50. Deal in serious jeopardy: no recent activity, ghosted contacts, or major signal mismatch. Immediate intervention needed.
                              </TooltipContent>
                            </Tooltip>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Row 2: Full-width AI summary */}
                  <div className="flex items-start gap-3 rounded-lg bg-white/[0.03] border border-border/20 px-4 py-3 w-full">
                    <div className="shrink-0 mt-0.5 flex h-7 w-7 items-center justify-center rounded-md bg-violet-500/15">
                      <BrainCircuit className="h-4 w-4 text-violet-400" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-[10px] font-semibold uppercase tracking-widest text-violet-400/70 mb-1">
                        AI Pipeline Analysis
                      </p>
                      {loadingSummary ? (
                        <div className="flex items-center gap-2">
                          <Loader2 className="h-3.5 w-3.5 animate-spin text-slate-500" />
                          <span className="text-sm text-slate-500 italic">Analysing pipeline…</span>
                        </div>
                      ) : pipelineSummary ? (
                        <p className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed">{pipelineSummary}</p>
                      ) : null}
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Supporting metrics — stacked 1/3 */}
              <div className="flex flex-col gap-3 animate-slide-up" style={{ animationDelay: "60ms" }}>
                {([
                  {
                    label: "Pipeline Value",
                    value: metrics?.total_value,
                    format: formatCurrency,
                    desc: "Active deals this quarter",
                    valueClass: "text-slate-900 dark:text-white",
                    icon: DollarSign,
                  },
                  {
                    label: "Total Deals",
                    value: metrics?.total_deals,
                    format: (v: number) => String(v),
                    desc: "In your pipeline",
                    valueClass: "text-slate-900 dark:text-white",
                    icon: Users,
                  },
                  {
                    label: "Needs Action",
                    value: metrics?.deals_needing_action,
                    format: (v: number) => String(v),
                    desc: "Health score below 75",
                    valueClass: (metrics?.deals_needing_action ?? 0) > 0 ? "text-rose-400" : "text-emerald-400",
                    icon: AlertTriangle,
                  },
                ] as const).map((stat) => (
                  <div
                    key={stat.label}
                    className="flex-1 rounded-xl border border-border/30 bg-card/50 px-5 py-4 flex items-center gap-4"
                  >
                    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-white/5">
                      <stat.icon className="h-4 w-4 text-slate-400" />
                    </div>
                    <div className="min-w-0">
                      <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-500 mb-0.5">
                        {stat.label}
                      </p>
                      <p className={cn("font-mono text-2xl font-bold tabular-nums leading-none", stat.valueClass)}>
                        {stat.value != null ? <MetricValue value={stat.value} format={stat.format} /> : "—"}
                      </p>
                      <p className="text-[10px] text-slate-600 mt-1">{stat.desc}</p>
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>

        {/* ── Health breakdown pills ── */}
        {metrics && !loadingMetrics && (
          <div className="flex flex-wrap gap-2 animate-fade-in" style={{ animationDelay: "220ms" }}>
            {HEALTH_PILLS.filter(pill => (metrics[pill.metricKey] ?? 0) > 0).map(pill => {
              const isActive = filterHealth === pill.key;
              return (
                <button
                  key={pill.key}
                  onClick={() => setFilterHealth(isActive ? "all" : pill.key)}
                  className={cn(
                    "flex items-center gap-2 rounded-full border px-3.5 py-1.5 text-xs font-semibold transition-all duration-150",
                    isActive ? pill.active : pill.inactive
                  )}
                >
                  <span className={cn("h-1.5 w-1.5 rounded-full", pill.dot, isActive && "animate-pulse-slow")} />
                  {metrics[pill.metricKey]} {pill.label}
                </button>
              );
            })}
            {filterHealth !== "all" && (
              <button
                onClick={() => setFilterHealth("all")}
                className="flex items-center gap-1.5 rounded-full border border-border/40 bg-secondary/30 px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground hover:bg-secondary/60"
              >
                <X className="h-3 w-3" /> Clear
              </button>
            )}
          </div>
        )}

        {/* ── Deal Pipeline Table ── */}
        <Card ref={dealTableRef} className="overflow-hidden border-border/40 bg-card/60 animate-slide-up" style={{ animationDelay: "180ms" }} data-tour="deals-table">

          {/* Table header / filters */}
          <div className="p-5 pb-4 space-y-3.5">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-base font-semibold text-foreground">Deal Pipeline</h2>
                <p className="mt-0.5 text-xs text-muted-foreground/70">
                  Worst health first · Active current-quarter deals
                  {!hasActiveFilters && totalDeals > 0 && ` · ${startItem}–${endItem} of ${totalDeals}`}
                  {hasActiveFilters && ` · ${filteredAndSortedDeals.length} match${filteredAndSortedDeals.length !== 1 ? "es" : ""}`}
                </p>
              </div>
              {hasActiveFilters && (
                <button
                  onClick={clearFilters}
                  className="flex items-center gap-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground"
                >
                  <X className="h-3 w-3" /> Clear filters
                </button>
              )}
            </div>

            {/* Filter bar */}
            <div className="flex flex-wrap gap-2">
              <div className="relative flex-1 min-w-[200px]">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground/50" />
                <Input
                  value={searchName}
                  onChange={e => setSearchName(e.target.value)}
                  placeholder="Search deal or company…"
                  className="h-9 border-border/40 bg-secondary/40 pl-9 text-sm placeholder:text-muted-foreground/40 focus-visible:ring-primary/40"
                />
                {searchName && (
                  <button onClick={() => setSearchName("")}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground/50 hover:text-foreground">
                    <X className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>

              <Select value={filterOwner} onValueChange={setFilterOwner}>
                <SelectTrigger className="h-9 w-[148px] border-border/40 bg-secondary/40 text-sm">
                  <SelectValue placeholder="All Owners" />
                </SelectTrigger>
                <SelectContent className="border-border/40 bg-card">
                  <SelectItem value="all">All Owners</SelectItem>
                  {ownerOptions.map(o => <SelectItem key={o} value={o}>{o}</SelectItem>)}
                </SelectContent>
              </Select>

              <Select value={filterStage} onValueChange={setFilterStage}>
                <SelectTrigger className="h-9 w-[158px] border-border/40 bg-secondary/40 text-sm">
                  <SelectValue placeholder="All Stages" />
                </SelectTrigger>
                <SelectContent className="border-border/40 bg-card">
                  <SelectItem value="all">All Stages</SelectItem>
                  {stageOptions.map(s => <SelectItem key={s} value={s}>{s}</SelectItem>)}
                </SelectContent>
              </Select>

              <Select value={filterHealth} onValueChange={setFilterHealth}>
                <SelectTrigger className="h-9 w-[142px] border-border/40 bg-secondary/40 text-sm">
                  <SelectValue placeholder="All Health" />
                </SelectTrigger>
                <SelectContent className="border-border/40 bg-card">
                  <SelectItem value="all">All Health</SelectItem>
                  <SelectItem value="healthy">Healthy</SelectItem>
                  <SelectItem value="at_risk">At Risk</SelectItem>
                  <SelectItem value="critical">Critical</SelectItem>
                  <SelectItem value="zombie">Zombie</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* Sort label */}
            {!loadingDeals && filteredAndSortedDeals.length > 0 && (
              <div className="flex items-center gap-2">
                <span className="text-[11px] text-muted-foreground/50">
                  {sortAsc ? "Sorted by urgency — best deals first" : "Sorted by urgency — deals needing attention first"}
                </span>
                <button
                  onClick={() => setSortAsc(v => !v)}
                  className="flex items-center gap-1 rounded border border-border/40 bg-secondary/30 px-2 py-0.5 text-[11px] text-muted-foreground/60 transition-colors hover:bg-secondary/60 hover:text-foreground"
                >
                  <ArrowUpDown className="h-3 w-3" />
                  {sortAsc ? "Worst first" : "Best first"}
                </button>
              </div>
            )}
          </div>

          <CardContent className="p-0">
            {/* Skeleton loaders */}
            {loadingDeals ? (
              <div className="divide-y divide-border/20">
                {[...Array(6)].map((_, i) => <TableRowSkeleton key={i} />)}
              </div>
            ) : noDealsLoaded ? (
              /* Empty state — no deals in CRM */
              <EmptyDealsState onConnectCRM={handleConnectCRM} onTryDemo={handleTryDemo} />
            ) : filteredAndSortedDeals.length === 0 ? (
              /* Filtered empty state */
              <div className="flex flex-col items-center justify-center py-20 text-center">
                <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl border border-border/40 bg-secondary/30">
                  <Filter className="h-6 w-6 text-muted-foreground/30" />
                </div>
                <p className="text-sm font-semibold text-muted-foreground">No deals match your filters</p>
                <p className="mt-1 max-w-xs text-xs text-muted-foreground/50">
                  Try broadening your search or clearing the active filters
                </p>
                <button onClick={clearFilters} className="mt-4 text-xs font-semibold text-primary hover:underline">
                  Clear all filters
                </button>
              </div>
            ) : (
              <>
                {/* Cache freshness indicator */}
                {cacheMeta && (
                  <div className="flex items-center gap-1.5 px-6 py-2 border-b border-border/20 text-xs text-muted-foreground/60">
                    {cacheMeta.needs_background_sync ? (
                      <>
                        <span className="h-1.5 w-1.5 rounded-full bg-yellow-400 animate-pulse" />
                        <span>Syncing in background…</span>
                      </>
                    ) : cacheMeta.source === "zoho" ? (
                      <>
                        <span className="h-1.5 w-1.5 rounded-full bg-blue-400" />
                        <span>Just updated from Zoho</span>
                      </>
                    ) : cacheMeta.fresh ? (
                      <>
                        <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
                        <span>Live · {cacheMeta.age_seconds != null && cacheMeta.age_seconds < 60
                          ? `${cacheMeta.age_seconds}s ago`
                          : cacheMeta.age_seconds != null
                            ? `${Math.round(cacheMeta.age_seconds / 60)}m ago`
                            : "cached"}</span>
                      </>
                    ) : null}
                  </div>
                )}
                <Table>
                  <TableHeader>
                    <TableRow className="border-border/30 hover:bg-transparent">
                      <TableHead className="py-3 pl-6 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/50">Deal</TableHead>
                      <TableHead className="py-3 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/50">Stage</TableHead>
                      <TableHead className="py-3 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/50">Owner</TableHead>
                      <TableHead className="py-3 text-right text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/50">Amount</TableHead>
                      <TableHead className="py-3 text-center text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/50">Score</TableHead>
                      <TableHead className="py-3 text-center text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/50">Warnings</TableHead>
                      <TableHead className="py-3 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/50">Status</TableHead>
                      <TableHead className="w-8" />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {(() => {
                      // Warn if 5+ deals share identical non-zero scores — likely a scoring bug
                      const scoreCounts: Record<number, number> = {};
                      filteredAndSortedDeals.forEach(d => { if (d.health_score > 0) scoreCounts[d.health_score] = (scoreCounts[d.health_score] ?? 0) + 1; });
                      Object.entries(scoreCounts).forEach(([score, count]) => {
                        if (count >= 5) console.warn(`[DealIQ] ${count} deals share health_score=${score} — possible scoring bug`);
                      });
                      return null;
                    })()}
                    {filteredAndSortedDeals.map((deal, idx) => {
                      const whyLine = getDealWhyLine(deal);
                      const scoreBarColor =
                        deal.health_score >= 75 ? "bg-health-green" :
                          deal.health_score >= 50 ? "bg-health-yellow" :
                            deal.health_score >= 25 ? "bg-health-orange" :
                              "bg-health-red";
                      const healthHex = deal.health_score >= 75 ? "#10b981" : deal.health_score >= 50 ? "#f59e0b" : deal.health_score >= 25 ? "#f97316" : "#ef4444";
                      const scoreLabel =
                        deal.health_score >= 75 ? "Healthy" :
                          deal.health_score >= 50 ? "At Risk" :
                            deal.health_score >= 25 ? "Critical" : "Zombie";
                      return (
                        <TableRow
                          key={deal.id}
                          onClick={() => { setPanelInitialSection(undefined); setSelectedDealId(deal.id); }}
                          className={cn(
                            "deal-row group cursor-pointer border-border/20 transition-all duration-100 fade-slide-in relative",
                            selectedDealId === deal.id
                              ? "bg-primary/10 hover:bg-primary/[0.13]"
                              : ""
                          )}
                          style={{ animationDelay: `${idx * 30}ms`, '--row-health-color': healthHex } as React.CSSProperties}
                          // Mark first row for tour
                          {...(idx === 0 ? { "data-tour": "analyse-btn" } : {})}
                        >
                          {/* Deal + Company */}
                          <TableCell className="py-3.5 pl-6">
                            <div className="flex items-center gap-3 min-w-0">
                              <div className={cn(
                                "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-xs font-bold",
                                dealInitialClass(deal.health_label)
                              )}>
                                {deal.deal_name.charAt(0).toUpperCase()}
                              </div>
                              <div className="min-w-0">
                                <div className="flex items-center gap-2">
                                  <p className="truncate text-sm font-semibold leading-tight text-foreground">
                                    {deal.deal_name}
                                  </p>
                                  <button
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      setPanelInitialSection(undefined);
                                      setPanelInitialTab("Battle Card");
                                      setSelectedDealId(deal.id);
                                    }}
                                    className="opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-1 text-xs text-sky-400 hover:text-sky-300 bg-sky-500/10 hover:bg-sky-500/15 border border-sky-500/20 rounded-lg px-2 py-0.5 flex-shrink-0"
                                  >
                                    <Zap size={10} strokeWidth={2.5} />
                                    Brief
                                  </button>
                                </div>
                                <p className="mt-0.5 truncate text-xs text-muted-foreground/60">
                                  {deal.company}
                                </p>
                                {whyLine && (
                                  <p className={cn("mt-0.5 truncate text-[10px] italic", whyLine.colorClass)}>
                                    {whyLine.text}
                                  </p>
                                )}
                              </div>
                            </div>
                          </TableCell>

                          {/* Stage — click to edit inline */}
                          <TableCell className="py-3.5" onClick={(e) => e.stopPropagation()}>
                            {savingStage === deal.id ? (
                              <div className="inline-flex items-center gap-1.5 text-xs text-muted-foreground/60">
                                <Loader2 size={12} className="animate-spin" />
                                Saving…
                              </div>
                            ) : editingStage?.dealId === deal.id ? (
                              <select
                                autoFocus
                                value={editingStage.value}
                                onChange={(e) => setEditingStage({ dealId: deal.id, value: e.target.value })}
                                onBlur={() => {
                                  if (editingStage.value !== deal.stage) {
                                    saveStageEdit(deal.id, editingStage.value, deal.stage);
                                  } else {
                                    setEditingStage(null);
                                  }
                                }}
                                onKeyDown={(e) => {
                                  if (e.key === "Enter") {
                                    if (editingStage.value !== deal.stage) {
                                      saveStageEdit(deal.id, editingStage.value, deal.stage);
                                    } else {
                                      setEditingStage(null);
                                    }
                                  }
                                  if (e.key === "Escape") setEditingStage(null);
                                }}
                                className="text-xs bg-secondary border border-border/60 rounded-lg px-2 py-1 text-foreground focus:outline-none focus:ring-1 focus:ring-primary/50"
                              >
                                {["Qualification", "Needs Analysis", "Value Proposition", "Proposal", "Negotiation", "Contract Sent", "Closed Won", "Closed Lost"].map((s) => (
                                  <option key={s} value={s}>{s}</option>
                                ))}
                              </select>
                            ) : (
                              <span
                                className={cn(
                                  "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium whitespace-nowrap cursor-pointer hover:opacity-80 transition-opacity",
                                  stagePillClass(deal.stage)
                                )}
                                title="Click to edit stage"
                                onClick={() => setEditingStage({ dealId: deal.id, value: deal.stage })}
                              >
                                {deal.stage}
                              </span>
                            )}
                          </TableCell>

                          {/* Owner */}
                          <TableCell className="py-3.5 max-w-[150px]">
                            <OwnerAvatar name={deal.owner ?? "—"} />
                          </TableCell>

                          {/* Amount */}
                          <TableCell className="py-3.5 text-right">
                            <span className="font-mono tabular-nums text-sm font-semibold text-foreground/90">
                              {formatCurrency(deal.amount)}
                            </span>
                          </TableCell>

                          {/* Health Score */}
                          <TableCell className="py-3.5 text-center">
                            <div
                              className="flex flex-col items-center gap-0.5"
                              title={`Health Score: ${deal.health_score}/100 — ${scoreLabel}`}
                            >
                              <div className="flex items-center gap-1">
                                <HealthRing score={deal.health_score} />
                                {deal.score_trend === "improving" && (
                                  <span className="text-xs text-health-green" title="Score improving">↗</span>
                                )}
                                {deal.score_trend === "declining" && (
                                  <span className="text-xs text-destructive" title="Score declining">↘</span>
                                )}
                                {deal.score_trend === "stable" && (
                                  <span className="text-xs text-muted-foreground" title="Score stable">→</span>
                                )}
                              </div>
                              <div className="w-full h-1 max-w-[40px] rounded-full bg-border/40 overflow-hidden">
                                <div
                                  className={cn("h-full rounded-full transition-all", scoreBarColor)}
                                  style={{ width: `${Math.max(deal.health_score, 2)}%` }}
                                />
                              </div>
                            </div>
                          </TableCell>

                          {/* Warnings */}
                          <TableCell className="py-3.5 text-center">
                            {(() => {
                              const w = dealWarnings[deal.id];
                              if (!w) {
                                return <span className="text-muted-foreground/20 text-xs">—</span>;
                              }
                              const tooltipText = w.top_warning
                                ? w.top_warning
                                : w.has_critical
                                  ? `${w.warning_count} critical warning${w.warning_count !== 1 ? "s" : ""} — click to view`
                                  : w.warning_count > 0
                                    ? `${w.warning_count} warning${w.warning_count !== 1 ? "s" : ""} — click to view`
                                    : "All signals healthy";
                              if (w.has_critical) {
                                return (
                                  <Tooltip>
                                    <TooltipTrigger asChild>
                                      <div className="inline-flex items-center gap-1 rounded-lg border border-rose-500/25 bg-rose-500/15 px-2 py-0.5 text-rose-400 cursor-help">
                                        <AlertTriangle size={11} strokeWidth={2.5} />
                                        <span className="text-xs font-semibold">{w.warning_count}</span>
                                      </div>
                                    </TooltipTrigger>
                                    <TooltipContent side="top" className="max-w-[220px] text-xs text-center">
                                      {tooltipText}
                                    </TooltipContent>
                                  </Tooltip>
                                );
                              }
                              if (w.warning_count > 0) {
                                return (
                                  <Tooltip>
                                    <TooltipTrigger asChild>
                                      <div className="inline-flex items-center gap-1 rounded-lg border border-amber-500/25 bg-amber-500/15 px-2 py-0.5 text-amber-400 cursor-help">
                                        <AlertCircle size={11} strokeWidth={2.5} />
                                        <span className="text-xs font-semibold">{w.warning_count}</span>
                                      </div>
                                    </TooltipTrigger>
                                    <TooltipContent side="top" className="max-w-[220px] text-xs text-center">
                                      {tooltipText}
                                    </TooltipContent>
                                  </Tooltip>
                                );
                              }
                              return <CheckCircle2 size={14} className="text-emerald-500" strokeWidth={2} />;
                            })()}
                          </TableCell>

                          {/* Status Badge */}
                          <TableCell className="py-3.5">
                            <Badge variant="outline" className={cn(
                              "border text-xs font-medium capitalize",
                              healthColor(deal.health_label)
                            )}>
                              {deal.health_label.replace("_", " ")}
                            </Badge>
                          </TableCell>

                          {/* Chevron */}
                          <TableCell className="py-3.5 pr-4 w-8">
                            <ChevronRight className={cn(
                              "h-4 w-4 transition-all duration-150",
                              selectedDealId === deal.id
                                ? "text-primary opacity-100"
                                : "text-muted-foreground opacity-0 group-hover:opacity-50"
                            )} />
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>

                {/* Pagination */}
                {totalPages > 1 && (
                  <div className="flex items-center justify-between border-t border-border/20 px-6 py-4">
                    {/* Left: range label */}
                    <p className="text-sm text-muted-foreground/50 tabular-nums">
                      {loadingDeals
                        ? "Loading…"
                        : `Showing ${startItem}–${endItem} of ${totalDeals} deals`}
                    </p>

                    {/* Right: page buttons */}
                    <div className="flex items-center gap-1">
                      {/* Prev */}
                      <button
                        onClick={() => goToPage(currentPage - 1)}
                        disabled={!hasPrev || loadingDeals}
                        className="px-3 py-1 rounded text-sm bg-secondary/60 text-muted-foreground border border-border/40 transition-colors duration-150 hover:bg-secondary hover:text-foreground disabled:opacity-30 disabled:cursor-not-allowed"
                      >
                        ← Prev
                      </button>

                      {/* Page number buttons with ellipsis */}
                      {buildPageList(currentPage, totalPages).map((pg, i) =>
                        pg === "..." ? (
                          <span key={`ellipsis-${i}`} className="px-2 py-1 text-sm text-muted-foreground/40 select-none">
                            …
                          </span>
                        ) : (
                          <button
                            key={pg}
                            onClick={() => goToPage(pg)}
                            disabled={loadingDeals}
                            className={cn(
                              "px-3 py-1 rounded text-sm font-medium transition-colors duration-150 min-w-[32px]",
                              pg === currentPage
                                ? "bg-primary text-primary-foreground"
                                : "bg-secondary/60 text-muted-foreground border border-border/40 hover:bg-secondary hover:text-foreground disabled:opacity-30"
                            )}
                          >
                            {pg}
                          </button>
                        )
                      )}

                      {/* Next */}
                      <button
                        onClick={() => goToPage(currentPage + 1)}
                        disabled={!hasNext || loadingDeals}
                        className="px-3 py-1 rounded text-sm bg-secondary/60 text-muted-foreground border border-border/40 transition-colors duration-150 hover:bg-secondary hover:text-foreground disabled:opacity-30 disabled:cursor-not-allowed"
                      >
                        Next →
                      </button>
                    </div>
                  </div>
                )}
              </>
            )}
          </CardContent>
        </Card>

        {/* ── Team Activity Card ── */}
        <Card className="overflow-hidden border-border/40 bg-card/60 animate-slide-up" style={{ animationDelay: "240ms" }}>
          <div className="flex items-center justify-between px-5 pt-5 pb-3">
              <button
                onClick={handleTeamSummaryToggle}
                className="flex items-center gap-2.5 text-left flex-1 min-w-0"
              >
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 shrink-0">
                  <Users2 className="h-4 w-4 text-primary" />
                </div>
                <div className="min-w-0">
                  <h2 className="text-sm font-semibold text-foreground">Team Activity — Last 7 Days</h2>
                  {teamSummary && (
                    <p className="text-xs text-muted-foreground/60">
                      Team avg: {teamSummary.team_avg_deals_touched_7d} deals touched
                      {teamSummary.team_avg_health_score > 0
                        ? ` · Health avg: ${Math.round(teamSummary.team_avg_health_score)}`
                        : " · Health avg: calculating…"}
                    </p>
                  )}
                  {!teamSummaryFetched && !loadingTeam && (
                    <p className="text-xs text-muted-foreground/40">Click to load</p>
                  )}
                </div>
                <ChevronDown className={cn("h-4 w-4 text-muted-foreground/50 shrink-0 transition-transform ml-1", teamSummaryExpanded && "rotate-180")} />
              </button>
              {teamSummaryFetched && (
                <button
                  onClick={(e) => { e.stopPropagation(); fetchTeamSummary(); }}
                  disabled={loadingTeam}
                  className="flex items-center gap-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground disabled:opacity-50 ml-3"
                >
                  <RefreshCw className={cn("h-3.5 w-3.5", loadingTeam && "animate-spin")} />
                  Refresh
                </button>
              )}
            </div>

            {teamSummaryExpanded && <CardContent className="p-0 pb-4">
              {loadingTeam ? (
                <div className="space-y-2 px-5">
                  {[...Array(3)].map((_, i) => (
                    <Skeleton key={i} className="h-10 w-full rounded-lg animate-pulse" />
                  ))}
                </div>
              ) : teamSummary && teamSummary.reps.length > 0 ? (
                <div className="divide-y divide-border/20">
                  {/* Header row */}
                  <div className="grid grid-cols-[1fr_100px_80px_100px_80px] gap-2 px-5 py-2">
                    <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/50">Rep</span>
                    <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/50 text-center">Deals Touched</span>
                    <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/50 text-center">Avg Health</span>
                    <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/50 text-right">Pipeline</span>
                    <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/50 text-right">Trend</span>
                  </div>
                  {teamSummary.reps.map((rep) => {
                    const initials = rep.rep_name.split(" ").filter(Boolean).map(n => n[0]).slice(0, 2).join("").toUpperCase() || "?";
                    return (
                      <div key={rep.rep_name} className="grid grid-cols-[1fr_100px_80px_100px_80px] items-center gap-2 px-5 py-3 hover:bg-secondary/30 transition-colors">
                        <div className="flex items-center gap-2 min-w-0">
                          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/15 text-[10px] font-bold text-primary">
                            {initials}
                          </div>
                          <div className="min-w-0">
                            <p className="text-sm font-medium text-foreground truncate">{rep.rep_name}</p>
                            <p className="text-[10px] text-muted-foreground/60">{rep.deals_active} deals</p>
                          </div>
                        </div>
                        <div className="text-center">
                          <span className={cn(
                            "text-sm font-bold tabular-nums",
                            rep.deals_touched_7d / Math.max(rep.deals_active, 1) >= 0.6 ? "text-health-green" :
                              rep.deals_touched_7d / Math.max(rep.deals_active, 1) >= 0.3 ? "text-health-yellow" :
                                "text-health-red"
                          )}>
                            {rep.deals_touched_7d}
                          </span>
                          <span className="text-xs text-muted-foreground"> / {rep.deals_active}</span>
                        </div>
                        <div className="text-center">
                          {rep.avg_health_score > 0 ? (
                            <span className={cn("text-sm font-bold tabular-nums", scoreColor(rep.avg_health_score))}>
                              {Math.round(rep.avg_health_score)}
                            </span>
                          ) : (
                            <span className="text-xs text-muted-foreground/40">—</span>
                          )}
                        </div>
                        <div className="text-right">
                          <span className="text-sm font-semibold tabular-nums text-foreground/80">
                            {formatCurrency(rep.total_pipeline_value)}
                          </span>
                        </div>
                        <div
                          className="flex items-center justify-end gap-1"
                          title="Active = touched 50%+ of their deals this week"
                        >
                          {rep.activity_trend === "active" && (
                            <><TrendingUp className="h-3.5 w-3.5 text-health-green" /><span className="text-xs text-health-green font-medium">↗ Active</span></>
                          )}
                          {rep.activity_trend === "slowing" && (
                            <><Minus className="h-3.5 w-3.5 text-health-yellow" /><span className="text-xs text-health-yellow font-medium">→ Slowing</span></>
                          )}
                          {rep.activity_trend === "inactive" && (
                            <><TrendingDown className="h-3.5 w-3.5 text-health-red" /><span className="text-xs text-health-red font-medium">↘ Inactive</span></>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="px-5 py-4 text-xs text-muted-foreground">Could not load team data.</p>
              )}
            </CardContent>}
          </Card>

      </main>

      {/* ── Floating Action Button — Check Email Before Sending ── */}
      {allDeals.length > 0 && (
        <div
          className="fixed bottom-6 right-6 z-30"
          data-tour="mismatch-fab"
        >
          <button
            onClick={openMismatchForMostAtRisk}
            className="group flex items-center gap-0 overflow-hidden rounded-full border border-border/40 bg-card/80 backdrop-blur-sm px-3 py-2.5 text-xs font-medium text-muted-foreground shadow-lg shadow-black/30 transition-all duration-300 hover:border-amber-500/40 hover:text-amber-400 hover:bg-card hover:gap-2 hover:px-4"
          >
            <ClipboardCheck className="h-4 w-4 shrink-0 transition-transform group-hover:scale-110" />
            <span className="max-w-0 overflow-hidden whitespace-nowrap transition-all duration-300 group-hover:max-w-xs">
              Check Email Before Sending
            </span>
          </button>
        </div>
      )}

      {/* ── Panels ── */}
      <DealDetailPanel
        dealId={selectedDealId}
        dealName={selectedDeal?.deal_name ?? ""}
        repName={selectedDeal?.owner ?? session?.display_name}
        stage={selectedDeal?.stage}
        amount={selectedDeal?.amount}
        healthScore={selectedDeal?.health_score}
        healthLabel={selectedDeal?.health_label}
        onClose={() => { setSelectedDealId(null); setPanelInitialSection(undefined); setPanelInitialTab("Overview"); }}
        initialSection={panelInitialSection}
        initialTab={panelInitialTab}
        onDealUpdated={(field, value) => {
          if (!selectedDealId) return;
          setAllDeals((prev) => prev.map((d) => {
            if (d.id !== selectedDealId) return d;
            if (field === "Stage") return { ...d, stage: String(value) };
            if (field === "Amount") return { ...d, amount: Number(value) };
            if (field === "health_score") return { ...d, health_score: Number(value) };
            if (field === "health_label") return { ...d, health_label: String(value) };
            return d;
          }));
        }}
      />
      <AlertsDigestPanel open={digestOpen} onClose={() => setDigestOpen(false)} />
      <BuyingSignalPanel open={signalPanelOpen} onClose={() => setSignalPanelOpen(false)} />

      {/* ── Guided tour ── */}
      {tourActive && <DemoTour onEnd={() => setTourActive(false)} />}
    </div>
  );
}
