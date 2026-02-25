import { useState } from "react";
import {
  Sheet, SheetContent, SheetHeader, SheetTitle
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useToast } from "@/hooks/use-toast";
import { api } from "@/lib/api";
import {
  Radar, Zap, AlertTriangle, Copy, Check, TrendingUp,
  Users, Clock, DollarSign, ArrowRight, Flame, ChevronRight
} from "lucide-react";

// ── Types ─────────────────────────────────────────────────────────────────────

interface Signal {
  type: string;
  label: string;
  quote: string;
  speaker?: string;
  context: string;
  urgency: "high" | "medium" | "low";
  confidence: "high" | "medium" | "low";
}

interface SignalResult {
  signals: Signal[];
  overall_intent: string;
  hotness_score: number;
  hotness_rationale: string;
  recommended_action: string;
  suggested_outreach: { subject: string; opening: string };
  timing_insight: string;
  risk_flags: string[];
  deal_association: string | null;
  next_step_for_sales: string;
  analysed_at?: string;
  error?: string;
}

// ── Signal type config ─────────────────────────────────────────────────────────

const SIGNAL_CONFIG: Record<string, { label: string; icon: any; color: string }> = {
  expansion_intent:  { label: "Expansion Intent",   icon: TrendingUp,    color: "text-health-green border-health-green/40 bg-health-green/10" },
  competitor_pain:   { label: "Competitor Pain",     icon: Zap,           color: "text-health-orange border-health-orange/40 bg-health-orange/10" },
  budget_signal:     { label: "Budget Signal",       icon: DollarSign,    color: "text-primary border-primary/40 bg-primary/10" },
  timeline_signal:   { label: "Timeline Urgency",    icon: Clock,         color: "text-health-yellow border-health-yellow/40 bg-health-yellow/10" },
  stakeholder_signal:{ label: "Stakeholder Intel",   icon: Users,         color: "text-accent border-accent/40 bg-accent/10" },
  urgency_trigger:   { label: "Urgency Trigger",     icon: Flame,         color: "text-health-red border-health-red/40 bg-health-red/10" },
  referral_signal:   { label: "Referral Signal",     icon: ArrowRight,    color: "text-health-green border-health-green/40 bg-health-green/10" },
  evaluation_signal: { label: "Evaluating Vendors",  icon: ChevronRight,  color: "text-health-orange border-health-orange/40 bg-health-orange/10" },
  risk_signal:       { label: "Risk / Blocker",      icon: AlertTriangle, color: "text-health-red border-health-red/40 bg-health-red/10" },
};

function urgencyBadgeClass(u: string) {
  if (u === "high")   return "border-health-red/40 bg-health-red/10 text-health-red";
  if (u === "medium") return "border-health-yellow/40 bg-health-yellow/10 text-health-yellow";
  return "border-border/50 text-muted-foreground";
}

function intentLabel(intent: string) {
  switch (intent) {
    case "strong_buy":  return { text: "Strong Buyer",    cls: "text-health-green" };
    case "lean_buy":    return { text: "Lean Buy",        cls: "text-health-yellow" };
    case "neutral":     return { text: "Neutral",         cls: "text-muted-foreground" };
    case "lean_no":     return { text: "Lean No",         cls: "text-health-orange" };
    default:            return { text: "No Signal",       cls: "text-muted-foreground" };
  }
}

// ── Sub-component: hotness bar ─────────────────────────────────────────────────

function HotnessBar({ score }: { score: number }) {
  const color = score >= 70 ? "bg-health-green" : score >= 45 ? "bg-health-yellow" : score >= 20 ? "bg-health-orange" : "bg-health-red";
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <span className="text-xs text-muted-foreground font-medium">Buyer Hotness</span>
        <span className={`text-xl font-bold ${score >= 70 ? "text-health-green" : score >= 45 ? "text-health-yellow" : "text-health-orange"}`}>{score}</span>
      </div>
      <div className="h-2 w-full rounded-full bg-secondary">
        <div className={`h-2 rounded-full transition-all ${color}`} style={{ width: `${score}%` }} />
      </div>
    </div>
  );
}

