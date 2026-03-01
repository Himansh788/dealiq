import { useState, useRef, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/hooks/use-toast";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  MessageSquare,
  Sparkles,
  Send,
  Copy,
  RefreshCw,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  CheckCircle,
  FileText,
  Mail,
  BarChart3,
  ArrowRight,
  User,
} from "lucide-react";

// ── Types ─────────────────────────────────────────────────────────────────────

interface QAMessage {
  id: string;
  question: string;
  answer: string;
  sources: string[];
  confidence: "high" | "medium" | "low";
  risks: string[];
  nextStep: string | null;
  loadingMs: number;
}

interface MeddicElement {
  status: "strong" | "partial" | "missing" | "unknown";
  detail: string;
  evidence: string;
  identified?: boolean;
  name?: string | null;
  criteria_list?: string[];
  steps_identified?: string[];
  timeline?: string | null;
  pain_points?: string[];
}

interface MeddicResult {
  metrics: MeddicElement;
  economic_buyer: MeddicElement;
  decision_criteria: MeddicElement;
  decision_process: MeddicElement;
  identify_pain: MeddicElement;
  champion: MeddicElement;
  overall_score: "strong" | "moderate" | "weak";
  gaps: string[];
  recommended_questions_for_next_call: string[];
}

interface BriefResult {
  snapshot: string;
  timeline: Array<{ date: string; event: string; source: string }>;
  current_status: string;
  stakeholders: Array<{ name: string; role: string; engagement: string; last_contact: string }>;
  risks: Array<{ risk: string; severity: "high" | "medium" | "low"; evidence: string }>;
  actions: Array<{ priority: number; action: string; reason: string }>;
}

interface FollowUpEmailResult {
  subject: string;
  body: string;
  commitments_included: string[];
  next_step: string;
  warnings: string[];
  health_impact: string;
}

type Tab = "qa" | "meddic" | "brief" | "email";

// ── Helpers ───────────────────────────────────────────────────────────────────

const CONFIDENCE_STYLES: Record<string, string> = {
  high:   "border-health-green/30 bg-health-green/10 text-health-green",
  medium: "border-health-yellow/30 bg-health-yellow/10 text-health-yellow",
  low:    "border-muted-foreground/30 bg-secondary/50 text-muted-foreground",
};

const MEDDIC_STATUS_STYLES: Record<string, string> = {
  strong:  "border-health-green/40 bg-health-green/10 text-health-green",
  partial: "border-health-yellow/40 bg-health-yellow/10 text-health-yellow",
  missing: "border-health-red/40 bg-health-red/10 text-health-red",
  unknown: "border-border/40 bg-secondary/30 text-muted-foreground",
};

const SEVERITY_STYLES: Record<string, string> = {
  high:   "border-health-red/30 bg-health-red/5 text-health-red",
  medium: "border-health-orange/30 bg-health-orange/5 text-health-orange",
  low:    "border-border/30 bg-secondary/30 text-muted-foreground",
};

const ENGAGEMENT_STYLES: Record<string, string> = {
  active:      "text-health-green",
  quiet:       "text-health-yellow",
  disengaged:  "text-health-red",
};

const MEDDIC_LABELS: Record<string, string> = {
  metrics:           "Metrics",
  economic_buyer:    "Economic Buyer",
  decision_criteria: "Decision Criteria",
  decision_process:  "Decision Process",
  identify_pain:     "Identify Pain",
  champion:          "Champion",
};

function shortId(): string {
  return Math.random().toString(36).slice(2, 8);
}

function sourceBadgeLabel(src: string): string {
  if (src.startsWith("email_")) return `Email ${src.replace("email_", "")}`;
  if (src.startsWith("transcript_")) return `Transcript ${src.replace("transcript_", "")}`;
  return src;
}

// ── Sub-components ────────────────────────────────────────────────────────────

function TabButton({ active, onClick, icon: Icon, label }: {
  active: boolean;
  onClick: () => void;
  icon: React.ElementType;
  label: string;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "flex flex-1 items-center justify-center gap-1.5 rounded-md px-2 py-2 text-xs font-medium transition-colors",
        active
          ? "bg-background text-foreground shadow-sm"
          : "text-muted-foreground hover:text-foreground"
      )}
    >
      <Icon className="h-3.5 w-3.5" />
      <span className="hidden sm:inline">{label}</span>
    </button>
  );
}

