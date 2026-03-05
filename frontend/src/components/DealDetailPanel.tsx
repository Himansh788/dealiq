import { useState, useEffect, useCallback, useRef } from "react";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Brain, Clock, Phone, Activity, GitMerge, Layers, ScanSearch, GraduationCap, Zap, Sparkles, Trophy, Loader2, Check, X } from "lucide-react";
import BattleCardPanel from "./deal/BattleCardPanel";
import { Badge } from "@/components/ui/badge";
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
  /** Accordion section to auto-expand on open (e.g. "mismatch") */
  initialSection?: string;
  /** Tab to activate on open */
  initialTab?: PanelTab;
  onDealUpdated?: (field: string, value: string | number) => void;
}

function formatCurrency(val: number): string {
  if (val >= 1_000_000) return `$${(val / 1_000_000).toFixed(1)}M`;
  if (val >= 1_000) return `$${Math.round(val / 1_000)}K`;
  return `$${val}`;
}

function scoreColor(score: number) {
  if (score >= 75) return "text-health-green";
  if (score >= 50) return "text-health-yellow";
  return "text-health-red";
}

function stagePillClass(stage: string): string {
  const s = stage.toLowerCase();
  if (s.includes("discovery")) return "bg-sky-500/10 text-sky-400 border-sky-500/20";
  if (s.includes("qualif")) return "bg-violet-500/10 text-violet-400 border-violet-500/20";
  if (s.includes("proposal")) return "bg-amber-500/10 text-amber-400 border-amber-500/20";
  if (s.includes("negotiat")) return "bg-orange-500/10 text-orange-400 border-orange-500/20";
  if (s.includes("won")) return "bg-health-green/10 text-health-green border-health-green/20";
  if (s.includes("lost")) return "bg-health-red/10 text-health-red border-health-red/20";
  return "bg-secondary/60 text-muted-foreground border-border/30";
}

const SECTION_STYLES = {
  timeline: { icon: Clock, label: "Deal Timeline", iconColor: "text-sky-400", activeBorder: "border-l-sky-400/50" },
  health: { icon: Activity, label: "Health Score Breakdown", iconColor: "text-primary", activeBorder: "border-l-primary/50" },
  activity: { icon: Zap, label: "Activity Feed", iconColor: "text-blue-400", activeBorder: "border-l-blue-400/50" },
  "ai-rep": { icon: Brain, label: "AI Sales Rep", iconColor: "text-accent", activeBorder: "border-l-accent/50" },
  "call-brief": { icon: Phone, label: "Pre-Call Intelligence Brief", iconColor: "text-green-400", activeBorder: "border-l-green-400/50" },
  mismatch: { icon: GitMerge, label: "Narrative Check + Live Email Coach", iconColor: "text-amber-400", activeBorder: "border-l-amber-400/50" },
  trackers: { icon: ScanSearch, label: "Smart Trackers", iconColor: "text-primary", activeBorder: "border-l-primary/50" },
  ack: { icon: Layers, label: "Advance / Close / Kill", iconColor: "text-health-red", activeBorder: "border-l-health-red/50" },
  coaching: { icon: GraduationCap, label: "Call Coaching", iconColor: "text-cyan-400", activeBorder: "border-l-cyan-400/50" },
  ask: { icon: Sparkles, label: "Ask DealIQ", iconColor: "text-violet-400", activeBorder: "border-l-violet-400/50" },
  outcome: { icon: Trophy, label: "Mark Outcome", iconColor: "text-amber-400", activeBorder: "border-l-amber-400/50" },
} as const;

type SectionKey = keyof typeof SECTION_STYLES;

const DEFAULT_OPEN: SectionKey[] = ["timeline", "health", "ai-rep"];

