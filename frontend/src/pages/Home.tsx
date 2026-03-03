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
  CheckCircle,
  Clock,
  Zap,
  ChevronRight,
  X,
  AlarmClockOff,
  Database,
} from "lucide-react";

// ── Types ─────────────────────────────────────────────────────────────────────

interface Action {
  id: string;
  type: string;
  deal_id: string;
  deal_name: string;
  company: string;
  amount: number;
  stage: string;
  urgency_score: number;
  context: string;
  suggested_action: string;
  draft?: string;
}

interface PendingUpdate {
  id: string;
  deal_id: string;
  deal_name?: string;
  field_name: string;
  old_value?: string;
  new_value: string;
  confidence: string;
  context?: string;
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

function urgencyLabel(score: number): "URGENT" | "ACTION NEEDED" | "OPPORTUNITY" {
  if (score >= 80) return "URGENT";
  if (score >= 50) return "ACTION NEEDED";
  return "OPPORTUNITY";
}

const URGENCY_CONFIG = {
  URGENT:        { cardClass: "border-health-red/30 bg-health-red/5",      dotClass: "bg-health-red",    badgeClass: "text-health-red bg-health-red/10 border-health-red/30" },
  "ACTION NEEDED": { cardClass: "border-health-orange/30 bg-health-orange/5", dotClass: "bg-health-orange", badgeClass: "text-health-orange bg-health-orange/10 border-health-orange/30" },
  OPPORTUNITY:   { cardClass: "border-health-green/30 bg-health-green/5",  dotClass: "bg-health-green",  badgeClass: "text-health-green bg-health-green/10 border-health-green/30" },
} as const;

// ── Component ─────────────────────────────────────────────────────────────────

export default function Home() {
  const { session } = useSession();
  const { toast } = useToast();

  const [actions, setActions] = useState<Action[]>([]);
  const [pendingUpdates, setPendingUpdates] = useState<PendingUpdate[]>([]);
  const [loading, setLoading] = useState(true);
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());
  const [composer, setComposer] = useState<{ dealId: string; dealName: string; draft?: string } | null>(null);

  useEffect(() => {
    Promise.all([api.getTodayActions(), api.getPendingCrmUpdates()])
      .then(([actionsData, updatesData]) => {
        setActions(actionsData.actions ?? []);
        setPendingUpdates(updatesData.updates ?? []);
      })
      .catch((err: Error) =>
        toast({ title: "Failed to load actions", description: err.message, variant: "destructive" })
      )
      .finally(() => setLoading(false));
  }, []);

  const visibleActions = actions.filter((a) => !dismissed.has(a.id));
  const urgentActions = visibleActions.filter((a) => a.urgency_score >= 80);
  const otherActions = visibleActions.filter((a) => a.urgency_score < 80);
  const atRiskValue = visibleActions.reduce((sum, a) => sum + (a.amount || 0), 0);

  const displayName = session?.display_name ?? "there";

  async function handleDismiss(id: string) {
    setDismissed((prev) => new Set([...prev, id]));
    await api.dismissAction(id).catch(() => null);
  }

  async function handleSnooze(id: string) {
    setDismissed((prev) => new Set([...prev, id]));
    await api.snoozeAction(id).catch(() => null);
    toast({ title: "Snoozed 24h", description: "Action will reappear tomorrow." });
  }

  async function handleApproveUpdate(id: string) {
    await api.approveCrmUpdate(id).catch(() => null);
    setPendingUpdates((prev) => prev.filter((u) => u.id !== id));
    toast({ title: "CRM updated", description: "Field update applied to Zoho." });
  }

