import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Bell,
  AlertTriangle,
  AlertCircle,
  Clock,
  Skull,
  TrendingDown,
  ArrowRight,
  RefreshCw,
  CheckCircle,
} from "lucide-react";

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

interface DigestData {
  generated_at: string;
  total_alerts: number;
  critical_count: number;
  warning_count: number;
  critical_alerts: DigestAlert[];
  warning_alerts: DigestAlert[];
  top_actions: { deal_name: string; owner: string; amount_fmt: string; action: string; severity: string }[];
  deals_scanned: number;
  simulated?: boolean;
}

// ── Config ────────────────────────────────────────────────────────────────────

const TYPE_CONFIG: Record<string, { icon: React.ElementType; label: string }> = {
  CLOSING_OVERDUE:    { icon: Clock,          label: "Overdue" },
  CLOSING_URGENT:     { icon: AlertTriangle,  label: "Urgent" },
  WENT_SILENT:        { icon: AlertCircle,    label: "Gone Silent" },
  ZOMBIE_IN_FORECAST: { icon: Skull,          label: "Zombie" },
  HIGH_VALUE_RISK:    { icon: TrendingDown,   label: "High Value Risk" },
  NO_NEXT_STEP:       { icon: ArrowRight,     label: "No Next Step" },
};

// ── Sub-component ─────────────────────────────────────────────────────────────

function AlertCard({ alert }: { alert: DigestAlert }) {
  const config = TYPE_CONFIG[alert.type] ?? { icon: AlertCircle, label: alert.type };
  const Icon = config.icon;
  const isCritical = alert.severity === "critical";

  return (
    <div className={cn(
      "rounded-xl border px-4 py-3 space-y-1.5",
      isCritical
        ? "border-health-red/30 bg-health-red/5"
        : "border-health-orange/30 bg-health-orange/5"
    )}>
      <div className="flex items-center gap-2">
        <Icon className={cn(
          "h-3.5 w-3.5 shrink-0",
          isCritical ? "text-health-red" : "text-health-orange"
        )} />
        <span className={cn(
          "text-[10px] font-semibold uppercase tracking-wider",
          isCritical ? "text-health-red" : "text-health-orange"
        )}>
          {config.label}
        </span>
        <Badge variant="outline" className="ml-auto text-[10px] h-4 px-1.5 border-border/40 text-muted-foreground">
          {alert.amount_fmt}
        </Badge>
      </div>
      <p className="text-xs font-semibold text-foreground">{alert.deal_name}</p>
      <p className="text-[11px] text-muted-foreground leading-relaxed">{alert.message}</p>
      <p className="text-[11px] font-medium text-foreground/80">{alert.action}</p>
    </div>
  );
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function AlertsPage() {
  const { toast } = useToast();
  const [data,    setData]    = useState<DigestData | null>(null);
  const [loading, setLoading] = useState(true);

  const loadAlerts = useCallback(() => {
    setLoading(true);
    api.getAlertsDigest()
      .then(setData)
      .catch((err: Error) =>
        toast({ title: "Failed to load alerts", description: err.message, variant: "destructive" })
      )
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { loadAlerts(); }, [loadAlerts]);

  const criticalAlerts = data?.critical_alerts ?? [];
  const warningAlerts  = data?.warning_alerts  ?? [];

  return (
    <div className="min-h-screen bg-background">

      {/* ── Header ── */}
      <div className="border-b border-border/40 px-6 py-4">
        <div className="flex items-center justify-between max-w-5xl mx-auto">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-health-orange/15">
              <Bell className="h-4 w-4 text-health-orange" />
            </div>
            <div>
              <h1 className="text-sm font-semibold text-foreground">Alerts</h1>
              <p className="text-xs text-muted-foreground">
                {loading
                  ? "Loading…"
                  : data
                    ? `${data.total_alerts} alerts across ${data.deals_scanned} deals`
                    : "No data"}
              </p>
            </div>
          </div>
          <Button
            variant="outline"
            size="sm"
            className="h-7 text-xs border-border/50"
            onClick={loadAlerts}
            disabled={loading}
          >
            <RefreshCw className={cn("mr-1.5 h-3 w-3", loading && "animate-spin")} />
            Refresh
          </Button>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-6 py-6">
        {loading ? (
          <div className="space-y-3">
            {[...Array(6)].map((_, i) => <Skeleton key={i} className="h-20 rounded-xl" />)}
          </div>
        ) : criticalAlerts.length === 0 && warningAlerts.length === 0 ? (
          <div className="flex flex-col items-center gap-2 rounded-xl border border-border/30 bg-card/40 px-6 py-16">
            <CheckCircle className="h-8 w-8 text-health-green" />
            <p className="text-sm font-medium text-foreground">No alerts — pipeline looks healthy!</p>
            <p className="text-xs text-muted-foreground">All deals are on track.</p>
          </div>
        ) : (
          <div className="space-y-2">
            {criticalAlerts.length > 0 && (
              <>
                <p className="text-[11px] font-semibold uppercase tracking-widest text-health-red/80 mb-2">
                  Critical ({criticalAlerts.length})
                </p>
                {criticalAlerts.map((a, i) => <AlertCard key={i} alert={a} />)}
              </>
            )}

            {warningAlerts.length > 0 && (
              <>
                <p className={cn(
                  "text-[11px] font-semibold uppercase tracking-widest text-health-orange/80 mb-2",
                  criticalAlerts.length > 0 && "mt-6"
                )}>
                  Warnings ({warningAlerts.length})
                </p>
                {warningAlerts.map((a, i) => <AlertCard key={i} alert={a} />)}
              </>
            )}

            {data?.simulated && (
              <p className="text-[10px] text-muted-foreground/40 pt-2 text-center">
                Demo data — connect Zoho CRM for live alerts
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
