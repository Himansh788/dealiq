import { useState } from "react";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/hooks/use-toast";
import { api } from "@/lib/api";
import { ScanSearch, AlertTriangle, AlertCircle, Info, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";

// ── Types ─────────────────────────────────────────────────────────────────────

interface TrackerMatch {
  tracker_id: string;
  tracker_name: string;
  severity: "critical" | "warning" | "info";
  matched_text: string;
  timestamp_hint: string | null;
  confidence_score: number;
  context_snippet: string;
}

interface AnalysisResult {
  matches: TrackerMatch[];
  total_matches: number;
  trackers_run: number;
  critical_count: number;
  warning_count: number;
  info_count: number;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function severityConfig(severity: string) {
  switch (severity) {
    case "critical": return {
      icon: AlertTriangle,
      badge: "border-health-red/40 bg-health-red/10 text-health-red",
      border: "border-l-health-red/60",
    };
    case "warning": return {
      icon: AlertCircle,
      badge: "border-health-yellow/40 bg-health-yellow/10 text-health-yellow",
      border: "border-l-health-yellow/60",
    };
    default: return {
      icon: Info,
      badge: "border-primary/40 bg-primary/10 text-primary",
      border: "border-l-primary/60",
    };
  }
}

function ConfidencePip({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const color = pct >= 85 ? "text-health-green" : pct >= 65 ? "text-health-yellow" : "text-muted-foreground";
  return (
    <span className={cn("text-xs font-medium tabular-nums", color)}>{pct}%</span>
  );
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function TrackerPanel({ dealId }: { dealId: string }) {
  const { toast } = useToast();
  const [transcript, setTranscript] = useState("");
  const [loading, setLoading]       = useState(false);
  const [result, setResult]         = useState<AnalysisResult | null>(null);

  const run = async (isDemo = false) => {
    if (!isDemo && transcript.trim().length < 60) {
      toast({ title: "Transcript too short", description: "Paste at least a few lines.", variant: "destructive" });
      return;
    }
    setLoading(true);
    setResult(null);
    try {
      const data = isDemo
        ? await api.getDemoTrackers()
        : await api.analyzeTranscript(transcript);
      setResult(data as AnalysisResult);
    } catch (e: any) {
      toast({ title: "Tracker analysis failed", description: e.message ?? "Unknown error", variant: "destructive" });
    } finally {
      setLoading(false);
    }
  };

  // Sort: critical first, then warning, then info
  const sorted = result
    ? [...result.matches].sort((a, b) => {
        const order = { critical: 0, warning: 1, info: 2 };
        return (order[a.severity] ?? 3) - (order[b.severity] ?? 3);
      })
    : [];

  return (
    <div className="space-y-4 pb-2">

      {/* Input */}
      {!result && !loading && (
        <div className="space-y-3">
          <Textarea
            value={transcript}
            onChange={e => setTranscript(e.target.value)}
            placeholder={"Paste this deal's call transcript here…\n\nSmart Trackers will detect: discount pressure, competitor mentions, budget objections, absent decision makers, vague next steps, and timeline urgency — even when they're expressed indirectly."}
            className="min-h-[180px] resize-none border-border/50 bg-secondary/40 text-sm font-mono leading-relaxed focus-visible:ring-primary/40"
          />
          <div className="flex gap-2">
            <Button
              onClick={() => run(false)}
              disabled={loading}
              size="sm"
              className="flex-1 bg-primary hover:bg-primary/90 text-white gap-1.5"
            >
              <ScanSearch className="h-3.5 w-3.5" />
              Run Smart Trackers
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => run(true)}
              disabled={loading}
              className="border-border/50 text-muted-foreground hover:text-foreground text-xs"
            >
              Demo
            </Button>
          </div>
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="space-y-3 py-2">
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <div className="h-3.5 w-3.5 rounded-full border-2 border-primary/30 border-t-primary animate-spin" />
            Scanning for concept matches…
          </div>
          {[...Array(3)].map((_, i) => <Skeleton key={i} className="h-16 w-full rounded-lg" />)}
        </div>
      )}

      {/* Results */}
      {result && !loading && (
        <div className="space-y-3">

          {/* Summary row */}
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-semibold text-foreground">{result.total_matches} match{result.total_matches !== 1 ? "es" : ""}</span>
            {result.critical_count > 0 && (
              <Badge variant="outline" className="text-xs border-health-red/40 bg-health-red/10 text-health-red">
                {result.critical_count} critical
              </Badge>
            )}
            {result.warning_count > 0 && (
              <Badge variant="outline" className="text-xs border-health-yellow/40 bg-health-yellow/10 text-health-yellow">
                {result.warning_count} warning
              </Badge>
            )}
            {result.info_count > 0 && (
              <Badge variant="outline" className="text-xs border-primary/40 bg-primary/10 text-primary">
                {result.info_count} info
              </Badge>
            )}
            <span className="ml-auto text-xs text-muted-foreground/60">{result.trackers_run} trackers run</span>
          </div>

          {/* Match cards */}
          {sorted.length === 0 ? (
            <p className="text-xs text-muted-foreground py-3 text-center">
              No tracker concepts detected in this transcript.
            </p>
          ) : (
            sorted.map((match, i) => {
              const cfg = severityConfig(match.severity);
              const Icon = cfg.icon;
              return (
                <div key={i} className={cn(
                  "rounded-lg border border-border/40 bg-card/40 p-3 space-y-2 border-l-2",
                  cfg.border
                )}>
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-1.5 min-w-0">
                      <Icon className={cn("h-3.5 w-3.5 shrink-0", cfg.badge.split(" ")[2])} />
                      <span className="text-xs font-semibold text-foreground truncate">{match.tracker_name}</span>
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0">
                      <ConfidencePip score={match.confidence_score} />
                      <Badge variant="outline" className={cn("text-[10px] px-1.5 py-0", cfg.badge)}>
                        {match.severity}
                      </Badge>
                    </div>
                  </div>

                  <blockquote className="rounded border-l-2 border-current/30 bg-secondary/40 px-2.5 py-1.5 text-xs italic text-muted-foreground leading-relaxed">
                    "{match.matched_text}"
                    {match.timestamp_hint && (
                      <span className="ml-2 not-italic text-muted-foreground/50">{match.timestamp_hint}</span>
                    )}
                  </blockquote>

                  <p className="text-xs text-foreground/70 leading-relaxed">{match.context_snippet}</p>
                </div>
              );
            })
          )}

          {/* Reset */}
          <button
            onClick={() => { setResult(null); setTranscript(""); }}
            className="w-full text-xs text-muted-foreground hover:text-foreground transition-colors py-1"
          >
            ↩ Analyse another transcript
          </button>
        </div>
      )}
    </div>
  );
}
