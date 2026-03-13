import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  Target, TrendingUp, TrendingDown, AlertTriangle,
  BarChart3, Globe, Map, Zap, ChevronDown, ChevronRight,
} from "lucide-react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, Cell,
} from "recharts";

// ── Types ─────────────────────────────────────────────────────────────────────

interface RegionStat {
  region: string;
  target: number;
  achieved: number;
  gap: number;
  attainment_pct: number;
  status: "on_track" | "at_risk" | "critical";
  component_id: string | null;
  source: string;
}

interface GapDeal {
  id: string;
  name: string;
  stage: string;
  amount: number;
  health_score: number;
  health_label: string;
  recovery_potential: number;
  region: string;
  owner: string;
  account_name: string;
  closing_date: string;
}

interface RegionalSummary {
  quarter: string;
  fiscal_year: number;
  regions: RegionStat[];
  total_target: number;
  total_achieved: number;
  total_gap: number;
  total_attainment_pct: number;
  regions_at_risk: number;
  simulated: boolean;
}

interface RegionDealsResponse {
  region: string;
  deals: GapDeal[];
  simulated: boolean;
}

// ── Constants ─────────────────────────────────────────────────────────────────

const QUARTERS = ["Q1", "Q2", "Q3", "Q4"];
const CURRENT_YEAR = new Date().getFullYear();

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmt(n: number) {
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `$${(n / 1_000).toFixed(0)}K`;
  return `$${n.toFixed(0)}`;
}

function healthColor(label: string) {
  switch (label) {
    case "healthy":  return "bg-emerald-500/20 text-emerald-400 border-emerald-500/30";
    case "at_risk":  return "bg-amber-500/20 text-amber-400 border-amber-500/30";
    case "critical": return "bg-red-500/20 text-red-400 border-red-500/30";
    default:         return "bg-zinc-500/20 text-zinc-400 border-zinc-500/30";
  }
}

function statusColors(status: string) {
  switch (status) {
    case "on_track": return {
      border: "border-emerald-500/40", bg: "bg-emerald-500/10",
      text: "text-emerald-400", badge: "bg-emerald-500/20 text-emerald-400",
    };
    case "at_risk": return {
      border: "border-amber-500/40", bg: "bg-amber-500/10",
      text: "text-amber-400", badge: "bg-amber-500/20 text-amber-400",
    };
    case "critical": return {
      border: "border-red-500/40", bg: "bg-red-500/10",
      text: "text-red-400", badge: "bg-red-500/20 text-red-400",
    };
    default: return {
      border: "border-border", bg: "bg-card",
      text: "text-foreground", badge: "bg-muted text-muted-foreground",
    };
  }
}

function statusLabel(status: string) {
  return status === "on_track" ? "On Track" : status === "at_risk" ? "At Risk" : "Critical";
}

function AttainmentBar({ pct }: { pct: number }) {
  const clamped = Math.min(100, Math.max(0, pct));
  const color = pct >= 90 ? "bg-emerald-500" : pct >= 60 ? "bg-amber-500" : "bg-red-500";
  return (
    <div className="w-full h-1.5 bg-muted rounded-full overflow-hidden">
      <div className={cn("h-full rounded-full transition-all", color)} style={{ width: `${clamped}%` }} />
    </div>
  );
}

// ── Sub-components ────────────────────────────────────────────────────────────

function MetricCard({ icon, label, value, sub, color }: {
  icon: React.ReactNode; label: string; value: string; sub: string; color: string;
}) {
  return (
    <div className="rounded-lg border border-border bg-card px-4 py-3 space-y-1">
      <div className={cn("flex items-center gap-1.5 text-xs text-muted-foreground", color)}>
        {icon}<span>{label}</span>
      </div>
      <p className={cn("text-xl font-bold", color)}>{value}</p>
      <p className="text-[11px] text-muted-foreground">{sub}</p>
    </div>
  );
}

