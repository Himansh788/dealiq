import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import {
  ScanSearch, AlertTriangle, AlertCircle,
  Info, Plus, ChevronDown, ChevronUp, Sparkles, Shield, Check
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select, SelectContent, SelectItem,
  SelectTrigger, SelectValue
} from "@/components/ui/select";
import { useSession } from "@/contexts/SessionContext";
import { useToast } from "@/hooks/use-toast";
import { api } from "@/lib/api";
import NavBar from "@/components/NavBar";
import AlertsDigestPanel from "@/components/AlertsDigestPanel";
import BuyingSignalPanel from "@/components/BuyingSignalPanel";
import { cn } from "@/lib/utils";

// ── Types ─────────────────────────────────────────────────────────────────────

interface Tracker {
  id: string;
  name: string;
  concept_description: string;
  severity: "info" | "warning" | "critical";
  is_default: boolean;
}

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
  analysed_at: string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function severityConfig(severity: string) {
  switch (severity) {
    case "critical": return {
      icon: AlertTriangle,
      badge: "border-health-red/40 bg-health-red/10 text-health-red",
      leftBorder: "border-l-health-red/60",
      dot: "bg-health-red",
    };
    case "warning": return {
      icon: AlertCircle,
      badge: "border-health-yellow/40 bg-health-yellow/10 text-health-yellow",
      leftBorder: "border-l-health-yellow/60",
      dot: "bg-health-yellow",
    };
    default: return {
      icon: Info,
      badge: "border-primary/40 bg-primary/10 text-primary",
      leftBorder: "border-l-primary/60",
      dot: "bg-primary",
    };
  }
}

// ── Sub-components ─────────────────────────────────────────────────────────────