// ── Sub-component: copy button ─────────────────────────────────────────────────

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <button onClick={copy} className="p-1.5 rounded text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors">
      {copied ? <Check className="h-3.5 w-3.5 text-health-green" /> : <Copy className="h-3.5 w-3.5" />}
    </button>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function BuyingSignalPanel({ open, onClose }: Props) {
  const { toast } = useToast();

  const [transcript,       setTranscript]       = useState("");
  const [researcherName,   setResearcherName]   = useState("");
  const [companyContext,   setCompanyContext]   = useState("");
  const [loading,          setLoading]          = useState(false);
  const [result,           setResult]           = useState<SignalResult | null>(null);
  const [activeTab,        setActiveTab]        = useState("signals");

  const runAnalysis = async (isDemo = false) => {
    if (!isDemo && transcript.trim().length < 80) {
      toast({ title: "Transcript too short", description: "Paste at least a few lines of the call transcript.", variant: "destructive" });
      return;
    }
    setLoading(true);
    setResult(null);
    try {
      const data = isDemo
        ? await api.getDemoSignals()
        : await api.detectSignals(transcript, researcherName || undefined, companyContext || undefined);
      setResult(data as SignalResult);
      setActiveTab("signals");
    } catch (e: any) {
      toast({ title: "Analysis failed", description: e.message ?? "Unknown error", variant: "destructive" });
    } finally {
      setLoading(false);
    }
  };

  const loadDemo = () => {
    setTranscript("");
    setResearcherName("Priya (Research Team)");
    setCompanyContext("GlobalRetail Ltd — Head of Operations");
    runAnalysis(true);
  };

  const signalCount = result?.signals.length ?? 0;
  const highUrgencyCount = result?.signals.filter(s => s.urgency === "high").length ?? 0;
  const intent = result ? intentLabel(result.overall_intent) : null;

  return (
    <Sheet open={open} onOpenChange={(v) => !v && onClose()}>
      <SheetContent
        side="right"
        className="w-full sm:max-w-2xl overflow-y-auto border-l border-border/50 bg-background p-0"
      >
        {/* Header */}
        <SheetHeader className="sticky top-0 z-10 border-b border-border/50 bg-background/95 backdrop-blur-sm px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-health-orange/20">
              <Radar className="h-5 w-5 text-health-orange" />
            </div>
            <div>
              <SheetTitle className="text-base font-semibold text-foreground">
                Signal Radar
              </SheetTitle>
              <p className="text-xs text-muted-foreground">
                Detect buying signals in non-sales call transcripts
              </p>
            </div>
          </div>
        </SheetHeader>

        <div className="px-6 py-5 space-y-5">

          {/* Input form */}
          {!result && (
            <div className="space-y-4">
              <div className="flex gap-2">
                <div className="flex-1 space-y-1">
                  <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Researcher / Caller</label>
                  <Input
                    value={researcherName}
                    onChange={e => setResearcherName(e.target.value)}
                    placeholder="e.g. Priya Singh"
                    className="h-9 border-border/50 bg-secondary/50 text-sm focus-visible:ring-health-orange/50"
                  />
                </div>
                <div className="flex-1 space-y-1">
                  <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Company / Context</label>
                  <Input
                    value={companyContext}
                    onChange={e => setCompanyContext(e.target.value)}
                    placeholder="e.g. Acme Corp — Product Research"
                    className="h-9 border-border/50 bg-secondary/50 text-sm focus-visible:ring-health-orange/50"
                  />
                </div>
              </div>

              <div className="space-y-1">
                <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Call Transcript</label>
                <Textarea
                  value={transcript}
                  onChange={e => setTranscript(e.target.value)}
                  placeholder={`Paste your call transcript here...\n\nExample:\nResearcher: How are you managing your pipeline today?\nInterviewee: Honestly we've been struggling with Salesforce — it's too complex for our team...`}
                  className="min-h-[280px] resize-none border-border/50 bg-secondary/50 text-sm font-mono leading-relaxed focus-visible:ring-health-orange/50"
                />
                <p className="text-xs text-muted-foreground">{transcript.length} characters</p>
              </div>

              <div className="flex gap-2">
                <Button
                  onClick={() => runAnalysis(false)}
                  disabled={loading}
                  className="flex-1 bg-health-orange hover:bg-health-orange/90 text-white font-medium gap-2"
                >
                  <Radar className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
                  {loading ? "Detecting Signals…" : "Detect Buying Signals"}
                </Button>
                <Button
                  variant="outline"
                  onClick={loadDemo}
                  disabled={loading}
                  className="border-border/50 text-muted-foreground hover:text-foreground text-sm"
                >
                  Try Demo
                </Button>
              </div>
            </div>
          )}

          {/* Loading */}
          {loading && (
            <div className="flex flex-col items-center justify-center py-16 gap-3 text-center">
              <div className="h-10 w-10 rounded-full border-2 border-health-orange/30 border-t-health-orange animate-spin" />
              <p className="text-sm font-medium text-foreground">Scanning transcript for buying signals…</p>
              <p className="text-xs text-muted-foreground">Analysing intent, urgency triggers, and stakeholder cues</p>
            </div>
          )}

          {/* Results */}
          {result && !loading && (
            <div className="space-y-5">

              {/* Summary header */}
              <div className="rounded-lg border border-border/50 bg-card/60 p-4 space-y-3">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-xs text-muted-foreground uppercase tracking-wide font-medium mb-1">
                      {result.deal_association ?? "Analysed Transcript"}
                    </p>
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-2xl font-bold text-foreground">{signalCount}</span>
                      <span className="text-sm text-muted-foreground">signal{signalCount !== 1 ? "s" : ""} found</span>
                      {highUrgencyCount > 0 && (
                        <Badge variant="outline" className="border-health-red/40 bg-health-red/10 text-health-red text-xs">
                          {highUrgencyCount} high urgency
                        </Badge>
                      )}
                      {intent && (
                        <Badge variant="outline" className={`text-xs border-current/30 bg-current/10 ${intent.cls}`}>
                          {intent.text}
                        </Badge>
                      )}
                    </div>
                    {result.hotness_rationale && (
                      <p className="text-xs text-muted-foreground mt-1">{result.hotness_rationale}</p>
                    )}
                  </div>
                  <div className="w-36 shrink-0">
                    <HotnessBar score={result.hotness_score} />
                  </div>
                </div>

                {result.recommended_action && (
                  <div className="flex items-start gap-2 pt-2 border-t border-border/30">
                    <Zap className="h-4 w-4 text-health-orange mt-0.5 shrink-0" />
                    <p className="text-sm font-medium text-foreground">{result.recommended_action}</p>
                  </div>
                )}
              </div>

              {/* Tabs */}
              <Tabs value={activeTab} onValueChange={setActiveTab}>
                <TabsList className="bg-secondary/60 border border-border/50 w-full">
                  <TabsTrigger value="signals" className="flex-1 text-xs data-[state=active]:bg-health-orange data-[state=active]:text-white">
                    Signals ({signalCount})
                  </TabsTrigger>
                  <TabsTrigger value="briefing" className="flex-1 text-xs data-[state=active]:bg-health-orange data-[state=active]:text-white">
                    Sales Briefing
                  </TabsTrigger>
                  <TabsTrigger value="outreach" className="flex-1 text-xs data-[state=active]:bg-health-orange data-[state=active]:text-white">
                    Outreach Draft
                  </TabsTrigger>
                </TabsList>

                {/* ── Signals tab ── */}
                <TabsContent value="signals" className="space-y-3 mt-4">
                  {result.signals.length === 0 ? (
                    <div className="text-center py-10 text-muted-foreground text-sm">
                      No buying signals detected in this transcript.
                    </div>
                  ) : (
                    result.signals.map((signal, i) => {
                      const cfg = SIGNAL_CONFIG[signal.type] ?? {
                        label: signal.type, icon: Zap,
                        color: "text-muted-foreground border-border/50 bg-secondary/50"
                      };
                      const Icon = cfg.icon;
                      return (
                        <div key={i} className="rounded-lg border border-border/50 bg-card/60 p-4 space-y-2">
                          <div className="flex items-start justify-between gap-2">
                            <div className="flex items-center gap-2">
                              <div className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-md border ${cfg.color}`}>
                                <Icon className="h-3.5 w-3.5" />
                              </div>
                              <span className="text-sm font-semibold text-foreground">{signal.label}</span>
                            </div>
                            <div className="flex items-center gap-1.5 shrink-0">
                              <Badge variant="outline" className={`text-xs ${urgencyBadgeClass(signal.urgency)}`}>
                                {signal.urgency}
                              </Badge>
                              <Badge variant="outline" className={`text-xs border-current/20 ${cfg.color}`}>
                                {cfg.label}
                              </Badge>
                            </div>
                          </div>

                          {/* Exact quote */}
                          <div className="flex items-start gap-2">
                            <blockquote className="flex-1 rounded-md border-l-2 border-health-orange/60 bg-secondary/40 px-3 py-2 text-xs italic text-muted-foreground leading-relaxed">
                              "{signal.quote}"
                            </blockquote>
                            <CopyButton text={signal.quote} />
                          </div>

                          {signal.speaker && (
                            <p className="text-xs text-muted-foreground/70">— {signal.speaker}</p>
                          )}
                          <p className="text-xs text-foreground/80">{signal.context}</p>
                        </div>
                      );
                    })
                  )}
                </TabsContent>

                {/* ── Briefing tab ── */}
                <TabsContent value="briefing" className="space-y-4 mt-4">
                  {result.next_step_for_sales && (
                    <div className="rounded-lg border border-health-orange/30 bg-health-orange/5 p-4 space-y-1">
                      <p className="text-xs font-medium text-health-orange uppercase tracking-wide">Next Step for Sales</p>
                      <p className="text-sm font-semibold text-foreground">{result.next_step_for_sales}</p>
                    </div>
                  )}

                  {result.timing_insight && (
                    <div className="rounded-lg border border-border/50 bg-card/60 p-4 space-y-1">
                      <div className="flex items-center gap-2">
                        <Clock className="h-4 w-4 text-primary" />
                        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Timing Insight</p>
                      </div>
                      <p className="text-sm text-foreground">{result.timing_insight}</p>
                    </div>
                  )}

                  {/* Signal type summary */}
                  {result.signals.length > 0 && (
                    <div className="rounded-lg border border-border/50 bg-card/60 p-4 space-y-3">
                      <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Signal Breakdown</p>
                      <div className="space-y-2">
                        {Object.entries(
                          result.signals.reduce((acc, s) => {
                            acc[s.type] = (acc[s.type] || 0) + 1;
                            return acc;
                          }, {} as Record<string, number>)
                        ).map(([type, count]) => {
                          const cfg = SIGNAL_CONFIG[type] ?? { label: type, icon: Zap, color: "text-muted-foreground" };
                          const Icon = cfg.icon;
                          return (
                            <div key={type} className="flex items-center justify-between text-sm">
                              <div className="flex items-center gap-2">
                                <Icon className={`h-3.5 w-3.5 ${cfg.color.split(" ")[0]}`} />
                                <span className="text-foreground/80">{cfg.label}</span>
                              </div>
                              <Badge variant="outline" className={`text-xs ${cfg.color}`}>{count}</Badge>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  {/* Risk flags */}
                  {result.risk_flags.length > 0 && (
                    <div className="rounded-lg border border-health-red/30 bg-health-red/5 p-4 space-y-2">
                      <div className="flex items-center gap-2">
                        <AlertTriangle className="h-4 w-4 text-health-red" />
                        <p className="text-xs font-medium text-health-red uppercase tracking-wide">Risk Flags</p>
                      </div>
                      <ul className="space-y-1">
                        {result.risk_flags.map((flag, i) => (
                          <li key={i} className="text-xs text-foreground/80 flex items-start gap-1.5">
                            <span className="text-health-red mt-0.5">•</span>
                            {flag}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </TabsContent>

                {/* ── Outreach tab ── */}
                <TabsContent value="outreach" className="space-y-4 mt-4">
                  {result.suggested_outreach.subject || result.suggested_outreach.opening ? (
                    <>
                      <div className="rounded-lg border border-border/50 bg-card/60 p-4 space-y-2">
                        <div className="flex items-center justify-between">
                          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Subject Line</p>
                          <CopyButton text={result.suggested_outreach.subject} />
                        </div>
                        <p className="text-sm font-semibold text-foreground">{result.suggested_outreach.subject}</p>
                      </div>

                      <div className="rounded-lg border border-border/50 bg-card/60 p-4 space-y-2">
                        <div className="flex items-center justify-between">
                          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Opening Paragraph</p>
                          <CopyButton text={result.suggested_outreach.opening} />
                        </div>
                        <p className="text-sm text-foreground leading-relaxed whitespace-pre-wrap">{result.suggested_outreach.opening}</p>
                      </div>

                      <p className="text-xs text-muted-foreground italic text-center">
                        This opening references signals naturally — personalise with your voice before sending.
                      </p>
                    </>
                  ) : (
                    <div className="text-center py-10 text-muted-foreground text-sm">
                      No outreach draft generated for this transcript.
                    </div>
                  )}
                </TabsContent>
              </Tabs>

              {/* Reset button */}
              <Button
                variant="outline"
                onClick={() => { setResult(null); setTranscript(""); }}
                className="w-full border-border/50 text-muted-foreground hover:text-foreground text-sm"
              >
                Analyse Another Transcript
              </Button>
            </div>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
