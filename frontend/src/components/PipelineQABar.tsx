import { useState, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/hooks/use-toast";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  Sparkles,
  Send,
  X,
  Copy,
  ChevronRight,
  AlertTriangle,
} from "lucide-react";

// ── Types ─────────────────────────────────────────────────────────────────────

interface DealRef {
  deal_id: string;
  deal_name: string;
}

interface PipelineAnswer {
  answer: string;
  deals_referenced: DealRef[];
  confidence: "high" | "medium" | "low";
  processing_time_ms?: number;
}

interface Props {
  /** Called when user clicks a referenced deal badge — opens the deal panel */
  onSelectDeal?: (dealId: string) => void;
}

// ── Constants ─────────────────────────────────────────────────────────────────

const PRESET_QUESTIONS = [
  "Which deals are at risk and why?",
  "What deals have no next step defined?",
  "Summarise my pipeline health in 3 sentences",
  "Which deals have gone quiet in the last 2 weeks?",
  "Which deals mentioned discounts?",
];

const CONFIDENCE_DOT: Record<string, string> = {
  high: "bg-health-green",
  medium: "bg-health-yellow",
  low: "bg-muted-foreground",
};

const CONFIDENCE_LABEL: Record<string, string> = {
  high: "text-health-green",
  medium: "text-health-yellow",
  low: "text-muted-foreground",
};

// ── Component ─────────────────────────────────────────────────────────────────

