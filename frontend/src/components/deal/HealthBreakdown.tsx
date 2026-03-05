import { useEffect, useState } from "react";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { useCountUp } from "@/hooks/useCountUp";
import { Mail, TrendingUp, TrendingDown, AlertTriangle, Sparkles, ArrowRight, Users, XCircle } from "lucide-react";

interface Signal {
  name: string;
  score: number;
  max_score?: number;
  label: string;
  detail: string;
}

interface EmailAnalysis {
  generated: boolean;
  summary: string;
  buyer_sentiment: string;
  last_buyer_response_days: number | null;
  discount_mentions: number;
  objections: string[];
  red_flags: string[];
  green_flags: string[];
  next_step_promised: string | null;
  email_health_score: number;
  email_count?: number;
  reason?: string;
}

interface HealthData {
  overall_score?: number;
  total_score?: number;
  health_label: string;
  signals: Signal[];
  recommendation: string;
  action_required: boolean;
  email_analysis?: EmailAnalysis;
}

const SIGNAL_SORT_ORDER: Record<string, number> = { critical: 0, warn: 1, insufficient_data: 2, good: 3 };

function sortedSignals(signals: Signal[]): Signal[] {
  return [...signals].sort((a, b) =>
    (SIGNAL_SORT_ORDER[a.label] ?? 4) - (SIGNAL_SORT_ORDER[b.label] ?? 4)
  );
}

function labelColor(label: string) {
  switch (label) {
    case "good": return "bg-health-green/20 text-health-green border-health-green/30";
    case "warn": return "bg-health-yellow/20 text-health-yellow border-health-yellow/30";
    case "critical": return "bg-health-red/20 text-health-red border-health-red/30";
    case "insufficient_data": return "bg-muted/60 text-muted-foreground border-border/40";
    default: return "bg-muted text-muted-foreground";
  }
}

function labelDisplay(label: string) {
  return label === "insufficient_data" ? "no data" : label;
}

function scoreRingColor(label: string) {
  switch (label) {
    case "healthy": return "text-health-green";
    case "at_risk": return "text-health-yellow";
    case "critical": return "text-health-orange";
    case "zombie": return "text-health-red";
    default: return "text-muted-foreground";
  }
}

function progressColor(label: string) {
  switch (label) {
    case "good": return "[&>div]:bg-health-green";
    case "warn": return "[&>div]:bg-health-yellow";
    case "critical": return "[&>div]:bg-health-red";
    case "insufficient_data": return "[&>div]:bg-muted-foreground/30";
    default: return "";
  }
}

function sentimentConfig(sentiment: string) {
  switch (sentiment) {
    case "positive": return { cls: "text-health-green border-health-green/30 bg-health-green/10", label: "Positive" };
    case "neutral": return { cls: "text-health-yellow border-health-yellow/30 bg-health-yellow/10", label: "Neutral" };
    case "negative": return { cls: "text-health-red border-health-red/30 bg-health-red/10", label: "Negative" };
    case "no_response": return { cls: "text-health-red border-health-red/30 bg-health-red/10", label: "No Response" };
    default: return { cls: "text-muted-foreground border-border/40", label: "Unknown" };
  }
}