function TrackerCard({ tracker }: { tracker: Tracker }) {
  const [expanded, setExpanded] = useState(false);
  const cfg = severityConfig(tracker.severity);
  return (
    <div className="rounded-lg border border-border/40 bg-card/40 p-3 space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className={cn("h-2 w-2 rounded-full shrink-0", cfg.dot)} />
          <span className="text-xs font-semibold text-foreground truncate">{tracker.name}</span>
          {tracker.is_default && (
            <span className="shrink-0 rounded-full bg-secondary/60 px-1.5 py-0 text-[10px] text-muted-foreground">
              built-in
            </span>
          )}
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          <Badge variant="outline" className={cn("text-[10px] px-1.5 py-0", cfg.badge)}>
            {tracker.severity}
          </Badge>
          <button
            onClick={() => setExpanded(v => !v)}
            className="text-muted-foreground/40 hover:text-muted-foreground"
          >
            {expanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
          </button>
        </div>
      </div>
      {expanded && (
        <p className="text-xs text-muted-foreground/80 leading-relaxed pl-4">
          {tracker.concept_description}
        </p>
      )}
    </div>
  );
}

function MatchCard({ match }: { match: TrackerMatch }) {
  const cfg = severityConfig(match.severity);
  const Icon = cfg.icon;
  const pct = Math.round(match.confidence_score * 100);
  const confColor = pct >= 85 ? "text-health-green" : pct >= 65 ? "text-health-yellow" : "text-muted-foreground";

  return (
    <div className={cn(
      "rounded-lg border border-border/40 bg-card/40 p-4 space-y-2.5 border-l-2",
      cfg.leftBorder
    )}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <Icon className={cn("h-3.5 w-3.5 shrink-0", cfg.badge.split(" ")[2])} />
          <span className="text-sm font-semibold text-foreground">{match.tracker_name}</span>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className={cn("text-xs font-medium tabular-nums", confColor)}>{pct}% conf.</span>
          <Badge variant="outline" className={cn("text-xs", cfg.badge)}>
            {match.severity}
          </Badge>
        </div>
      </div>

      <blockquote className="rounded border-l-2 border-current/20 bg-secondary/50 px-3 py-2 text-xs italic text-muted-foreground leading-relaxed">
        "{match.matched_text}"
        {match.timestamp_hint && (
          <span className="ml-2 not-italic text-muted-foreground/40 text-[10px]">{match.timestamp_hint}</span>
        )}
      </blockquote>

      <p className="text-xs text-foreground/75 leading-relaxed">{match.context_snippet}</p>
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function TrackersPage() {
  const { session } = useSession();
  const navigate    = useNavigate();
  const { toast }   = useToast();

  const [digestOpen, setDigestOpen]             = useState(false);
  const [signalPanelOpen, setSignalPanelOpen]   = useState(false);

  // Tracker library
  const [trackers, setTrackers]         = useState<Tracker[]>([]);
  const [loadingTrackers, setLoadingTrackers] = useState(true);

  // Create form
  const [showCreate, setShowCreate]     = useState(false);
  const [newName, setNewName]           = useState("");
  const [newConcept, setNewConcept]     = useState("");
  const [newSeverity, setNewSeverity]   = useState("warning");
  const [creating, setCreating]         = useState(false);

  // Analysis
  const [transcript, setTranscript]     = useState("");
  const [analyzing, setAnalyzing]       = useState(false);
  const [result, setResult]             = useState<AnalysisResult | null>(null);

  useEffect(() => {
    if (!session) { navigate("/", { replace: true }); return; }
    api.listTrackers()
      .then((data: Tracker[]) => setTrackers(data))
      .catch(() => {})
      .finally(() => setLoadingTrackers(false));
  }, [session, navigate]);

  const handleCreateTracker = async () => {
    if (!newName.trim() || !newConcept.trim()) {
      toast({ title: "Name and concept are required", variant: "destructive" });
      return;
    }
    setCreating(true);
    try {
      const created = await api.createTracker(newName.trim(), newConcept.trim(), newSeverity) as Tracker;
      setTrackers(prev => [...prev, created]);
      setNewName(""); setNewConcept(""); setNewSeverity("warning");
      setShowCreate(false);
      toast({ title: "Tracker created", description: `"${created.name}" added to your library.` });
    } catch (e: any) {
      toast({ title: "Failed to create tracker", description: e.message, variant: "destructive" });
    } finally {
      setCreating(false);
    }
  };

  const runAnalysis = async (isDemo = false) => {
    if (!isDemo && transcript.trim().length < 60) {
      toast({ title: "Transcript too short", description: "Paste at least a few lines.", variant: "destructive" });
      return;
    }
    setAnalyzing(true);
    setResult(null);
    try {
      const data = isDemo
        ? await api.getDemoTrackers()
        : await api.analyzeTranscript(transcript);
      setResult(data as AnalysisResult);
    } catch (e: any) {
      toast({ title: "Analysis failed", description: e.message ?? "Unknown error", variant: "destructive" });
    } finally {
      setAnalyzing(false);
    }
  };

  const loadDemo = () => {
    setTranscript("");
    runAnalysis(true);
  };

  const sorted = result
    ? [...result.matches].sort((a, b) => {
        const order = { critical: 0, warning: 1, info: 2 };
        return (order[a.severity] ?? 3) - (order[b.severity] ?? 3);
      })
    : [];

  const defaultTrackers  = trackers.filter(t => t.is_default);
  const customTrackers   = trackers.filter(t => !t.is_default);

  return (
    <div className="min-h-screen bg-background">

      {/* ── Header ── */}
      <NavBar
        onOpenDigest={() => setDigestOpen(true)}
        onOpenSignal={() => setSignalPanelOpen(true)}
      />

      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[320px_1fr]">

          {/* ── Left: Tracker library ── */}
          <div className="space-y-4">

            {/* Header */}
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-sm font-semibold text-foreground">Tracker Library</h2>
                <p className="text-xs text-muted-foreground/60 mt-0.5">Concept-based, not keyword-based</p>
              </div>
              <button
                onClick={() => setShowCreate(v => !v)}
                className={cn(
                  "flex items-center gap-1 text-xs font-medium transition-colors",
                  showCreate ? "text-primary" : "text-muted-foreground hover:text-foreground"
                )}
              >
                <Plus className="h-3.5 w-3.5" />
                New
              </button>
            </div>

            {/* Create form */}
            {showCreate && (
              <Card className="border-primary/30 bg-primary/5">
                <CardContent className="p-4 space-y-3">
                  <p className="text-xs font-semibold text-primary uppercase tracking-wide">Create Tracker</p>
                  <div className="space-y-2">
                    <Input
                      value={newName}
                      onChange={e => setNewName(e.target.value)}
                      placeholder="Tracker name (e.g. Legal Blocker)"
                      className="h-8 text-xs border-border/50 bg-background"
                    />
                    <Textarea
                      value={newConcept}
                      onChange={e => setNewConcept(e.target.value)}
                      placeholder="Describe the CONCEPT to detect — what situation, intent, or language pattern should trigger this tracker?"
                      className="min-h-[90px] resize-none text-xs border-border/50 bg-background leading-relaxed"
                    />
                    <Select value={newSeverity} onValueChange={setNewSeverity}>
                      <SelectTrigger className="h-8 text-xs border-border/50 bg-background">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent className="border-border/40 bg-card">
                        <SelectItem value="info">Info</SelectItem>
                        <SelectItem value="warning">Warning</SelectItem>
                        <SelectItem value="critical">Critical</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      onClick={handleCreateTracker}
                      disabled={creating}
                      className="flex-1 h-8 text-xs bg-primary hover:bg-primary/90 gap-1"
                    >
                      {creating
                        ? <><div className="h-3 w-3 rounded-full border border-white/30 border-t-white animate-spin" /> Creating…</>
                        : <><Check className="h-3 w-3" /> Create</>
                      }
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setShowCreate(false)}
                      className="h-8 text-xs text-muted-foreground"
                    >
                      Cancel
                    </Button>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Default trackers */}
            {loadingTrackers ? (
              <div className="space-y-2">
                {[...Array(6)].map((_, i) => <Skeleton key={i} className="h-10 w-full rounded-lg" />)}
              </div>
            ) : (
              <div className="space-y-2">
                <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/50 px-1">
                  Built-in · {defaultTrackers.length}
                </p>
                {defaultTrackers.map(t => <TrackerCard key={t.id} tracker={t} />)}

                {customTrackers.length > 0 && (
                  <>
                    <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/50 px-1 pt-2">
                      Custom · {customTrackers.length}
                    </p>
                    {customTrackers.map(t => <TrackerCard key={t.id} tracker={t} />)}
                  </>
                )}
              </div>
            )}

            {/* Legend */}
            <div className="rounded-lg border border-border/30 bg-secondary/20 p-3 space-y-1.5">
              <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/50">Severity</p>
              {[
                { key: "critical", label: "Critical — deal-threatening signal", color: "bg-health-red" },
                { key: "warning",  label: "Warning — friction or risk",         color: "bg-health-yellow" },
                { key: "info",     label: "Info — noteworthy, monitor",          color: "bg-primary" },
              ].map(s => (
                <div key={s.key} className="flex items-center gap-2">
                  <span className={cn("h-1.5 w-1.5 rounded-full shrink-0", s.color)} />
                  <span className="text-xs text-muted-foreground/70">{s.label}</span>
                </div>
              ))}
            </div>
          </div>

          {/* ── Right: Analysis workspace ── */}
          <div className="space-y-4">

            {/* Page description */}
            <div className="rounded-xl border border-primary/20 bg-primary/5 p-4 flex items-start gap-3">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/20">
                <Shield className="h-4 w-4 text-primary" />
              </div>
              <div>
                <p className="text-sm font-semibold text-foreground">Concept-based call analysis</p>
                <p className="text-xs text-muted-foreground/80 mt-0.5 leading-relaxed">
                  Paste any sales call transcript. Smart Trackers detect concepts — not exact keywords — using AI.
                  "Is that your best price?" fires <span className="font-medium text-foreground">Discount Pressure</span>.
                  "I'll need to loop in legal" fires <span className="font-medium text-foreground">Decision Maker Absent</span>.
                </p>
              </div>
            </div>

            {/* Transcript input */}
            {!result && !analyzing && (
              <Card className="border-border/40 bg-card/60">
                <CardContent className="p-5 space-y-4">
                  <div className="flex items-center justify-between">
                    <h3 className="text-sm font-semibold text-foreground">Paste Transcript</h3>
                    <span className="text-xs text-muted-foreground/50">{transcript.length} chars</span>
                  </div>
                  <Textarea
                    value={transcript}
                    onChange={e => setTranscript(e.target.value)}
                    placeholder={"Paste your sales call transcript here…\n\nExample:\n[00:02:14]\nRep: Here's the pricing for the Enterprise tier.\nBuyer: That seems high — is there any room to negotiate? We're also talking to Salesforce…"}
                    className="min-h-[260px] resize-none border-border/50 bg-secondary/30 text-sm font-mono leading-relaxed focus-visible:ring-primary/40"
                  />
                  <div className="flex gap-2">
                    <Button
                      onClick={() => runAnalysis(false)}
                      disabled={analyzing}
                      className="flex-1 bg-primary hover:bg-primary/90 text-white gap-2"
                    >
                      <ScanSearch className="h-4 w-4" />
                      Run All Trackers
                    </Button>
                    <Button
                      variant="outline"
                      onClick={loadDemo}
                      disabled={analyzing}
                      className="border-border/50 text-muted-foreground hover:text-foreground gap-1.5"
                    >
                      <Sparkles className="h-3.5 w-3.5" />
                      Try Demo
                    </Button>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Loading */}
            {analyzing && (
              <Card className="border-border/40 bg-card/60">
                <CardContent className="p-8 flex flex-col items-center gap-4">
                  <div className="h-10 w-10 rounded-full border-2 border-primary/30 border-t-primary animate-spin" />
                  <div className="text-center">
                    <p className="text-sm font-medium text-foreground">Running {trackers.length} trackers…</p>
                    <p className="text-xs text-muted-foreground mt-1">Detecting concepts, not just keywords</p>
                  </div>
                  <div className="space-y-2 w-full max-w-sm">
                    {[...Array(3)].map((_, i) => <Skeleton key={i} className="h-14 w-full rounded-lg" />)}
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Results */}
            {result && !analyzing && (
              <div className="space-y-4">

                {/* Summary */}
                <Card className="border-border/40 bg-card/60">
                  <CardContent className="p-4">
                    <div className="flex items-center justify-between gap-4 flex-wrap">
                      <div>
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-2xl font-black text-foreground tabular-nums">{result.total_matches}</span>
                          <span className="text-sm text-muted-foreground">concept{result.total_matches !== 1 ? "s" : ""} detected</span>
                          {result.critical_count > 0 && (
                            <Badge variant="outline" className="border-health-red/40 bg-health-red/10 text-health-red">
                              {result.critical_count} critical
                            </Badge>
                          )}
                          {result.warning_count > 0 && (
                            <Badge variant="outline" className="border-health-yellow/40 bg-health-yellow/10 text-health-yellow">
                              {result.warning_count} warning
                            </Badge>
                          )}
                          {result.info_count > 0 && (
                            <Badge variant="outline" className="border-primary/40 bg-primary/10 text-primary">
                              {result.info_count} info
                            </Badge>
                          )}
                        </div>
                        <p className="text-xs text-muted-foreground/60 mt-1">{result.trackers_run} trackers run</p>
                      </div>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => { setResult(null); setTranscript(""); }}
                        className="border-border/40 text-muted-foreground hover:text-foreground text-xs gap-1"
                      >
                        ↩ New analysis
                      </Button>
                    </div>
                  </CardContent>
                </Card>

                {/* Match cards */}
                {sorted.length === 0 ? (
                  <Card className="border-border/40 bg-card/60">
                    <CardContent className="p-8 text-center">
                      <Check className="h-8 w-8 text-health-green mx-auto mb-3" />
                      <p className="text-sm font-medium text-foreground">No tracker concepts detected</p>
                      <p className="text-xs text-muted-foreground mt-1">
                        This transcript doesn't appear to contain any of the tracked risk patterns.
                      </p>
                    </CardContent>
                  </Card>
                ) : (
                  <div className="space-y-3">
                    {sorted.map((match, i) => <MatchCard key={i} match={match} />)}
                  </div>
                )}
              </div>
            )}
          </div>

        </div>
      </main>

      <AlertsDigestPanel open={digestOpen} onClose={() => setDigestOpen(false)} />
      <BuyingSignalPanel open={signalPanelOpen} onClose={() => setSignalPanelOpen(false)} />
    </div>
  );
}
