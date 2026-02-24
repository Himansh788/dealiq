import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import {
  BarChart3, TrendingUp, TrendingDown, AlertTriangle,
  ArrowLeft, RefreshCw, Target, Skull, LifeBuoy,
  DollarSign, Calendar, X, Sparkles, Brain,
  ChevronDown, ChevronUp, Zap, ShieldAlert, Clock
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Progress } from "@/components/ui/progress";
import { useSession } from "@/contexts/SessionContext";
import { useToast } from "@/hooks/use-toast";
import { api } from "@/lib/api";

// ── Types ─────────────────────────────────────────────────────────────────────

interface RepDeal { id: string; name: string; amount: number; stage: string; health_score: number; closing_date: string | null; }

interface RepForecast {
  name: string; deal_count: number; total_pipeline: number;
  crm_forecast: number; dealiq_forecast: number; avg_health_score: number;
  healthy_count: number; at_risk_count: number; critical_count: number; zombie_count: number;
  overconfidence_gap: number; top_deal: string | null;
  deals_by_health: Record<string, RepDeal[]>;
}

interface MonthlyProjection { month: string; month_key: string; deals_closing: number; crm_value: number; dealiq_value: number; deals: string[]; }

interface OverforecastedDeal { id: string; name: string; account_name: string; owner: string; amount: number; stage: string; crm_expected: number; dealiq_expected: number; gap: number; health_label: string; health_score: number; risk_flag: string | null; closing_date: string | null; }

interface RescueDeal { id: string; name: string; account_name: string; owner: string; amount: number; stage: string; health_label: string; health_score: number; days_to_close: number; closing_date: string | null; rescue_upside: number; current_dealiq_value: number; }

interface DeadDeal { id: string; name: string; account_name: string; owner: string; amount: number; stage: string; crm_expected: number; is_overdue: boolean; days_to_close: number | null; }

// AI types
interface AINarrative { generated: boolean; headline: string; status: string; paragraphs: string[]; key_risks: string[]; biggest_opportunity: string; }
interface AIRepCoaching { generated: boolean; summary: string; pattern_identified: string; strength: string; coaching_action: string; priority_deal: string; }
interface AIRescuePriority { rank: number; deal_name: string; owner: string; amount: number; action: string; why_this_one: string; urgency: string; }
interface AIRescuePriorities { generated: boolean; strategy: string; total_rescue_potential: number; priorities: AIRescuePriority[]; }
interface AIRepPattern { generated: boolean; pattern: string; insight: string; action: string; }

interface ForecastAI {
  narrative: AINarrative | null;
  rep_coaching: Record<string, AIRepCoaching>;
  rescue_priorities: AIRescuePriorities | null;
}

interface ForecastData {
  total_pipeline: number; crm_forecast: number; dealiq_realistic: number;
  dealiq_optimistic: number; dealiq_conservative: number; forecast_gap: number; gap_percentage: number;
  this_month_crm: number; this_month_dealiq: number; this_month_gap: number;
  deals_closing_this_month: number; at_risk_this_month: number;
  by_rep: RepForecast[]; by_month: MonthlyProjection[];
  overforecasted_deals: OverforecastedDeal[]; rescue_opportunities: RescueDeal[]; already_dead: DeadDeal[];
  total_deals_analysed: number; simulated: boolean; generated_at: string;
  ai: ForecastAI;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtUSD(val: number): string {
  if (val >= 1_000_000) return `$${(val / 1_000_000).toFixed(1)}M`;
  if (val >= 1_000) return `$${Math.round(val / 1_000)}K`;
  return `$${Math.round(val)}`;
}
function scoreColor(score: number) { return score >= 75 ? "text-health-green" : score >= 50 ? "text-health-yellow" : "text-health-red"; }
function healthBadge(label: string) {
  switch (label) {
    case "healthy": return "bg-health-green/20 text-health-green border-health-green/30";
    case "at_risk": return "bg-health-yellow/20 text-health-yellow border-health-yellow/30";
    case "critical": return "bg-health-orange/20 text-health-orange border-health-orange/30";
    case "zombie": return "bg-health-red/20 text-health-red border-health-red/30";
    default: return "bg-muted text-muted-foreground";
  }
}
const urgencyColor: Record<string, string> = {
  today: "text-health-red border-health-red/30 bg-health-red/10",
  this_week: "text-health-orange border-health-orange/30 bg-health-orange/10",
  before_month_end: "text-health-yellow border-health-yellow/30 bg-health-yellow/10",
};

// ── Sub-components ────────────────────────────────────────────────────────────

function AIBadge() {
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-primary/30 bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
      <Sparkles className="h-3 w-3" /> AI
    </span>
  );
}