export default function HealthBreakdown({ dealId }: { dealId: string }) {
  const [data, setData] = useState<HealthData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.getDealHealth(dealId)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [dealId]);

  // Compute display score early so useCountUp is ALWAYS called unconditionally
  // (React Rules of Hooks: hooks must not be called after conditional returns)
  const displayScore = data
    ? (typeof data.total_score === "number" ? data.total_score
      : typeof data.overall_score === "number" ? data.overall_score : 0)
    : 0;
  const animatedScore = useCountUp(displayScore, 1200);

  if (loading) return (
    <div className="space-y-3 py-4">
      {[...Array(4)].map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}
    </div>
  );
  if (!data) return <p className="text-xs text-muted-foreground py-4">Could not load health data.</p>;

  const circumference = 2 * Math.PI * 45;
  const offset = circumference - (animatedScore / 100) * circumference;
  const ea = data.email_analysis;
  const sentiment = ea ? sentimentConfig(ea.buyer_sentiment) : null;

  return (
    <div className="space-y-6 pb-4">
      {/* Score Ring */}
      <div className="flex justify-center relative">
        {/* Ambient glow */}
        <div
          className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 h-24 w-24 rounded-full"
          style={{
            background: `radial-gradient(circle, var(--health-${data.health_label.replace("healthy", "green").replace("at_risk", "yellow").replace("zombie", "red")}, currentColor) 0%, transparent 70%)`,
            opacity: 0.15,
            filter: 'blur(20px)',
          }}
        />
        <div className="relative h-32 w-32 z-10">
          <svg className="h-32 w-32 -rotate-90" viewBox="0 0 100 100">
            <circle cx="50" cy="50" r="45" fill="none" strokeWidth="6" className="stroke-secondary" />
            <circle cx="50" cy="50" r="45" fill="none" strokeWidth="6" strokeLinecap="round"
              className={`${scoreRingColor(data.health_label)} stroke-current transition-all`}
              strokeDasharray={circumference} strokeDashoffset={offset}
              style={{ transition: "stroke-dashoffset 1.2s ease-out 300ms" }} />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className={`text-3xl font-bold font-numeric tabular-nums ${scoreRingColor(data.health_label)}`}>{animatedScore}</span>
            <span className="text-xs uppercase text-muted-foreground">{data.health_label.replace("_", " ")}</span>
          </div>
        </div>
      </div>

      {/* Signals */}
      <div className="space-y-3">
        {sortedSignals(data.signals).map((signal, idx) => (
          <div key={signal.name} className="space-y-1">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-foreground">{signal.name}</span>
              <Badge variant="outline" className={`text-xs ${labelColor(signal.label)}`}>
                {labelDisplay(signal.label)}
              </Badge>
            </div>
            <div className="relative h-2 w-full overflow-hidden rounded-full bg-secondary">
              <div
                className={`h-full w-full flex-1 transition-transform duration-[600ms] ease-out origin-left animate-in fade-in fill-mode-both ${progressColor(signal.label).replace('[&>div]:', '')}`}
                style={{
                  transform: `scaleX(${signal.score / (signal.max_score || 20)})`,
                  animationDelay: `${500 + idx * 80}ms`
                }}
              />
            </div>
            <p className={`text-xs ${signal.label === "insufficient_data" ? "text-muted-foreground/50 italic" : "text-muted-foreground"}`}>
              {signal.detail}
            </p>
          </div>
        ))}
      </div>

      {/* Email Intelligence */}
      {ea && ea.generated && (
        <div className="space-y-3 rounded-xl border border-primary/20 bg-primary/5 p-4">
          <div className="flex items-center gap-2">
            <div className="flex h-6 w-6 items-center justify-center rounded-lg bg-primary/20">
              <Mail className="h-3.5 w-3.5 text-primary" />
            </div>
            <span className="text-xs font-semibold text-primary uppercase tracking-wider">Email Thread Intelligence</span>
            <span className="inline-flex items-center gap-1 rounded-full border border-primary/30 bg-primary/10 px-1.5 py-0.5 text-xs font-medium text-primary">
              <Sparkles className="h-2.5 w-2.5" /> AI
            </span>
            {ea.email_count && <span className="ml-auto text-xs text-muted-foreground">{ea.email_count} emails</span>}
          </div>

          <p className="text-xs text-foreground/90 leading-relaxed">{ea.summary}</p>

          <div className="flex items-center gap-3 flex-wrap">
            {sentiment && (
              <Badge variant="outline" className={`text-xs ${sentiment.cls}`}>Buyer: {sentiment.label}</Badge>
            )}
            {ea.last_buyer_response_days !== null && (
              <span className={`text-xs font-medium ${(ea.last_buyer_response_days ?? 0) > 14 ? "text-health-red" : (ea.last_buyer_response_days ?? 0) > 7 ? "text-health-yellow" : "text-health-green"}`}>
                Last response: {ea.last_buyer_response_days}d ago
              </span>
            )}
            {ea.discount_mentions > 0 && (
              <Badge variant="outline" className="text-xs text-health-orange border-health-orange/30 bg-health-orange/10">
                Discount mentioned {ea.discount_mentions}x
              </Badge>
            )}
          </div>

          {ea.green_flags.length > 0 && (
            <div className="space-y-1">
              <p className="text-xs font-semibold text-health-green uppercase tracking-wider">Green Flags</p>
              {ea.green_flags.map((f, i) => (
                <div key={i} className="flex items-start gap-1.5">
                  <TrendingUp className="h-3 w-3 text-health-green mt-0.5 shrink-0" />
                  <p className="text-xs text-foreground/80">{f}</p>
                </div>
              ))}
            </div>
          )}

          {ea.red_flags.length > 0 && (
            <div className="space-y-1">
              <p className="text-xs font-semibold text-health-red uppercase tracking-wider">Red Flags</p>
              {ea.red_flags.map((f, i) => (
                <div key={i} className="flex items-start gap-1.5">
                  <TrendingDown className="h-3 w-3 text-health-red mt-0.5 shrink-0" />
                  <p className="text-xs text-foreground/80">{f}</p>
                </div>
              ))}
            </div>
          )}

          {ea.objections.length > 0 && (
            <div className="space-y-1">
              <p className="text-xs font-semibold text-health-orange uppercase tracking-wider">Objections Raised</p>
              {ea.objections.map((o, i) => (
                <div key={i} className="flex items-start gap-1.5">
                  <AlertTriangle className="h-3 w-3 text-health-orange mt-0.5 shrink-0" />
                  <p className="text-xs text-foreground/80">{o}</p>
                </div>
              ))}
            </div>
          )}

          {ea.next_step_promised && (
            <div className="rounded-md border border-primary/20 bg-background/50 px-3 py-2">
              <p className="text-xs font-semibold text-primary mb-0.5">Promised Next Step</p>
              <p className="text-xs text-foreground">{ea.next_step_promised}</p>
            </div>
          )}
        </div>
      )}

      {ea && !ea.generated && ea.reason === "no_emails" && (
        <div className="flex items-center gap-2 rounded-lg border border-border/40 bg-secondary/30 px-3 py-2">
          <Mail className="h-3.5 w-3.5 text-muted-foreground/60" />
          <p className="text-xs text-muted-foreground">No email thread found in Zoho for this deal.</p>
        </div>
      )}

      {/* Recommendation */}
      <Card className={`border ${data.action_required ? "border-health-orange/40 bg-health-orange/5" : "border-border/50 bg-secondary/50"}`}>
        <CardContent className="p-4">
          <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-1">Recommendation</p>
          <p className="text-sm text-foreground">{data.recommendation}</p>
        </CardContent>
      </Card>

      {/* Quick Actions */}
      <div className="space-y-2">
        <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Quick Actions</p>
        <div className="flex flex-wrap gap-2">
          <Button
            size="sm"
            variant="outline"
            className="gap-1.5 border-sky-500/40 bg-sky-500/10 text-sky-400 hover:bg-sky-500/20 hover:text-sky-300 text-xs"
          >
            <ArrowRight className="h-3.5 w-3.5" />
            Advance Stage
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="gap-1.5 border-amber-500/40 bg-amber-500/10 text-amber-400 hover:bg-amber-500/20 hover:text-amber-300 text-xs"
          >
            <Users className="h-3.5 w-3.5" />
            Escalate
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="gap-1.5 border-health-red/40 bg-health-red/10 text-health-red hover:bg-health-red/20 text-xs"
          >
            <XCircle className="h-3.5 w-3.5" />
            Mark as Lost
          </Button>
        </div>
      </div>
    </div>
  );
}
