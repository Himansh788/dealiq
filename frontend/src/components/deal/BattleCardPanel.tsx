import { useState } from "react";
import {
  Zap, RefreshCw, Target, BookOpen, Clock, MessageSquare,
  AlertCircle, AlertTriangle, Users,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import { useToast } from "@/hooks/use-toast";

// ── Types ─────────────────────────────────────────────────────────────────────

interface KeyContact {
  name: string;
  role: string;
  last_contact_days: number;
}

interface BattleCardSections {
  situation: string;
  last_interaction: string;
  open_loops: string[];
  key_contacts: KeyContact[];
  talk_track: string[];
  watch_out: string[];
  one_liner: string;
}

interface Warning {
  type: string;
  severity: string;
  title: string;
  message: string;
  suggested_action?: string;
  days_affected?: number | null;
}

interface BattleCardResponse {
  deal_id: string;
  deal_name: string;
  company: string;
  amount: number;
  stage: string;
  health_score: number;
  generated_at: string;
  sections: BattleCardSections;
  warnings: Warning[];
  cached: boolean;
}

interface Props {
  dealId: string;
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function BattleCardPanel({ dealId }: Props) {
  const { toast } = useToast();
  const [card, setCard] = useState<BattleCardResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [meetingContext, setMeetingContext] = useState("");

  async function generate(forceRefresh = false) {
    setLoading(true);
    try {
      if (forceRefresh) {
        await api.clearBattleCardCache(dealId);
      }
      const result = await api.generateBattleCard(dealId, meetingContext) as BattleCardResponse;
      setCard(result);
    } catch (err) {
      toast({ title: "Failed to generate battle card", variant: "destructive" });
    } finally {
      setLoading(false);
    }
  }

  // ── Empty state ──────────────────────────────────────────────────────────

  if (!card && !loading) {
    return (
      <div className="flex flex-col items-center justify-center py-10 gap-4">
        <div className="w-12 h-12 rounded-2xl bg-sky-500/15 border border-sky-500/25 flex items-center justify-center">
          <Zap size={22} className="text-sky-400" strokeWidth={2} />
        </div>
        <div className="text-center">
          <p className="text-foreground font-semibold mb-1">Pre-Meeting Battle Card</p>
          <p className="text-muted-foreground/70 text-sm max-w-[260px]">
            AI-generated brief for your next call. Takes ~5 seconds.
          </p>
        </div>

        <input
          type="text"
          placeholder="Meeting type (optional): renewal, demo, pricing…"
          value={meetingContext}
          onChange={(e) => setMeetingContext(e.target.value)}
          className="w-full max-w-xs bg-muted/50 border border-border rounded-xl px-3 py-2 text-sm text-foreground/80 placeholder:text-muted-foreground/40 focus:outline-none focus:border-sky-500/50"
        />

        <button
          onClick={() => generate(false)}
          className="flex items-center gap-2 bg-sky-600 hover:bg-sky-500 text-white text-sm font-medium px-5 py-2.5 rounded-xl transition-colors"
        >
          <Zap size={14} strokeWidth={2.5} />
          Generate Battle Card
        </button>
      </div>
    );
  }

  // ── Loading state ────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-10 gap-3">
        <div className="w-10 h-10 rounded-full border-2 border-sky-500/30 border-t-sky-400 animate-spin" />
        <p className="text-muted-foreground text-sm">Generating battle card…</p>
        <p className="text-muted-foreground/50 text-xs">Analyzing deal history and signals</p>
      </div>
    );
  }

  // ── Card content ─────────────────────────────────────────────────────────

  const s = card!.sections;

  return (
    <div className="space-y-4">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-lg bg-sky-500/20 flex items-center justify-center">
            <Zap size={13} className="text-sky-400" strokeWidth={2.5} />
          </div>
          <span className="text-sm font-semibold text-foreground">Battle Card</span>
          {card!.cached && (
            <span className="text-xs text-muted-foreground/50 bg-muted/50 px-2 py-0.5 rounded-full">cached</span>
          )}
        </div>
        <button
          onClick={() => generate(true)}
          className="flex items-center gap-1.5 text-xs text-muted-foreground/70 hover:text-foreground/80 transition-colors"
        >
          <RefreshCw size={11} strokeWidth={2.5} />
          Refresh
        </button>
      </div>

      {/* One liner */}
      <div className="bg-sky-500/10 border border-sky-500/25 rounded-2xl p-4">
        <div className="flex items-center gap-2 mb-2">
          <Target size={13} className="text-sky-400" strokeWidth={2.5} />
          <span className="text-xs text-sky-400 uppercase tracking-wider font-semibold">Goal for this call</span>
        </div>
        <p className="text-foreground font-medium text-sm leading-relaxed">{s.one_liner}</p>
      </div>

      {/* Situation */}
      <div className="bg-muted/50/60 rounded-2xl p-4">
        <div className="flex items-center gap-2 mb-2">
          <BookOpen size={13} className="text-muted-foreground" strokeWidth={2} />
          <span className="text-xs text-muted-foreground/70 uppercase tracking-wider font-medium">Situation</span>
        </div>
        <p className="text-foreground/80 text-sm leading-relaxed">{s.situation}</p>
      </div>

      {/* Last interaction */}
      <div className="bg-muted/50/60 rounded-2xl p-4">
        <div className="flex items-center gap-2 mb-2">
          <Clock size={13} className="text-muted-foreground" strokeWidth={2} />
          <span className="text-xs text-muted-foreground/70 uppercase tracking-wider font-medium">Last Interaction</span>
        </div>
        <p className="text-foreground/80 text-sm leading-relaxed">{s.last_interaction}</p>
      </div>

      {/* Talk track */}
      <div className="bg-muted/50/60 rounded-2xl p-4">
        <div className="flex items-center gap-2 mb-3">
          <MessageSquare size={13} className="text-emerald-400" strokeWidth={2} />
          <span className="text-xs text-emerald-400 uppercase tracking-wider font-semibold">Talk Track</span>
        </div>
        <div className="space-y-2">
          {s.talk_track.map((item, i) => (
            <div key={i} className="flex items-start gap-2.5">
              <div className="w-5 h-5 rounded-full bg-emerald-500/15 border border-emerald-500/25 flex items-center justify-center flex-shrink-0 mt-0.5">
                <span className="text-emerald-400 text-xs font-bold">{i + 1}</span>
              </div>
              <p className="text-foreground/80 text-sm leading-relaxed">{item}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Open loops */}
      {s.open_loops.length > 0 && (
        <div className="bg-amber-500/8 border border-amber-500/20 rounded-2xl p-4">
          <div className="flex items-center gap-2 mb-3">
            <AlertCircle size={13} className="text-amber-400" strokeWidth={2} />
            <span className="text-xs text-amber-400 uppercase tracking-wider font-semibold">Open Loops</span>
            <span className="text-xs text-amber-500/60">— follow up on these</span>
          </div>
          <div className="space-y-1.5">
            {s.open_loops.map((loop, i) => (
              <div key={i} className="flex items-start gap-2">
                <div className="w-1.5 h-1.5 rounded-full bg-amber-400 mt-1.5 flex-shrink-0" />
                <p className="text-amber-200/80 text-sm">{loop}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Watch out */}
      {s.watch_out.length > 0 && (
        <div className="bg-rose-500/8 border border-rose-500/20 rounded-2xl p-4">
          <div className="flex items-center gap-2 mb-3">
            <AlertTriangle size={13} className="text-rose-400" strokeWidth={2.5} />
            <span className="text-xs text-rose-400 uppercase tracking-wider font-semibold">Watch Out</span>
          </div>
          <div className="space-y-1.5">
            {s.watch_out.map((risk, i) => (
              <div key={i} className="flex items-start gap-2">
                <div className="w-1.5 h-1.5 rounded-full bg-rose-400 mt-1.5 flex-shrink-0" />
                <p className="text-rose-200/80 text-sm">{risk}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Key contacts */}
      {s.key_contacts.length > 0 && (
        <div className="bg-muted/50/60 rounded-2xl p-4">
          <div className="flex items-center gap-2 mb-3">
            <Users size={13} className="text-muted-foreground" strokeWidth={2} />
            <span className="text-xs text-muted-foreground/70 uppercase tracking-wider font-medium">Key Contacts</span>
          </div>
          <div className="space-y-2">
            {s.key_contacts.map((contact, i) => (
              <div key={i} className="flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <div className="w-7 h-7 rounded-full bg-muted/70 flex items-center justify-center flex-shrink-0">
                    <span className="text-muted-foreground text-xs font-medium">
                      {contact.name !== "Unknown" ? contact.name[0].toUpperCase() : "?"}
                    </span>
                  </div>
                  <div>
                    <p className="text-foreground/80 text-xs font-medium">{contact.name}</p>
                    <p className="text-muted-foreground/50 text-xs">{contact.role}</p>
                  </div>
                </div>
                {contact.last_contact_days >= 0 && (
                  <span className={cn("text-xs", contact.last_contact_days > 14 ? "text-rose-400" : "text-muted-foreground/70")}>
                    {contact.last_contact_days}d ago
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      <p className="text-xs text-muted-foreground/40 text-center pb-2">
        Generated {new Date(card!.generated_at).toLocaleString()}
      </p>
    </div>
  );
}
