import { useState, useEffect, useCallback } from "react";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Brain, Clock, Phone, Activity, GitMerge, Layers, ScanSearch, GraduationCap, Zap, Sparkles } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
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

interface Props {
  dealId: string | null;
  dealName: string;
  repName?: string;
  stage?: string;
  amount?: number;
  healthScore?: number;
  healthLabel?: string;
  onClose: () => void;
  /** Accordion section to auto-expand on open (e.g. "mismatch") */
  initialSection?: string;
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
  if (s.includes("discovery"))  return "bg-sky-500/10 text-sky-400 border-sky-500/20";
  if (s.includes("qualif"))     return "bg-violet-500/10 text-violet-400 border-violet-500/20";
  if (s.includes("proposal"))   return "bg-amber-500/10 text-amber-400 border-amber-500/20";
  if (s.includes("negotiat"))   return "bg-orange-500/10 text-orange-400 border-orange-500/20";
  if (s.includes("won"))        return "bg-health-green/10 text-health-green border-health-green/20";
  if (s.includes("lost"))       return "bg-health-red/10 text-health-red border-health-red/20";
  return "bg-secondary/60 text-muted-foreground border-border/30";
}

const SECTION_STYLES = {
  timeline:   { icon: Clock,        label: "Deal Timeline",                      iconColor: "text-sky-400",    activeBorder: "border-l-sky-400/50" },
  health:     { icon: Activity,     label: "Health Score Breakdown",             iconColor: "text-primary",    activeBorder: "border-l-primary/50" },
  activity:   { icon: Zap,          label: "Activity Feed",                      iconColor: "text-blue-400",   activeBorder: "border-l-blue-400/50" },
  "ai-rep":   { icon: Brain,        label: "AI Sales Rep",                       iconColor: "text-accent",     activeBorder: "border-l-accent/50" },
  "call-brief": { icon: Phone,      label: "Pre-Call Intelligence Brief",        iconColor: "text-green-400",  activeBorder: "border-l-green-400/50" },
  mismatch:   { icon: GitMerge,     label: "Narrative Check + Live Email Coach", iconColor: "text-amber-400",  activeBorder: "border-l-amber-400/50" },
  trackers:   { icon: ScanSearch,   label: "Smart Trackers",                     iconColor: "text-primary",    activeBorder: "border-l-primary/50" },
  ack:        { icon: Layers,       label: "Advance / Close / Kill",             iconColor: "text-health-red", activeBorder: "border-l-health-red/50" },
  coaching:   { icon: GraduationCap,label: "Call Coaching",                      iconColor: "text-cyan-400",   activeBorder: "border-l-cyan-400/50" },
  ask:        { icon: Sparkles,     label: "Ask DealIQ",                         iconColor: "text-violet-400", activeBorder: "border-l-violet-400/50" },
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
  dealId, dealName, repName, stage, amount, healthScore, healthLabel, onClose, initialSection
}: Props) {
  const [liveScore, setLiveScore] = useState<number | undefined>(undefined);
  const [liveLabel, setLiveLabel] = useState<string | undefined>(undefined);

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
  const showMeta = stage || (amount != null && amount > 0) || displayScore != null;

  // Build default open sections, adding initialSection if supplied
  const defaultOpen: string[] = initialSection && !DEFAULT_OPEN.includes(initialSection as SectionKey)
    ? [...DEFAULT_OPEN, initialSection]
    : [...DEFAULT_OPEN];

  return (
    <Sheet open={!!dealId} onOpenChange={(open) => !open && onClose()}>
      <SheetContent
        side="right"
        className="w-full overflow-y-auto border-l border-border/40 bg-background p-0 sm:max-w-2xl transition-transform duration-300"
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

          {/* Deal meta strip */}
          {showMeta && (
            <div className="mt-3 flex flex-wrap items-center gap-2">
              {stage && (
                <span className={cn(
                  "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium",
                  stagePillClass(stage)
                )}>
                  {stage}
                </span>
              )}
              {amount != null && amount > 0 && (
                <span className="rounded-md border border-border/40 bg-secondary/40 px-2.5 py-0.5 text-xs font-semibold tabular-nums text-foreground/80">
                  {formatCurrency(amount)}
                </span>
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

        {/* Accordion sections */}
        {dealId && (
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
                  <AccordionTrigger className="border-b-0 px-4 py-3 hover:no-underline hover:bg-transparent [&>svg]:text-muted-foreground/50">
                    <SectionTrigger sectionKey={key} healthScore={displayScore} />
                  </AccordionTrigger>
                  <AccordionContent className="px-4 pb-4 pt-0">
                    {key === "timeline"    && <DealTimeline dealId={dealId} />}
                    {key === "health"      && <HealthBreakdown dealId={dealId} />}
                    {key === "activity"    && <ActivityFeedPanel dealId={dealId} stage={stage} />}
                    {key === "ai-rep"      && <AIRepPanel dealId={dealId} dealName={dealName} repName={repName} />}
                    {key === "call-brief"  && <CallBriefPanel dealId={dealId} repName={repName} />}
                    {key === "mismatch"    && <MismatchChecker dealId={dealId} />}
                    {key === "trackers"    && <TrackerPanel dealId={dealId} />}
                    {key === "ack"         && <AckSection dealId={dealId} dealName={dealName} />}
                    {key === "coaching"    && <CoachingPanel dealId={dealId} repName={repName} />}
                    {key === "ask"         && <AskDealIQPanel dealId={dealId} dealName={dealName} />}
                  </AccordionContent>
                </AccordionItem>
              ))}
            </Accordion>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