  async function handleRejectUpdate(id: string) {
    await api.rejectCrmUpdate(id).catch(() => null);
    setPendingUpdates((prev) => prev.filter((u) => u.id !== id));
  }

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
                  ? "Loading your day…"
                  : `${visibleActions.length} action${visibleActions.length !== 1 ? "s" : ""} today · ${formatCurrency(atRiskValue)} at risk${pendingUpdates.length > 0 ? ` · ${pendingUpdates.length} CRM update${pendingUpdates.length !== 1 ? "s" : ""} pending` : ""}`}
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

          {/* ── Pending CRM Updates Banner ── */}
          {!loading && pendingUpdates.length > 0 && (
            <section>
              <div className="flex items-center gap-2 mb-2">
                <Database className="h-4 w-4 text-blue-400" />
                <h2 className="text-sm font-semibold text-foreground">CRM Updates Awaiting Approval</h2>
                <Badge variant="outline" className="ml-auto text-[10px] h-4 px-1.5 text-blue-400 border-blue-400/30 bg-blue-400/10">
                  {pendingUpdates.length} pending
                </Badge>
              </div>
              <div className="space-y-2">
                {pendingUpdates.map((u) => (
                  <div
                    key={u.id}
                    className="flex items-center gap-3 rounded-xl border border-blue-400/20 bg-blue-400/5 px-4 py-3"
                  >
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-semibold text-foreground">
                        {u.deal_name || u.deal_id} — <span className="font-normal text-muted-foreground">{u.field_name}</span>
                      </p>
                      <p className="text-[11px] text-muted-foreground mt-0.5">
                        {u.old_value ? <><span className="line-through">{u.old_value}</span> → </> : ""}{u.new_value}
                      </p>
                      {u.context && <p className="text-[10px] text-muted-foreground/60 mt-0.5">{u.context}</p>}
                    </div>
                    <Badge variant="outline" className="text-[10px] h-4 px-1.5 shrink-0 capitalize text-muted-foreground">
                      {u.confidence}
                    </Badge>
                    <Button
                      size="sm"
                      variant="outline"
                      className="shrink-0 h-6 px-2 text-[11px] border-health-green/40 text-health-green hover:bg-health-green/10"
                      onClick={() => handleApproveUpdate(u.id)}
                    >
                      Apply
                    </Button>
                    <button
                      className="text-muted-foreground/40 hover:text-muted-foreground shrink-0"
                      onClick={() => handleRejectUpdate(u.id)}
                      aria-label="Reject update"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* ── Urgent Actions ── */}
          {loading ? (
            <div className="space-y-2">
              {[...Array(4)].map((_, i) => <Skeleton key={i} className="h-20 w-full rounded-xl" />)}
            </div>
          ) : visibleActions.length === 0 ? (
            <div className="flex flex-col items-center gap-2 rounded-xl border border-border/30 bg-card/40 px-6 py-10">
              <CheckCircle className="h-8 w-8 text-health-green" />
              <p className="text-sm font-medium text-foreground">All clear — pipeline looks healthy!</p>
              <p className="text-xs text-muted-foreground">No critical or at-risk deals need attention right now.</p>
            </div>
          ) : (
            <>
              {urgentActions.length > 0 && (
                <ActionSection
                  title="URGENT"
                  dotClass={URGENCY_CONFIG.URGENT.dotClass}
                  actions={urgentActions}
                  onEmail={(a) => setComposer({ dealId: a.deal_id, dealName: a.deal_name, draft: a.draft })}
                  onDismiss={handleDismiss}
                  onSnooze={handleSnooze}
                />
              )}

              {otherActions.length > 0 && (
                <ActionSection
                  title="ACTION NEEDED"
                  dotClass={URGENCY_CONFIG["ACTION NEEDED"].dotClass}
                  actions={otherActions}
                  onEmail={(a) => setComposer({ dealId: a.deal_id, dealName: a.deal_name, draft: a.draft })}
                  onDismiss={handleDismiss}
                  onSnooze={handleSnooze}
                />
              )}
            </>
          )}

          {/* ── Quick Links ── */}
          <section className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {[
              { href: "/dashboard", icon: AlertTriangle, label: "Pipeline",   desc: "All deals" },
              { href: "/ask",       icon: Sparkles,      label: "Ask AI",     desc: "Deal Q&A engine" },
              { href: "/settings",  icon: Clock,         label: "Integrations", desc: "Connect Outlook & Zoho" },
            ].map(({ href, icon: Icon, label, desc }) => (
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

function ActionSection({
  title,
  dotClass,
  actions,
  onEmail,
  onDismiss,
  onSnooze,
}: {
  title: string;
  dotClass: string;
  actions: Action[];
  onEmail: (a: Action) => void;
  onDismiss: (id: string) => void;
  onSnooze: (id: string) => void;
}) {
  return (
    <section>
      <div className="flex items-center gap-2 mb-2">
        <Zap className="h-3.5 w-3.5 text-muted-foreground/60" />
        <span className={cn("h-1.5 w-1.5 rounded-full shrink-0", dotClass)} />
        <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground/60">{title}</span>
      </div>
      <div className="space-y-2">
        {actions.map((action) => (
          <ActionCard
            key={action.id}
            action={action}
            onEmail={() => onEmail(action)}
            onDismiss={() => onDismiss(action.id)}
            onSnooze={() => onSnooze(action.id)}
          />
        ))}
      </div>
    </section>
  );
}

function ActionCard({
  action,
  onEmail,
  onDismiss,
  onSnooze,
}: {
  action: Action;
  onEmail: () => void;
  onDismiss: () => void;
  onSnooze: () => void;
}) {
  const label = urgencyLabel(action.urgency_score);
  const cfg = URGENCY_CONFIG[label];

  return (
    <div className={cn(
      "rounded-xl border px-4 py-3 transition-colors",
      cfg.cardClass,
    )}>
      {/* Top row: deal name + amount + dismiss */}
      <div className="flex items-start gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <p className="text-sm font-semibold text-foreground truncate">{action.deal_name}</p>
            <span className="text-[10px] text-muted-foreground/50 shrink-0">{action.company}</span>
            <span className="text-[10px] text-muted-foreground/50 shrink-0">{formatCurrency(action.amount)}</span>
            <Badge variant="outline" className={cn("text-[10px] h-4 px-1.5 shrink-0", cfg.badgeClass)}>
              {action.stage}
            </Badge>
          </div>
          {/* AI context */}
          <p className="text-xs text-muted-foreground mt-1">{action.context}</p>
          {/* Suggested action */}
          <p className="text-[11px] text-foreground/70 mt-0.5 flex items-start gap-1">
            <ChevronRight className="h-3 w-3 mt-0.5 shrink-0 text-muted-foreground/40" />
            {action.suggested_action}
          </p>
        </div>

        {/* Dismiss button */}
        <button
          className="text-muted-foreground/30 hover:text-muted-foreground shrink-0 mt-0.5"
          onClick={onDismiss}
          aria-label="Dismiss"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* Action buttons */}
      <div className="flex items-center gap-2 mt-3">
        <Button
          size="sm"
          variant="outline"
          className="h-7 px-3 text-xs border-border/50 hover:border-primary/40 hover:text-primary"
          onClick={onEmail}
        >
          <Mail className="mr-1.5 h-3 w-3" />
          {action.draft ? "Review Draft" : "Draft Email"}
        </Button>
        <button
          className="text-[11px] text-muted-foreground/50 hover:text-muted-foreground flex items-center gap-1"
          onClick={onSnooze}
        >
          <AlarmClockOff className="h-3 w-3" />
          Snooze
        </button>
      </div>
    </div>
  );
}
