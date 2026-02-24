import { useState } from "react";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Bell, AlertTriangle, AlertCircle, CheckCircle,
  RefreshCw, Zap, TrendingDown, Clock, Skull,
  ArrowRight, ChevronDown, ChevronUp
} from "lucide-react";
import { api } from "@/lib/api";

// ── Types ─────────────────────────────────────────────────────────────────────

interface DigestAlert {
  type: string;
  severity: "critical" | "warning" | "info";
  deal_id: string;
  deal_name: string;
  owner: string;
  amount: number;
  amount_fmt: string;
  stage: string;
  health_label: string;
  health_score: number;
  message: string;
  action: string;
  silence_days: number;
  days_to_close: number | null;
}

interface TopAction {
  deal_name: string;
  owner: string;
  amount_fmt: string;
  action: string;
  severity: string;
}

interface DigestData {
  generated_at: string;
  total_alerts: number;
  critical_count: number;
  warning_count: number;
  critical_alerts: DigestAlert[];
  warning_alerts: DigestAlert[];
  top_actions: TopAction[];
  deals_scanned: number;
  simulated?: boolean;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const typeConfig: Record<string, { icon: any; label: string }> = {
  CLOSING_OVERDUE:   { icon: Clock,         label: "Overdue" },
  CLOSING_URGENT:    { icon: AlertTriangle,  label: "Urgent" },
  WENT_SILENT:       { icon: AlertCircle,    label: "Gone Silent" },
  ZOMBIE_IN_FORECAST:{ icon: Skull,          label: "Zombie" },
  HIGH_VALUE_RISK:   { icon: TrendingDown,   label: "High Value Risk" },
  NO_NEXT_STEP:      { icon: ArrowRight,     label: "No Next Step" },
  STAGE_STUCK:       { icon: Clock,          label: "Stage Stuck" },
};

function AlertCard({ alert }: { alert: DigestAlert }) {
  const [expanded, setExpanded] = useState(false);
  const cfg = typeConfig[alert.type] ?? { icon: AlertCircle, label: alert.type };
  const Icon = cfg.icon;
  const isCritical = alert.severity === "critical";

  return (
    <div className={`rounded-lg border p-3 space-y-2 transition-all
      ${isCritical
        ? "border-health-red/25 bg-health-red/5"
        : "border-health-yellow/20 bg-health-yellow/5"}`}>

      {/* Header */}
      <div className="flex items-start gap-2">
        <div className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full
          ${isCritical ? "bg-health-red/20" : "bg-health-yellow/20"}`}>
          <Icon className={`h-3.5 w-3.5 ${isCritical ? "text-health-red" : "text-health-yellow"}`} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-2">
            <p className="text-xs font-semibold text-foreground leading-tight">{alert.deal_name}</p>
            <span className="shrink-0 text-xs font-bold text-foreground">{alert.amount_fmt}</span>
          </div>
          <p className="text-xs text-muted-foreground mt-0.5 leading-snug">{alert.message}</p>
        </div>
      </div>

      {/* Meta */}
      <div className="flex items-center gap-2 pl-8">
        <Badge variant="outline" className="text-xs py-0 border-border/40">{alert.owner}</Badge>
        <Badge variant="outline" className="text-xs py-0 border-border/40">{alert.stage}</Badge>
        <Badge variant="outline" className={`text-xs py-0
          ${cfg.label === "Zombie" ? "border-health-red/30 text-health-red" :
            isCritical ? "border-health-orange/30 text-health-orange" :
            "border-health-yellow/30 text-health-yellow"}`}>
          {cfg.label}
        </Badge>
      </div>

      {/* Action — expandable */}
      <button
        onClick={() => setExpanded(v => !v)}
        className="w-full flex items-center justify-between pl-8 pr-1 text-xs text-primary hover:text-primary/80 transition-colors">
        <span className="font-medium">Suggested action</span>
        {expanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
      </button>

      {expanded && (
        <div className="pl-8 pr-1">
          <div className="flex items-start gap-1.5 rounded-md bg-primary/10 border border-primary/20 px-3 py-2">
            <Zap className="h-3.5 w-3.5 text-primary mt-0.5 shrink-0" />
            <p className="text-xs text-foreground leading-relaxed">{alert.action}</p>
          </div>
        </div>
      )}
    </div>
  );
}


export function AlertsBell({ onClick, criticalCount }: { onClick: () => void; criticalCount?: number }) {
  return (
    <button
      onClick={onClick}
      className="relative flex items-center gap-1.5 rounded-lg border border-border/50 bg-secondary/50
        px-3 py-1.5 text-sm font-medium text-foreground hover:bg-secondary transition-colors">
      <Bell className="h-4 w-4" />
      <span className="hidden sm:inline">Daily Digest</span>
      {criticalCount !== undefined && criticalCount > 0 && (
        <span className="absolute -top-1.5 -right-1.5 flex h-4 w-4 items-center justify-center
          rounded-full bg-health-red text-xs font-bold text-white">
          {criticalCount > 9 ? "9+" : criticalCount}
        </span>
      )}
    </button>
  );
}

// ── Main Panel ────────────────────────────────────────────────────────────────

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function AlertsDigestPanel({ open, onClose }: Props) {
  const [data, setData] = useState<DigestData | null>(null);
  const [loading, setLoading] = useState(false);
  const [activeSection, setActiveSection] = useState<"actions" | "critical" | "warnings">("actions");

  const load = async () => {
    setLoading(true);
    try {
      const result = await api.getAlertsDigest();
      setData(result);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  // Load when panel opens
  const handleOpenChange = (isOpen: boolean) => {
    if (isOpen && !data) load();
    if (!isOpen) onClose();
  };

  const sections = [
    { id: "actions",   label: "Top Actions", count: data?.top_actions.length ?? 0 },
    { id: "critical",  label: "Critical",    count: data?.critical_count ?? 0, red: true },
    { id: "warnings",  label: "Warnings",    count: data?.warning_count ?? 0 },
  ] as const;

  return (
    <Sheet open={open} onOpenChange={handleOpenChange}>
      <SheetContent
        side="right"
        className="w-full overflow-y-auto border-border/50 bg-background sm:max-w-lg">

        <SheetHeader className="pb-4 border-b border-border/30">
          <div className="flex items-start justify-between">
            <div>
              <SheetTitle className="flex items-center gap-2 text-foreground">
                <Bell className="h-5 w-5" />
                Daily Pipeline Digest
              </SheetTitle>
              <p className="text-xs text-muted-foreground mt-1">
                {data
                  ? `${data.deals_scanned} deals scanned · ${data.total_alerts} alerts found`
                  : "Scanning your pipeline for what needs attention today"}
              </p>
            </div>
            {data && (
              <Button variant="ghost" size="sm" onClick={load} disabled={loading}
                className="text-muted-foreground h-8 w-8 p-0">
                <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
              </Button>
            )}
          </div>

          {/* Summary chips */}
          {data && !loading && (
            <div className="flex gap-2 mt-3">
              <div className="flex items-center gap-1.5 rounded-lg border border-health-red/30 bg-health-red/10 px-3 py-1.5">
                <AlertTriangle className="h-3.5 w-3.5 text-health-red" />
                <span className="text-sm font-bold text-health-red">{data.critical_count}</span>
                <span className="text-xs text-health-red/80">critical</span>
              </div>
              <div className="flex items-center gap-1.5 rounded-lg border border-health-yellow/30 bg-health-yellow/10 px-3 py-1.5">
                <AlertCircle className="h-3.5 w-3.5 text-health-yellow" />
                <span className="text-sm font-bold text-health-yellow">{data.warning_count}</span>
                <span className="text-xs text-health-yellow/80">warnings</span>
              </div>
              {data.critical_count === 0 && data.warning_count === 0 && (
                <div className="flex items-center gap-1.5 rounded-lg border border-health-green/30 bg-health-green/10 px-3 py-1.5">
                  <CheckCircle className="h-3.5 w-3.5 text-health-green" />
                  <span className="text-xs text-health-green font-medium">Pipeline looks healthy</span>
                </div>
              )}
            </div>
          )}
        </SheetHeader>

        {/* Loading state */}
        {loading && (
          <div className="space-y-3 pt-5">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <RefreshCw className="h-4 w-4 animate-spin text-primary" />
              Scanning {data ? "for updates" : "all deals"}...
            </div>
            {[...Array(5)].map((_, i) => (
              <div key={i} className="rounded-lg border border-border/40 p-3 space-y-2">
                <Skeleton className="h-3 w-2/3" />
                <Skeleton className="h-3 w-full" />
                <Skeleton className="h-3 w-1/2" />
              </div>
            ))}
          </div>
        )}

        {/* Content */}
        {!loading && data && (
          <div className="pt-4 space-y-4">

            {/* Section tabs */}
            <div className="flex gap-1 rounded-lg border border-border/40 bg-secondary/30 p-1">
              {sections.map(s => (
                <button key={s.id} onClick={() => setActiveSection(s.id)}
                  className={`flex-1 rounded-md px-2 py-1.5 text-xs font-medium transition-all flex items-center justify-center gap-1.5
                    ${activeSection === s.id
                      ? "bg-background text-foreground shadow-sm"
                      : "text-muted-foreground hover:text-foreground"}`}>
                  {s.label}
                  {s.count > 0 && (
                    <span className={`inline-flex h-4 min-w-4 items-center justify-center rounded-full px-1 text-xs font-bold
                      ${"red" in s && s.red && s.count > 0
                        ? "bg-health-red text-white"
                        : "bg-secondary text-muted-foreground"}`}>
                      {s.count}
                    </span>
                  )}
                </button>
              ))}
            </div>

            {/* Top Actions */}
            {activeSection === "actions" && (
              <div className="space-y-3">
                <p className="text-xs text-muted-foreground">
                  The {data.top_actions.length} most important things to do right now, ranked by severity and deal value.
                </p>
                {data.top_actions.length === 0 ? (
                  <div className="flex flex-col items-center gap-2 py-8 text-center">
                    <CheckCircle className="h-8 w-8 text-health-green/60" />
                    <p className="text-sm font-medium text-muted-foreground">No urgent actions needed</p>
                    <p className="text-xs text-muted-foreground/60">Your pipeline looks healthy today</p>
                  </div>
                ) : (
                  data.top_actions.map((action, i) => (
                    <div key={i} className={`rounded-lg border p-4 space-y-2
                      ${action.severity === "critical"
                        ? "border-health-red/20 bg-health-red/5"
                        : "border-health-yellow/20 bg-health-yellow/5"}`}>
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <div className={`flex h-5 w-5 items-center justify-center rounded-full text-xs font-bold
                            ${action.severity === "critical" ? "bg-health-red text-white" : "bg-health-yellow text-background"}`}>
                            {i + 1}
                          </div>
                          <span className="text-sm font-semibold text-foreground">{action.deal_name}</span>
                        </div>
                        <span className="text-xs font-bold text-foreground">{action.amount_fmt}</span>
                      </div>
                      <p className="text-xs text-muted-foreground pl-7">{action.owner}</p>
                      <div className="flex items-start gap-2 pl-7">
                        <Zap className="h-3.5 w-3.5 text-primary mt-0.5 shrink-0" />
                        <p className="text-xs text-foreground leading-relaxed">{action.action}</p>
                      </div>
                    </div>
                  ))
                )}
              </div>
            )}

            {/* Critical Alerts */}
            {activeSection === "critical" && (
              <div className="space-y-3">
                <p className="text-xs text-muted-foreground">
                  {data.critical_count} deals need immediate attention today.
                </p>
                {data.critical_alerts.length === 0 ? (
                  <div className="flex flex-col items-center gap-2 py-8 text-center">
                    <CheckCircle className="h-8 w-8 text-health-green/60" />
                    <p className="text-sm font-medium text-muted-foreground">No critical alerts</p>
                  </div>
                ) : (
                  data.critical_alerts.map((alert, i) => (
                    <AlertCard key={`${alert.deal_id}-${alert.type}-${i}`} alert={alert} />
                  ))
                )}
              </div>
            )}

            {/* Warnings */}
            {activeSection === "warnings" && (
              <div className="space-y-3">
                <p className="text-xs text-muted-foreground">
                  {data.warning_count} deals to watch this week.
                </p>
                {data.warning_alerts.length === 0 ? (
                  <div className="flex flex-col items-center gap-2 py-8 text-center">
                    <CheckCircle className="h-8 w-8 text-health-green/60" />
                    <p className="text-sm font-medium text-muted-foreground">No warnings</p>
                  </div>
                ) : (
                  data.warning_alerts.map((alert, i) => (
                    <AlertCard key={`${alert.deal_id}-${alert.type}-${i}`} alert={alert} />
                  ))
                )}
              </div>
            )}

            {/* Footer */}
            <div className="border-t border-border/30 pt-3 text-center">
              <p className="text-xs text-muted-foreground/60">
                Generated {new Date(data.generated_at).toLocaleTimeString()} ·
                {data.simulated ? " Demo data" : " Live Zoho data"}
              </p>
            </div>
          </div>
        )}

        {/* Initial empty state */}
        {!loading && !data && (
          <div className="flex flex-col items-center gap-3 py-16 text-center">
            <Bell className="h-10 w-10 text-muted-foreground/30" />
            <p className="text-sm font-medium text-muted-foreground">Ready to scan your pipeline</p>
            <Button size="sm" onClick={load} className="mt-1">
              Run Digest Now
            </Button>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