function PresetPill({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="rounded-full border border-border/40 bg-secondary/40 px-3 py-1 text-xs text-muted-foreground transition-colors hover:border-primary/40 hover:bg-primary/10 hover:text-primary whitespace-nowrap"
    >
      {label}
    </button>
  );
}

function QAMessageCard({ msg }: { msg: QAMessage }) {
  const { toast } = useToast();

  return (
    <div className="space-y-2">
      {/* Question bubble */}
      <div className="flex items-start justify-end gap-2">
        <div className="max-w-[85%] rounded-xl rounded-tr-sm bg-primary/15 px-3 py-2">
          <p className="text-xs text-foreground">{msg.question}</p>
        </div>
        <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-secondary/60 mt-0.5">
          <User className="h-3 w-3 text-muted-foreground" />
        </div>
      </div>

      {/* Answer bubble */}
      <div className="flex items-start gap-2">
        <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-violet-500/20 mt-0.5">
          <Sparkles className="h-3 w-3 text-violet-400" />
        </div>
        <div className="flex-1 min-w-0 space-y-2">
          <Card className="border-border/40 bg-card/60">
            <CardContent className="p-3 space-y-2.5">
              {/* Answer text */}
              <p className="text-sm text-foreground leading-relaxed whitespace-pre-wrap">{msg.answer}</p>

              {/* Sources */}
              {msg.sources.length > 0 && (
                <div className="flex flex-wrap gap-1 pt-1 border-t border-border/30">
                  {msg.sources.map((src, i) => (
                    <Badge key={i} variant="outline" className="text-[10px] border-border/40 text-muted-foreground font-normal">
                      {sourceBadgeLabel(src)}
                    </Badge>
                  ))}
                </div>
              )}

              {/* Risks */}
              {msg.risks.length > 0 && (
                <div className="space-y-1">
                  {msg.risks.map((r, i) => (
                    <div key={i} className="flex items-start gap-1.5 rounded-md border border-health-red/20 bg-health-red/5 px-2 py-1.5">
                      <AlertTriangle className="h-3 w-3 shrink-0 text-health-red mt-0.5" />
                      <p className="text-[11px] text-health-red">{r}</p>
                    </div>
                  ))}
                </div>
              )}

              {/* Suggested next step */}
              {msg.nextStep && (
                <div className="flex items-start gap-1.5 rounded-md border border-primary/20 bg-primary/5 px-2 py-1.5">
                  <ArrowRight className="h-3 w-3 shrink-0 text-primary mt-0.5" />
                  <p className="text-[11px] text-foreground">
                    <span className="font-medium text-primary">Next: </span>{msg.nextStep}
                  </p>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Footer row */}
          <div className="flex items-center gap-2 pl-1">
            <Badge variant="outline" className={cn("text-[10px] capitalize", CONFIDENCE_STYLES[msg.confidence])}>
              {msg.confidence} confidence
            </Badge>
            <span className="text-[10px] text-muted-foreground/60">{msg.loadingMs}ms</span>
            <Button
              variant="ghost"
              size="sm"
              className="ml-auto h-5 px-1.5 text-[10px] text-muted-foreground"
              onClick={() => {
                navigator.clipboard.writeText(msg.answer);
                toast({ title: "Answer copied" });
              }}
            >
              <Copy className="mr-1 h-2.5 w-2.5" />
              Copy
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

function MeddicCard({ label, element, isOpen, onToggle }: {
  label: string;
  element: MeddicElement;
  isOpen: boolean;
  onToggle: () => void;
}) {
  const statusStyle = MEDDIC_STATUS_STYLES[element.status] ?? MEDDIC_STATUS_STYLES.unknown;
  const statusLabel = element.status.charAt(0).toUpperCase() + element.status.slice(1);

  return (
    <div className={cn("rounded-lg border px-3 py-2.5 transition-colors", statusStyle)}>
      <button className="flex w-full items-center justify-between gap-2 text-left" onClick={onToggle}>
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-xs font-semibold truncate">{label}</span>
          <Badge variant="outline" className={cn("shrink-0 text-[10px] capitalize border-current/30", statusStyle)}>
            {statusLabel}
          </Badge>
        </div>
        {isOpen ? <ChevronUp className="h-3.5 w-3.5 shrink-0 opacity-60" /> : <ChevronDown className="h-3.5 w-3.5 shrink-0 opacity-60" />}
      </button>

      {isOpen && (
        <div className="mt-2.5 space-y-2 border-t border-current/20 pt-2.5">
          {element.detail && (
            <p className="text-xs leading-relaxed">{element.detail}</p>
          )}

          {/* Name (economic buyer / champion) */}
          {element.name && (
            <p className="text-xs font-medium">
              <span className="opacity-70">Identified: </span>{element.name}
            </p>
          )}

          {/* Lists */}
          {element.criteria_list && element.criteria_list.length > 0 && (
            <ul className="space-y-0.5">
              {element.criteria_list.map((c, i) => (
                <li key={i} className="flex items-start gap-1.5 text-xs">
                  <span className="mt-1 h-1 w-1 shrink-0 rounded-full bg-current opacity-60" />
                  {c}
                </li>
              ))}
            </ul>
          )}

          {element.steps_identified && element.steps_identified.length > 0 && (
            <ul className="space-y-0.5">
              {element.steps_identified.map((s, i) => (
                <li key={i} className="flex items-start gap-1.5 text-xs">
                  <span className="mt-1 h-1 w-1 shrink-0 rounded-full bg-current opacity-60" />
                  {s}
                </li>
              ))}
            </ul>
          )}

          {element.pain_points && element.pain_points.length > 0 && (
            <ul className="space-y-0.5">
              {element.pain_points.map((p, i) => (
                <li key={i} className="flex items-start gap-1.5 text-xs">
                  <span className="mt-1 h-1 w-1 shrink-0 rounded-full bg-current opacity-60" />
                  {p}
                </li>
              ))}
            </ul>
          )}

          {element.timeline && (
            <p className="text-xs opacity-80">
              <span className="font-medium">Timeline: </span>{element.timeline}
            </p>
          )}

          {/* Evidence quote */}
          {element.evidence && (
            <div className="rounded-md border border-current/20 bg-background/20 px-2.5 py-1.5">
              <p className="text-[11px] italic opacity-80">"{element.evidence}"</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Main Panel ────────────────────────────────────────────────────────────────

export default function AskDealIQPanel({ dealId, dealName }: { dealId: string; dealName: string }) {
  const [tab, setTab] = useState<Tab>("qa");

  // Q&A state
  const [messages, setMessages] = useState<QAMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [loadingQA, setLoadingQA] = useState(false);
  const [presets, setPresets] = useState<Record<string, string[]>>({});
  const [activePresetCategory, setActivePresetCategory] = useState<string>("deal_prep");
  const chatBottomRef = useRef<HTMLDivElement>(null);

  // MEDDIC state
  const [meddic, setMeddic] = useState<MeddicResult | null>(null);
  const [loadingMeddic, setLoadingMeddic] = useState(false);
  const [openMeddicKeys, setOpenMeddicKeys] = useState<Set<string>>(new Set());

  // Brief state
  const [brief, setBrief] = useState<BriefResult | null>(null);
  const [loadingBrief, setLoadingBrief] = useState(false);

  // Follow-up email state
  const [followUp, setFollowUp] = useState<FollowUpEmailResult | null>(null);
  const [loadingFollowUp, setLoadingFollowUp] = useState(false);

  const { toast } = useToast();

  // Load presets once on mount
  useEffect(() => {
    api.getAskPresets()
      .then(setPresets)
      .catch(() => {/* non-critical */});
  }, []);

  // Scroll chat to bottom when a new message arrives
  useEffect(() => {
    chatBottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const copyText = (text: string, label = "Copied") => {
    navigator.clipboard.writeText(text);
    toast({ title: label });
  };

  // ── Q&A ────────────────────────────────────────────────────────────────────

  const handleAsk = async (q: string) => {
    const trimmed = q.trim();
    if (!trimmed || loadingQA) return;
    setQuestion("");
    setLoadingQA(true);
    const start = Date.now();
    try {
      const data = await api.askDeal(dealId, trimmed);
      setMessages(prev => [...prev, {
        id: shortId(),
        question: trimmed,
        answer: data.answer ?? "No answer returned.",
        sources: data.sources_used ?? [],
        confidence: data.confidence ?? "medium",
        risks: data.deal_risks_detected ?? [],
        nextStep: data.suggested_next_step ?? null,
        loadingMs: data.processing_time_ms ?? (Date.now() - start),
      }]);
    } catch (err: any) {
      toast({ title: "Error", description: err.message, variant: "destructive" });
    } finally {
      setLoadingQA(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleAsk(question);
    }
  };

  // ── MEDDIC ─────────────────────────────────────────────────────────────────

  const handleMeddic = async () => {
    setLoadingMeddic(true);
    setMeddic(null);
    try {
      const data = await api.askMeddic(dealId);
      if (data.error) throw new Error(data.error);
      setMeddic(data);
      // Open any missing elements by default
      const missing = new Set<string>();
      const keys = ["metrics", "economic_buyer", "decision_criteria", "decision_process", "identify_pain", "champion"];
      keys.forEach(k => {
        const el = data[k as keyof MeddicResult] as MeddicElement | undefined;
        if (el && (el.status === "missing" || el.status === "partial")) missing.add(k);
      });
      setOpenMeddicKeys(missing);
    } catch (err: any) {
      toast({ title: "MEDDIC failed", description: err.message, variant: "destructive" });
    } finally {
      setLoadingMeddic(false);
    }
  };

  const toggleMeddicKey = (key: string) => {
    setOpenMeddicKeys(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  // ── Brief ──────────────────────────────────────────────────────────────────

  const handleBrief = async () => {
    setLoadingBrief(true);
    setBrief(null);
    try {
      const data = await api.askBrief(dealId);
      if (data.error) throw new Error(data.error);
      setBrief(data);
    } catch (err: any) {
      toast({ title: "Brief failed", description: err.message, variant: "destructive" });
    } finally {
      setLoadingBrief(false);
    }
  };

  // ── Follow-up email ────────────────────────────────────────────────────────

  const handleFollowUp = async () => {
    setLoadingFollowUp(true);
    setFollowUp(null);
    try {
      const data = await api.askFollowUpEmail(dealId);
      if (data.error) throw new Error(data.error);
      setFollowUp(data);
    } catch (err: any) {
      toast({ title: "Email generation failed", description: err.message, variant: "destructive" });
    } finally {
      setLoadingFollowUp(false);
    }
  };

  const MEDDIC_KEYS = ["metrics", "economic_buyer", "decision_criteria", "decision_process", "identify_pain", "champion"] as const;

  const overallScoreStyle = meddic
    ? meddic.overall_score === "strong" ? "text-health-green"
    : meddic.overall_score === "moderate" ? "text-health-yellow"
    : "text-health-red"
    : "";

  return (
    <div className="space-y-3 pb-4">

      {/* Header */}
      <div className="flex items-center gap-2">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-violet-500/20">
          <Sparkles className="h-4 w-4 text-violet-400" />
        </div>
        <div>
          <p className="text-sm font-semibold text-foreground">Ask DealIQ</p>
          <p className="text-xs text-muted-foreground">AI Q&A on {dealName}</p>
        </div>
      </div>

      {/* Tab bar */}
      <div className="grid grid-cols-4 gap-0.5 rounded-lg bg-secondary/50 p-0.5">
        <TabButton active={tab === "qa"}     onClick={() => setTab("qa")}     icon={MessageSquare} label="Q&A" />
        <TabButton active={tab === "meddic"} onClick={() => setTab("meddic")} icon={BarChart3}     label="MEDDIC" />
        <TabButton active={tab === "brief"}  onClick={() => setTab("brief")}  icon={FileText}      label="Brief" />
        <TabButton active={tab === "email"}  onClick={() => setTab("email")}  icon={Mail}          label="Follow-up" />
      </div>

      {/* ── Q&A Tab ──────────────────────────────────────────────────────────── */}
      {tab === "qa" && (
        <div className="space-y-3">

          {/* Preset category pills */}
          {Object.keys(presets).length > 0 && (
            <div className="space-y-2">
              <div className="flex items-center gap-1.5">
                {Object.keys(presets).map(cat => (
                  <button
                    key={cat}
                    onClick={() => setActivePresetCategory(cat)}
                    className={cn(
                      "rounded-full border px-2.5 py-0.5 text-[10px] font-medium transition-colors",
                      activePresetCategory === cat
                        ? "border-violet-500/50 bg-violet-500/15 text-violet-400"
                        : "border-border/40 bg-secondary/40 text-muted-foreground hover:text-foreground"
                    )}
                  >
                    {cat.replace("_", " ")}
                  </button>
                ))}
              </div>
              <div className="flex gap-1.5 overflow-x-auto pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
                {(presets[activePresetCategory] ?? []).map((q, i) => (
                  <PresetPill key={i} label={q} onClick={() => handleAsk(q)} />
                ))}
              </div>
            </div>
          )}

          {/* Chat history */}
          {messages.length > 0 && (
            <div className="space-y-4 max-h-[500px] overflow-y-auto rounded-lg border border-border/30 bg-secondary/20 p-3">
              {messages.map(msg => (
                <QAMessageCard key={msg.id} msg={msg} />
              ))}
              {loadingQA && (
                <div className="flex items-start gap-2">
                  <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-violet-500/20">
                    <Sparkles className="h-3 w-3 text-violet-400 animate-pulse" />
                  </div>
                  <div className="flex-1 space-y-2 pt-0.5">
                    <Skeleton className="h-3 w-3/4" />
                    <Skeleton className="h-3 w-full" />
                    <Skeleton className="h-3 w-1/2" />
                  </div>
                </div>
              )}
              <div ref={chatBottomRef} />
            </div>
          )}

          {/* Input */}
          <div className="space-y-2">
            {messages.length === 0 && !loadingQA && (
              <p className="text-xs text-muted-foreground">
                Ask anything — pain points, budget, timeline, competitors, stakeholders.
              </p>
            )}
            <div className="flex gap-2">
              <Textarea
                value={question}
                onChange={e => setQuestion(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask anything about this deal..."
                className="min-h-[72px] resize-none border-border/50 bg-secondary/50 text-sm"
                disabled={loadingQA}
              />
            </div>
            <div className="flex items-center gap-2">
              <Button
                className="flex-1 bg-violet-600 hover:bg-violet-500 font-semibold"
                onClick={() => handleAsk(question)}
                disabled={!question.trim() || loadingQA}
              >
                <Send className="mr-2 h-3.5 w-3.5" />
                {loadingQA ? "Thinking..." : "Ask DealIQ"}
              </Button>
              {messages.length > 0 && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-xs text-muted-foreground"
                  onClick={() => setMessages([])}
                >
                  <RefreshCw className="mr-1 h-3 w-3" />
                  Clear
                </Button>
              )}
            </div>
            <p className="text-[10px] text-muted-foreground/60">Enter to send · Shift+Enter for new line</p>
          </div>
        </div>
      )}

      {/* ── MEDDIC Tab ───────────────────────────────────────────────────────── */}
      {tab === "meddic" && (
        <div className="space-y-3">
          {!meddic && !loadingMeddic && (
            <Card className="border-border/50 bg-secondary/20">
              <CardContent className="p-4 space-y-3">
                <p className="text-xs text-muted-foreground leading-relaxed">
                  AI will analyse the most recent call transcript using the{" "}
                  <span className="font-semibold text-foreground">MEDDIC</span> framework —
                  Metrics, Economic Buyer, Decision Criteria, Decision Process, Identify Pain, Champion.
                  Each element is rated and backed by transcript evidence.
                </p>
                <Button
                  className="w-full bg-violet-600 hover:bg-violet-500 font-semibold"
                  onClick={handleMeddic}
                >
                  <BarChart3 className="mr-2 h-4 w-4" />
                  Run MEDDIC Analysis
                </Button>
              </CardContent>
            </Card>
          )}

          {loadingMeddic && (
            <div className="space-y-3">
              <p className="text-xs text-center text-muted-foreground animate-pulse">
                Analysing call transcript with MEDDIC framework...
              </p>
              <div className="grid grid-cols-2 gap-2">
                {MEDDIC_KEYS.map(k => (
                  <Skeleton key={k} className="h-16 w-full rounded-lg" />
                ))}
              </div>
            </div>
          )}

          {meddic && !loadingMeddic && (
            <div className="space-y-3">
              {/* Overall score */}
              <div className="flex items-center justify-between rounded-lg border border-border/40 bg-secondary/30 px-3 py-2">
                <span className="text-xs font-semibold text-foreground">Overall MEDDIC Quality</span>
                <div className="flex items-center gap-2">
                  <span className={cn("text-sm font-bold capitalize", overallScoreStyle)}>
                    {meddic.overall_score}
                  </span>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 text-[10px] text-muted-foreground px-2"
                    onClick={handleMeddic}
                  >
                    <RefreshCw className="mr-1 h-2.5 w-2.5" />
                    Re-run
                  </Button>
                </div>
              </div>

              {/* 6 MEDDIC elements */}
              <div className="space-y-1.5">
                {MEDDIC_KEYS.map(key => {
                  const el = meddic[key] as MeddicElement;
                  if (!el) return null;
                  return (
                    <MeddicCard
                      key={key}
                      label={MEDDIC_LABELS[key]}
                      element={el}
                      isOpen={openMeddicKeys.has(key)}
                      onToggle={() => toggleMeddicKey(key)}
                    />
                  );
                })}
              </div>

              {/* Gaps */}
              {meddic.gaps.length > 0 && (
                <div className="space-y-1.5">
                  <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Gaps to address</p>
                  {meddic.gaps.map((gap, i) => (
                    <div key={i} className="flex items-start gap-2 rounded-md border border-health-orange/20 bg-health-orange/5 px-2.5 py-1.5">
                      <AlertTriangle className="h-3 w-3 shrink-0 text-health-orange mt-0.5" />
                      <p className="text-xs text-foreground">{gap}</p>
                    </div>
                  ))}
                </div>
              )}

              {/* Questions for next call */}
              {meddic.recommended_questions_for_next_call.length > 0 && (
                <div className="space-y-1.5">
                  <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Ask on next call</p>
                  {meddic.recommended_questions_for_next_call.map((q, i) => (
                    <div key={i} className="flex items-start gap-2 rounded-md border border-border/30 bg-secondary/30 px-2.5 py-1.5">
                      <span className="text-xs font-bold text-primary shrink-0 mt-px">{i + 1}.</span>
                      <p className="text-xs text-foreground italic">"{q}"</p>
                    </div>
                  ))}
                  <Button
                    variant="outline"
                    size="sm"
                    className="w-full text-xs border-border/50 mt-1"
                    onClick={() => copyText(
                      meddic.recommended_questions_for_next_call.map((q, i) => `${i + 1}. "${q}"`).join("\n"),
                      "Questions copied"
                    )}
                  >
                    <Copy className="mr-1.5 h-3 w-3" />
                    Copy all questions
                  </Button>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* ── Brief Tab ────────────────────────────────────────────────────────── */}
      {tab === "brief" && (
        <div className="space-y-3">
          {!brief && !loadingBrief && (
            <Card className="border-border/50 bg-secondary/20">
              <CardContent className="p-4 space-y-3">
                <p className="text-xs text-muted-foreground leading-relaxed">
                  Generate a comprehensive deal brief — snapshot, recent timeline, stakeholder map,
                  risks, and prioritised actions. Built from emails, transcripts, and CRM data.
                </p>
                <Button
                  className="w-full bg-violet-600 hover:bg-violet-500 font-semibold"
                  onClick={handleBrief}
                >
                  <FileText className="mr-2 h-4 w-4" />
                  Generate Deal Brief
                </Button>
              </CardContent>
            </Card>
          )}

          {loadingBrief && (
            <div className="space-y-3">
              <p className="text-xs text-center text-muted-foreground animate-pulse">
                Synthesising deal brief from all available data...
              </p>
              {[...Array(5)].map((_, i) => <Skeleton key={i} className="h-16 w-full" />)}
            </div>
          )}

          {brief && !loadingBrief && (
            <div className="space-y-3">
              {/* Snapshot */}
              <div className="rounded-lg border border-violet-500/30 bg-violet-500/10 px-3 py-2.5">
                <p className="text-xs font-semibold text-violet-400 uppercase tracking-wider mb-1">Snapshot</p>
                <p className="text-sm text-foreground leading-relaxed">{brief.snapshot}</p>
              </div>

              {/* Current status */}
              <div className="rounded-lg border border-border/40 bg-secondary/30 px-3 py-2.5">
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1">Current Status</p>
                <p className="text-sm text-foreground leading-relaxed">{brief.current_status}</p>
              </div>

              {/* Timeline */}
              {brief.timeline.length > 0 && (
                <div className="space-y-1.5">
                  <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">What Happened</p>
                  <div className="relative">
                    <div className="absolute left-[9px] top-2 bottom-2 w-px bg-border/30" />
                    <div className="space-y-2 pl-5">
                      {brief.timeline.map((item, i) => (
                        <div key={i} className="relative">
                          <span className="absolute -left-5 top-1.5 h-2 w-2 rounded-full bg-border/60" />
                          <p className="text-[10px] text-muted-foreground tabular-nums">{item.date} · {item.source}</p>
                          <p className="text-xs text-foreground leading-relaxed">{item.event}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {/* Stakeholders */}
              {brief.stakeholders.length > 0 && (
                <div className="space-y-1.5">
                  <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Stakeholders</p>
                  {brief.stakeholders.map((s, i) => (
                    <div key={i} className="flex items-start justify-between gap-2 rounded-lg border border-border/30 bg-secondary/20 px-3 py-2">
                      <div>
                        <p className="text-xs font-semibold text-foreground">{s.name}</p>
                        <p className="text-[10px] text-muted-foreground">{s.role}</p>
                        {s.last_contact && (
                          <p className="text-[10px] text-muted-foreground/60">Last: {s.last_contact}</p>
                        )}
                      </div>
                      <span className={cn("text-[10px] font-semibold capitalize mt-0.5", ENGAGEMENT_STYLES[s.engagement] ?? "text-muted-foreground")}>
                        {s.engagement}
                      </span>
                    </div>
                  ))}
                </div>
              )}

              {/* Risks */}
              {brief.risks.length > 0 && (
                <div className="space-y-1.5">
                  <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Risks & Red Flags</p>
                  {brief.risks.map((r, i) => (
                    <div key={i} className={cn("rounded-lg border px-3 py-2", SEVERITY_STYLES[r.severity])}>
                      <div className="flex items-start gap-2">
                        <AlertTriangle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
                        <div>
                          <p className="text-xs font-semibold">{r.risk}</p>
                          {r.evidence && (
                            <p className="text-[11px] italic opacity-80 mt-0.5">"{r.evidence}"</p>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Actions */}
              {brief.actions.length > 0 && (
                <div className="space-y-1.5">
                  <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Recommended Actions</p>
                  {brief.actions.map((a, i) => (
                    <div key={i} className="flex items-start gap-2.5 rounded-lg border border-primary/20 bg-primary/5 px-3 py-2">
                      <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary/20 text-[10px] font-bold text-primary">
                        {a.priority}
                      </span>
                      <div>
                        <p className="text-xs font-semibold text-foreground">{a.action}</p>
                        <p className="text-[11px] text-muted-foreground mt-0.5">{a.reason}</p>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              <div className="flex gap-2 pt-1">
                <Button
                  variant="outline"
                  size="sm"
                  className="flex-1 text-xs border-border/50"
                  onClick={() => {
                    const text = [
                      `DEAL BRIEF: ${dealName}`,
                      `\nSNAPSHOT\n${brief.snapshot}`,
                      `\nSTATUS\n${brief.current_status}`,
                      `\nRISKS\n${brief.risks.map(r => `• [${r.severity.toUpperCase()}] ${r.risk}`).join("\n")}`,
                      `\nACTIONS\n${brief.actions.map(a => `${a.priority}. ${a.action}`).join("\n")}`,
                    ].join("\n");
                    copyText(text, "Brief copied");
                  }}
                >
                  <Copy className="mr-1.5 h-3 w-3" />
                  Copy brief
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-xs text-muted-foreground"
                  onClick={handleBrief}
                >
                  <RefreshCw className="mr-1 h-3 w-3" />
                  Refresh
                </Button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Follow-up Email Tab ───────────────────────────────────────────────── */}
      {tab === "email" && (
        <div className="space-y-3">
          {!followUp && !loadingFollowUp && (
            <Card className="border-border/50 bg-secondary/20">
              <CardContent className="p-4 space-y-3">
                <p className="text-xs text-muted-foreground leading-relaxed">
                  AI will draft a follow-up email based on the most recent call transcript —
                  matching your tone, capturing all commitments, and proposing a specific next step.
                </p>
                <Button
                  className="w-full bg-violet-600 hover:bg-violet-500 font-semibold"
                  onClick={handleFollowUp}
                >
                  <Mail className="mr-2 h-4 w-4" />
                  Generate Follow-up Email
                </Button>
              </CardContent>
            </Card>
          )}

          {loadingFollowUp && (
            <div className="space-y-3">
              <p className="text-xs text-center text-muted-foreground animate-pulse">
                Drafting follow-up based on call transcript...
              </p>
              {[...Array(4)].map((_, i) => <Skeleton key={i} className="h-12 w-full" />)}
            </div>
          )}

          {followUp && !loadingFollowUp && (
            <div className="space-y-3">
              {/* Warnings */}
              {followUp.warnings.length > 0 && (
                <div className="space-y-1">
                  {followUp.warnings.map((w, i) => (
                    <div key={i} className="flex items-start gap-2 rounded-md border border-health-orange/30 bg-health-orange/5 px-2.5 py-1.5">
                      <AlertTriangle className="h-3 w-3 shrink-0 text-health-orange mt-0.5" />
                      <p className="text-[11px] text-health-orange">{w}</p>
                    </div>
                  ))}
                </div>
              )}

              {/* Subject */}
              <div className="space-y-1">
                <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Subject</p>
                <div className="flex items-center gap-2 rounded-lg border border-border/40 bg-secondary/30 px-3 py-2">
                  <p className="flex-1 text-sm font-medium text-foreground">{followUp.subject}</p>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 px-1.5 text-[10px] text-muted-foreground"
                    onClick={() => copyText(followUp.subject)}
                  >
                    <Copy className="h-3 w-3" />
                  </Button>
                </div>
              </div>

              {/* Body */}
              <div className="space-y-1">
                <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Body</p>
                <div className="relative rounded-lg border border-border/40 bg-secondary/20 p-3">
                  <pre className="whitespace-pre-wrap text-sm text-foreground font-sans leading-relaxed">
                    {followUp.body}
                  </pre>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="absolute top-2 right-2 h-6 px-1.5 text-[10px] text-muted-foreground"
                    onClick={() => copyText(followUp.body)}
                  >
                    <Copy className="h-3 w-3" />
                  </Button>
                </div>
              </div>

              {/* Commitments */}
              {followUp.commitments_included.length > 0 && (
                <div className="space-y-1">
                  <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Commitments covered</p>
                  <div className="space-y-1">
                    {followUp.commitments_included.map((c, i) => (
                      <div key={i} className="flex items-center gap-1.5 text-xs text-muted-foreground">
                        <CheckCircle className="h-3 w-3 shrink-0 text-health-green" />
                        {c}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Next step */}
              {followUp.next_step && (
                <div className="flex items-start gap-2 rounded-md border border-primary/20 bg-primary/5 px-2.5 py-2">
                  <ArrowRight className="h-3.5 w-3.5 shrink-0 text-primary mt-0.5" />
                  <p className="text-xs text-foreground">
                    <span className="font-medium text-primary">Next step: </span>
                    {followUp.next_step}
                  </p>
                </div>
              )}

              {/* Health impact */}
              {followUp.health_impact && (
                <p className="text-[11px] text-muted-foreground px-0.5">{followUp.health_impact}</p>
              )}

              {/* Actions */}
              <div className="flex gap-2">
                <Button
                  className="flex-1 font-semibold"
                  variant="outline"
                  onClick={() =>
                    copyText(
                      `Subject: ${followUp.subject}\n\n${followUp.body}`,
                      "Full email copied"
                    )
                  }
                >
                  <Copy className="mr-2 h-3.5 w-3.5" />
                  Copy full email
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-xs text-muted-foreground"
                  onClick={handleFollowUp}
                >
                  <RefreshCw className="mr-1 h-3 w-3" />
                  Regenerate
                </Button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
