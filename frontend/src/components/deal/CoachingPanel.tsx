import { useState } from "react";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/hooks/use-toast";
import { api } from "@/lib/api";
import {
  GraduationCap, AlertTriangle, AlertCircle, Check, Sparkles, Mic2
} from "lucide-react";
import { cn } from "@/lib/utils";

// ── Types ─────────────────────────────────────────────────────────────────────

interface KeyMoment {
  type: string;
  text: string;
  position_pct: number;
}

interface CoachingResult {
  rep_label: string | null;
  prospect_label: string | null;
  talk_ratio_rep: number;
  talk_ratio_prospect: number;
  estimated_duration_minutes: number;
  longest_monologue_seconds: number;
  question_count_rep: number;
  question_count_prospect: number;
  filler_word_count: number;
  filler_words_per_minute: number;
  filler_breakdown: Record<string, number>;
  key_moments: KeyMoment[];
  coaching_tips: string[];
  overall_score: number;
  score_rationale: string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtSeconds(s: number): string {
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const r = s % 60;
  return r > 0 ? `${m}m ${r}s` : `${m}m`;
}

type Status = "good" | "warn" | "bad";

function monologueStatus(s: number): Status {
  return s <= 76 ? "good" : s <= 150 ? "warn" : "bad";
}
function questionStatus(n: number): Status {
  return n >= 11 && n <= 14 ? "good" : n >= 7 ? "warn" : "bad";
}
function fillerStatus(r: number): Status {
  return r < 5 ? "good" : r < 8 ? "warn" : "bad";
}
function talkRatioStatus(pct: number): Status {
  const d = Math.abs(pct - 43);
  return d <= 7 ? "good" : d <= 17 ? "warn" : "bad";
}
function scoreColor(n: number) {
  return n >= 70 ? "text-health-green" : n >= 40 ? "text-health-yellow" : "text-health-red";
}

function statusIcon(s: Status) {
  if (s === "good") return <Check className="h-3 w-3 text-health-green" />;
  if (s === "warn") return <AlertCircle className="h-3 w-3 text-health-yellow" />;
  return <AlertTriangle className="h-3 w-3 text-health-red" />;
}

function statusText(s: Status) {
  if (s === "good") return "text-health-green";
  if (s === "warn") return "text-health-yellow";
  return "text-health-red";
}

const MOMENT_CONFIG: Record<string, string> = {
  objection:  "border-health-red/40 bg-health-red/10 text-health-red",
  competitor: "border-health-orange/40 bg-health-orange/10 text-health-orange",
  pricing:    "border-health-yellow/40 bg-health-yellow/10 text-health-yellow",
  commitment: "border-health-green/40 bg-health-green/10 text-health-green",
  question:   "border-primary/40 bg-primary/10 text-primary",
};

// ── Sub-components ────────────────────────────────────────────────────────────

function TalkRatioBar({ ratioRep, repLabel, prospectLabel }: {
  ratioRep: number; repLabel: string | null; prospectLabel: string | null;
}) {
  const st = talkRatioStatus(ratioRep);
  const barColor = st === "good" ? "bg-health-green" : st === "warn" ? "bg-health-yellow" : "bg-health-red";
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-xs">
        <span className={cn("font-semibold", statusText(st))}>{repLabel || "Rep"} {ratioRep}%</span>
        <span className="text-muted-foreground">{prospectLabel || "Prospect"} {Math.round(100 - ratioRep)}%</span>
      </div>
      <div className="relative h-3 w-full rounded-full bg-secondary overflow-visible">
        <div className={cn("h-3 rounded-full transition-all", barColor)} style={{ width: `${ratioRep}%` }} />
        {/* 43% benchmark tick */}
        <div className="absolute -top-1 bottom-[-4px] w-0.5 bg-white/50 rounded-full" style={{ left: "43%" }} />
      </div>
      <p className="text-[10px] text-muted-foreground/50 text-right">ideal 43% ↑</p>
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function CoachingPanel({ dealId, repName }: { dealId: string; repName?: string }) {
  const { toast } = useToast();
  const [transcript, setTranscript] = useState("");
  const [repNameInput, setRepNameInput] = useState(repName || "");
  const [loading, setLoading]   = useState(false);
  const [result, setResult]     = useState<CoachingResult | null>(null);

  const run = async (isDemo = false) => {
    if (!isDemo && transcript.trim().split(/\s+/).length < 50) {
      toast({ title: "Transcript too short", description: "Paste at least 50 words.", variant: "destructive" });
      return;
    }
    setLoading(true);
    setResult(null);
    try {
      const data = isDemo
        ? await api.getDemoCoaching()
        : await api.analyzeConversation(transcript, repNameInput || undefined);
      setResult(data as CoachingResult);
    } catch (e: any) {
      toast({ title: "Analysis failed", description: e.message ?? "Unknown error", variant: "destructive" });
    } finally {
      setLoading(false);
    }
  };

  // ── Input state ──────────────────────────────────────────────────────────

  if (!result && !loading) return (
    <div className="space-y-3 pb-2">
      <Input
        value={repNameInput}
        onChange={e => setRepNameInput(e.target.value)}
        placeholder="Rep name (optional — helps speaker detection)"
        className="h-8 text-xs border-border/50 bg-secondary/40"
      />
      <Textarea
        value={transcript}
        onChange={e => setTranscript(e.target.value)}
        placeholder={"Paste the call transcript here…\n\nFormat: Rep: text / Prospect: text\nLabeled speaker turns work best for talk ratio metrics."}
        className="min-h-[160px] resize-none border-border/50 bg-secondary/40 text-sm font-mono leading-relaxed focus-visible:ring-primary/40"
      />
      <div className="flex gap-2">
        <Button onClick={() => run(false)} size="sm" className="flex-1 bg-primary hover:bg-primary/90 text-white gap-1.5 text-xs">
          <Mic2 className="h-3.5 w-3.5" />
          Analyse Call
        </Button>
        <Button variant="outline" size="sm" onClick={() => run(true)}
          className="border-border/50 text-muted-foreground hover:text-foreground text-xs gap-1">
          <Sparkles className="h-3 w-3" />
          Demo
        </Button>
      </div>
    </div>
  );

  // ── Loading ──────────────────────────────────────────────────────────────

  if (loading) return (
    <div className="space-y-3 py-2">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <div className="h-3.5 w-3.5 rounded-full border-2 border-primary/30 border-t-primary animate-spin" />
        Analysing conversation metrics…
      </div>
      {[...Array(4)].map((_, i) => <Skeleton key={i} className="h-10 w-full rounded-lg" />)}
    </div>
  );

  if (!result) return null;

  // ── Results ──────────────────────────────────────────────────────────────

  const mono  = monologueStatus(result.longest_monologue_seconds);
  const qst   = questionStatus(result.question_count_rep);
  const fill  = fillerStatus(result.filler_words_per_minute);

  const metrics = [
    {
      label: "Monologue",
      value: fmtSeconds(result.longest_monologue_seconds),
      benchmark: "< 76s ideal",
      status: mono,
    },
    {
      label: "Rep questions",
      value: String(result.question_count_rep),
      benchmark: "11–14 ideal",
      status: qst,
    },
    {
      label: "Filler rate",
      value: `${result.filler_words_per_minute}/min`,
      benchmark: "< 5/min ideal",
      status: fill,
    },
  ];

  return (
    <div className="space-y-4 pb-2">

      {/* Score + rationale */}
      <div className="flex items-center gap-3 rounded-lg border border-border/40 bg-card/40 p-3">
        <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full border-2 border-border/40">
          <span className={cn("text-2xl font-black tabular-nums", scoreColor(result.overall_score))}>
            {result.overall_score}
          </span>
        </div>
        <div className="min-w-0">
          <p className="text-xs font-semibold text-foreground uppercase tracking-wide mb-0.5">Call Score</p>
          <p className="text-xs text-muted-foreground leading-relaxed line-clamp-2">{result.score_rationale}</p>
        </div>
      </div>

      {/* Talk ratio */}
      <div className="rounded-lg border border-border/40 bg-card/40 p-3 space-y-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground/60">Talk Ratio</p>
        <TalkRatioBar
          ratioRep={result.talk_ratio_rep}
          repLabel={result.rep_label}
          prospectLabel={result.prospect_label}
        />
      </div>

      {/* Metric pills */}
      <div className="grid grid-cols-3 gap-2">
        {metrics.map(m => (
          <div key={m.label} className={cn(
            "rounded-lg border p-2.5 text-center space-y-0.5",
            m.status === "good" ? "border-health-green/30 bg-health-green/5" :
            m.status === "warn" ? "border-health-yellow/30 bg-health-yellow/5" :
            "border-health-red/30 bg-health-red/5"
          )}>
            <div className="flex justify-center">{statusIcon(m.status)}</div>
            <p className={cn("text-sm font-bold tabular-nums", statusText(m.status))}>{m.value}</p>
            <p className="text-[10px] text-muted-foreground/60 leading-tight">{m.label}</p>
          </div>
        ))}
      </div>

      {/* Filler breakdown */}
      {Object.keys(result.filler_breakdown).length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {Object.entries(result.filler_breakdown).map(([word, count]) => (
            <span key={word} className="rounded-full border border-border/40 bg-secondary/40 px-2 py-0.5 text-xs text-muted-foreground">
              "{word}" ×{count}
            </span>
          ))}
        </div>
      )}

      {/* Coaching tips */}
      {result.coaching_tips.length > 0 && (
        <div className="rounded-lg border border-primary/20 bg-primary/5 p-3 space-y-2">
          <div className="flex items-center gap-1.5">
            <GraduationCap className="h-3.5 w-3.5 text-primary" />
            <span className="text-xs font-semibold text-primary uppercase tracking-wide">Coaching Tips</span>
          </div>
          <ul className="space-y-1.5">
            {result.coaching_tips.map((tip, i) => (
              <li key={i} className="flex items-start gap-1.5 text-xs text-foreground/80 leading-relaxed">
                <span className="text-primary mt-0.5 shrink-0">•</span>
                {tip}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Key moments */}
      {result.key_moments.length > 0 && (
        <div className="space-y-1.5">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground/50">Key Moments</p>
          {result.key_moments.slice(0, 6).map((m, i) => {
            const cls = MOMENT_CONFIG[m.type] ?? "border-border/40 text-muted-foreground bg-secondary/40";
            return (
              <div key={i} className="flex items-start gap-2">
                <Badge variant="outline" className={cn("text-[10px] shrink-0 px-1.5 capitalize", cls)}>
                  {m.type}
                </Badge>
                <p className="text-xs text-muted-foreground/80 leading-relaxed italic">"{m.text}"</p>
              </div>
            );
          })}
        </div>
      )}

      <button
        onClick={() => { setResult(null); setTranscript(""); }}
        className="w-full text-xs text-muted-foreground hover:text-foreground transition-colors py-1"
      >
        ↩ Analyse another transcript
      </button>
    </div>
  );
}