export default function PipelineQABar({ onSelectDeal }: Props) {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [answer, setAnswer] = useState<PipelineAnswer | null>(null);
  const [askedQ, setAskedQ] = useState("");
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const { toast } = useToast();

  const ask = async (q: string) => {
    const trimmed = q.trim();
    if (!trimmed || loading) return;
    setQuestion("");
    setAskedQ(trimmed);
    setAnswer(null);
    setLoading(true);
    try {
      const data = await api.askPipeline(trimmed);
      setAnswer({
        answer: data.answer ?? "No answer returned.",
        deals_referenced: data.deals_referenced ?? [],
        confidence: data.confidence ?? "medium",
        processing_time_ms: data.processing_time_ms,
      });
    } catch (err: any) {
      toast({ title: "Pipeline Q&A error", description: err.message, variant: "destructive" });
      setAskedQ("");
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      ask(question);
    }
  };

  const clear = () => {
    setAnswer(null);
    setAskedQ("");
    setQuestion("");
    inputRef.current?.focus();
  };

  const hasResult = !loading && (answer || askedQ);

  return (
    <div className={cn(
      "overflow-hidden rounded-xl border transition-all duration-200",
      hasResult
        ? "border-violet-500/30 bg-violet-500/5"
        : "border-border/40 bg-card/60 hover:border-border/60"
    )}>

      {/* ── Input row ── */}
      <div className="flex items-start gap-3 px-4 py-3.5">

        {/* Icon */}
        <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-violet-500/20">
          <Sparkles className="h-3.5 w-3.5 text-violet-400" />
        </div>

        {/* Label + input stacked */}
        <div className="flex-1 min-w-0 space-y-2">
          <p className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground/60">
            Ask about your pipeline
          </p>

          <div className="flex items-end gap-2">
            <textarea
              ref={inputRef}
              value={question}
              onChange={e => setQuestion(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="e.g. Which deals are at risk? · What deals closed this month?"
              rows={1}
              disabled={loading}
              className={cn(
                "flex-1 resize-none rounded-lg border bg-background/50 px-3 py-2 text-sm text-foreground",
                "placeholder:text-muted-foreground/40 focus:outline-none focus:ring-1 focus:ring-violet-500/50",
                "border-border/40 transition-colors disabled:opacity-50",
                "leading-relaxed min-h-[36px]"
              )}
              style={{ fieldSizing: "content", maxHeight: "120px" } as React.CSSProperties}
            />
            <Button
              onClick={() => ask(question)}
              disabled={!question.trim() || loading}
              className="shrink-0 bg-violet-600 hover:bg-violet-500 font-semibold h-9 px-3"
              size="sm"
            >
              {loading
                ? <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                : <Send className="h-3.5 w-3.5" />
              }
            </Button>
          </div>

          {/* Preset pills */}
          <div className="flex flex-wrap gap-1.5 pt-1">
            {PRESET_QUESTIONS.map((q, i) => (
              <button
                key={i}
                onClick={() => ask(q)}
                disabled={loading}
                className={cn(
                  "rounded-full border px-2.5 py-0.5 text-[11px] font-medium transition-all duration-300 whitespace-nowrap fade-slide-in",
                  "border-border/40 bg-secondary/40 text-muted-foreground",
                  "hover:border-violet-500/40 hover:bg-violet-500/10 hover:text-violet-400",
                  "disabled:pointer-events-none disabled:opacity-40"
                )}
                style={{ animationDelay: `${i * 60 + 100}ms` }}
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* ── Loading skeleton ── */}
      {loading && (
        <div className="border-t border-violet-500/10 px-4 pb-4 pt-3 space-y-2">
          <p className="text-[11px] text-muted-foreground/60 animate-pulse">
            Analysing {askedQ.length > 60 ? askedQ.slice(0, 60) + "…" : askedQ}
          </p>
          <Skeleton className="h-4 w-full rounded" />
          <Skeleton className="h-4 w-4/5 rounded" />
          <Skeleton className="h-4 w-3/5 rounded" />
        </div>
      )}

      {/* ── Answer ── */}
      {!loading && answer && (
        <div className="border-t border-violet-500/15 px-4 pb-4 pt-3 space-y-3 bg-gradient-to-r from-violet-500/10 to-transparent border-l-[3px] border-l-violet-500 fade-slide-in">

          {/* Question echo + clear */}
          <div className="flex items-start justify-between gap-3">
            <p className="text-[11px] text-muted-foreground/60 leading-relaxed">
              <span className="font-medium text-muted-foreground/80">Q: </span>
              {askedQ}
            </p>
            <button
              onClick={clear}
              className="mt-px shrink-0 text-muted-foreground/40 transition-colors hover:text-muted-foreground"
              aria-label="Clear answer"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>

          {/* Answer text */}
          <p className="text-sm text-foreground leading-relaxed whitespace-pre-wrap">
            {answer.answer}
          </p>

          {/* Referenced deals */}
          {answer.deals_referenced.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5 pt-0.5">
              <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/50 mr-1">
                Referenced
              </span>
              {answer.deals_referenced.map((d, i) => (
                <button
                  key={i}
                  onClick={() => onSelectDeal?.(d.deal_id)}
                  disabled={!onSelectDeal}
                  className={cn(
                    "inline-flex items-center gap-1 rounded-full border border-violet-500/25 bg-violet-500/10",
                    "px-2.5 py-0.5 text-[11px] font-medium text-violet-400",
                    "transition-colors",
                    onSelectDeal
                      ? "cursor-pointer hover:border-violet-500/50 hover:bg-violet-500/20"
                      : "cursor-default"
                  )}
                >
                  {d.deal_name}
                  {onSelectDeal && <ChevronRight className="h-3 w-3 opacity-60" />}
                </button>
              ))}
            </div>
          )}

          {/* Footer row */}
          <div className="flex items-center gap-3 pt-0.5">
            {/* Confidence indicator */}
            <div className="flex items-center gap-1.5">
              <span className={cn(
                "h-1.5 w-1.5 rounded-full shrink-0",
                CONFIDENCE_DOT[answer.confidence] ?? "bg-muted-foreground"
              )} />
              <span className={cn(
                "text-[10px] font-medium capitalize",
                CONFIDENCE_LABEL[answer.confidence] ?? "text-muted-foreground"
              )}>
                {answer.confidence} confidence
              </span>
            </div>

            {/* Processing time */}
            {answer.processing_time_ms != null && (
              <span className="text-[10px] text-muted-foreground/40 tabular-nums">
                {answer.processing_time_ms}ms
              </span>
            )}

            {/* Copy */}
            <Button
              variant="ghost"
              size="sm"
              className="ml-auto h-6 px-2 text-[10px] text-muted-foreground hover:text-foreground"
              onClick={() => {
                navigator.clipboard.writeText(answer.answer);
                toast({ title: "Answer copied" });
              }}
            >
              <Copy className="mr-1 h-3 w-3" />
              Copy
            </Button>

            {/* Ask another */}
            <Button
              variant="ghost"
              size="sm"
              className="h-6 px-2 text-[10px] text-violet-400 hover:text-violet-300"
              onClick={clear}
            >
              Ask another
            </Button>
          </div>

          {/* No deals found nudge */}
          {answer.deals_referenced.length === 0 && answer.confidence === "low" && (
            <div className="flex items-start gap-2 rounded-lg border border-border/30 bg-secondary/30 px-3 py-2">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground/50" />
              <p className="text-[11px] text-muted-foreground leading-relaxed">
                The AI had limited data to work with. Try opening a specific deal for deeper analysis.
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