// Per-section badge previews shown in the collapsed accordion header
function SectionBadge({ sectionKey, healthScore }: { sectionKey: SectionKey; healthScore?: number }) {
  if (sectionKey === "health" && healthScore != null) {
    const color = healthScore >= 65 ? "border-health-green/40 text-health-green bg-health-green/10"
      : healthScore >= 45 ? "border-health-yellow/40 text-health-yellow bg-health-yellow/10"
        : "border-health-red/40 text-health-red bg-health-red/10";
    return (
      <span className={cn("ml-2 rounded-full border px-2 py-0.5 text-[10px] font-bold tabular-nums", color)}>
        {healthScore}/100
      </span>
    );
  }
  if (sectionKey === "ai-rep") {
    return (
      <span className="ml-2 flex items-center gap-1 rounded-full border border-blue-500/30 bg-blue-500/10 px-2 py-0.5 text-[10px] font-medium text-blue-400">
        <span className="h-1.5 w-1.5 rounded-full bg-blue-400" />
        1 waiting
      </span>
    );
  }
  return null;
}

function SectionTrigger({ sectionKey, healthScore }: { sectionKey: SectionKey; healthScore?: number }) {
  const { icon: Icon, label, iconColor } = SECTION_STYLES[sectionKey];
  return (
    <div className="flex items-center gap-2.5">
      <Icon className={cn("h-4 w-4 shrink-0", iconColor)} />
      <span className="text-sm font-semibold text-foreground">{label}</span>
      <SectionBadge sectionKey={sectionKey} healthScore={healthScore} />
    </div>
  );
}