function GapIndicator({ crm, dealiq, label }: { crm: number; dealiq: number; label: string }) {
  const gap = crm - dealiq;
  const gapPct = crm > 0 ? ((gap / crm) * 100) : 0;
  const isOver = gap > 0;
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>{label}</span>
        <span className={isOver ? "text-health-red font-medium" : "text-health-green font-medium"}>
          {isOver ? "▼" : "▲"} {Math.abs(gapPct).toFixed(0)}% {isOver ? "overforecast" : "underforecast"}
        </span>
      </div>
      <div className="relative h-3 rounded-full bg-secondary overflow-hidden">
        <div className="absolute left-0 top-0 h-full rounded-full bg-primary transition-all duration-700"
          style={{ width: `${Math.min((dealiq / Math.max(crm, dealiq)) * 100, 100)}%` }} />
      </div>
      <div className="flex justify-between text-xs">
        <span className="text-primary font-medium">DealIQ: {fmtUSD(dealiq)}</span>
        <span className="text-muted-foreground">CRM: {fmtUSD(crm)}</span>
      </div>
    </div>
  );
}

// Inline deal drawer shown when health badge is clicked
function RepDealDrawer({ repName, deals, label, onClose, apiUrl }: {
  repName: string; deals: RepDeal[]; label: string; onClose: () => void; apiUrl: string;
}) {
  const [pattern, setPattern] = useState<AIRepPattern | null>(null);
  const [loadingPattern, setLoadingPattern] = useState(true);

  const labelCfg: Record<string, { cls: string; title: string }> = {
    healthy:  { cls: "text-health-green border-health-green/30 bg-health-green/10",  title: "✓ Healthy Deals" },
    at_risk:  { cls: "text-health-yellow border-health-yellow/30 bg-health-yellow/10", title: "⚠ At-Risk Deals" },
    critical: { cls: "text-health-orange border-health-orange/30 bg-health-orange/10", title: "✕ Critical Deals" },
    zombie:   { cls: "text-health-red border-health-red/30 bg-health-red/10", title: "💀 Zombie Deals" },
  };
  const cfg = labelCfg[label] ?? { cls: "text-muted-foreground", title: "Deals" };
  const [colorCls, borderCls, bgCls] = cfg.cls.split(" ");

  // Lazy-load AI pattern when drawer opens
  useEffect(() => {
    setLoadingPattern(true);
    const raw = localStorage.getItem("dealiq_session");
    const headers: any = { "Content-Type": "application/json" };
    if (raw) headers["Authorization"] = `Bearer ${raw}`;

    fetch(`${apiUrl}/forecast/rep-pattern`, {
      method: "POST",
      headers,
      body: JSON.stringify({ rep_name: repName, health_label: label, deals }),
    })
      .then(r => r.json())
      .then(setPattern)
      .catch(() => setPattern(null))
      .finally(() => setLoadingPattern(false));
  }, [repName, label]);

  return (
    <div className={`mt-3 rounded-lg border ${borderCls} overflow-hidden`}>
      <div className={`flex items-center justify-between px-4 py-2.5 ${bgCls} border-b ${borderCls}`}>
        <div className="flex items-center gap-2">
          <span className={`text-xs font-semibold ${colorCls}`}>{cfg.title} — {deals.length} deals</span>
          <AIBadge />
        </div>
        <button onClick={onClose} className="text-muted-foreground hover:text-foreground"><X className="h-3.5 w-3.5" /></button>
      </div>

      {/* AI Pattern insight */}
      {loadingPattern ? (
        <div className="px-4 py-3 space-y-1.5">
          <Skeleton className="h-3 w-3/4" />
          <Skeleton className="h-3 w-1/2" />
        </div>
      ) : pattern?.generated && (
        <div className={`px-4 py-3 ${bgCls} border-b ${borderCls} space-y-1`}>
          <p className="text-xs text-muted-foreground">{pattern.pattern}</p>
          {pattern.action && (
            <p className={`text-xs font-medium ${colorCls} flex items-center gap-1`}>
              <Zap className="h-3 w-3" /> {pattern.action}
            </p>
          )}
        </div>
      )}

      {/* Deal list */}
      <div className="divide-y divide-border/20 max-h-60 overflow-y-auto">
        {deals.map(deal => (
          <div key={deal.id} className="flex items-center justify-between px-4 py-2.5 hover:bg-secondary/30 transition-colors">
            <div className="flex-1 min-w-0 mr-4">
              <p className="text-sm font-medium text-foreground truncate">{deal.name}</p>
              <p className="text-xs text-muted-foreground">{deal.stage}</p>
            </div>
            <div className="text-right shrink-0">
              <p className="text-sm font-bold text-foreground">{fmtUSD(deal.amount)}</p>
              <p className={`text-xs font-medium ${scoreColor(deal.health_score)}`}>Health: {deal.health_score}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export default function ForecastPage() {
  const { session } = useSession();
  const navigate = useNavigate();
  const { toast } = useToast();

  const [data, setData] = useState<ForecastData | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<"overview" | "reps" | "pipeline" | "alerts">("overview");
  const [expandedRep, setExpandedRep] = useState<string | null>(null);
  const [expandedLabel, setExpandedLabel] = useState<string | null>(null);
  const [expandedCoaching, setExpandedCoaching] = useState<string | null>(null);
  const [narrativeExpanded, setNarrativeExpanded] = useState(true);

  useEffect(() => {
    if (!session) { navigate("/", { replace: true }); return; }
    loadForecast();
  }, [session]);

  const loadForecast = async () => {
    setLoading(true);
    try {
      const result = await api.getForecast();
      setData(result);
    } catch (err: any) {
      toast({ title: "Error loading forecast", description: err.message, variant: "destructive" });
    } finally {
      setLoading(false);
    }
  };

  const toggleDrillDown = (repName: string, label: string) => {
    if (expandedRep === repName && expandedLabel === label) {
      setExpandedRep(null); setExpandedLabel(null);
    } else {
      setExpandedRep(repName); setExpandedLabel(label);
    }
  };

  const tabs = [
    { id: "overview", label: "Overview" },
    { id: "reps",     label: "By Rep" },
    { id: "pipeline", label: "Monthly" },
    { id: "alerts",   label: `Alerts${data ? ` (${data.rescue_opportunities.length + data.already_dead.length})` : ""}` },
  ] as const;

  const ai = data?.ai;

  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-40 border-b border-border/50 bg-background/80 backdrop-blur-sm">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6">
          <div className="flex items-center gap-3">
            <Link to="/dashboard">
              <Button variant="ghost" size="sm" className="text-muted-foreground">
                <ArrowLeft className="mr-1 h-4 w-4" /> Dashboard
              </Button>
            </Link>
            <div className="h-4 w-px bg-border/50" />
            <div className="flex items-center gap-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-primary to-accent">
                <TrendingUp className="h-4 w-4 text-foreground" />
              </div>
              <span className="text-lg font-bold text-foreground">AI Forecast</span>
              {data?.simulated && <Badge className="border-health-orange/30 bg-health-orange/20 text-health-orange text-xs">DEMO</Badge>}
            </div>
          </div>
          <Button variant="ghost" size="sm" onClick={loadForecast} disabled={loading} className="text-muted-foreground">
            <RefreshCw className={`mr-1 h-4 w-4 ${loading ? "animate-spin" : ""}`} /> Refresh
          </Button>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 space-y-6">
        {loading ? (
          <div className="space-y-6">
            <div className="rounded-xl border border-primary/20 bg-primary/5 p-5 space-y-3">
              <div className="flex items-center gap-2"><Sparkles className="h-4 w-4 text-primary animate-pulse" /><span className="text-sm text-primary font-medium">AI is reading your pipeline...</span></div>
              <Skeleton className="h-4 w-3/4" /><Skeleton className="h-4 w-full" /><Skeleton className="h-4 w-5/6" />
            </div>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">{[...Array(3)].map((_, i) => <Skeleton key={i} className="h-36 w-full" />)}</div>
            <Skeleton className="h-64 w-full" />
          </div>
        ) : data ? (
          <div className="space-y-6">

            {/* ── AI PIPELINE NARRATIVE — Prime real estate ── */}
            {ai?.narrative?.generated && (
              <div className={`rounded-xl border p-5 space-y-4 transition-all ${
                ai.narrative.status === "critical" ? "border-health-red/30 bg-health-red/5" :
                ai.narrative.status === "at_risk"  ? "border-health-orange/30 bg-health-orange/5" :
                "border-health-green/30 bg-health-green/5"
              }`}>
                {/* Header */}
                <div className="flex items-start justify-between gap-4">
                  <div className="flex items-start gap-3 flex-1">
                    <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-primary/20">
                      <Brain className="h-4 w-4 text-primary" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">AI Pipeline Intelligence</span>
                        <AIBadge />
                        <Badge variant="outline" className={`text-xs ${
                          ai.narrative.status === "critical" ? "border-health-red/30 text-health-red" :
                          ai.narrative.status === "at_risk"  ? "border-health-orange/30 text-health-orange" :
                          "border-health-green/30 text-health-green"
                        }`}>
                          {ai.narrative.status.replace("_", " ").toUpperCase()}
                        </Badge>
                      </div>
                      <p className="text-base font-semibold text-foreground leading-snug">{ai.narrative.headline}</p>
                    </div>
                  </div>
                  <button onClick={() => setNarrativeExpanded(v => !v)} className="text-muted-foreground hover:text-foreground shrink-0 mt-1">
                    {narrativeExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                  </button>
                </div>

                {narrativeExpanded && (
                  <>
                    {/* Narrative paragraphs */}
                    <div className="space-y-3 pl-10">
                      {ai.narrative.paragraphs.map((p, i) => (
                        <p key={i} className="text-sm text-foreground/90 leading-relaxed">{p}</p>
                      ))}
                    </div>

                    {/* Key risks */}
                    {ai.narrative.key_risks?.length > 0 && (
                      <div className="pl-10 space-y-2">
                        <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Key Risks</p>
                        <div className="space-y-1.5">
                          {ai.narrative.key_risks.map((risk, i) => (
                            <div key={i} className="flex items-start gap-2">
                              <ShieldAlert className="h-3.5 w-3.5 text-health-orange mt-0.5 shrink-0" />
                              <p className="text-sm text-foreground/80">{risk}</p>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Biggest opportunity */}
                    {ai.narrative.biggest_opportunity && (
                      <div className="pl-10 rounded-lg border border-primary/20 bg-primary/5 p-3">
                        <div className="flex items-start gap-2">
                          <Zap className="h-4 w-4 text-primary mt-0.5 shrink-0" />
                          <div>
                            <p className="text-xs font-semibold text-primary uppercase tracking-wider mb-0.5">Highest-Leverage Action This Week</p>
                            <p className="text-sm text-foreground">{ai.narrative.biggest_opportunity}</p>
                          </div>
                        </div>
                      </div>
                    )}
                  </>
                )}
              </div>
            )}

            {/* ── THE NUMBERS HEADLINE ── */}
            <div className="rounded-xl border border-border/50 bg-card/80 p-6">
              <p className="text-xs font-medium text-muted-foreground mb-4 uppercase tracking-wider">
                {data.total_deals_analysed} deals analysed
              </p>
              <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
                <div className="space-y-1">
                  <div className="flex items-center gap-2"><div className="h-3 w-3 rounded-full bg-muted-foreground/40" /><p className="text-xs text-muted-foreground uppercase tracking-wider">CRM Says</p></div>
                  <p className="text-4xl font-bold text-muted-foreground">{fmtUSD(data.crm_forecast)}</p>
                  <p className="text-xs text-muted-foreground">Based on rep-entered probability</p>
                </div>
                <div className="space-y-1 lg:border-x lg:border-border/30 lg:px-6">
                  <div className="flex items-center gap-2"><div className="h-3 w-3 rounded-full bg-primary" /><p className="text-xs text-primary uppercase tracking-wider font-semibold">DealIQ Realistic</p></div>
                  <p className="text-4xl font-bold text-foreground">{fmtUSD(data.dealiq_realistic)}</p>
                  <p className="text-xs text-muted-foreground">Based on actual deal health signals</p>
                </div>
                <div className="space-y-1">
                  <div className="flex items-center gap-2"><div className={`h-3 w-3 rounded-full ${data.forecast_gap > 0 ? "bg-health-red" : "bg-health-green"}`} /><p className="text-xs text-muted-foreground uppercase tracking-wider">Forecast Gap</p></div>
                  <p className={`text-4xl font-bold ${data.forecast_gap > 0 ? "text-health-red" : "text-health-green"}`}>
                    {data.forecast_gap > 0 ? "-" : "+"}{fmtUSD(Math.abs(data.forecast_gap))}
                  </p>
                  <p className="text-xs text-muted-foreground">CRM is {Math.abs(data.gap_percentage).toFixed(0)}% {data.forecast_gap > 0 ? "overestimating" : "underestimating"}</p>
                </div>
              </div>

              <div className="mt-6 space-y-3">
                {[
                  { label: "DealIQ Realistic", val: data.dealiq_realistic, max: data.crm_forecast, cls: "bg-primary" },
                  { label: "CRM Forecast",     val: data.crm_forecast,     max: data.crm_forecast, cls: "bg-muted-foreground/40" },
                  { label: "DealIQ Optimistic (if at-risk rescued)", val: data.dealiq_optimistic, max: Math.max(data.crm_forecast, data.dealiq_optimistic), cls: "bg-health-green/60" },
                ].map(row => (
                  <div key={row.label} className="space-y-1">
                    <div className="flex justify-between text-xs text-muted-foreground">
                      <span>{row.label}</span>
                      <span className={row.cls === "bg-primary" ? "text-primary font-medium" : row.cls.includes("green") ? "text-health-green font-medium" : ""}>{fmtUSD(row.val)}</span>
                    </div>
                    <div className="h-4 w-full rounded-full bg-secondary overflow-hidden">
                      <div className={`h-full rounded-full ${row.cls} transition-all duration-700`}
                        style={{ width: `${Math.min((row.val / Math.max(row.max, 1)) * 100, 100)}%` }} />
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* ── This Month Cards ── */}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {[
                { icon: Calendar, label: "This Month CRM", value: fmtUSD(data.this_month_crm), sub: `${data.deals_closing_this_month} deals scheduled`, accent: false },
                { icon: Target, label: "This Month DealIQ", value: fmtUSD(data.this_month_dealiq), sub: "Reality-adjusted close", accent: true },
                { icon: data.this_month_gap > 0 ? TrendingDown : TrendingUp, label: "Gap This Month",
                  value: `${data.this_month_gap > 0 ? "-" : "+"}${fmtUSD(Math.abs(data.this_month_gap))}`,
                  sub: data.this_month_gap > 0 ? "Likely to miss by this amount" : "May exceed forecast",
                  red: data.this_month_gap > 0, green: data.this_month_gap <= 0 },
                { icon: AlertTriangle, label: "At-Risk This Month", value: String(data.at_risk_this_month),
                  sub: "Critical/zombie closing this month", orange: data.at_risk_this_month > 0 },
              ].map((card, i) => (
                <Card key={i} className={`border-border/50 ${card.accent ? "border-primary/30 bg-primary/5" : "bg-card/80"}`}>
                  <CardContent className="p-5">
                    <div className="flex items-center gap-2 mb-2">
                      <card.icon className={`h-4 w-4 ${card.accent ? "text-primary" : card.red ? "text-health-red" : card.green ? "text-health-green" : card.orange ? "text-health-orange" : "text-muted-foreground"}`} />
                      <p className={`text-xs font-medium uppercase tracking-wider ${card.accent ? "text-primary" : "text-muted-foreground"}`}>{card.label}</p>
                    </div>
                    <p className={`text-2xl font-bold ${card.accent ? "text-foreground" : card.red ? "text-health-red" : card.green ? "text-health-green" : card.orange ? "text-health-orange" : "text-muted-foreground"}`}>{card.value}</p>
                    <p className="text-xs text-muted-foreground mt-1">{card.sub}</p>
                  </CardContent>
                </Card>
              ))}
            </div>

            {/* ── Tabs ── */}
            <div className="flex gap-1 rounded-lg border border-border/50 bg-secondary/30 p-1 w-fit">
              {tabs.map(tab => (
                <button key={tab.id} onClick={() => setActiveTab(tab.id)}
                  className={`rounded-md px-4 py-1.5 text-sm font-medium transition-all ${activeTab === tab.id ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"}`}>
                  {tab.label}
                </button>
              ))}
            </div>

            {/* ── Overview Tab ── */}
            {activeTab === "overview" && (
              <Card className="border-border/50 bg-card/80">
                <CardContent className="p-5 space-y-4">
                  <h3 className="text-sm font-semibold text-foreground">Forecast Scenarios</h3>
                  {[
                    { label: "Optimistic — if at-risk rescued", val: data.dealiq_optimistic, cls: "text-health-green", barCls: "[&>div]:bg-health-green" },
                    { label: "Realistic — current health",       val: data.dealiq_realistic,  cls: "text-primary",      barCls: "[&>div]:bg-primary" },
                    { label: "Conservative — only healthy",      val: data.dealiq_conservative, cls: "text-muted-foreground", barCls: "" },
                  ].map(row => (
                    <div key={row.label} className="space-y-1">
                      <div className="flex justify-between text-sm">
                        <span className={`font-medium ${row.cls}`}>{row.label}</span>
                        <span className={`font-bold ${row.cls}`}>{fmtUSD(row.val)}</span>
                      </div>
                      <Progress value={(row.val / data.total_pipeline) * 100} className={`h-2 ${row.barCls}`} />
                    </div>
                  ))}
                  <div className="space-y-1 border-t border-border/30 pt-3">
                    <div className="flex justify-between text-sm">
                      <span className="text-muted-foreground/60">Total Pipeline</span>
                      <span className="text-muted-foreground/60">{fmtUSD(data.total_pipeline)}</span>
                    </div>
                    <Progress value={100} className="h-2 [&>div]:bg-muted-foreground/20" />
                  </div>
                </CardContent>
              </Card>
            )}

            {/* ── By Rep Tab ── */}
            {activeTab === "reps" && (
              <div className="space-y-4">
                {data.by_rep.map(rep => {
                  const coaching = ai?.rep_coaching?.[rep.name];
                  const isCoachingOpen = expandedCoaching === rep.name;

                  return (
                    <Card key={rep.name} className="border-border/50 bg-card/80 overflow-hidden">
                      <CardContent className="p-5 space-y-3">
                        {/* Rep header */}
                        <div className="flex items-start justify-between">
                          <div>
                            <p className="font-semibold text-foreground">{rep.name}</p>
                            <p className="text-xs text-muted-foreground">{rep.deal_count} deals · Pipeline: {fmtUSD(rep.total_pipeline)}</p>
                          </div>
                          <div className="flex items-center gap-2">
                            {rep.overconfidence_gap > 0
                              ? <Badge variant="outline" className="bg-health-red/10 text-health-red border-health-red/30 text-xs">Over by {fmtUSD(rep.overconfidence_gap)}</Badge>
                              : <Badge variant="outline" className="bg-health-green/10 text-health-green border-health-green/30 text-xs">On track</Badge>
                            }
                          </div>
                        </div>

                        <GapIndicator crm={rep.crm_forecast} dealiq={rep.dealiq_forecast} label="CRM vs DealIQ" />

                        {/* Clickable health badges */}
                        <div className="flex items-center gap-2 flex-wrap">
                          {[
                            { label: "healthy",  count: rep.healthy_count,  icon: "✓", cls: "text-health-green border-health-green/30 hover:bg-health-green/20" },
                            { label: "at_risk",  count: rep.at_risk_count,  icon: "⚠", cls: "text-health-yellow border-health-yellow/30 hover:bg-health-yellow/20" },
                            { label: "critical", count: rep.critical_count, icon: "✕", cls: "text-health-orange border-health-orange/30 hover:bg-health-orange/20" },
                            { label: "zombie",   count: rep.zombie_count,   icon: "💀", cls: "text-health-red border-health-red/30 hover:bg-health-red/20" },
                          ].map(b => b.count > 0 && (
                            <button key={b.label}
                              onClick={() => toggleDrillDown(rep.name, b.label)}
                              className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium transition-all
                                ${b.cls} ${expandedRep === rep.name && expandedLabel === b.label ? "ring-1 ring-current bg-current/10" : "bg-transparent"}`}>
                              {b.icon} {b.count} {b.label.replace("_", "-")}
                            </button>
                          ))}
                          <span className="ml-auto text-xs text-muted-foreground">
                            Avg: <span className={`font-bold ${scoreColor(rep.avg_health_score)}`}>{Math.round(rep.avg_health_score)}</span>
                          </span>
                        </div>

                        {/* Drill-down drawer */}
                        {expandedRep === rep.name && expandedLabel && rep.deals_by_health?.[expandedLabel] && (
                          <RepDealDrawer
                            repName={rep.name}
                            deals={rep.deals_by_health[expandedLabel]}
                            label={expandedLabel}
                            apiUrl={API_URL}
                            onClose={() => { setExpandedRep(null); setExpandedLabel(null); }}
                          />
                        )}

                        {/* AI Coaching Card */}
                        {coaching?.generated && (
                          <div className="rounded-lg border border-primary/20 bg-primary/5 overflow-hidden">
                            <button
                              onClick={() => setExpandedCoaching(isCoachingOpen ? null : rep.name)}
                              className="w-full flex items-center justify-between px-4 py-2.5 hover:bg-primary/10 transition-colors">
                              <div className="flex items-center gap-2">
                                <Brain className="h-3.5 w-3.5 text-primary" />
                                <span className="text-xs font-semibold text-primary">AI Coaching Insight</span>
                                <AIBadge />
                              </div>
                              {isCoachingOpen ? <ChevronUp className="h-3.5 w-3.5 text-primary" /> : <ChevronDown className="h-3.5 w-3.5 text-primary" />}
                            </button>

                            {isCoachingOpen && (
                              <div className="px-4 pb-4 space-y-3 border-t border-primary/20">
                                <p className="text-sm text-foreground/90 italic mt-3">"{coaching.summary}"</p>
                                <div className="space-y-2">
                                  {coaching.pattern_identified && (
                                    <div className="flex items-start gap-2">
                                      <ShieldAlert className="h-3.5 w-3.5 text-health-orange mt-0.5 shrink-0" />
                                      <p className="text-xs text-foreground/80">{coaching.pattern_identified}</p>
                                    </div>
                                  )}
                                  {coaching.strength && (
                                    <div className="flex items-start gap-2">
                                      <TrendingUp className="h-3.5 w-3.5 text-health-green mt-0.5 shrink-0" />
                                      <p className="text-xs text-foreground/80">{coaching.strength}</p>
                                    </div>
                                  )}
                                </div>
                                <div className="rounded-md border border-primary/20 bg-background/50 px-3 py-2">
                                  <p className="text-xs font-semibold text-primary mb-1">This Week's Action</p>
                                  <p className="text-xs text-foreground">{coaching.coaching_action}</p>
                                </div>
                                {coaching.priority_deal && (
                                  <p className="text-xs text-muted-foreground">
                                    <span className="font-medium text-foreground">Priority deal: </span>{coaching.priority_deal}
                                  </p>
                                )}
                              </div>
                            )}
                          </div>
                        )}

                        {rep.top_deal && (
                          <p className="text-xs text-muted-foreground border-t border-border/20 pt-2">
                            Best deal: <span className="text-foreground">{rep.top_deal}</span>
                          </p>
                        )}
                      </CardContent>
                    </Card>
                  );
                })}
              </div>
            )}

            {/* ── Monthly Tab ── */}
            {activeTab === "pipeline" && (
              <div className="space-y-3">
                {data.by_month.length === 0 ? (
                  <Card className="border-border/50">
                    <CardContent className="p-8 text-center text-muted-foreground text-sm">
                      No closing dates set on deals — add closing dates in Zoho CRM to see monthly projections.
                    </CardContent>
                  </Card>
                ) : data.by_month.map(month => (
                  <Card key={month.month_key} className="border-border/50 bg-card/80">
                    <CardContent className="p-5">
                      <div className="flex items-center justify-between mb-3">
                        <div>
                          <p className="font-semibold text-foreground">{month.month}</p>
                          <p className="text-xs text-muted-foreground">{month.deals_closing} deals</p>
                        </div>
                        <div className="text-right">
                          <p className="text-sm font-bold text-primary">{fmtUSD(month.dealiq_value)}</p>
                          <p className="text-xs text-muted-foreground">CRM: {fmtUSD(month.crm_value)}</p>
                        </div>
                      </div>
                      <div className="h-3 w-full rounded-full bg-secondary overflow-hidden">
                        <div className="h-full rounded-full bg-primary/70 transition-all duration-500"
                          style={{ width: `${Math.min((month.dealiq_value / Math.max(month.crm_value, 1)) * 100, 100)}%` }} />
                      </div>
                      {month.deals.length > 0 && (
                        <p className="mt-2 text-xs text-muted-foreground truncate">
                          {month.deals.slice(0, 4).join(" · ")}{month.deals_closing > 4 ? ` +${month.deals_closing - 4} more` : ""}
                        </p>
                      )}
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}

            {/* ── Alerts Tab ── */}
            {activeTab === "alerts" && (
              <div className="space-y-6">

                {/* AI Rescue Prioritisation — THE headline feature */}
                {ai?.rescue_priorities?.generated && ai.rescue_priorities.priorities.length > 0 && (
                  <div className="rounded-xl border border-primary/30 bg-primary/5 p-5 space-y-4">
                    <div className="flex items-center gap-3">
                      <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/20">
                        <Brain className="h-4 w-4 text-primary" />
                      </div>
                      <div className="flex-1">
                        <div className="flex items-center gap-2">
                          <p className="text-sm font-semibold text-foreground">AI Rescue Plan</p>
                          <AIBadge />
                        </div>
                        <p className="text-xs text-muted-foreground">{ai.rescue_priorities.strategy}</p>
                      </div>
                      {ai.rescue_priorities.total_rescue_potential > 0 && (
                        <div className="text-right">
                          <p className="text-xs text-muted-foreground">Rescue potential</p>
                          <p className="text-lg font-bold text-health-green">+{fmtUSD(ai.rescue_priorities.total_rescue_potential)}</p>
                        </div>
                      )}
                    </div>

                    <div className="space-y-3">
                      {ai.rescue_priorities.priorities.map(p => (
                        <div key={p.rank} className="rounded-lg border border-border/40 bg-background/60 p-4 space-y-2">
                          <div className="flex items-start justify-between gap-3">
                            <div className="flex items-start gap-3">
                              <div className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-bold
                                ${p.rank === 1 ? "bg-primary text-background" : "bg-secondary text-muted-foreground"}`}>
                                {p.rank}
                              </div>
                              <div>
                                <p className="text-sm font-medium text-foreground">{p.deal_name}</p>
                                <p className="text-xs text-muted-foreground">{p.owner} · {fmtUSD(p.amount)}</p>
                              </div>
                            </div>
                            <Badge variant="outline" className={`text-xs shrink-0 ${urgencyColor[p.urgency] ?? ""}`}>
                              <Clock className="h-3 w-3 mr-1" />{p.urgency.replace(/_/g, " ")}
                            </Badge>
                          </div>
                          <div className="pl-9 space-y-1">
                            <p className="text-xs text-muted-foreground italic">{p.why_this_one}</p>
                            <div className="flex items-start gap-1.5">
                              <Zap className="h-3.5 w-3.5 text-primary mt-0.5 shrink-0" />
                              <p className="text-xs text-foreground font-medium">{p.action}</p>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Rescue Opportunities (raw data) */}
                {data.rescue_opportunities.length > 0 && (
                  <div className="space-y-3">
                    <div className="flex items-center gap-2">
                      <LifeBuoy className="h-4 w-4 text-health-yellow" />
                      <h3 className="text-sm font-semibold text-foreground">All Rescue Opportunities</h3>
                      <Badge variant="outline" className="text-xs border-health-yellow/30 text-health-yellow">{data.rescue_opportunities.length}</Badge>
                    </div>
                    {data.rescue_opportunities.map(deal => (
                      <Card key={deal.id} className="border-health-yellow/20 bg-health-yellow/5">
                        <CardContent className="p-4 space-y-2">
                          <div className="flex items-start justify-between">
                            <div>
                              <p className="font-medium text-foreground text-sm">{deal.name}</p>
                              <p className="text-xs text-muted-foreground">{deal.account_name} · {deal.owner}</p>
                            </div>
                            <Badge variant="outline" className={`text-xs capitalize ${healthBadge(deal.health_label)}`}>{deal.health_label.replace("_", " ")}</Badge>
                          </div>
                          <div className="flex items-center gap-4 text-xs">
                            <span className="text-foreground font-medium">{fmtUSD(deal.amount)}</span>
                            <span className={deal.days_to_close <= 7 ? "text-health-red font-medium" : "text-muted-foreground"}>
                              {deal.days_to_close <= 0 ? `${Math.abs(deal.days_to_close)}d overdue` : `${deal.days_to_close}d to close`}
                            </span>
                            <span className="text-muted-foreground">{deal.stage}</span>
                          </div>
                          <div className="flex items-center justify-between bg-health-yellow/10 rounded px-3 py-2">
                            <span className="text-xs text-muted-foreground">Rescue upside</span>
                            <span className="text-sm font-bold text-health-yellow">+{fmtUSD(deal.rescue_upside)}</span>
                          </div>
                        </CardContent>
                      </Card>
                    ))}
                  </div>
                )}

                {/* Overforecasted */}
                {data.overforecasted_deals.length > 0 && (
                  <div className="space-y-3">
                    <div className="flex items-center gap-2">
                      <TrendingDown className="h-4 w-4 text-health-red" />
                      <h3 className="text-sm font-semibold text-foreground">Most Overforecasted</h3>
                      <Badge variant="outline" className="text-xs border-health-red/30 text-health-red">{data.overforecasted_deals.length}</Badge>
                    </div>
                    {data.overforecasted_deals.map(deal => (
                      <Card key={deal.id} className="border-health-red/20 bg-health-red/5">
                        <CardContent className="p-4 space-y-2">
                          <div className="flex items-start justify-between">
                            <div>
                              <p className="font-medium text-foreground text-sm">{deal.name}</p>
                              <p className="text-xs text-muted-foreground">{deal.account_name} · {deal.owner}</p>
                            </div>
                            <Badge variant="outline" className={`text-xs capitalize ${healthBadge(deal.health_label)}`}>{deal.health_label.replace("_", " ")}</Badge>
                          </div>
                          {deal.risk_flag && <p className="text-xs text-health-red italic">{deal.risk_flag}</p>}
                          <div className="grid grid-cols-3 gap-2 text-xs">
                            <div className="rounded bg-secondary/50 px-2 py-1 text-center"><p className="text-muted-foreground">CRM expects</p><p className="font-bold text-foreground">{fmtUSD(deal.crm_expected)}</p></div>
                            <div className="rounded bg-primary/10 px-2 py-1 text-center"><p className="text-muted-foreground">DealIQ says</p><p className="font-bold text-primary">{fmtUSD(deal.dealiq_expected)}</p></div>
                            <div className="rounded bg-health-red/10 px-2 py-1 text-center"><p className="text-muted-foreground">Overcount</p><p className="font-bold text-health-red">-{fmtUSD(deal.gap)}</p></div>
                          </div>
                        </CardContent>
                      </Card>
                    ))}
                  </div>
                )}

                {/* Zombies */}
                {data.already_dead.length > 0 && (
                  <div className="space-y-3">
                    <div className="flex items-center gap-2">
                      <Skull className="h-4 w-4 text-health-red" />
                      <h3 className="text-sm font-semibold text-foreground">Zombie Deals in Forecast</h3>
                      <Badge variant="outline" className="text-xs border-health-red/30 text-health-red">{data.already_dead.length}</Badge>
                    </div>
                    {data.already_dead.map(deal => (
                      <Card key={deal.id} className="border-health-red/30 bg-health-red/5">
                        <CardContent className="p-4 flex items-center justify-between">
                          <div>
                            <p className="font-medium text-foreground text-sm">{deal.name}</p>
                            <p className="text-xs text-muted-foreground">{deal.account_name} · {deal.stage}</p>
                            {deal.is_overdue && <p className="text-xs text-health-red mt-0.5">Closing date passed {deal.days_to_close !== null ? Math.abs(deal.days_to_close) : "?"} days ago</p>}
                          </div>
                          <div className="text-right">
                            <p className="text-sm font-bold text-health-red line-through opacity-60">{fmtUSD(deal.crm_expected)}</p>
                            <p className="text-xs text-muted-foreground">CRM expects</p>
                          </div>
                        </CardContent>
                      </Card>
                    ))}
                  </div>
                )}
              </div>
            )}

          </div>
        ) : null}
      </main>
    </div>
  );
}
