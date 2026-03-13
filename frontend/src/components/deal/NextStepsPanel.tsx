import { useState } from "react";
import {
  Zap, RefreshCw, Target, Clock, AlertCircle, AlertTriangle, Users,
  Mail, Phone, MessageCircle, ChevronRight,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import { useToast } from "@/hooks/use-toast";

// ── Types ─────────────────────────────────────────────────────────────────────

interface NextStep {
  action: string;
  channel: "email" | "call" | "whatsapp";
  contact: string;
  timing: string;
  why: string;
  message_hint: string;
}

interface KeyContact {
  name: string;
  role: string;
  last_contact_days: number;
  engagement?: string;
}

interface EmailIntelligence {
  last_buyer_reply: string;
  buyer_tone: "positive" | "neutral" | "cool" | "disengaged" | "urgent";
  crm_gap: string;
  key_commitment: string;
}

interface NextStepsSections {
  situation: string;
  last_interaction: string;
  next_steps: NextStep[];
  open_loops: string[];
  key_contacts: KeyContact[];
  watch_out: string[];
  one_liner: string;
  email_intelligence: EmailIntelligence;
}

interface Warning {
  type: string;
  severity: string;
  title: string;
  message: string;
  suggested_action?: string;
  days_affected?: number | null;
}

interface NextStepsResponse {
  deal_id: string;
  deal_name: string;
  company: string;
  amount: number;
  stage: string;
  health_score: number;
  generated_at: string;
  sections: NextStepsSections;
  warnings: Warning[];
  cached: boolean;
}

interface Props {
  dealId: string;
}

// ── Channel config ─────────────────────────────────────────────────────────────

const CHANNEL_CONFIG = {
  email: {
    icon: Mail,
    label: "Email",
    color: "text-sky-400",
    bg: "bg-sky-500/10 border-sky-500/20",
    badge: "bg-sky-500/15 text-sky-400",
  },
  call: {
    icon: Phone,
    label: "Call",
    color: "text-emerald-400",
    bg: "bg-emerald-500/10 border-emerald-500/20",
    badge: "bg-emerald-500/15 text-emerald-400",
  },
  whatsapp: {
    icon: MessageCircle,
    label: "WhatsApp",
    color: "text-green-400",
    bg: "bg-green-500/10 border-green-500/20",
    badge: "bg-green-500/15 text-green-400",
  },
} as const;

const TONE_COLOR: Record<string, string> = {
  positive: "text-emerald-400",
  neutral: "text-muted-foreground",
  cool: "text-amber-400",
  disengaged: "text-rose-400",
  urgent: "text-sky-400",
};

// ── Component ─────────────────────────────────────────────────────────────────

export default function NextStepsPanel({ dealId }: Props) {
  const { toast } = useToast();
  const [card, setCard] = useState<NextStepsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [meetingContext, setMeetingContext] = useState("");

  async function generate(forceRefresh = false) {
    setLoading(true);
    try {
      if (forceRefresh) {
        await api.clearNextStepsCache(dealId);
      }
      const result = await api.generateNextSteps(dealId, meetingContext) as NextStepsResponse;
      setCard(result);
    } catch {
      toast({ title: "Failed to generate next steps", variant: "destructive" });
    } finally {
      setLoading(false);
    }
  }

  // ── Empty state ──────────────────────────────────────────────────────────

  if (!card && !loading) {
    return (
      <div className="flex flex-col items-center justify-center py-10 gap-4">
        <div className="w-12 h-12 rounded-2xl bg-sky-500/15 border border-sky-500/25 flex items-center justify-center">
          <ChevronRight size={22} className="text-sky-400" strokeWidth={2} />
        </div>
        <div className="text-center">
          <p className="text-foreground font-semibold mb-1">Next Steps</p>
          <p className="text-muted-foreground/70 text-sm max-w-[280px]">
            AI-recommended actions with the right channel — email, call, or WhatsApp — based on deal history and emails.
          </p>
        </div>

        <input
          type="text"
          placeholder="Context (optional): renewal, pricing call, stalled…"
          value={meetingContext}
          onChange={(e) => setMeetingContext(e.target.value)}
          className="w-full max-w-xs bg-muted/50 border border-border rounded-xl px-3 py-2 text-sm text-foreground/80 placeholder:text-muted-foreground/40 focus:outline-none focus:border-sky-500/50"
        />

        <button
          onClick={() => generate(false)}
          className="flex items-center gap-2 bg-sky-600 hover:bg-sky-500 text-white text-sm font-medium px-5 py-2.5 rounded-xl transition-colors"
        >
          <Zap size={14} strokeWidth={2.5} />
          Generate Next Steps
        </button>
      </div>
    );
  }

  // ── Loading state ────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-10 gap-3">
        <div className="w-10 h-10 rounded-full border-2 border-sky-500/30 border-t-sky-400 animate-spin" />
        <p className="text-muted-foreground text-sm">Analyzing deal history…</p>
        <p className="text-muted-foreground/50 text-xs">Reading emails, notes, and CRM signals</p>
      </div>
    );
  }

  // ── Card content ─────────────────────────────────────────────────────────

  const s = card!.sections;
  const ei = s.email_intelligence;

  return (
    <div className="space-y-4">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-lg bg-sky-500/20 flex items-center justify-center">
            <ChevronRight size={13} className="text-sky-400" strokeWidth={2.5} />
          </div>
          <span className="text-sm font-semibold text-foreground">Next Steps</span>
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
          <span className="text-xs text-sky-400 uppercase tracking-wider font-semibold">What needs to happen</span>
        </div>
        <p className="text-foreground font-medium text-sm leading-relaxed">{s.one_liner}</p>
      </div>

      {/* Next steps — primary section */}
      {s.next_steps && s.next_steps.length > 0 && (
        <div className="space-y-2.5">
          <div className="flex items-center gap-2">
            <Zap size={13} className="text-sky-400" strokeWidth={2.5} />
            <span className="text-xs text-sky-400 uppercase tracking-wider font-semibold">Recommended Actions</span>
          </div>
          {s.next_steps.map((step, i) => {
            const ch = CHANNEL_CONFIG[step.channel] ?? CHANNEL_CONFIG.email;
            const ChannelIcon = ch.icon;
            return (
              <div key={i} className={cn("border rounded-2xl p-4 space-y-2", ch.bg)}>
                {/* Row 1: priority badge + channel + contact + timing */}
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="w-5 h-5 rounded-full bg-foreground/10 flex items-center justify-center text-foreground/60 text-xs font-bold flex-shrink-0">
                    {i + 1}
                  </span>
                  <span className={cn("flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full", ch.badge)}>
                    <ChannelIcon size={10} strokeWidth={2.5} />
                    {ch.label}
                  </span>
                  {step.contact && (
                    <span className="text-xs text-muted-foreground/70 font-medium">→ {step.contact}</span>
                  )}
                  <span className="ml-auto text-xs text-muted-foreground/50 flex-shrink-0">{step.timing}</span>
                </div>

                {/* Row 2: action */}
                <p className="text-foreground/90 text-sm font-medium leading-snug">{step.action}</p>

                {/* Row 3: message hint */}
                {step.message_hint && (
                  <p className="text-muted-foreground/60 text-xs italic leading-relaxed border-l-2 border-border pl-2">
                    "{step.message_hint}"
                  </p>
                )}

                {/* Row 4: why */}
                {step.why && (
                  <p className="text-muted-foreground/50 text-xs leading-relaxed">
                    Why: {step.why}
                  </p>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Situation */}
      <div className="bg-muted/40 rounded-2xl p-4">
        <div className="flex items-center gap-2 mb-2">
          <Clock size={13} className="text-muted-foreground" strokeWidth={2} />
          <span className="text-xs text-muted-foreground/70 uppercase tracking-wider font-medium">Situation</span>
        </div>
        <p className="text-foreground/80 text-sm leading-relaxed">{s.situation}</p>
      </div>

      {/* Last interaction */}
      <div className="bg-muted/40 rounded-2xl p-4">
        <div className="flex items-center gap-2 mb-1.5">
          <Clock size={12} className="text-muted-foreground/60" strokeWidth={2} />
          <span className="text-xs text-muted-foreground/60 uppercase tracking-wider font-medium">Last Touchpoint</span>
        </div>
        <p className="text-foreground/70 text-sm leading-relaxed">{s.last_interaction}</p>
      </div>

      {/* Email intelligence */}
      {ei && (
        <div className="bg-muted/40 rounded-2xl p-4">
          <div className="flex items-center gap-2 mb-3">
            <Mail size={13} className="text-muted-foreground" strokeWidth={2} />
            <span className="text-xs text-muted-foreground/70 uppercase tracking-wider font-medium">Email Intelligence</span>
          </div>
          <div className="space-y-1.5 text-xs">
            <div className="flex items-start gap-2">
              <span className="text-muted-foreground/50 w-28 flex-shrink-0">Last buyer reply</span>
              <span className="text-foreground/70">{ei.last_buyer_reply}</span>
            </div>
            <div className="flex items-start gap-2">
              <span className="text-muted-foreground/50 w-28 flex-shrink-0">Buyer tone</span>
              <span className={cn("font-medium capitalize", TONE_COLOR[ei.buyer_tone] ?? "text-muted-foreground")}>{ei.buyer_tone}</span>
            </div>
            {ei.key_commitment && ei.key_commitment !== "none" && (
              <div className="flex items-start gap-2">
                <span className="text-muted-foreground/50 w-28 flex-shrink-0">Open commitment</span>
                <span className="text-amber-300/80">{ei.key_commitment}</span>
              </div>
            )}
            {ei.crm_gap && ei.crm_gap !== "No gap detected" && (
              <div className="flex items-start gap-2">
                <span className="text-muted-foreground/50 w-28 flex-shrink-0">CRM gap</span>
                <span className="text-rose-300/80">{ei.crm_gap}</span>
              </div>
            )}
          </div>
        </div>
      )}

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
        <div className="bg-muted/40 rounded-2xl p-4">
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
                <div className="flex items-center gap-2">
                  {contact.engagement && (
                    <span className={cn("text-xs capitalize", {
                      "text-emerald-400": contact.engagement === "hot",
                      "text-sky-400": contact.engagement === "warm",
                      "text-amber-400": contact.engagement === "cold",
                      "text-rose-400": contact.engagement === "silent",
                    })}>{contact.engagement}</span>
                  )}
                  {contact.last_contact_days >= 0 && (
                    <span className={cn("text-xs", contact.last_contact_days > 14 ? "text-rose-400" : "text-muted-foreground/70")}>
                      {contact.last_contact_days}d ago
                    </span>
                  )}
                </div>
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
