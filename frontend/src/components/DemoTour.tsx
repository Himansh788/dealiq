/**
 * DemoTour — lightweight guided tour, no external dependencies.
 * Uses fixed-position tooltips anchored to page regions via data-tour attributes.
 */
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { X, ChevronRight, ChevronLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface TourStep {
  target: string;        // data-tour= attribute value
  title: string;
  description: string;
  placement: "bottom" | "top" | "left" | "right";
}

const STEPS: TourStep[] = [
  {
    target: "metric-cards",
    title: "Your pipeline at a glance",
    description: "Four live metrics: total deals, pipeline value, average health score, and how many need immediate action.",
    placement: "bottom",
  },
  {
    target: "deals-table",
    title: "Worst deals shown first",
    description: "Deals are sorted by urgency. Red = critical, orange = at risk. Click any row to deep-dive.",
    placement: "top",
  },
  {
    target: "analyse-btn",
    title: "Deep-dive any deal",
    description: "Click a deal row to open the AI analysis panel — health breakdown, email coach, next best action, and more.",
    placement: "left",
  },
  {
    target: "mismatch-fab",
    title: "Catch errors before sending",
    description: "Paste a draft email here before you hit send. DealIQ checks it against call notes to flag broken promises.",
    placement: "top",
  },
];

interface TooltipPos {
  top: number;
  left: number;
  arrowSide: "top" | "bottom" | "left" | "right";
}

function getTooltipPos(target: HTMLElement, placement: TourStep["placement"]): TooltipPos {
  const rect = target.getBoundingClientRect();
  const TOOLTIP_W = 300;
  const TOOLTIP_H = 150;
  const OFFSET = 16;

  switch (placement) {
    case "bottom":
      return {
        top: rect.bottom + OFFSET,
        left: Math.max(8, Math.min(rect.left + rect.width / 2 - TOOLTIP_W / 2, window.innerWidth - TOOLTIP_W - 8)),
        arrowSide: "top",
      };
    case "top":
      return {
        top: rect.top - TOOLTIP_H - OFFSET,
        left: Math.max(8, Math.min(rect.left + rect.width / 2 - TOOLTIP_W / 2, window.innerWidth - TOOLTIP_W - 8)),
        arrowSide: "bottom",
      };
    case "left":
      return {
        top: Math.max(8, rect.top + rect.height / 2 - TOOLTIP_H / 2),
        left: rect.left - TOOLTIP_W - OFFSET,
        arrowSide: "right",
      };
    case "right":
    default:
      return {
        top: Math.max(8, rect.top + rect.height / 2 - TOOLTIP_H / 2),
        left: rect.right + OFFSET,
        arrowSide: "left",
      };
  }
}

interface Props {
  onEnd: () => void;
}

export default function DemoTour({ onEnd }: Props) {
  const [step, setStep] = useState(0);
  const [pos, setPos] = useState<TooltipPos | null>(null);
  const [highlightRect, setHighlightRect] = useState<DOMRect | null>(null);

  const currentStep = STEPS[step];

  useEffect(() => {
    const el = document.querySelector(`[data-tour="${currentStep.target}"]`) as HTMLElement | null;
    if (!el) {
      setPos(null);
      setHighlightRect(null);
      return;
    }
    el.scrollIntoView({ block: "nearest", behavior: "smooth" });
    const update = () => {
      const rect = el.getBoundingClientRect();
      setHighlightRect(rect);
      setPos(getTooltipPos(el, currentStep.placement));
    };
    // Small delay to let scroll finish
    const t = setTimeout(update, 150);
    return () => clearTimeout(t);
  }, [step, currentStep.target, currentStep.placement]);

  // Escape key ends tour
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === "Escape") onEnd(); };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onEnd]);

  const next = () => { if (step < STEPS.length - 1) setStep(s => s + 1); else onEnd(); };
  const prev = () => { if (step > 0) setStep(s => s - 1); };

  return createPortal(
    <>
      {/* Overlay */}
      <div className="fixed inset-0 z-[9998] pointer-events-none">
        {/* Dark backdrop */}
        <div className="absolute inset-0 bg-black/60" />
        {/* Highlight cutout — uses box-shadow trick */}
        {highlightRect && (
          <div
            className="absolute rounded-lg ring-2 ring-primary/80 transition-all duration-300"
            style={{
              top:    highlightRect.top    - 4,
              left:   highlightRect.left   - 4,
              width:  highlightRect.width  + 8,
              height: highlightRect.height + 8,
              boxShadow: "0 0 0 9999px rgba(0,0,0,0.6)",
              background: "transparent",
              pointerEvents: "none",
              zIndex: 9999,
            }}
          />
        )}
      </div>

      {/* Tooltip */}
      {pos && (
        <div
          className="fixed z-[10000] w-[300px] rounded-xl border border-border/60 bg-card p-4 shadow-2xl"
          style={{ top: pos.top, left: pos.left }}
        >
          {/* Step counter + close */}
          <div className="mb-2 flex items-center justify-between">
            <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground/60">
              Step {step + 1} of {STEPS.length}
            </span>
            <button onClick={onEnd} className="text-muted-foreground/50 hover:text-foreground">
              <X className="h-3.5 w-3.5" />
            </button>
          </div>

          {/* Progress dots */}
          <div className="mb-3 flex gap-1">
            {STEPS.map((_, i) => (
              <div
                key={i}
                className={cn(
                  "h-1 rounded-full transition-all duration-300",
                  i === step ? "w-5 bg-primary" : i < step ? "w-1.5 bg-primary/40" : "w-1.5 bg-border/50"
                )}
              />
            ))}
          </div>

          <p className="text-sm font-semibold text-foreground mb-1">{currentStep.title}</p>
          <p className="text-xs text-muted-foreground leading-relaxed">{currentStep.description}</p>

          <div className="mt-4 flex items-center justify-between gap-2">
            <Button
              variant="ghost" size="sm"
              className="h-7 px-2 text-xs text-muted-foreground"
              onClick={prev}
              disabled={step === 0}
            >
              <ChevronLeft className="h-3.5 w-3.5 mr-1" />
              Back
            </Button>
            <Button
              size="sm"
              className="h-7 gap-1 px-3 text-xs"
              onClick={next}
            >
              {step === STEPS.length - 1 ? "Done" : "Next"}
              {step < STEPS.length - 1 && <ChevronRight className="h-3.5 w-3.5" />}
            </Button>
          </div>
        </div>
      )}
    </>,
    document.body
  );
}