export default function DealDetailPanel({
  dealId, dealName, repName, stage, amount, closingDate, healthScore, healthLabel,
  onClose, initialSection, initialTab, onDealUpdated,
}: Props) {
  const { toast } = useToast();
  const [activeTab, setActiveTab] = useState<PanelTab>(initialTab ?? "Overview");
  const [liveScore, setLiveScore] = useState<number | undefined>(undefined);
  const [liveLabel, setLiveLabel] = useState<string | undefined>(undefined);

  // Inline edit state
  const [localStage, setLocalStage] = useState<string | undefined>(stage);
  const [localAmount, setLocalAmount] = useState<number | undefined>(amount);
  const [editingAmount, setEditingAmount] = useState(false);
  const [amountInput, setAmountInput] = useState("");
  const [savingField, setSavingField] = useState<string | null>(null);
  const [savedField, setSavedField] = useState<string | null>(null); // shows ✓ briefly

  // Notes section
  const [noteOpen, setNoteOpen] = useState(false);
  const [noteText, setNoteText] = useState("");
  const [savingNote, setSavingNote] = useState(false);

  const amountInputRef = useRef<HTMLInputElement>(null);

  // Sync props → local state when deal changes
  useEffect(() => {
    setLocalStage(stage);
    setLocalAmount(amount);
    setEditingAmount(false);
    setNoteText("");
    setNoteOpen(false);
    setActiveTab(initialTab ?? "Overview");
  }, [dealId, stage, amount, initialTab]);

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
      // Revert
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
        setLiveScore(data.total_score ?? data.overall_score);
        setLiveLabel(data.health_label);
      })
      .catch(() => { /* fall back to stale list score */ });
  }, [dealId]);

  // Escape key — close panel
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
  const showMeta = localStage || (localAmount != null && localAmount > 0) || displayScore != null;

  // Build default open sections, adding initialSection if supplied
  const defaultOpen: string[] = initialSection && !DEFAULT_OPEN.includes(initialSection as SectionKey)
    ? [...DEFAULT_OPEN, initialSection]
    : [...DEFAULT_OPEN];

  return (
    <Sheet open={!!dealId} onOpenChange={(open) => !open && onClose()}>
      <SheetContent
        side="right"
        className="w-full overflow-y-auto border-l border-border/40 bg-background p-0 sm:max-w-2xl transition-transform duration-400 ease-[cubic-bezier(0.32,0.72,0,1)] data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:slide-out-to-right data-[state=open]:slide-in-from-right"
        style={{
          boxShadow: '-20px 0 60px rgba(0,0,0,0.4)',
        }}
      >
        {/* Drag handle indicator */}
        <div className="absolute left-0 top-1/2 -translate-y-1/2 flex flex-col items-center gap-1 py-4 px-1.5 opacity-30 hover:opacity-60 transition-opacity cursor-grab">
          <div className="h-8 w-1 rounded-full bg-muted-foreground/60" />
        </div>

        {/* Panel header */}
        <div className="sticky top-0 z-10 border-b border-border/40 bg-background/95 px-6 py-5 backdrop-blur-sm">
          <SheetHeader className="gap-1">
            <SheetTitle className="text-lg font-bold text-foreground leading-tight">
              {dealName || "Deal Analysis"}
            </SheetTitle>
            <SheetDescription className="text-xs text-muted-foreground/60">
              In-depth deal intelligence and AI-powered actions
            </SheetDescription>
          </SheetHeader>

          {/* Deal meta strip — inline editable fields */}
          {showMeta && (
            <div className="mt-3 flex flex-wrap items-center gap-2">

              {/* Stage — click to edit */}
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
                      "focus:outline-none focus:ring-1 focus:ring-primary/50",
                      stagePillClass(localStage)
                    )}
                    title="Click to change stage"
                  >
                    {["Qualification", "Needs Analysis", "Value Proposition", "Proposal", "Negotiation", "Contract Sent", "Closed Won", "Closed Lost"].map((s) => (
                      <option key={s} value={s} className="bg-background text-foreground">{s}</option>
                    ))}
                    {/* Keep current stage in list even if not in default options */}
                    {!["Qualification", "Needs Analysis", "Value Proposition", "Proposal", "Negotiation", "Contract Sent", "Closed Won", "Closed Lost"].includes(localStage) && (
                      <option value={localStage} className="bg-background text-foreground">{localStage}</option>
                    )}
                  </select>
                  {savingField === "Stage" && <Loader2 size={11} className="animate-spin text-muted-foreground absolute right-1.5 top-1/2 -translate-y-1/2" />}
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
                        className="w-28 rounded-md border border-border/60 bg-secondary/60 px-2 py-0.5 text-xs font-semibold tabular-nums text-foreground focus:outline-none focus:ring-1 focus:ring-primary/50"
                        placeholder={String(localAmount)}
                      />
                      <button onClick={() => setEditingAmount(false)} className="text-muted-foreground/60 hover:text-foreground">
                        <X size={11} />
                      </button>
                    </div>
                  ) : (
                    <span
                      className="rounded-md border border-border/40 bg-secondary/40 px-2.5 py-0.5 text-xs font-semibold tabular-nums text-foreground/80 cursor-pointer hover:bg-secondary/70 transition-colors"
                      title="Click to edit amount"
                      onClick={() => { setAmountInput(String(localAmount)); setEditingAmount(true); }}
                    >
                      {savingField === "Amount" ? <Loader2 size={11} className="inline animate-spin mr-1" /> : null}
                      {savedField === "Amount" ? <Check size={11} className="inline text-emerald-400 mr-1" /> : null}
                      {formatCurrency(localAmount)}
                    </span>
                  )}
                </div>
              )}

              {displayScore != null && (
                <span className={cn(
                  "rounded-md border border-border/40 bg-secondary/40 px-2.5 py-0.5 text-xs font-bold tabular-nums",
                  scoreColor(displayScore)
                )}>
                  Health {displayScore}
                </span>
              )}
            </div>
          )}
        </div>

        {/* Tab bar */}
        {dealId && (
          <div className="flex border-b border-border/40 px-4">
            {(["Overview", "Battle Card"] as PanelTab[]).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={cn(
                  "px-4 py-2.5 text-sm font-medium border-b-2 transition-colors",
                  activeTab === tab
                    ? "border-sky-500 text-sky-400"
                    : "border-transparent text-slate-500 hover:text-slate-300"
                )}
              >
                {tab === "Battle Card" && (
                  <Zap size={12} className="inline mr-1.5 mb-0.5" strokeWidth={2.5} />
                )}
                {tab}
              </button>
            ))}
          </div>
        )}

        {/* Battle Card tab */}
        {dealId && activeTab === "Battle Card" && (
          <div className="px-4 py-4">
            <BattleCardPanel dealId={dealId} />
          </div>
        )}

        {/* Accordion sections */}
        {dealId && activeTab === "Overview" && (
          <div className="px-4 py-4">
            <Accordion
              type="multiple"
              defaultValue={defaultOpen}
              className="space-y-2"
            >
              {(Object.keys(SECTION_STYLES) as SectionKey[]).map(key => (
                <AccordionItem
                  key={key}
                  value={key}
                  className="overflow-hidden rounded-lg border border-border/40 bg-card/40 px-0 transition-all duration-200 hover:border-border/60 data-[state=open]:border-border/60 data-[state=open]:bg-card/60"
                >
                  <AccordionTrigger className="border-b-0 px-4 py-3 hover:no-underline hover:bg-transparent [&>svg]:text-muted-foreground/50 transition-all [&[data-state=open]>svg]:rotate-180 [&>svg]:transition-transform [&>svg]:duration-300 [&>svg]:ease-[cubic-bezier(0.4,0,0.2,1)]">
                    <SectionTrigger sectionKey={key} healthScore={displayScore} />
                  </AccordionTrigger>
                  <AccordionContent className="px-4 pb-4 pt-0 transition-all duration-300 data-[state=closed]:animate-accordion-up data-[state=open]:animate-accordion-down">
                    {key === "timeline" && <DealTimeline dealId={dealId} />}
                    {key === "health" && <HealthBreakdown dealId={dealId} />}
                    {key === "activity" && <ActivityFeedPanel dealId={dealId} stage={stage} />}
                    {key === "ai-rep" && <AIRepPanel dealId={dealId} dealName={dealName} repName={repName} />}
                    {key === "call-brief" && <CallBriefPanel dealId={dealId} repName={repName} />}
                    {key === "mismatch" && <MismatchChecker dealId={dealId} />}
                    {key === "trackers" && <TrackerPanel dealId={dealId} />}
                    {key === "ack" && <AckSection dealId={dealId} dealName={dealName} />}
                    {key === "coaching" && <CoachingPanel dealId={dealId} repName={repName} />}
                    {key === "ask" && <AskDealIQPanel dealId={dealId} dealName={dealName} />}
                    {key === "outcome" && <MarkOutcomeSection dealId={dealId} dealName={dealName} />}
                  </AccordionContent>
                </AccordionItem>
              ))}
            </Accordion>

            {/* ── Add CRM Note ───────────────────────────────── */}
            {dealId && (
              <div className="mt-4 rounded-lg border border-border/40 bg-card/40 px-4 py-3">
                {noteOpen ? (
                  <div className="space-y-2">
                    <label className="text-xs text-muted-foreground/60 uppercase tracking-wider">Add note to Zoho CRM</label>
                    <textarea
                      value={noteText}
                      onChange={(e) => setNoteText(e.target.value.slice(0, 500))}
                      rows={3}
                      placeholder="Type your note here…"
                      className="w-full bg-secondary/40 border border-border/40 rounded-lg px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground/40 focus:outline-none focus:ring-1 focus:ring-primary/50 resize-none"
                    />
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-muted-foreground/40">{noteText.length}/500</span>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => { setNoteOpen(false); setNoteText(""); }}
                          className="text-xs text-muted-foreground/60 hover:text-foreground"
                        >
                          Cancel
                        </button>
                        <button
                          onClick={handleSaveNote}
                          disabled={savingNote || !noteText.trim()}
                          className="flex items-center gap-1.5 rounded-lg bg-primary/80 hover:bg-primary disabled:opacity-50 px-3 py-1.5 text-xs font-semibold text-primary-foreground transition-colors"
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
                    className="text-xs text-muted-foreground/60 hover:text-foreground transition-colors"
                  >
                    + Add CRM note
                  </button>
                )}
              </div>
            )}
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
