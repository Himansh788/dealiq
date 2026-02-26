import { useEffect, useState, useMemo } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  AlertTriangle, Activity, DollarSign, Users, Search, X, Filter, ChevronRight,
  Users2, TrendingUp, TrendingDown, Minus, RefreshCw,
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
  owner?: string;
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

function healthColor(label: string) {
  switch (label) {
    case "healthy":  return "bg-health-green/15 text-health-green border-health-green/25";
    case "at_risk":  return "bg-health-yellow/15 text-health-yellow border-health-yellow/25";
    case "critical": return "bg-health-orange/15 text-health-orange border-health-orange/25";
    case "zombie":   return "bg-health-red/15 text-health-red border-health-red/25";
    default:         return "bg-muted text-muted-foreground border-border/40";
  }
}

function dealInitialClass(label: string): string {
  switch (label) {
    case "healthy":  return "bg-health-green/15 text-health-green";
    case "at_risk":  return "bg-health-yellow/15 text-health-yellow";
    case "critical": return "bg-health-orange/15 text-health-orange";
    case "zombie":   return "bg-health-red/15 text-health-red";
    default:         return "bg-secondary text-muted-foreground";
  }
}

function stagePillClass(stage: string): string {
  const s = stage.toLowerCase();
  if (s.includes("discovery"))  return "bg-sky-500/10 text-sky-400 border-sky-500/20";
  if (s.includes("qualif"))     return "bg-violet-500/10 text-violet-400 border-violet-500/20";
  if (s.includes("proposal"))   return "bg-amber-500/10 text-amber-400 border-amber-500/20";
  if (s.includes("negotiat"))   return "bg-orange-500/10 text-orange-400 border-orange-500/20";
  if (s.includes("won"))        return "bg-health-green/10 text-health-green border-health-green/20";
  if (s.includes("lost"))       return "bg-health-red/10 text-health-red border-health-red/20";
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

// Health pill config — static class strings for Tailwind JIT
const HEALTH_PILLS = [
  {
    key: "healthy",
    label: "Healthy",
    metricKey: "healthy_count" as keyof Metrics,
    active:   "border-health-green/60 bg-health-green/20 text-health-green",
    inactive: "border-health-green/20 bg-health-green/5 text-health-green/80 hover:bg-health-green/15 hover:border-health-green/40",
    dot: "bg-health-green",
  },
  {
    key: "at_risk",
    label: "At Risk",
    metricKey: "at_risk_count" as keyof Metrics,
    active:   "border-health-yellow/60 bg-health-yellow/20 text-health-yellow",
    inactive: "border-health-yellow/20 bg-health-yellow/5 text-health-yellow/80 hover:bg-health-yellow/15 hover:border-health-yellow/40",
    dot: "bg-health-yellow",
  },
  {
    key: "critical",
    label: "Critical",
    metricKey: "critical_count" as keyof Metrics,
    active:   "border-health-orange/60 bg-health-orange/20 text-health-orange",
    inactive: "border-health-orange/20 bg-health-orange/5 text-health-orange/80 hover:bg-health-orange/15 hover:border-health-orange/40",
    dot: "bg-health-orange",
  },
  {
    key: "zombie",
    label: "Zombie",
    metricKey: "zombie_count" as keyof Metrics,
    active:   "border-health-red/60 bg-health-red/20 text-health-red",
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
  { id: "1", deal_name: "Acme Corp Enterprise",  company: "Acme Corp",    stage: "Negotiation",   amount: 450000, health_score: 28, health_label: "zombie",   owner: "Sarah Chen" },
  { id: "2", deal_name: "TechFlow Platform",      company: "TechFlow Inc", stage: "Proposal",      amount: 320000, health_score: 42, health_label: "critical", owner: "James Okafor" },
  { id: "3", deal_name: "DataVault Migration",    company: "DataVault",    stage: "Discovery",     amount: 180000, health_score: 55, health_label: "at_risk",  owner: "Maya Patel" },
  { id: "4", deal_name: "CloudSync Annual",       company: "CloudSync",    stage: "Negotiation",   amount: 275000, health_score: 88, health_label: "healthy",  owner: "Sarah Chen" },
  { id: "5", deal_name: "Nexus Analytics Suite",  company: "Nexus Labs",   stage: "Qualification", amount: 195000, health_score: 35, health_label: "critical", owner: "James Okafor" },
  { id: "6", deal_name: "Orbital SaaS Rollout",   company: "Orbital Inc",  stage: "Negotiation",   amount: 420000, health_score: 71, health_label: "at_risk",  owner: "Maya Patel" },
];

// ── Component ─────────────────────────────────────────────────────────────────

export default function Dashboard() {
  const { session } = useSession();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { toast } = useToast();

  // Data state
  const [metrics, setMetrics]               = useState<Metrics | null>(null);
  const [allDeals, setAllDeals]             = useState<Deal[]>([]);
  const [loadingMetrics, setLoadingMetrics] = useState(true);
  const [loadingDeals, setLoadingDeals]     = useState(true);
  const [selectedDealId, setSelectedDealId] = useState<string | null>(null);
  const [digestOpen, setDigestOpen]         = useState(false);
  const [digestCriticalCount, setDigestCriticalCount] = useState<number | undefined>(undefined);
  const [signalPanelOpen, setSignalPanelOpen] = useState(false);
  const [teamSummary, setTeamSummary]         = useState<TeamActivitySummary | null>(null);
  const [loadingTeam, setLoadingTeam]         = useState(false);

  // Pagination
  const [currentPage, setCurrentPage] = useState(1);
  const [totalDeals, setTotalDeals]   = useState(0);
  const PER_PAGE = 20;

  // Filter state
  const [searchName, setSearchName]     = useState("");
  const [filterOwner, setFilterOwner]   = useState("all");
  const [filterStage, setFilterStage]   = useState("all");
  const [filterHealth, setFilterHealth] = useState("all");

  // Load metrics
  useEffect(() => {
    if (!session) { navigate("/", { replace: true }); return; }
    api.getMetrics()
      .then((data: any) => {
        setMetrics({
          total_deals:          data.total_deals          ?? 0,
          total_value:          data.total_value          ?? data.pipeline_value  ?? 0,
          average_health_score: data.average_health_score ?? data.avg_health_score ?? 0,
          healthy_count:        data.healthy_count        ?? 0,
          at_risk_count:        data.at_risk_count        ?? 0,
          critical_count:       data.critical_count       ?? 0,
          zombie_count:         data.zombie_count         ?? 0,
          deals_needing_action: data.deals_needing_action ?? data.needs_action    ?? 0,
        });
      })
      .catch(() => setMetrics(DEMO_METRICS))
      .finally(() => setLoadingMetrics(false));
  }, [session, navigate]);

  // Load all deals once
  useEffect(() => {
    if (!session) return;
    setLoadingDeals(true);
    api.getAllDeals()
      .then((list: any[]) => {
        const mapped: Deal[] = list.map((d: any) => ({
          id:           d.id,
          deal_name:    d.name ?? d.deal_name ?? "Unnamed Deal",
          company:      d.account_name ?? d.company ?? "—",
          stage:        d.stage ?? "Unknown",
          amount:       d.amount ?? 0,
          health_score: d.health_score ?? 0,
          health_label: d.health_label ?? "critical",
          owner:        typeof d.owner === "object" ? d.owner?.name : d.owner ?? "—",
        }));
        setAllDeals(mapped);
        setTotalDeals(mapped.length);
      })
      .catch(() => { setAllDeals(DEMO_DEALS); setTotalDeals(DEMO_DEALS.length); })
      .finally(() => setLoadingDeals(false));
  }, [session]);

  // Load team activity summary (lazy, low priority)
  const fetchTeamSummary = () => {
    if (!session) return;
    setLoadingTeam(true);
    api.getTeamActivitySummary()
      .then(setTeamSummary)
      .catch(() => { /* silent — team card just won't render */ })
      .finally(() => setLoadingTeam(false));
  };

  useEffect(() => {
    if (!session) return;
    fetchTeamSummary();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session]);

  // Derived filter options
  const ownerOptions = useMemo(() => {
    const names = [...new Set(allDeals.map(d => d.owner).filter(Boolean))] as string[];
    return names.sort();
  }, [allDeals]);

  const stageOptions = useMemo(() => {
    const stages = [...new Set(allDeals.map(d => d.stage).filter(Boolean))] as string[];
    return stages.sort();
  }, [allDeals]);

  // Client-side filtering
  const filteredDeals = useMemo(() => {
    return allDeals.filter(deal => {
      if (searchName && !deal.deal_name.toLowerCase().includes(searchName.toLowerCase()) &&
          !deal.company.toLowerCase().includes(searchName.toLowerCase())) return false;
      if (filterOwner !== "all" && deal.owner !== filterOwner) return false;
      if (filterStage !== "all" && deal.stage !== filterStage) return false;
      if (filterHealth !== "all" && deal.health_label !== filterHealth) return false;
      return true;
    });
  }, [allDeals, searchName, filterOwner, filterStage, filterHealth]);

  const hasActiveFilters = searchName || filterOwner !== "all" || filterStage !== "all" || filterHealth !== "all";

  const clearFilters = () => {
    setSearchName(""); setFilterOwner("all"); setFilterStage("all"); setFilterHealth("all");
  };

  // Pagination
  const totalPages = Math.ceil(totalDeals / PER_PAGE);
  const startItem  = (currentPage - 1) * PER_PAGE + 1;
  const endItem    = Math.min(currentPage * PER_PAGE, totalDeals);

  const selectedDeal = allDeals.find(d => d.id === selectedDealId);

  // Open deal from ?deal=ID query param (set by command palette on other pages)
  useEffect(() => {
    const dealParam = searchParams.get("deal");
    if (dealParam && allDeals.length > 0) {
      const found = allDeals.find(d => d.id === dealParam);
      if (found) {
        setSelectedDealId(dealParam);
        setSearchParams({}, { replace: true });
      }
    }
  }, [searchParams, allDeals, setSearchParams]);

  const summaryCards = [
    { label: "Total Deals",    value: metrics?.total_deals,           icon: Users,         format: (v: number) => String(v),              isAlert: false },
    { label: "Pipeline Value", value: metrics?.total_value,           icon: DollarSign,    format: formatCurrency,                        isAlert: false },
    { label: "Avg Health",     value: metrics?.average_health_score,  icon: Activity,      format: (v: number) => String(Math.round(v)),  isAlert: false, colorFn: (v: number) => scoreColor(v) },
    { label: "Needs Action",   value: metrics?.deals_needing_action,  icon: AlertTriangle, format: (v: number) => String(v),              isAlert: true },
  ];

  return (
    <div className="min-h-screen bg-background">

      {/* ── Header ── */}
      <NavBar
        onOpenDigest={() => setDigestOpen(true)}
        onOpenSignal={() => setSignalPanelOpen(true)}
        digestCriticalCount={digestCriticalCount}
        deals={allDeals}
        onSelectDeal={(id) => setSelectedDealId(id)}
      />

      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 space-y-5">

        {/* ── Summary Cards ── */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {summaryCards.map((card, idx) => (
            <Card
              key={card.label}
              className="group relative overflow-hidden border-border/40 bg-card/60 transition-all duration-200 hover:border-border/70 hover:shadow-xl hover:shadow-black/25 animate-slide-up"
              style={{ animationDelay: `${idx * 55}ms` }}
            >
              {/* Top accent line */}
              <div className={cn(
                "absolute inset-x-0 top-0 h-px",
                card.isAlert
                  ? "bg-gradient-to-r from-transparent via-health-red/70 to-transparent"
                  : "bg-gradient-to-r from-transparent via-primary/50 to-transparent"
              )} />
              <CardContent className="flex items-center gap-4 p-5">
                <div className={cn(
                  "flex h-11 w-11 shrink-0 items-center justify-center rounded-xl",
                  card.isAlert ? "bg-health-red/10" : "bg-primary/10"
                )}>
                  <card.icon className={cn("h-5 w-5", card.isAlert ? "text-health-red" : "text-primary")} />
                </div>
                <div className="min-w-0">
                  <p className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground/60 mb-0.5">
                    {card.label}
                  </p>
                  {loadingMetrics ? (
                    <Skeleton className="mt-1 h-8 w-20" />
                  ) : (
                    <p className={cn(
                      "text-3xl font-black tracking-tight tabular-nums",
                      card.colorFn ? card.colorFn(card.value ?? 0) : card.isAlert ? "text-health-red" : "text-foreground"
                    )}>
                      {card.value != null ? card.format(card.value) : "—"}
                    </p>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>

        {/* ── Health breakdown pills ── */}
        {metrics && !loadingMetrics && (
          <div className="flex flex-wrap gap-2 animate-fade-in" style={{ animationDelay: "220ms" }}>
            {HEALTH_PILLS.map(pill => {
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
        <Card className="overflow-hidden border-border/40 bg-card/60 animate-slide-up" style={{ animationDelay: "180ms" }}>

          {/* Table header / filters */}
          <div className="p-5 pb-4 space-y-3.5">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-base font-semibold text-foreground">Deal Pipeline</h2>
                <p className="mt-0.5 text-xs text-muted-foreground/70">
                  Worst health first · Active current-quarter deals
                  {!hasActiveFilters && totalDeals > 0 && ` · ${startItem}–${endItem} of ${totalDeals}`}
                  {hasActiveFilters && ` · ${filteredDeals.length} match${filteredDeals.length !== 1 ? "es" : ""}`}
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
          </div>

          <CardContent className="p-0">
            {loadingDeals ? (
              <div className="divide-y divide-border/20 px-6 py-2">
                {[...Array(6)].map((_, i) => (
                  <div key={i} className="flex items-center gap-4 py-4">
                    <Skeleton className="h-8 w-8 shrink-0 rounded-lg" />
                    <div className="flex-1 space-y-2">
                      <Skeleton className="h-3.5 w-44" />
                      <Skeleton className="h-3 w-28" />
                    </div>
                    <Skeleton className="h-5 w-20 rounded-full" />
                    <Skeleton className="h-5 w-24" />
                    <Skeleton className="h-5 w-16" />
                    <Skeleton className="h-5 w-12 rounded-full" />
                  </div>
                ))}
              </div>
            ) : filteredDeals.length === 0 ? (
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
                <Table>
                  <TableHeader>
                    <TableRow className="border-border/30 hover:bg-transparent">
                      <TableHead className="py-3 pl-6 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/50">
                        Deal
                      </TableHead>
                      <TableHead className="py-3 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/50">
                        Stage
                      </TableHead>
                      <TableHead className="py-3 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/50">
                        Owner
                      </TableHead>
                      <TableHead className="py-3 text-right text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/50">
                        Amount
                      </TableHead>
                      <TableHead className="py-3 text-center text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/50">
                        Score
                      </TableHead>
                      <TableHead className="py-3 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/50">
                        Status
                      </TableHead>
                      <TableHead className="w-8" />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {filteredDeals.map((deal) => (
                      <TableRow
                        key={deal.id}
                        onClick={() => setSelectedDealId(deal.id)}
                        className={cn(
                          "group cursor-pointer border-border/20 transition-colors duration-100",
                          selectedDealId === deal.id
                            ? "bg-primary/10 hover:bg-primary/[0.13]"
                            : "hover:bg-secondary/40"
                        )}
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
                              <p className="truncate text-sm font-semibold leading-tight text-foreground">
                                {deal.deal_name}
                              </p>
                              <p className="mt-0.5 truncate text-xs text-muted-foreground/60">
                                {deal.company}
                              </p>
                            </div>
                          </div>
                        </TableCell>

                        {/* Stage */}
                        <TableCell className="py-3.5">
                          <span className={cn(
                            "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium whitespace-nowrap",
                            stagePillClass(deal.stage)
                          )}>
                            {deal.stage}
                          </span>
                        </TableCell>

                        {/* Owner */}
                        <TableCell className="py-3.5 max-w-[150px]">
                          <OwnerAvatar name={deal.owner ?? "—"} />
                        </TableCell>

                        {/* Amount */}
                        <TableCell className="py-3.5 text-right">
                          <span className="tabular-nums text-sm font-semibold text-foreground/90">
                            {formatCurrency(deal.amount)}
                          </span>
                        </TableCell>

                        {/* Health Ring */}
                        <TableCell className="py-3.5 text-center">
                          <div className="flex justify-center">
                            <HealthRing score={deal.health_score} />
                          </div>
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
                    ))}
                  </TableBody>
                </Table>

                {/* Pagination */}
                {!hasActiveFilters && totalPages > 1 && (
                  <div className="flex items-center justify-between border-t border-border/20 px-6 py-4">
                    <p className="text-xs text-muted-foreground/50">Page {currentPage} of {totalPages}</p>
                    <div className="flex items-center gap-1">
                      <Button variant="outline" size="sm"
                        onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                        disabled={currentPage === 1}
                        className="h-8 border-border/40 px-3 text-xs">
                        Previous
                      </Button>
                      {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                        const start = Math.max(1, Math.min(currentPage - 2, totalPages - 4));
                        return start + i;
                      }).map(page => (
                        <Button
                          key={page}
                          variant={page === currentPage ? "default" : "outline"}
                          size="sm"
                          onClick={() => setCurrentPage(page)}
                          className={cn("h-8 w-8 p-0 text-xs", page !== currentPage && "border-border/40")}
                        >
                          {page}
                        </Button>
                      ))}
                      <Button variant="outline" size="sm"
                        onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                        disabled={currentPage === totalPages}
                        className="h-8 border-border/40 px-3 text-xs">
                        Next
                      </Button>
                    </div>
                  </div>
                )}
              </>
            )}
          </CardContent>
        </Card>
        {/* ── Team Activity Card ── */}
        {(loadingTeam || teamSummary) && (
          <Card className="overflow-hidden border-border/40 bg-card/60 animate-slide-up" style={{ animationDelay: "240ms" }}>
            <div className="flex items-center justify-between px-5 pt-5 pb-3">
              <div className="flex items-center gap-2.5">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10">
                  <Users2 className="h-4 w-4 text-primary" />
                </div>
                <div>
                  <h2 className="text-sm font-semibold text-foreground">Team Activity — Last 7 Days</h2>
                  {teamSummary && (
                    <p className="text-xs text-muted-foreground/60">
                      Team avg: {teamSummary.team_avg_deals_touched_7d} deals touched · Health avg: {Math.round(teamSummary.team_avg_health_score)}
                    </p>
                  )}
                </div>
              </div>
              <button
                onClick={fetchTeamSummary}
                disabled={loadingTeam}
                className="flex items-center gap-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground disabled:opacity-50"
              >
                <RefreshCw className={cn("h-3.5 w-3.5", loadingTeam && "animate-spin")} />
                Refresh
              </button>
            </div>

            <CardContent className="p-0 pb-4">
              {loadingTeam ? (
                <div className="space-y-2 px-5">
                  {[...Array(3)].map((_, i) => (
                    <Skeleton key={i} className="h-10 w-full rounded-lg" />
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
                          <span className={cn(
                            "text-sm font-bold tabular-nums",
                            scoreColor(rep.avg_health_score)
                          )}>
                            {Math.round(rep.avg_health_score)}
                          </span>
                        </div>
                        <div className="text-right">
                          <span className="text-sm font-semibold tabular-nums text-foreground/80">
                            {formatCurrency(rep.total_pipeline_value)}
                          </span>
                        </div>
                        <div className="flex items-center justify-end gap-1">
                          {rep.activity_trend === "active" && (
                            <>
                              <TrendingUp className="h-3.5 w-3.5 text-health-green" />
                              <span className="text-xs text-health-green font-medium">Active</span>
                            </>
                          )}
                          {rep.activity_trend === "slowing" && (
                            <>
                              <Minus className="h-3.5 w-3.5 text-health-yellow" />
                              <span className="text-xs text-health-yellow font-medium">Slowing</span>
                            </>
                          )}
                          {rep.activity_trend === "inactive" && (
                            <>
                              <TrendingDown className="h-3.5 w-3.5 text-health-red" />
                              <span className="text-xs text-health-red font-medium">Inactive ⚠</span>
                            </>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="px-5 py-4 text-xs text-muted-foreground">Could not load team data.</p>
              )}
            </CardContent>
          </Card>
        )}

      </main>

      <DealDetailPanel
        dealId={selectedDealId}
        dealName={selectedDeal?.deal_name ?? ""}
        repName={selectedDeal?.owner ?? session?.display_name}
        stage={selectedDeal?.stage}
        amount={selectedDeal?.amount}
        healthScore={selectedDeal?.health_score}
        healthLabel={selectedDeal?.health_label}
        onClose={() => setSelectedDealId(null)}
      />
      <AlertsDigestPanel open={digestOpen} onClose={() => setDigestOpen(false)} />
      <BuyingSignalPanel open={signalPanelOpen} onClose={() => setSignalPanelOpen(false)} />
    </div>
  );
}
