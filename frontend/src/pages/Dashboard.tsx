import { useEffect, useState, useMemo } from "react";
import { useNavigate, Link } from "react-router-dom";
import {
  BarChart3, AlertTriangle, LogOut, TrendingUp,
  Activity, DollarSign, Users, Search, X, Filter, Radar
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
import DealDetailPanel from "@/components/DealDetailPanel";
import AlertsDigestPanel, { AlertsBell } from "@/components/AlertsDigestPanel";
import BuyingSignalPanel from "@/components/BuyingSignalPanel";

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

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatCurrency(val: number): string {
  if (val >= 1_000_000) return `$${(val / 1_000_000).toFixed(1)}M`;
  if (val >= 1_000) return `$${Math.round(val / 1_000)}K`;
  return `$${val}`;
}

function healthColor(label: string) {
  switch (label) {
    case "healthy":  return "bg-health-green/20 text-health-green border-health-green/30";
    case "at_risk":  return "bg-health-yellow/20 text-health-yellow border-health-yellow/30";
    case "critical": return "bg-health-orange/20 text-health-orange border-health-orange/30";
    case "zombie":   return "bg-health-red/20 text-health-red border-health-red/30";
    default:         return "bg-muted text-muted-foreground";
  }
}

function scoreColor(score: number) {
  if (score >= 75) return "text-health-green";
  if (score >= 50) return "text-health-yellow";
  return "text-health-red";
}

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
  const { session, logout, isDemo } = useSession();
  const navigate = useNavigate();
  const { toast } = useToast();

  // Data state
  const [metrics, setMetrics]               = useState<Metrics | null>(null);
  const [allDeals, setAllDeals]             = useState<Deal[]>([]);   // full unfiltered list for this page
  const [loadingMetrics, setLoadingMetrics] = useState(true);
  const [loadingDeals, setLoadingDeals]     = useState(true);
  const [selectedDealId, setSelectedDealId] = useState<string | null>(null);
  const [digestOpen, setDigestOpen] = useState(false);
  const [digestCriticalCount, setDigestCriticalCount] = useState<number | undefined>(undefined);
  const [signalPanelOpen, setSignalPanelOpen] = useState(false);

  // Pagination
  const [currentPage, setCurrentPage] = useState(1);
  const [totalDeals, setTotalDeals]   = useState(0);
  const PER_PAGE = 20;

  // ── Filter state ──────────────────────────────────────────────────────────
  const [searchName, setSearchName]     = useState("");
  const [filterOwner, setFilterOwner]   = useState("all");
  const [filterStage, setFilterStage]   = useState("all");
  const [filterHealth, setFilterHealth] = useState("all");

  // ── Load metrics ──────────────────────────────────────────────────────────
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

  // ── Load ALL deals once — getAllDeals loops pages internally ─────────────
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
      })
      .catch(() => { setAllDeals(DEMO_DEALS); })
      .finally(() => setLoadingDeals(false));
  }, [session]);   // ← runs once on login — getAllDeals handles all pages

  // ── Derived filter options (built from loaded deals) ──────────────────────
  const ownerOptions = useMemo(() => {
    const names = [...new Set(allDeals.map(d => d.owner).filter(Boolean))] as string[];
    return names.sort();
  }, [allDeals]);

  const stageOptions = useMemo(() => {
    const stages = [...new Set(allDeals.map(d => d.stage).filter(Boolean))] as string[];
    return stages.sort();
  }, [allDeals]);

  // ── Client-side filtering ─────────────────────────────────────────────────
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
    setSearchName("");
    setFilterOwner("all");
    setFilterStage("all");
    setFilterHealth("all");
  };

  // ── Pagination ────────────────────────────────────────────────────────────
  // When filters are active, show filtered count. Otherwise show server total.
  const displayTotal   = hasActiveFilters ? filteredDeals.length : totalDeals;
  const totalPages     = Math.ceil(totalDeals / PER_PAGE);
  const startItem      = (currentPage - 1) * PER_PAGE + 1;
  const endItem        = Math.min(currentPage * PER_PAGE, totalDeals);

  const handleLogout = () => { logout(); navigate("/"); };
  const selectedDeal = allDeals.find(d => d.id === selectedDealId);

  const summaryCards = [
    { label: "Total Deals",    value: metrics?.total_deals,           icon: Users,         format: (v: number) => String(v) },
    { label: "Pipeline Value", value: metrics?.total_value,           icon: DollarSign,    format: formatCurrency },
    { label: "Avg Health",     value: metrics?.average_health_score,  icon: Activity,      format: (v: number) => String(Math.round(v)), colorFn: (v: number) => scoreColor(v) },
    { label: "Needs Action",   value: metrics?.deals_needing_action,  icon: AlertTriangle, format: (v: number) => String(v), isAlert: true },
  ];

  return (
    <div className="min-h-screen bg-background">

      {/* ── Header ── */}
      <header className="sticky top-0 z-40 border-b border-border/50 bg-background/80 backdrop-blur-sm">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-primary to-accent">
              <BarChart3 className="h-5 w-5 text-foreground" />
            </div>
            <span className="text-xl font-bold text-foreground">DealIQ</span>
            {isDemo && (
              <Badge className="ml-2 border-health-orange/30 bg-health-orange/20 text-health-orange text-xs">DEMO MODE</Badge>
            )}
          </div>
          <div className="flex items-center gap-3">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setSignalPanelOpen(true)}
              className="border-health-orange/40 text-health-orange hover:bg-health-orange/10 hover:border-health-orange/60 font-medium gap-1.5"
            >
              <Radar className="h-4 w-4" />
              Signal Radar
            </Button>
            <Link to="/forecast">
              <Button variant="outline" size="sm" className="border-primary/40 text-primary hover:bg-primary/10 hover:border-primary/60 font-medium gap-1.5">
                <TrendingUp className="h-4 w-4" />
                AI Forecast
              </Button>
            </Link>
            <AlertsBell
              onClick={() => setDigestOpen(true)}
              criticalCount={digestCriticalCount}
            />
            <div className="hidden text-right sm:block">
              <p className="text-sm font-medium text-foreground">{session?.display_name ?? "User"}</p>
              <p className="text-xs text-muted-foreground">{session?.email ?? ""}</p>
            </div>
            <Button variant="ghost" size="sm" onClick={handleLogout} className="text-muted-foreground hover:text-foreground">
              <LogOut className="mr-1 h-4 w-4" /> Logout
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 space-y-6">

        {/* ── Summary Cards ── */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {summaryCards.map((card) => (
            <Card key={card.label} className="border-border/50 bg-card/80">
              <CardContent className="flex items-center gap-4 p-5">
                <div className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-lg ${card.isAlert ? "bg-health-red/20" : "bg-primary/10"}`}>
                  <card.icon className={`h-5 w-5 ${card.isAlert ? "text-health-red" : "text-primary"}`} />
                </div>
                <div>
                  <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">{card.label}</p>
                  {loadingMetrics ? (
                    <Skeleton className="mt-1 h-7 w-16" />
                  ) : (
                    <p className={`text-2xl font-bold ${card.colorFn ? card.colorFn(card.value ?? 0) : card.isAlert ? "text-health-red" : "text-foreground"}`}>
                      {card.value != null ? card.format(card.value) : "—"}
                    </p>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>

        {/* ── Health breakdown badges ── */}
        {metrics && !loadingMetrics && (
          <div className="flex flex-wrap gap-2">
            <Badge variant="outline" className="border-health-green/30 bg-health-green/10 text-health-green cursor-pointer hover:bg-health-green/20"
              onClick={() => setFilterHealth(filterHealth === "healthy" ? "all" : "healthy")}>
              ✓ {metrics.healthy_count} Healthy
            </Badge>
            <Badge variant="outline" className="border-health-yellow/30 bg-health-yellow/10 text-health-yellow cursor-pointer hover:bg-health-yellow/20"
              onClick={() => setFilterHealth(filterHealth === "at_risk" ? "all" : "at_risk")}>
              ⚠ {metrics.at_risk_count} At Risk
            </Badge>
            <Badge variant="outline" className="border-health-orange/30 bg-health-orange/10 text-health-orange cursor-pointer hover:bg-health-orange/20"
              onClick={() => setFilterHealth(filterHealth === "critical" ? "all" : "critical")}>
              ✕ {metrics.critical_count} Critical
            </Badge>
            <Badge variant="outline" className="border-health-red/30 bg-health-red/10 text-health-red cursor-pointer hover:bg-health-red/20"
              onClick={() => setFilterHealth(filterHealth === "zombie" ? "all" : "zombie")}>
              💀 {metrics.zombie_count} Zombie
            </Badge>
            {filterHealth !== "all" && (
              <Badge variant="outline" className="border-border/50 text-muted-foreground cursor-pointer hover:bg-secondary/80"
                onClick={() => setFilterHealth("all")}>
                <X className="h-3 w-3 mr-1" /> Clear
              </Badge>
            )}
          </div>
        )}

        {/* ── Deal Pipeline Table ── */}
        <Card className="border-border/50 bg-card/80">
          <div className="p-5 pb-4 space-y-4">
            {/* Title row */}
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-lg font-semibold text-foreground">Deal Pipeline</h2>
                <p className="text-sm text-muted-foreground">
                  Sorted by health score — worst first · Active deals only
                  {!hasActiveFilters && totalDeals > 0 && ` · Showing ${startItem}–${endItem} of ${totalDeals}`}
                  {hasActiveFilters && ` · ${filteredDeals.length} match${filteredDeals.length !== 1 ? "es" : ""} your filters`}
                </p>
              </div>
              {hasActiveFilters && (
                <Button variant="ghost" size="sm" onClick={clearFilters}
                  className="text-muted-foreground hover:text-foreground text-xs gap-1.5">
                  <X className="h-3 w-3" /> Clear all filters
                </Button>
              )}
            </div>

            {/* ── Filter bar ── */}
            <div className="flex flex-wrap gap-2">
              {/* Deal name / company search */}
              <div className="relative flex-1 min-w-[200px]">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
                <Input
                  value={searchName}
                  onChange={e => setSearchName(e.target.value)}
                  placeholder="Search deal or company..."
                  className="pl-9 h-9 border-border/50 bg-secondary/50 text-sm focus-visible:ring-primary/50"
                />
                {searchName && (
                  <button onClick={() => setSearchName("")}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">
                    <X className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>

              {/* Owner filter */}
              <Select value={filterOwner} onValueChange={setFilterOwner}>
                <SelectTrigger className="h-9 w-[160px] border-border/50 bg-secondary/50 text-sm">
                  <SelectValue placeholder="All Owners" />
                </SelectTrigger>
                <SelectContent className="bg-card border-border/50">
                  <SelectItem value="all">All Owners</SelectItem>
                  {ownerOptions.map(owner => (
                    <SelectItem key={owner} value={owner}>{owner}</SelectItem>
                  ))}
                </SelectContent>
              </Select>

              {/* Stage filter */}
              <Select value={filterStage} onValueChange={setFilterStage}>
                <SelectTrigger className="h-9 w-[170px] border-border/50 bg-secondary/50 text-sm">
                  <SelectValue placeholder="All Stages" />
                </SelectTrigger>
                <SelectContent className="bg-card border-border/50">
                  <SelectItem value="all">All Stages</SelectItem>
                  {stageOptions.map(stage => (
                    <SelectItem key={stage} value={stage}>{stage}</SelectItem>
                  ))}
                </SelectContent>
              </Select>

              {/* Health filter */}
              <Select value={filterHealth} onValueChange={setFilterHealth}>
                <SelectTrigger className="h-9 w-[150px] border-border/50 bg-secondary/50 text-sm">
                  <SelectValue placeholder="All Health" />
                </SelectTrigger>
                <SelectContent className="bg-card border-border/50">
                  <SelectItem value="all">All Health</SelectItem>
                  <SelectItem value="healthy">✓ Healthy</SelectItem>
                  <SelectItem value="at_risk">⚠ At Risk</SelectItem>
                  <SelectItem value="critical">✕ Critical</SelectItem>
                  <SelectItem value="zombie">💀 Zombie</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <CardContent className="p-0">
            {loadingDeals ? (
              <div className="space-y-3 p-5">{[...Array(5)].map((_, i) => <Skeleton key={i} className="h-12 w-full" />)}</div>
            ) : filteredDeals.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-center">
                <Filter className="h-8 w-8 text-muted-foreground/40 mb-3" />
                <p className="text-sm font-medium text-muted-foreground">No deals match your filters</p>
                <p className="text-xs text-muted-foreground/60 mt-1">Try adjusting or clearing the filters above</p>
                <Button variant="ghost" size="sm" onClick={clearFilters} className="mt-3 text-xs text-primary">
                  Clear all filters
                </Button>
              </div>
            ) : (
              <>
                <Table>
                  <TableHeader>
                    <TableRow className="border-border/50 hover:bg-transparent">
                      <TableHead>Deal Name</TableHead>
                      <TableHead>Company</TableHead>
                      <TableHead>Stage</TableHead>
                      <TableHead>Owner</TableHead>
                      <TableHead className="text-right">Amount</TableHead>
                      <TableHead className="text-center">Health</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead className="text-right">Action</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {filteredDeals.map((deal) => (
                      <TableRow key={deal.id} className="border-border/30 hover:bg-secondary/50 cursor-pointer"
                        onClick={() => setSelectedDealId(deal.id)}>
                        <TableCell className="font-medium text-foreground">{deal.deal_name}</TableCell>
                        <TableCell className="text-muted-foreground">{deal.company}</TableCell>
                        <TableCell className="text-muted-foreground text-sm">{deal.stage}</TableCell>
                        <TableCell className="text-muted-foreground text-sm">{deal.owner ?? "—"}</TableCell>
                        <TableCell className="text-right text-foreground font-medium">{formatCurrency(deal.amount)}</TableCell>
                        <TableCell className="text-center">
                          <span className={`text-sm font-bold ${scoreColor(deal.health_score)}`}>{deal.health_score}</span>
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline" className={`text-xs capitalize ${healthColor(deal.health_label)}`}>
                            {deal.health_label.replace("_", " ")}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right">
                          <Button size="sm" variant="ghost" className="text-primary hover:text-primary hover:bg-primary/10"
                            onClick={(e) => { e.stopPropagation(); setSelectedDealId(deal.id); }}>
                            Analyse →
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>

                {/* ── Pagination — only shown when no active filters ── */}
                {!hasActiveFilters && totalPages > 1 && (
                  <div className="flex items-center justify-between border-t border-border/30 px-5 py-4">
                    <p className="text-xs text-muted-foreground">Page {currentPage} of {totalPages}</p>
                    <div className="flex items-center gap-1">
                      <Button variant="outline" size="sm" onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                        disabled={currentPage === 1} className="h-8 border-border/50 text-xs">Previous</Button>
                      {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                        const start = Math.max(1, Math.min(currentPage - 2, totalPages - 4));
                        return start + i;
                      }).map(page => (
                        <Button key={page} variant={page === currentPage ? "default" : "outline"} size="sm"
                          onClick={() => setCurrentPage(page)}
                          className={`h-8 w-8 p-0 text-xs ${page === currentPage ? "" : "border-border/50"}`}>
                          {page}
                        </Button>
                      ))}
                      <Button variant="outline" size="sm" onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                        disabled={currentPage === totalPages} className="h-8 border-border/50 text-xs">Next</Button>
                    </div>
                  </div>
                )}
              </>
            )}
          </CardContent>
        </Card>
      </main>

      <DealDetailPanel
        dealId={selectedDealId}
        dealName={selectedDeal?.deal_name ?? ""}
        repName={selectedDeal?.owner ?? session?.display_name}
        onClose={() => setSelectedDealId(null)}
      />
      <AlertsDigestPanel
        open={digestOpen}
        onClose={() => setDigestOpen(false)}
      />
      <BuyingSignalPanel
        open={signalPanelOpen}
        onClose={() => setSignalPanelOpen(false)}
      />
    </div>
  );
}
