import { useState, useEffect, useCallback, useRef } from "react";
import { Sheet, SheetContent, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import {
  Brain, Clock, Phone, Activity, GitMerge, Layers, ScanSearch,
  GraduationCap, Zap, Sparkles, Trophy, Loader2, Check, X, Users2, AlertTriangle, ArrowRight,
} from "lucide-react";
import BattleCardPanel from "./deal/BattleCardPanel";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import { useToast } from "@/hooks/use-toast";
import HealthBreakdown from "./deal/HealthBreakdown";
import AckSection from "./deal/AckSection";
import MismatchChecker from "./deal/MismatchChecker";
import DealTimeline from "./deal/DealTimeline";
import AIRepPanel from "./deal/AIRepPanel";
import CallBriefPanel from "./deal/CallBriefPanel";
import TrackerPanel from "./deal/TrackerPanel";
import CoachingPanel from "./deal/CoachingPanel";
import ActivityFeedPanel from "./deal/ActivityFeedPanel";
import AskDealIQPanel from "./deal/AskDealIQPanel";
import MarkOutcomeSection from "./deal/MarkOutcomeSection";
import ContactsPanel from "./deal/ContactsPanel";

type PanelTab = "Overview" | "Battle Card";

interface Props {
  dealId: string | null;
  dealName: string;
  repName?: string;
  stage?: string;
  amount?: number;
  closingDate?: string;
  healthScore?: number;
  healthLabel?: string;
  onClose: () => void;
  initialSection?: string;
  initialTab?: PanelTab;
  onDealUpdated?: (field: string, value: string | number) => void;
}

function formatCurrency(val: number): string {
  if (val >= 1_000_000) return `$${(val / 1_000_000).toFixed(1)}M`;
  if (val >= 1_000) return `$${Math.round(val / 1_000)}K`;
  return `$${val}`;
}

function scoreColor(score: number) {
  if (score >= 75) return "text-emerald-500";
  if (score >= 50) return "text-amber-500";
  return "text-rose-500";
}

function scoreRingColor(score: number) {
  if (score >= 75) return "stroke-emerald-500";
  if (score >= 50) return "stroke-amber-500";
  return "stroke-rose-500";
}

function healthSummary(score: number, label?: string): string {
  if (score >= 75) return "This deal is on track. Momentum is strong and key signals are healthy.";
  if (score >= 50) return "Deal needs attention. One or more signals indicate risk — review timeline and next steps.";
  if (score >= 25) return "High risk. Multiple warning signals detected. Immediate action recommended.";
  return "Deal is stalled. No recent activity and critical signals are failing. Consider escalation or kill.";
}

function stagePillClass(stage: string): string {
  const s = stage.toLowerCase();
  if (s.includes("discovery")) return "bg-sky-500/10 text-sky-400 border-sky-500/20";
  if (s.includes("qualif")) return "bg-violet-500/10 text-violet-400 border-violet-500/20";
  if (s.includes("proposal")) return "bg-amber-500/10 text-amber-400 border-amber-500/20";
  if (s.includes("negotiat")) return "bg-orange-500/10 text-orange-400 border-orange-500/20";
  if (s.includes("won")) return "bg-emerald-500/10 text-emerald-400 border-emerald-500/20";
  if (s.includes("lost")) return "bg-rose-500/10 text-rose-400 border-rose-500/20";
  return "bg-slate-100/60 dark:bg-slate-700/60 text-slate-600 dark:text-slate-300 border-slate-300/30 dark:border-slate-600/30";
}

// ── Animated health ring (80px) ────────────────────────────────────────────────

function IntelRing({ score }: { score: number }) {
  const [animated, setAnimated] = useState(0);
  const r = 32;
  const circ = 2 * Math.PI * r;
  const filled = (animated / 100) * circ;

  useEffect(() => {
    setAnimated(0);
    const raf = requestAnimationFrame(() => {
      const start = performance.now();
      const duration = 800;
      const tick = (now: number) => {
        const t = Math.min((now - start) / duration, 1);
        // ease-out cubic
        const eased = 1 - Math.pow(1 - t, 3);
        setAnimated(Math.round(eased * score));
        if (t < 1) requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    });
    return () => cancelAnimationFrame(raf);
  }, [score]);

  return (
    <div className="relative flex items-center justify-center w-20 h-20 shrink-0">
      <svg width="80" height="80" viewBox="0 0 80 80" className="-rotate-90">
        <circle cx="40" cy="40" r={r} fill="none" strokeWidth="5" className="stroke-slate-200 dark:stroke-slate-700" />
        <circle
          cx="40" cy="40" r={r} fill="none" strokeWidth="5"
          strokeDasharray={`${filled} ${circ}`} strokeLinecap="round"
          className={scoreRingColor(score)}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className={cn("text-xl font-black tabular-nums leading-none", scoreColor(score))}>
          {animated}
        </span>
        <span className="text-[9px] font-semibold text-slate-500 mt-0.5">/ 100</span>
      </div>
    </div>
  );
}

// ── Section tier config ────────────────────────────────────────────────────────

const EVIDENCE_SECTIONS = ["timeline", "health", "activity", "contacts"] as const;
const TOOLS_SECTIONS = ["ai-rep", "call-brief", "mismatch", "trackers", "ack", "coaching", "ask", "outcome"] as const;

const SECTION_STYLES = {
  timeline:    { icon: Clock,          label: "Deal Timeline",                   iconColor: "text-slate-400" },
  health:      { icon: Activity,       label: "Health Score Breakdown",           iconColor: "text-slate-400" },
  activity:    { icon: Zap,            label: "Activity Feed",                    iconColor: "text-slate-400" },
  contacts:    { icon: Users2,         label: "Contacts & Personas",              iconColor: "text-slate-400" },
  "ai-rep":    { icon: Brain,          label: "AI Sales Rep",                     iconColor: "text-slate-400" },
  "call-brief":{ icon: Phone,          label: "Pre-Call Intelligence Brief",      iconColor: "text-slate-400" },
  mismatch:    { icon: GitMerge,       label: "Narrative Check + Email Coach",    iconColor: "text-slate-400" },
  trackers:    { icon: ScanSearch,     label: "Smart Trackers",                   iconColor: "text-slate-400" },
  ack:         { icon: Layers,         label: "Advance / Close / Kill",           iconColor: "text-slate-400" },
  coaching:    { icon: GraduationCap,  label: "Call Coaching",                    iconColor: "text-slate-400" },
  ask:         { icon: Sparkles,       label: "Ask DealIQ",                       iconColor: "text-slate-400" },
  outcome:     { icon: Trophy,         label: "Mark Outcome",                     iconColor: "text-slate-400" },
} as const;

type SectionKey = keyof typeof SECTION_STYLES;

const DEFAULT_OPEN: SectionKey[] = ["timeline"];

// ── Component ─────────────────────────────────────────────────────────────────

export default function DealDetailPanel({
  dealId, dealName, repName, stage, amount, healthScore, healthLabel,
  onClose, initialSection, initialTab, onDealUpdated,
}: Props) {
  const { toast } = useToast();
  const [activeTab, setActiveTab] = useState<PanelTab>(initialTab ?? "Overview");
  const [liveScore, setLiveScore] = useState<number | undefined>(undefined);
  const [liveLabel, setLiveLabel] = useState<string | undefined>(undefined);
  const [openedSections, setOpenedSections] = useState<Set<string>>(new Set(DEFAULT_OPEN));

  // Inline edit state
  const [localStage, setLocalStage] = useState<string | undefined>(stage);
  const [localAmount, setLocalAmount] = useState<number | undefined>(amount);
  const [editingAmount, setEditingAmount] = useState(false);
  const [amountInput, setAmountInput] = useState("");
  const [savingField, setSavingField] = useState<string | null>(null);
  const [savedField, setSavedField] = useState<string | null>(null);

  // Stage drift detection
  const [stageDrift, setStageDrift] = useState<{
    suggested_stage: string;
    confidence: string;
    reasoning: string;
    evidence: string[];
  } | null>(null);
  const [stageDriftDismissed, setStageDriftDismissed] = useState(false);
  const [applyingStageDrift, setApplyingStageDrift] = useState(false);

  // Notes
  const [noteOpen, setNoteOpen] = useState(false);
  const [noteText, setNoteText] = useState("");
  const [savingNote, setSavingNote] = useState(false);

  const amountInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setLocalStage(stage);
    setLocalAmount(amount);
    setEditingAmount(false);
    setNoteText("");
    setNoteOpen(false);
    setActiveTab(initialTab ?? "Overview");
    setOpenedSections(new Set(initialSection ? ["timeline", initialSection] : ["timeline"]));
    setStageDrift(null);
    setStageDriftDismissed(false);
  }, [dealId, stage, amount, initialTab, initialSection]);

  // Auto-trigger stage drift detection when panel opens with a deal
  useEffect(() => {
    if (!dealId || !stage) return;
    let cancelled = false;
    api.checkStageDrift(dealId, stage, dealName).then((res) => {
      if (cancelled) return;
      if (!res.no_drift && res.suggested_stage) {
        setStageDrift({
          suggested_stage: res.suggested_stage,
          confidence: res.confidence ?? "medium",
          reasoning: res.reasoning ?? "",
          evidence: res.evidence ?? [],
        });
      }
    }).catch(() => { /* silent — non-critical */ });
    return () => { cancelled = true; };
  }, [dealId, stage]);

  async function handleFieldSave(field: string, value: string | number) {
    if (!dealId) return;
    setSavingField(field);
    try {
      const res = await api.updateDealField(dealId, field, value);
      if (!res.success) throw new Error(res.error ?? "Save failed");
      setSavedField(field);
      setTimeout(() => setSavedField(null), 1500);
      onDealUpdated?.(field, value);
    } catch {
      toast({ title: `Failed to update ${field} in Zoho`, variant: "destructive" });
      if (field === "Stage") setLocalStage(stage);
      if (field === "Amount") setLocalAmount(amount);
    } finally {
      setSavingField(null);
    }
  }

  async function handleSaveNote() {
    if (!dealId || !noteText.trim()) return;
    setSavingNote(true);
    try {
      const res = await api.updateDealField(dealId, "Description", noteText.trim());
      if (!res.success) throw new Error(res.error ?? "Save failed");
      toast({ title: "Note saved to Zoho CRM" });
      setNoteText("");
      setNoteOpen(false);
    } catch {
      toast({ title: "Failed to save note to Zoho", variant: "destructive" });
    } finally {
      setSavingNote(false);
    }
  }

  useEffect(() => {
    if (!dealId) return;
    setLiveScore(undefined);
    setLiveLabel(undefined);
    api.getDealHealth(dealId)
      .then((data) => {
        const score = data.total_score ?? data.overall_score;
        const label = data.health_label;
        setLiveScore(score);
        setLiveLabel(label);
        if (score != null) onDealUpdated?.("health_score", score);
        if (label) onDealUpdated?.("health_label", label);
      })
      .catch(() => { /* fall back to stale score */ });
  }, [dealId]);

  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === "Escape") onClose();
  }, [onClose]);

  useEffect(() => {
    if (!dealId) return;
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [dealId, handleKeyDown]);

  const displayScore = liveScore ?? healthScore;
  const displayLabel = liveLabel ?? healthLabel;

  const defaultOpen: string[] = initialSection && !DEFAULT_OPEN.includes(initialSection as SectionKey)
    ? [...DEFAULT_OPEN, initialSection]
    : [...DEFAULT_OPEN];

  return (
    <Sheet open={!!dealId} onOpenChange={(open) => !open && onClose()}>
      <SheetContent
        side="right"
        className="w-full overflow-y-auto border-l border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-0 sm:max-w-2xl"
        style={{
          boxShadow: "-24px 0 80px rgba(0,0,0,0.5)",
          // Override Shadcn default transition to match spec
          "--tw-enter-translate-x": "100%",
          transition: "transform 300ms cubic-bezier(0.32,0.72,0,1)",
        } as React.CSSProperties}
      >
        {/* Screen reader accessibility */}
        <SheetTitle className="sr-only">{dealName || "Deal Analysis"}</SheetTitle>
        <SheetDescription className="sr-only">Deal intelligence panel</SheetDescription>

        {/* Drag handle */}
        <div className="absolute left-0 top-1/2 -translate-y-1/2 flex flex-col items-center gap-1 py-4 px-1.5 opacity-20 hover:opacity-50 transition-opacity cursor-grab">
          <div className="h-8 w-1 rounded-full bg-slate-500" />
        </div>

        {/* ── Header ─────────────────────────────────────────── */}
        <div className="sticky top-0 z-10 border-b border-slate-200 dark:border-slate-800 bg-white/95 dark:bg-slate-900/95 px-6 py-4 backdrop-blur-sm">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0 flex-1">
              <h2 className="text-lg font-bold text-slate-900 dark:text-white leading-tight truncate">
                {dealName || "Deal Analysis"}
              </h2>
              {/* Inline meta: stage + amount + score */}
              <div className="mt-2 flex flex-wrap items-center gap-2">

                {/* Stage — inline editable */}
                {localStage && (
                  <div className="relative flex items-center gap-1">
                    <select
                      value={localStage}
                      disabled={savingField === "Stage"}
                      onChange={(e) => {
                        const newStage = e.target.value;
                        setLocalStage(newStage);
                        handleFieldSave("Stage", newStage);
                      }}
                      className={cn(
                        "rounded-full border px-2.5 py-0.5 text-xs font-medium bg-transparent appearance-none cursor-pointer pr-5",
                        "focus:outline-none focus:ring-1 focus:ring-blue-500/50",
                        stagePillClass(localStage)
                      )}
                      title="Click to change stage"
                    >
                      {["Qualification", "Needs Analysis", "Value Proposition", "Proposal", "Negotiation", "Contract Sent", "Closed Won", "Closed Lost"].map((s) => (
                        <option key={s} value={s} className="bg-white dark:bg-slate-900 text-slate-900 dark:text-white">{s}</option>
                      ))}
                      {!["Qualification", "Needs Analysis", "Value Proposition", "Proposal", "Negotiation", "Contract Sent", "Closed Won", "Closed Lost"].includes(localStage) && (
                        <option value={localStage} className="bg-white dark:bg-slate-900 text-slate-900 dark:text-white">{localStage}</option>
                      )}
                    </select>
                    {savingField === "Stage" && <Loader2 size={11} className="animate-spin text-slate-500 absolute right-1.5 top-1/2 -translate-y-1/2" />}
                    {savedField === "Stage" && <Check size={11} className="text-emerald-400 absolute right-1.5 top-1/2 -translate-y-1/2" />}
                  </div>
                )}

                {/* Amount — click to edit */}
                {localAmount != null && localAmount > 0 && (
                  <div className="relative flex items-center">
                    {editingAmount ? (
                      <div className="flex items-center gap-1">
                        <input
                          ref={amountInputRef}
                          type="number"
                          value={amountInput}
                          autoFocus
                          onChange={(e) => setAmountInput(e.target.value)}
                          onBlur={() => {
                            const n = parseFloat(amountInput);
                            if (!isNaN(n) && n > 0 && n !== localAmount) {
                              setLocalAmount(n);
                              handleFieldSave("Amount", n);
                            }
                            setEditingAmount(false);
                          }}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") {
                              const n = parseFloat(amountInput);
                              if (!isNaN(n) && n > 0 && n !== localAmount) {
                                setLocalAmount(n);
                                handleFieldSave("Amount", n);
                              }
                              setEditingAmount(false);
                            }
                            if (e.key === "Escape") setEditingAmount(false);
                          }}
                          className="w-28 rounded-md border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 px-2 py-0.5 text-xs font-semibold tabular-nums text-slate-900 dark:text-white focus:outline-none focus:ring-1 focus:ring-blue-500/50"
                          placeholder={String(localAmount)}
                        />
                        <button onClick={() => setEditingAmount(false)} className="text-slate-500 hover:text-slate-900 dark:hover:text-white">
                          <X size={11} />
                        </button>
                      </div>
                    ) : (
                      <span
                        className="rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-2.5 py-0.5 text-xs font-semibold tabular-nums text-slate-600 dark:text-slate-300 cursor-pointer hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
                        title="Click to edit amount"
                        onClick={() => { setAmountInput(String(localAmount)); setEditingAmount(true); }}
                      >
                        {savingField === "Amount" && <Loader2 size={11} className="inline animate-spin mr-1" />}
                        {savedField === "Amount" && <Check size={11} className="inline text-emerald-400 mr-1" />}
                        {formatCurrency(localAmount)}
                      </span>
                    )}
                  </div>
                )}

                {/* Health score — small inline badge */}
                {displayScore != null && (
                  <span className={cn(
                    "rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-2.5 py-0.5 text-xs font-bold tabular-nums",
                    scoreColor(displayScore)
                  )}>
                    {displayScore}/100
                  </span>
                )}
              </div>
            </div>

            {/* Close button */}
            <button
              onClick={onClose}
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-slate-200 dark:border-slate-700 text-slate-500 transition-colors hover:border-slate-300 dark:hover:border-slate-600 hover:text-slate-900 dark:hover:text-white"
            >
              <X size={16} />
            </button>
          </div>

          {/* Stage Drift Banner */}
          {stageDrift && !stageDriftDismissed && (
            <div className="mt-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2.5">
              <div className="flex items-start gap-2">
                <AlertTriangle size={15} className="mt-0.5 shrink-0 text-amber-400" />
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-semibold text-amber-300 leading-tight">
                    CRM stage may be outdated
                  </p>
                  <p className="mt-0.5 text-xs text-amber-200/80 leading-snug">
                    {stageDrift.reasoning}
                  </p>
                  <div className="mt-2 flex items-center gap-2 flex-wrap">
                    <span className="flex items-center gap-1 text-xs text-slate-400">
                      <span className={cn("rounded-full border px-2 py-0.5 text-xs font-medium", stagePillClass(localStage ?? ""))}>
                        {localStage}
                      </span>
                      <ArrowRight size={12} className="text-amber-400" />
                      <span className={cn("rounded-full border px-2 py-0.5 text-xs font-medium", stagePillClass(stageDrift.suggested_stage))}>
                        {stageDrift.suggested_stage}
                      </span>
                    </span>
                    <button
                      disabled={applyingStageDrift || savingField === "Stage"}
                      onClick={async () => {
                        setApplyingStageDrift(true);
                        const newStage = stageDrift.suggested_stage;
                        setLocalStage(newStage);
                        setStageDriftDismissed(true);
                        await handleFieldSave("Stage", newStage);
                        setApplyingStageDrift(false);
                      }}
                      className="flex items-center gap-1 rounded-md bg-amber-500 px-2.5 py-1 text-xs font-semibold text-white hover:bg-amber-400 disabled:opacity-50 transition-colors"
                    >
                      {applyingStageDrift ? <Loader2 size={10} className="animate-spin" /> : <Check size={10} />}
                      Update stage
                    </button>
                    <button
                      onClick={() => setStageDriftDismissed(true)}
                      className="text-xs text-slate-500 hover:text-slate-300 transition-colors"
                    >
                      Dismiss
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Tab bar */}
          <div className="mt-3 flex gap-0 border-b border-slate-200 dark:border-slate-800 -mb-4 pb-0">
            {(["Overview", "Battle Card"] as PanelTab[]).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={cn(
                  "px-4 py-2 text-sm font-medium border-b-2 transition-colors",
                  activeTab === tab
                    ? "border-blue-500 text-blue-400"
                    : "border-transparent text-slate-500 hover:text-slate-700 dark:hover:text-slate-300"
                )}
              >
                {tab === "Battle Card" && (
                  <Zap size={12} className="inline mr-1.5 mb-0.5" strokeWidth={2.5} />
                )}
                {tab}
              </button>
            ))}
          </div>
        </div>

        {/* ── Battle Card tab ────────────────────────────────── */}
        {dealId && activeTab === "Battle Card" && (
          <div className="px-4 py-4">
            <BattleCardPanel dealId={dealId} />
          </div>
        )}

        {/* ── Overview tab ───────────────────────────────────── */}
        {dealId && activeTab === "Overview" && (
          <div className="px-4 pt-6 pb-6 space-y-5">

            {/* ── Intelligence Brief (always visible) ─────────── */}
            <div
              className="rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-800/50 p-5 opacity-0 animate-fade-in"
              style={{ animationDelay: "50ms", animationFillMode: "forwards" }}
            >
              <div className="flex items-start gap-5">
                {/* Health ring */}
                {displayScore != null ? (
                  <IntelRing score={displayScore} />
                ) : (
                  <div className="flex h-20 w-20 shrink-0 items-center justify-center rounded-full border border-slate-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-800">
                    <Loader2 className="h-5 w-5 animate-spin text-slate-600" />
                  </div>
                )}

                {/* Summary text */}
                <div className="flex-1 min-w-0">
                  <p className="text-[11px] font-semibold uppercase tracking-widest text-slate-600 mb-1">
                    Intelligence Brief
                  </p>
                  {displayScore != null ? (
                    <>
                      <p className={cn("text-sm font-semibold mb-1.5", scoreColor(displayScore))}>
                        {displayScore >= 75 ? "Healthy" : displayScore >= 50 ? "At Risk" : displayScore >= 25 ? "Critical" : "Zombie"}
                        {" "}— Score {displayScore}/100
                      </p>
                      <p className="text-sm text-slate-400 leading-relaxed">
                        {healthSummary(displayScore, displayLabel)}
                      </p>
                    </>
                  ) : (
                    <div className="space-y-2">
                      <div className="h-3 w-24 rounded bg-slate-700 animate-pulse" />
                      <div className="h-3 w-48 rounded bg-slate-700 animate-pulse" />
                      <div className="h-3 w-36 rounded bg-slate-700 animate-pulse" />
                    </div>
                  )}
                </div>
              </div>

              {/* Sub-stats row */}
              {displayScore != null && (
                <div className="mt-4 grid grid-cols-3 gap-3 border-t border-slate-200/60 dark:border-slate-700/60 pt-4">
                  <div>
                    <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-600">Risk Level</p>
                    <p className={cn("text-sm font-bold mt-0.5", scoreColor(displayScore))}>
                      {displayScore >= 75 ? "Low" : displayScore >= 50 ? "Medium" : "High"}
                    </p>
                  </div>
                  <div>
                    <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-600">Status</p>
                    <p className="text-sm font-bold text-slate-900 dark:text-white mt-0.5 capitalize">
                      {(displayLabel ?? "").replace("_", " ") || "—"}
                    </p>
                  </div>
                  <div>
                    <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-600">Rep</p>
                    <p className="text-sm font-bold text-slate-900 dark:text-white mt-0.5 truncate">
                      {repName ?? "—"}
                    </p>
                  </div>
                </div>
              )}
            </div>

            {/* ── Evidence tier ──────────────────────────────────── */}
            <div
              className="opacity-0 animate-fade-in"
              style={{ animationDelay: "150ms", animationFillMode: "forwards" }}
            >
              <div className="flex items-center gap-2 mb-2 px-1">
                <span className="text-[10px] font-bold uppercase tracking-widest text-slate-600">Evidence</span>
                <div className="flex-1 h-px bg-slate-200 dark:bg-slate-800" />
              </div>
              <Accordion
                type="multiple"
                defaultValue={defaultOpen.filter(d => (EVIDENCE_SECTIONS as readonly string[]).includes(d))}
                onValueChange={(vals) => {
                  setOpenedSections(prev => { const next = new Set(prev); vals.forEach(v => next.add(v)); return next; });
                }}
                className="space-y-1"
              >
                {EVIDENCE_SECTIONS.map((key) => {
                  const { icon: Icon, label: sectionLabel } = SECTION_STYLES[key];
                  return (
                    <AccordionItem key={key} value={key} className="overflow-hidden rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/50 px-0 transition-colors duration-150 hover:border-slate-300 dark:hover:border-slate-700 data-[state=open]:border-slate-300 dark:data-[state=open]:border-slate-700 data-[state=open]:bg-slate-100/40 dark:data-[state=open]:bg-slate-800/40">
                      <AccordionTrigger className="px-4 py-2.5 hover:no-underline hover:bg-transparent [&>svg]:text-slate-600 [&>svg]:transition-transform [&>svg]:duration-250 [&[data-state=open]>svg]:rotate-180">
                        <div className="flex items-center gap-2.5">
                          <Icon className="h-3.5 w-3.5 shrink-0 text-slate-500" />
                          <span className="text-sm font-medium text-slate-700 dark:text-slate-300">{sectionLabel}</span>
                        </div>
                      </AccordionTrigger>
                      <AccordionContent className="px-4 pb-4 pt-0">
                        {openedSections.has(key) && key === "timeline"  && <DealTimeline dealId={dealId} />}
                        {openedSections.has(key) && key === "health"    && <HealthBreakdown dealId={dealId} />}
                        {openedSections.has(key) && key === "activity"  && <ActivityFeedPanel dealId={dealId} stage={stage} />}
                        {openedSections.has(key) && key === "contacts"  && <ContactsPanel dealId={dealId} />}
                      </AccordionContent>
                    </AccordionItem>
                  );
                })}
              </Accordion>
            </div>

            {/* ── Tools tier ─────────────────────────────────────── */}
            <div
              className="opacity-0 animate-fade-in"
              style={{ animationDelay: "250ms", animationFillMode: "forwards" }}
            >
              <div className="flex items-center gap-2 mb-2 px-1">
                <span className="text-[10px] font-bold uppercase tracking-widest text-slate-600">Tools</span>
                <div className="flex-1 h-px bg-slate-200 dark:bg-slate-800" />
              </div>
              <Accordion
                type="multiple"
                defaultValue={defaultOpen.filter(d => (TOOLS_SECTIONS as readonly string[]).includes(d))}
                onValueChange={(vals) => {
                  setOpenedSections(prev => { const next = new Set(prev); vals.forEach(v => next.add(v)); return next; });
                }}
                className="space-y-1"
              >
                {TOOLS_SECTIONS.map((key) => {
                  const { icon: Icon, label: sectionLabel } = SECTION_STYLES[key];
                  return (
                    <AccordionItem key={key} value={key} className="overflow-hidden rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/50 px-0 transition-colors duration-150 hover:border-slate-300 dark:hover:border-slate-700 data-[state=open]:border-slate-300 dark:data-[state=open]:border-slate-700 data-[state=open]:bg-slate-100/40 dark:data-[state=open]:bg-slate-800/40">
                      <AccordionTrigger className="px-4 py-2.5 hover:no-underline hover:bg-transparent [&>svg]:text-slate-600 [&>svg]:transition-transform [&>svg]:duration-250 [&[data-state=open]>svg]:rotate-180">
                        <div className="flex items-center gap-2.5">
                          <Icon className="h-3.5 w-3.5 shrink-0 text-slate-500" />
                          <span className="text-sm font-medium text-slate-700 dark:text-slate-300">{sectionLabel}</span>
                        </div>
                      </AccordionTrigger>
                      <AccordionContent className="px-4 pb-4 pt-0">
                        {openedSections.has(key) && key === "ai-rep"     && <AIRepPanel dealId={dealId} dealName={dealName} repName={repName} />}
                        {openedSections.has(key) && key === "call-brief" && <CallBriefPanel dealId={dealId} repName={repName} />}
                        {openedSections.has(key) && key === "mismatch"   && <MismatchChecker dealId={dealId} />}
                        {openedSections.has(key) && key === "trackers"   && <TrackerPanel dealId={dealId} />}
                        {openedSections.has(key) && key === "ack"        && <AckSection dealId={dealId} dealName={dealName} />}
                        {openedSections.has(key) && key === "coaching"   && <CoachingPanel dealId={dealId} repName={repName} />}
                        {openedSections.has(key) && key === "ask"        && <AskDealIQPanel dealId={dealId} dealName={dealName} />}
                        {openedSections.has(key) && key === "outcome"    && <MarkOutcomeSection dealId={dealId} dealName={dealName} />}
                      </AccordionContent>
                    </AccordionItem>
                  );
                })}
              </Accordion>
            </div>

            {/* ── Add CRM Note ─────────────────────────────────── */}
            <div
              className="rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/50 px-4 py-3 opacity-0 animate-fade-in"
              style={{ animationDelay: "350ms", animationFillMode: "forwards" }}
            >
              {noteOpen ? (
                <div className="space-y-2">
                  <label className="text-[10px] font-semibold uppercase tracking-wider text-slate-600">
                    Add note to Zoho CRM
                  </label>
                  <textarea
                    value={noteText}
                    onChange={(e) => setNoteText(e.target.value.slice(0, 500))}
                    rows={3}
                    placeholder="Type your note here…"
                    className="w-full bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-900 dark:text-white placeholder:text-slate-400 dark:placeholder:text-slate-600 focus:outline-none focus:ring-1 focus:ring-blue-500/50 resize-none"
                  />
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-slate-600">{noteText.length}/500</span>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => { setNoteOpen(false); setNoteText(""); }}
                        className="text-xs text-slate-500 hover:text-slate-900 dark:hover:text-white transition-colors"
                      >
                        Cancel
                      </button>
                      <button
                        onClick={handleSaveNote}
                        disabled={savingNote || !noteText.trim()}
                        className="flex items-center gap-1.5 rounded-lg bg-blue-500 hover:bg-blue-600 disabled:opacity-50 px-3 py-1.5 text-xs font-semibold text-white transition-colors"
                      >
                        {savingNote ? <Loader2 size={11} className="animate-spin" /> : <Check size={11} />}
                        Save to Zoho
                      </button>
                    </div>
                  </div>
                </div>
              ) : (
                <button
                  onClick={() => setNoteOpen(true)}
                  className="text-xs text-slate-500 hover:text-slate-700 dark:hover:text-slate-300 transition-colors"
                >
                  + Add CRM note
                </button>
              )}
            </div>

          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