function GapDealsTable({ deals }: { deals: GapDeal[] }) {
  if (!deals.length) return (
    <p className="text-xs text-muted-foreground px-4 py-3">No gap deals found for this region.</p>
  );
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-border/50 text-muted-foreground">
            <th className="text-left px-4 py-2 font-medium">Deal</th>
            <th className="text-left px-4 py-2 font-medium">Stage</th>
            <th className="text-right px-4 py-2 font-medium">Amount</th>
            <th className="text-center px-4 py-2 font-medium">Health</th>
            <th className="text-right px-4 py-2 font-medium">Recovery</th>
          </tr>
        </thead>
        <tbody>
          {deals.map((d) => (
            <tr key={d.id} className="border-b border-border/30 hover:bg-muted/20 transition-colors">
              <td className="px-4 py-2.5">
                <div className="font-medium text-foreground truncate max-w-[180px]">{d.name}</div>
                {d.account_name && (
                  <div className="text-muted-foreground text-[10px]">{d.account_name}</div>
                )}
              </td>
              <td className="px-4 py-2.5">
                <span className="bg-muted text-muted-foreground px-2 py-0.5 rounded text-[10px] font-medium">
                  {d.stage}
                </span>
              </td>
              <td className="px-4 py-2.5 text-right font-medium text-foreground">{fmt(d.amount)}</td>
              <td className="px-4 py-2.5 text-center">
                <span className={cn("px-2 py-0.5 rounded text-[10px] font-semibold border", healthColor(d.health_label))}>
                  {d.health_score}
                </span>
              </td>
              <td className="px-4 py-2.5 text-right font-semibold text-violet-400">
                {fmt(d.recovery_potential)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RegionCard({ r, quarter, fy }: { r: RegionStat; quarter: string; fy: number }) {
  const [expanded, setExpanded] = useState(false);
  const [deals, setDeals] = useState<GapDeal[] | null>(null);
  const [loadingDeals, setLoadingDeals] = useState(false);
  const c = statusColors(r.status);

  const toggleExpand = async () => {
    if (!expanded && deals === null) {
      setLoadingDeals(true);
      try {
        const resp: RegionDealsResponse = await api.getRegionalSummaryByRegion(r.region, quarter, fy);
        setDeals(resp.deals || []);
      } catch {
        setDeals([]);
      } finally {
        setLoadingDeals(false);
      }
    }
    setExpanded((v) => !v);
  };

  return (
    <div className={cn("rounded-lg border overflow-hidden", c.border, c.bg)}>
      <button
        onClick={toggleExpand}
        className="w-full text-left px-4 py-3 hover:bg-black/5 dark:hover:bg-white/5 transition-colors"
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            {expanded
              ? <ChevronDown className={cn("w-3.5 h-3.5", c.text)} />
              : <ChevronRight className={cn("w-3.5 h-3.5", c.text)} />}
            <Globe className={cn("w-4 h-4", c.text)} />
            <span className="font-medium text-sm text-foreground">{r.region}</span>
          </div>
          <span className={cn("text-[10px] font-semibold px-2 py-0.5 rounded-full", c.badge)}>
            {statusLabel(r.status)}
          </span>
        </div>

        <div className="mt-2.5 space-y-1.5">
          <div className="flex justify-between text-xs">
            <span className="text-muted-foreground">
              {fmt(r.achieved)} achieved of {fmt(r.target)} target
            </span>
            <span className={cn("font-semibold", c.text)}>{r.attainment_pct}%</span>
          </div>
          <AttainmentBar pct={r.attainment_pct} />
          <div className="flex items-center gap-3 text-[10px] text-muted-foreground pt-0.5">
            <span>Gap: <span className={r.gap > 0 ? "text-red-400 font-medium" : "text-emerald-400 font-medium"}>
              {r.gap > 0 ? `-${fmt(r.gap)}` : `+${fmt(-r.gap)}`}
            </span></span>
            {r.source === "demo" && <span className="text-amber-400/70">demo data</span>}
          </div>
        </div>
      </button>

      {expanded && (
        <div className="border-t border-border/50">
          {loadingDeals ? (
            <div className="px-4 py-3 space-y-2">
              {[1, 2].map((i) => (
                <div key={i} className="h-8 bg-muted/50 rounded animate-pulse" />
              ))}
            </div>
          ) : (
            <GapDealsTable deals={deals || []} />
          )}
        </div>
      )}
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function RegionalAnalytics() {
  const [quarter, setQuarter] = useState<string>(() => {
    const m = new Date().getMonth();
    return `Q${Math.floor(m / 3) + 1}`;
  });
  const [summary, setSummary] = useState<RegionalSummary | null>(null);
  const [gapDeals, setGapDeals] = useState<GapDeal[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    Promise.all([
      api.getRegionalSummary(quarter, CURRENT_YEAR),
      api.getGapDeals(quarter, CURRENT_YEAR),
    ])
      .then(([s, g]) => {
        setSummary(s);
        setGapDeals(g.deals || []);
      })
      .catch((e: Error) => setError(e?.message || "Failed to load analytics"))
      .finally(() => setLoading(false));
  }, [quarter]);

  const chartData = summary?.regions.map((r) => ({
    name: r.region,
    Target: Math.round(r.target / 1000),
    Achieved: Math.round(r.achieved / 1000),
    status: r.status,
  })) ?? [];

  return (
    <div className="px-6 py-6 max-w-[1400px] mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-foreground flex items-center gap-2">
            <Map className="w-5 h-5 text-primary" />
            Regional Target Analytics
          </h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Achieved vs target by region — {quarter} {CURRENT_YEAR}
          </p>
        </div>
        {summary?.simulated && (
          <span className="text-[10px] font-medium bg-amber-500/15 text-amber-400 border border-amber-500/30 px-2 py-0.5 rounded-full">
            Demo Data
          </span>
        )}
      </div>

      {/* Quarter Selector */}
      <div className="flex gap-1.5">
        {QUARTERS.map((q) => (
          <button
            key={q}
            onClick={() => setQuarter(q)}
            className={cn(
              "px-4 py-1.5 rounded-md text-xs font-medium transition-colors border",
              quarter === q
                ? "bg-primary text-primary-foreground border-primary"
                : "bg-card text-muted-foreground border-border hover:bg-muted"
            )}
          >
            {q}
          </button>
        ))}
      </div>

      {loading && (
        <div className="grid grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-24 rounded-lg bg-muted animate-pulse" />
          ))}
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
          {error}
        </div>
      )}

      {summary && !loading && (
        <>
          {/* Summary Metric Cards */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <MetricCard
              icon={<BarChart3 className="w-4 h-4" />}
              label="Total Achieved"
              value={fmt(summary.total_achieved)}
              sub={`of ${fmt(summary.total_target)} target`}
              color="text-blue-400"
            />
            <MetricCard
              icon={<Target className="w-4 h-4" />}
              label="Attainment"
              value={`${summary.total_attainment_pct}%`}
              sub={`${quarter} ${CURRENT_YEAR} overall`}
              color="text-violet-400"
            />
            <MetricCard
              icon={summary.total_gap > 0 ? <TrendingDown className="w-4 h-4" /> : <TrendingUp className="w-4 h-4" />}
              label="Gap to Target"
              value={summary.total_gap > 0 ? `-${fmt(summary.total_gap)}` : `+${fmt(-summary.total_gap)}`}
              sub="across all regions"
              color={summary.total_gap > 0 ? "text-red-400" : "text-emerald-400"}
            />
            <MetricCard
              icon={<AlertTriangle className="w-4 h-4" />}
              label="Regions at Risk"
              value={String(summary.regions_at_risk)}
              sub="below 90% attainment"
              color={summary.regions_at_risk > 0 ? "text-amber-400" : "text-emerald-400"}
            />
          </div>

          {/* Bar Chart */}
          <div className="rounded-lg border border-border bg-card p-5">
            <h2 className="text-sm font-medium text-foreground mb-4">
              Achieved vs Target by Region ($K)
            </h2>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={chartData} barCategoryGap="35%" barGap={4}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
                <XAxis
                  dataKey="name"
                  tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
                  axisLine={false} tickLine={false}
                />
                <YAxis
                  tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
                  axisLine={false} tickLine={false}
                />
                <Tooltip
                  contentStyle={{
                    background: "hsl(var(--card))",
                    border: "1px solid hsl(var(--border))",
                    borderRadius: "8px",
                    fontSize: 12,
                    color: "hsl(var(--foreground))",
                  }}
                  formatter={(v: number) => [`$${v}K`, ""]}
                />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Bar dataKey="Target" fill="hsl(var(--muted-foreground))" radius={[3, 3, 0, 0]} opacity={0.45} />
                <Bar dataKey="Achieved" radius={[3, 3, 0, 0]}>
                  {chartData.map((entry, i) => (
                    <Cell
                      key={i}
                      fill={
                        entry.status === "on_track" ? "#10b981"
                          : entry.status === "at_risk" ? "#f59e0b"
                          : "#ef4444"
                      }
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Region Cards — expandable */}
          <div>
            <h2 className="text-sm font-semibold text-foreground mb-3">
              Region Breakdown
              <span className="text-xs font-normal text-muted-foreground ml-2">
                Click a region to see gap-closing deals
              </span>
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {summary.regions.map((r) => (
                <RegionCard key={r.region} r={r} quarter={quarter} fy={CURRENT_YEAR} />
              ))}
            </div>
          </div>

          {/* Global Gap-Closing Deals Table */}
          {gapDeals.length > 0 && (
            <div className="rounded-lg border border-border bg-card">
              <div className="flex items-center gap-2 px-4 py-3 border-b border-border">
                <Zap className="w-4 h-4 text-amber-400" />
                <h2 className="text-sm font-semibold text-foreground">
                  Priority Deals to Close the Gap
                </h2>
                <span className="text-xs text-muted-foreground ml-1">
                  ({gapDeals.length} deals in underperforming regions)
                </span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-border text-muted-foreground">
                      <th className="text-left px-4 py-2 font-medium">Deal</th>
                      <th className="text-left px-4 py-2 font-medium">Region</th>
                      <th className="text-left px-4 py-2 font-medium">Stage</th>
                      <th className="text-right px-4 py-2 font-medium">Amount</th>
                      <th className="text-center px-4 py-2 font-medium">Health</th>
                      <th className="text-right px-4 py-2 font-medium">Recovery</th>
                    </tr>
                  </thead>
                  <tbody>
                    {gapDeals.map((deal) => (
                      <tr key={deal.id} className="border-b border-border/50 hover:bg-muted/30 transition-colors">
                        <td className="px-4 py-2.5">
                          <div className="font-medium text-foreground truncate max-w-[200px]">{deal.name}</div>
                          {deal.account_name && (
                            <div className="text-muted-foreground text-[10px]">{deal.account_name}</div>
                          )}
                        </td>
                        <td className="px-4 py-2.5 text-muted-foreground">{deal.region}</td>
                        <td className="px-4 py-2.5">
                          <span className="bg-muted text-muted-foreground px-2 py-0.5 rounded text-[10px] font-medium">
                            {deal.stage}
                          </span>
                        </td>
                        <td className="px-4 py-2.5 text-right font-medium text-foreground">{fmt(deal.amount)}</td>
                        <td className="px-4 py-2.5 text-center">
                          <span className={cn("px-2 py-0.5 rounded text-[10px] font-semibold border", healthColor(deal.health_label))}>
                            {deal.health_score}
                          </span>
                        </td>
                        <td className="px-4 py-2.5 text-right font-semibold text-violet-400">
                          {fmt(deal.recovery_potential)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
