import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import {
  CheckCircle2, Circle, Mail, Phone, MessageSquare, BookOpen,
  Calendar, FileText, Clock, AlertTriangle, ChevronDown, ChevronUp,
  Send, Copy, ExternalLink, Loader2, SkipForward, RefreshCw,
  TrendingDown, DollarSign, Target, ArrowRight, Zap, Video,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

// ═══════════════════════════════════════════════════════════════════════════════
// Types
// ═══════════════════════════════════════════════════════════════════════════════

interface DealIntelligence {
  health_summary?: string;
  nba_summary?: string;
  has_cached_analysis?: boolean;
}

interface DigestTask {
  id: string;
  deal_id: string;
  deal_name: string;
  company: string;
  stage: string;
  amount: number | null;
  amount_fmt: string;
  task_type: string;
  task_type_label: string;
  task_text: string;
  reason: string;
  is_completed: boolean;
  completed_at: string | null;
  sort_order: number;
  deal_intelligence?: DealIntelligence;
}

interface UntouchedDeal {
  deal_id: string;
  deal_name: string;
  company: string;
  stage: string;
  amount: number | null;
  amount_fmt: string;
  owner: string;
  days_since_contact: number;
  suggested_action: string;
}

interface DecliningDeal {
  deal_id: string;
  deal_name: string;
  amount: number;
  health_score: number;
  health_label: string;
  stage: string;
}

interface CalendarEvent {
  subject: string;
  start: string;
  deal_id?: string;
  teams_link?: string;
  web_link?: string;
}

interface DashboardData {
  focus: {
    actions_remaining: number;
    actions_total: number;
    actions_completed: number;
    deals_needing_attention: number;
    revenue_at_risk: number;
    next_meeting: CalendarEvent | null;
  };
  actions: DigestTask[];
  completed_today: DigestTask[];
  calendar: CalendarEvent[];
  intelligence: {
    pipeline_health: number;
    pipeline_value: number;
    total_deals: number;
    deals_declining: DecliningDeal[];
    untouched_deals: UntouchedDeal[];
    weekly_progress: {
      actions_completed: number;
      actions_total: number;
    };
  };
  simulated?: boolean;
}

interface EmailDraft {
  to: { email: string; name: string }[];
  subject: string;
  body_html: string;
  body_plain: string;
}

interface ExecutionData {
  type: string;
  ready_to_send?: boolean;
  draft?: EmailDraft;
  can_send_via_outlook?: boolean;
  contact?: { name: string; phone: string | null };
  script?: {
    opening: string;
    if_positive: string;
    if_objection_price: string;
    if_objection_timing: string;
    close: string;
  };
  key_talking_points?: string[];
  message?: string;
  whatsapp_deep_link?: string;
  can_create_via_outlook?: boolean;
  recommended_content?: { title: string; type: string; url: string; relevance_reason: string; key_stats: string }[];
  draft_email?: EmailDraft;
  error?: string;
}

// ═══════════════════════════════════════════════════════════════════════════════
// Constants
// ═══════════════════════════════════════════════════════════════════════════════

const TASK_ICON: Record<string, React.ElementType> = {
  email: Mail, call: Phone, whatsapp: MessageSquare, case_study: BookOpen,
  meeting: Calendar, contract: FileText, re_engage: RefreshCw,
};

const TASK_COLOR: Record<string, string> = {
  email: "text-blue-400 bg-blue-500/10",
  call: "text-emerald-400 bg-emerald-500/10",
  whatsapp: "text-green-400 bg-green-500/10",
  case_study: "text-violet-400 bg-violet-500/10",
  meeting: "text-amber-400 bg-amber-500/10",
  contract: "text-orange-400 bg-orange-500/10",
  re_engage: "text-pink-400 bg-pink-500/10",
};

function formatCurrency(val: number): string {
  if (val >= 1_000_000) return `$${(val / 1_000_000).toFixed(1)}M`;
  if (val >= 1_000) return `$${Math.round(val / 1_000)}K`;
  return `$${Math.round(val)}`;
}

function formatTime(isoStr: string): string {
  try {
    return new Date(isoStr).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch {
    return isoStr;
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Utility: Copy button
// ═══════════════════════════════════════════════════════════════════════════════

function CopyButton({ text, label = "Copy" }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={async () => { await navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 2000); }}
      className="flex items-center gap-1 rounded px-2 py-1 text-[11px] text-muted-foreground hover:text-foreground hover:bg-secondary/60 transition-colors"
    >
      <Copy className="h-3 w-3" />
      {copied ? "Copied!" : label}
    </button>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// Execution Panels (email, call, whatsapp, meeting, case study)
// ═══════════════════════════════════════════════════════════════════════════════

function EmailExec({ exec, onExecute, onSkip, executing }: { exec: ExecutionData; onExecute: (a: string, p: any) => void; onSkip: () => void; executing: boolean }) {
  const draft = exec.draft;
  const [editMode, setEditMode] = useState(false);
  const [editedBody, setEditedBody] = useState(draft?.body_plain ?? "");
  const [editedSubject, setEditedSubject] = useState(draft?.subject ?? "");
  if (!draft) return null;

  return (
    <div className="mt-3 space-y-3">
      <div className="rounded-lg border border-border/30 bg-background/50 overflow-hidden">
        <div className="flex items-center gap-2 border-b border-border/30 px-3 py-2">
          <span className="text-[11px] text-muted-foreground/60">To:</span>
          <span className="text-[11px] text-foreground">{draft.to.map(r => r.name || r.email).join(", ")}</span>
        </div>
        <div className="flex items-center gap-2 border-b border-border/30 px-3 py-2">
          <span className="text-[11px] text-muted-foreground/60">Subject:</span>
          {editMode ? (
            <input value={editedSubject} onChange={e => setEditedSubject(e.target.value)} className="flex-1 bg-transparent text-[11px] text-foreground outline-none" />
          ) : (
            <span className="text-[11px] text-foreground font-medium">{draft.subject}</span>
          )}
        </div>
        <div className="px-3 py-3">
          {editMode ? (
            <Textarea value={editedBody} onChange={e => setEditedBody(e.target.value)} className="min-h-[120px] text-xs bg-transparent border-border/30 resize-none" />
          ) : (
            <div className="text-xs text-foreground/80 leading-relaxed prose prose-invert prose-xs max-w-none" dangerouslySetInnerHTML={{ __html: draft.body_html }} />
          )}
        </div>
      </div>
      <div className="flex items-center gap-2 flex-wrap">
        {exec.can_send_via_outlook ? (
          <Button size="sm" className="h-7 text-xs gap-1.5" onClick={() => onExecute("send_email", { subject: editedSubject, body_html: editMode ? editedBody.replace(/\n/g, "<br/>") : draft.body_html, to: draft.to, cc: [] })} disabled={executing}>
            {executing ? <Loader2 className="h-3 w-3 animate-spin" /> : <Send className="h-3 w-3" />}
            {executing ? "Sending..." : "Send via Outlook"}
          </Button>
        ) : (
          <CopyButton text={`${editedSubject}\n\n${draft.body_plain}`} label="Copy email" />
        )}
        <Button size="sm" variant="outline" className="h-7 text-xs border-border/40" onClick={() => setEditMode(v => !v)}>
          {editMode ? "Preview" : "Edit Draft"}
        </Button>
        <button onClick={onSkip} className="flex items-center gap-1 text-[11px] text-muted-foreground/60 hover:text-muted-foreground transition-colors ml-auto">
          <SkipForward className="h-3 w-3" /> Skip
        </button>
      </div>
    </div>
  );
}

function CallExec({ exec, onExecute, onSkip, executing }: { exec: ExecutionData; onExecute: (a: string, p: any) => void; onSkip: () => void; executing: boolean }) {
  const script = exec.script;
  const [outcome, setOutcome] = useState("");
  const [notes, setNotes] = useState("");
  if (!script) return null;

  const Line = ({ label, text }: { label: string; text: string }) => (
    <div className="rounded-lg border border-border/20 bg-card/40 p-3">
      <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/50 mb-1">{label}</p>
      <p className="text-xs text-foreground/80 leading-relaxed">{text}</p>
      <div className="flex justify-end mt-1"><CopyButton text={text} /></div>
    </div>
  );

  return (
    <div className="mt-3 space-y-2">
      {exec.key_talking_points && exec.key_talking_points.length > 0 && (
        <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-3">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-emerald-400/70 mb-1.5">Key talking points</p>
          <ul className="space-y-0.5">
            {exec.key_talking_points.map((pt, i) => (
              <li key={i} className="text-xs text-foreground/70 flex items-start gap-1.5">
                <span className="text-emerald-400/60 mt-0.5">·</span>{pt}
              </li>
            ))}
          </ul>
        </div>
      )}
      <Line label="Opening" text={script.opening} />
      <Line label="If they're engaged" text={script.if_positive} />
      <Line label="If they push back on price" text={script.if_objection_price} />
      <Line label="If the timing isn't right" text={script.if_objection_timing} />
      <Line label="Close" text={script.close} />
      <div className="rounded-lg border border-border/20 bg-card/30 p-3 space-y-2">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/50">Log call outcome</p>
        <div className="flex gap-2 flex-wrap">
          {["Connected", "Left voicemail", "No answer", "Not the right time"].map(o => (
            <button key={o} onClick={() => setOutcome(o)} className={cn("rounded-md border px-2.5 py-1 text-[11px] transition-colors", outcome === o ? "border-primary/50 bg-primary/10 text-primary" : "border-border/30 text-muted-foreground hover:border-border/50")}>{o}</button>
          ))}
        </div>
        <Textarea value={notes} onChange={e => setNotes(e.target.value)} placeholder="Add call notes (optional)..." className="min-h-[60px] text-xs bg-transparent border-border/30 resize-none" />
        <div className="flex items-center gap-2">
          <Button size="sm" className="h-7 text-xs" onClick={() => onExecute("log_call", { outcome, notes })} disabled={executing}>
            {executing ? <Loader2 className="h-3 w-3 animate-spin" /> : <CheckCircle2 className="h-3 w-3" />}
            Log & Mark Done
          </Button>
          <button onClick={onSkip} className="flex items-center gap-1 text-[11px] text-muted-foreground/60 hover:text-muted-foreground transition-colors ml-auto"><SkipForward className="h-3 w-3" />Skip</button>
        </div>
      </div>
    </div>
  );
}

function WhatsAppExec({ exec, onExecute, onSkip, executing }: { exec: ExecutionData; onExecute: (a: string, p: any) => void; onSkip: () => void; executing: boolean }) {
  const [msg, setMsg] = useState(exec.message ?? "");
  return (
    <div className="mt-3 space-y-3">
      <div className="rounded-lg border border-green-500/20 bg-green-500/5 p-3">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-green-400/70 mb-2">Pre-written message</p>
        <Textarea value={msg} onChange={e => setMsg(e.target.value)} className="min-h-[80px] text-xs bg-transparent border-border/30 resize-none text-foreground/80" />
      </div>
      <div className="flex items-center gap-2 flex-wrap">
        {exec.whatsapp_deep_link && (
          <Button size="sm" className="h-7 text-xs gap-1.5 bg-green-600 hover:bg-green-700 border-0" onClick={() => { window.open(`https://wa.me/?text=${encodeURIComponent(msg)}`, "_blank"); onExecute("mark_sent", { notes: "WhatsApp message sent" }); }} disabled={executing}>
            <ExternalLink className="h-3 w-3" /> Open WhatsApp
          </Button>
        )}
        <CopyButton text={msg} label="Copy message" />
        <Button size="sm" variant="outline" className="h-7 text-xs border-border/40" onClick={() => onExecute("mark_sent", { notes: "WhatsApp message sent manually" })} disabled={executing}>
          {executing ? <Loader2 className="h-3 w-3 animate-spin" /> : <CheckCircle2 className="h-3 w-3" />} Mark Sent
        </Button>
        <button onClick={onSkip} className="flex items-center gap-1 text-[11px] text-muted-foreground/60 hover:text-muted-foreground transition-colors ml-auto"><SkipForward className="h-3 w-3" />Skip</button>
      </div>
    </div>
  );
}

function MeetingExec({ exec, onExecute, onSkip, executing }: { exec: ExecutionData; onExecute: (a: string, p: any) => void; onSkip: () => void; executing: boolean }) {
  const draft = exec.draft as any;
  const [subject, setSubject] = useState(draft?.subject ?? "");
  return (
    <div className="mt-3 space-y-3">
      <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-3 space-y-2">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-amber-400/70">Invite draft</p>
        <div className="flex items-center gap-2">
          <span className="text-[11px] text-muted-foreground/60 w-16 shrink-0">Subject:</span>
          <input value={subject} onChange={e => setSubject(e.target.value)} className="flex-1 bg-transparent text-[11px] text-foreground outline-none border-b border-border/30 pb-0.5" />
        </div>
        {draft?.attendees?.length > 0 && (
          <div className="flex items-center gap-2">
            <span className="text-[11px] text-muted-foreground/60 w-16 shrink-0">Attendees:</span>
            <span className="text-[11px] text-foreground">{draft.attendees.map((a: any) => a.name || a.email).join(", ")}</span>
          </div>
        )}
      </div>
      <div className="flex items-center gap-2 flex-wrap">
        {exec.can_create_via_outlook ? (
          <Button size="sm" className="h-7 text-xs gap-1.5" onClick={() => { const t = new Date(); t.setDate(t.getDate() + 1); t.setHours(10, 0, 0, 0); onExecute("schedule_meeting", { subject, body_html: draft?.body_html ?? "", attendees: draft?.attendees ?? [], start_iso: t.toISOString(), duration_minutes: draft?.duration_minutes ?? 30 }); }} disabled={executing}>
            {executing ? <Loader2 className="h-3 w-3 animate-spin" /> : <Calendar className="h-3 w-3" />}
            {executing ? "Creating..." : "Create Invite"}
          </Button>
        ) : (
          <Button size="sm" variant="outline" className="h-7 text-xs border-border/40" onClick={() => onExecute("log_call", { outcome: "Meeting scheduled", notes: subject })} disabled={executing}>
            <CheckCircle2 className="h-3 w-3" /> Mark Scheduled
          </Button>
        )}
        <button onClick={onSkip} className="flex items-center gap-1 text-[11px] text-muted-foreground/60 hover:text-muted-foreground transition-colors ml-auto"><SkipForward className="h-3 w-3" />Skip</button>
      </div>
    </div>
  );
}

function CaseStudyExec({ exec, onExecute, onSkip, executing }: { exec: ExecutionData; onExecute: (a: string, p: any) => void; onSkip: () => void; executing: boolean }) {
  const items = exec.recommended_content ?? [];
  const draftEmail = exec.draft_email;
  return (
    <div className="mt-3 space-y-3">
      <div className="space-y-2">
        {items.map((item, i) => (
          <div key={i} className="flex items-start gap-3 rounded-lg border border-border/20 bg-card/30 p-3">
            <div className={cn("flex h-6 w-6 shrink-0 items-center justify-center rounded text-[10px] font-bold", item.type === "case_study" ? "bg-violet-500/15 text-violet-400" : "bg-blue-500/15 text-blue-400")}>
              {item.type === "case_study" ? "CS" : "B"}
            </div>
            <div className="flex-1 min-w-0">
              <a href={item.url} target="_blank" rel="noreferrer" className="text-xs font-medium text-foreground hover:text-primary transition-colors line-clamp-1">{item.title}</a>
              {item.relevance_reason && <p className="text-[11px] text-muted-foreground/60 mt-0.5">{item.relevance_reason}</p>}
            </div>
          </div>
        ))}
      </div>
      {draftEmail && (
        <div className="flex items-center gap-2 flex-wrap">
          {exec.can_send_via_outlook ? (
            <Button size="sm" className="h-7 text-xs gap-1.5" onClick={() => onExecute("send_resources", { subject: draftEmail.subject, body_html: draftEmail.body_html, to: draftEmail.to, cc: [] })} disabled={executing}>
              {executing ? <Loader2 className="h-3 w-3 animate-spin" /> : <Send className="h-3 w-3" />}
              {executing ? "Sending..." : "Send Resources"}
            </Button>
          ) : (
            <CopyButton text={`${draftEmail.subject}\n\n${draftEmail.body_plain}`} label="Copy email" />
          )}
          <button onClick={onSkip} className="flex items-center gap-1 text-[11px] text-muted-foreground/60 hover:text-muted-foreground transition-colors ml-auto"><SkipForward className="h-3 w-3" />Skip</button>
        </div>
      )}
    </div>
  );
}

function ExecutionPanel({ exec, onExecute, onSkip, executing }: { exec: ExecutionData | null; onExecute: (a: string, p: any) => void; onSkip: () => void; executing: boolean }) {
  if (!exec) return null;
  if (exec.type === "error") return <div className="mt-3 rounded-lg border border-destructive/20 bg-destructive/5 px-3 py-2 text-xs text-destructive/70">Could not generate execution content — {exec.error}</div>;
  if (exec.type === "email") return <EmailExec exec={exec} onExecute={onExecute} onSkip={onSkip} executing={executing} />;
  if (exec.type === "call_script") return <CallExec exec={exec} onExecute={onExecute} onSkip={onSkip} executing={executing} />;
  if (exec.type === "whatsapp_message") return <WhatsAppExec exec={exec} onExecute={onExecute} onSkip={onSkip} executing={executing} />;
  if (exec.type === "calendar_invite") return <MeetingExec exec={exec} onExecute={onExecute} onSkip={onSkip} executing={executing} />;
  if (exec.type === "content_recommendation") return <CaseStudyExec exec={exec} onExecute={onExecute} onSkip={onSkip} executing={executing} />;
  return null;
}

// ═══════════════════════════════════════════════════════════════════════════════
// Action Card
// ═══════════════════════════════════════════════════════════════════════════════

function ActionCard({ task, onToggle }: { task: DigestTask; onToggle: (id: string) => void }) {
  const Icon = TASK_ICON[task.task_type] ?? Circle;
  const colorClass = TASK_COLOR[task.task_type] ?? "text-muted-foreground bg-secondary/50";
  const [expanded, setExpanded] = useState(false);
  const [execData, setExecData] = useState<ExecutionData | null | undefined>(undefined);
  const [execLoading, setExecLoading] = useState(false);
  const [executing, setExecuting] = useState(false);

  const handleExpand = async () => {
    const next = !expanded;
    setExpanded(next);
    if (next && execData === undefined) {
      setExecLoading(true);
      try {
        const res = await api.getTaskExecution(task.id, {
          deal_name: task.deal_name, company: task.company,
          stage: task.stage, task_type: task.task_type, task_text: task.task_text,
        });
        setExecData(res?.execution ?? null);
      } catch {
        setExecData({ type: "error", error: "Failed to load" });
      } finally {
        setExecLoading(false);
      }
    }
  };

  const handleExecute = async (action: string, payload: Record<string, any>) => {
    setExecuting(true);
    try {
      const res = await api.executeDigestTask(task.id, { action, ...payload });
      if (res?.ok || res?.success) {
        toast.success("Done!");
        onToggle(task.id);
        setExpanded(false);
      } else {
        toast.error(res?.error || "Action failed");
      }
    } catch (e: any) {
      toast.error(e?.message || "Action failed");
    } finally {
      setExecuting(false);
    }
  };

  const handleSkip = async () => {
    try { await api.skipDigestTask(task.id, "skipped by rep"); } catch {}
    onToggle(task.id);
    setExpanded(false);
  };

  const intel = task.deal_intelligence;

  return (
    <div className={cn(
      "rounded-xl border transition-all duration-200",
      expanded ? "border-border/50 bg-card shadow-sm" : "border-border/30 bg-card/80 hover:border-border/50 hover:shadow-sm"
    )}>
      {/* Header */}
      <div className="flex items-start gap-3 p-4 cursor-pointer" onClick={handleExpand}>
        <div className={cn("mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg", colorClass)}>
          <Icon className="h-4 w-4" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <span className="text-sm font-semibold text-foreground">{task.deal_name}</span>
            {task.amount_fmt && (
              <Badge variant="outline" className="text-[10px] h-4 px-1.5 border-border/30 text-muted-foreground/70">{task.amount_fmt}</Badge>
            )}
            {task.stage && (
              <Badge variant="outline" className="text-[10px] h-4 px-1.5 border-border/30 text-muted-foreground/40">{task.stage}</Badge>
            )}
          </div>
          <p className="text-xs text-foreground/80 leading-relaxed">{task.task_text}</p>
          {task.reason && <p className="text-[11px] text-muted-foreground/50 mt-1">{task.reason}</p>}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button onClick={e => { e.stopPropagation(); onToggle(task.id); }} className="shrink-0 text-muted-foreground/40 hover:text-emerald-400 transition-colors" aria-label="Mark done">
            <CheckCircle2 className="h-5 w-5" />
          </button>
          {expanded ? <ChevronUp className="h-4 w-4 text-muted-foreground/40" /> : <ChevronDown className="h-4 w-4 text-muted-foreground/40" />}
        </div>
      </div>

      {/* Expanded content */}
      {expanded && (
        <div className="px-4 pb-4 border-t border-border/20 pt-3">
          {/* Deal intelligence from ai_cache */}
          {intel?.has_cached_analysis && (intel.health_summary || intel.nba_summary) && (
            <div className="rounded-lg border border-primary/20 bg-primary/5 p-3 mb-3">
              <p className="text-[10px] font-semibold uppercase tracking-wider text-primary/70 mb-1.5">Deal Intelligence</p>
              {intel.health_summary && (
                <p className="text-xs text-foreground/70 leading-relaxed mb-1">{intel.health_summary}</p>
              )}
              {intel.nba_summary && (
                <p className="text-xs text-foreground/70 leading-relaxed">{intel.nba_summary}</p>
              )}
            </div>
          )}

          {/* Execution panel */}
          {execLoading ? (
            <div className="flex items-center gap-2 py-6 justify-center">
              <Loader2 className="h-4 w-4 animate-spin text-muted-foreground/50" />
              <span className="text-xs text-muted-foreground/50">Preparing your action...</span>
            </div>
          ) : (
            <ExecutionPanel exec={execData ?? null} onExecute={handleExecute} onSkip={handleSkip} executing={executing} />
          )}
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// Zone 1: Focus Bar
// ═══════════════════════════════════════════════════════════════════════════════

function FocusBar({ focus, simulated }: { focus: DashboardData["focus"]; simulated?: boolean }) {
  const pct = focus.actions_total > 0 ? Math.round((focus.actions_completed / focus.actions_total) * 100) : 0;

  return (
    <div className="border-b border-border/40 bg-card/50 px-6 py-3">
      <div className="max-w-[1400px] mx-auto flex items-center gap-6 flex-wrap">
        {/* Progress */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <Target className="h-4 w-4 text-primary" />
            <span className="text-sm font-semibold text-foreground">
              {focus.actions_remaining} action{focus.actions_remaining !== 1 ? "s" : ""} today
            </span>
          </div>
          <div className="w-24 h-1.5 rounded-full bg-secondary/60 overflow-hidden">
            <div className="h-full rounded-full bg-primary transition-all duration-500" style={{ width: `${pct}%` }} />
          </div>
          <span className="text-[11px] text-muted-foreground">{focus.actions_completed}/{focus.actions_total}</span>
        </div>

        <div className="h-4 w-px bg-border/50" />

        {/* Deals needing attention */}
        {focus.deals_needing_attention > 0 && (
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <AlertTriangle className="h-3.5 w-3.5 text-amber-400" />
            <span>{focus.deals_needing_attention} deals need attention</span>
          </div>
        )}

        {/* Revenue at risk */}
        {focus.revenue_at_risk > 0 && (
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <DollarSign className="h-3.5 w-3.5 text-red-400" />
            <span>{formatCurrency(focus.revenue_at_risk)} at risk</span>
          </div>
        )}

        {/* Next meeting */}
        {focus.next_meeting && (
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground ml-auto">
            <Calendar className="h-3.5 w-3.5 text-blue-400" />
            <span>Next: {focus.next_meeting.subject}</span>
            {focus.next_meeting.start && <span className="text-muted-foreground/60">{formatTime(focus.next_meeting.start)}</span>}
          </div>
        )}

        {simulated && (
          <Badge variant="outline" className="text-[10px] border-amber-500/30 text-amber-400/70 ml-auto">Demo data</Badge>
        )}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// Zone 3: Intelligence Sidebar
// ═══════════════════════════════════════════════════════════════════════════════

function IntelligenceSidebar({ intelligence, calendar }: { intelligence: DashboardData["intelligence"]; calendar: CalendarEvent[] }) {
  const navigate = useNavigate();

  return (
    <div className="space-y-4">
      {/* Pipeline Pulse */}
      <div className="rounded-xl border border-border/30 bg-card p-4">
        <h3 className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/60 mb-2">Pipeline Pulse</h3>
        <div className="flex items-baseline gap-2 mb-1">
          <span className="text-2xl font-bold text-foreground">{intelligence.pipeline_health}</span>
          <span className="text-xs text-muted-foreground">/100</span>
        </div>
        <div className="flex items-center gap-3 text-xs text-muted-foreground">
          <span>{formatCurrency(intelligence.pipeline_value)} active</span>
          <span className="text-muted-foreground/40">·</span>
          <span>{intelligence.total_deals} deals</span>
        </div>
      </div>

      {/* Deals declining */}
      {intelligence.deals_declining.length > 0 && (
        <div className="rounded-xl border border-border/30 bg-card p-4">
          <h3 className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/60 mb-3">Deals at Risk</h3>
          <div className="space-y-2">
            {intelligence.deals_declining.map(d => (
              <div key={d.deal_id} className="flex items-center justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-xs font-medium text-foreground truncate">{d.deal_name}</p>
                  <p className="text-[11px] text-muted-foreground/50">{d.stage}</p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span className="text-xs text-muted-foreground/70">{formatCurrency(d.amount)}</span>
                  <div className="flex items-center gap-0.5">
                    <TrendingDown className="h-3 w-3 text-red-400" />
                    <span className="text-[11px] font-semibold text-red-400">{d.health_score}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
          <button
            onClick={() => navigate("/deals")}
            className="flex items-center gap-1 text-[11px] text-primary hover:text-primary/80 mt-3 transition-colors"
          >
            View all deals <ArrowRight className="h-3 w-3" />
          </button>
        </div>
      )}

      {/* Untouched deals */}
      {intelligence.untouched_deals.length > 0 && (
        <div className="rounded-xl border border-border/30 bg-card p-4">
          <h3 className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/60 mb-2">No Contact 30+ Days</h3>
          <div className="flex items-baseline gap-2 mb-2">
            <span className="text-lg font-bold text-amber-400">{intelligence.untouched_deals.length}</span>
            <span className="text-xs text-muted-foreground">
              deals · {formatCurrency(intelligence.untouched_deals.reduce((s, d) => s + (d.amount || 0), 0))} at risk
            </span>
          </div>
          <div className="space-y-1.5">
            {intelligence.untouched_deals.slice(0, 3).map(d => (
              <div key={d.deal_id} className="flex items-center justify-between text-xs">
                <span className="text-foreground/80 truncate">{d.deal_name}</span>
                <span className="text-amber-400/80 shrink-0 ml-2">{d.days_since_contact}d</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Upcoming calendar */}
      {calendar.length > 0 && (
        <div className="rounded-xl border border-border/30 bg-card p-4">
          <h3 className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/60 mb-3">Upcoming Today</h3>
          <div className="space-y-2">
            {calendar.map((ev, i) => (
              <div key={i} className="flex items-start gap-2">
                <Calendar className="h-3.5 w-3.5 text-blue-400 mt-0.5 shrink-0" />
                <div className="min-w-0">
                  <p className="text-xs text-foreground truncate">{ev.subject}</p>
                  <div className="flex items-center gap-2">
                    {ev.start && <span className="text-[11px] text-muted-foreground/50">{formatTime(ev.start)}</span>}
                    {ev.teams_link && (
                      <a href={ev.teams_link} target="_blank" rel="noreferrer" className="flex items-center gap-0.5 text-[11px] text-blue-400 hover:text-blue-300">
                        <Video className="h-3 w-3" /> Join
                      </a>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Weekly progress */}
      <div className="rounded-xl border border-border/30 bg-card p-4">
        <h3 className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/60 mb-2">Today's Progress</h3>
        <div className="flex items-baseline gap-2">
          <span className="text-lg font-bold text-foreground">{intelligence.weekly_progress.actions_completed}</span>
          <span className="text-xs text-muted-foreground">of {intelligence.weekly_progress.actions_total} actions completed</span>
        </div>
        {intelligence.weekly_progress.actions_completed === intelligence.weekly_progress.actions_total && intelligence.weekly_progress.actions_total > 0 && (
          <p className="text-xs text-emerald-400 mt-1">All done for today!</p>
        )}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// Skeletons
// ═══════════════════════════════════════════════════════════════════════════════

function FocusBarSkeleton() {
  return (
    <div className="border-b border-border/40 bg-card/50 px-6 py-3">
      <div className="max-w-[1400px] mx-auto flex items-center gap-6">
        <Skeleton className="h-5 w-40" />
        <Skeleton className="h-1.5 w-24 rounded-full" />
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-4 w-28" />
      </div>
    </div>
  );
}

function ActionCardSkeleton() {
  return (
    <div className="rounded-xl border border-border/20 bg-card/40 p-4 animate-pulse">
      <div className="flex items-start gap-3">
        <div className="h-8 w-8 rounded-lg bg-secondary/60 shrink-0" />
        <div className="flex-1 space-y-2">
          <div className="flex gap-2">
            <div className="h-4 w-32 rounded bg-secondary/60" />
            <div className="h-4 w-12 rounded bg-secondary/40" />
          </div>
          <div className="h-3 w-3/4 rounded bg-secondary/40" />
        </div>
      </div>
    </div>
  );
}

function SidebarSkeleton() {
  return (
    <div className="space-y-4">
      {[1, 2, 3].map(i => (
        <div key={i} className="rounded-xl border border-border/20 bg-card/40 p-4 animate-pulse">
          <div className="h-3 w-24 rounded bg-secondary/60 mb-3" />
          <div className="h-6 w-16 rounded bg-secondary/50 mb-2" />
          <div className="h-3 w-32 rounded bg-secondary/40" />
        </div>
      ))}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// Main Dashboard Component
// ═══════════════════════════════════════════════════════════════════════════════

export default function Dashboard() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.getDashboardToday();
      setData(result);
    } catch (e: any) {
      setError(e?.message || "Failed to load dashboard");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleToggle = useCallback(async (taskId: string) => {
    if (!data) return;
    // Optimistic: move from actions to completed
    setData(prev => {
      if (!prev) return prev;
      const allTasks = [...prev.actions, ...prev.completed_today];
      const task = allTasks.find(t => t.id === taskId);
      if (!task) return prev;
      const nowCompleted = !task.is_completed;
      const updated = { ...task, is_completed: nowCompleted, completed_at: nowCompleted ? new Date().toISOString() : null };
      const actions = nowCompleted
        ? prev.actions.filter(t => t.id !== taskId)
        : [...prev.actions, updated].sort((a, b) => a.sort_order - b.sort_order);
      const completed = nowCompleted
        ? [...prev.completed_today, updated]
        : prev.completed_today.filter(t => t.id !== taskId);
      const done = completed.length;
      const total = actions.length + completed.length;
      return {
        ...prev,
        actions,
        completed_today: completed,
        focus: { ...prev.focus, actions_completed: done, actions_remaining: total - done, actions_total: total },
        intelligence: { ...prev.intelligence, weekly_progress: { actions_completed: done, actions_total: total } },
      };
    });
    try { await api.completeDigestTask(taskId); } catch { toast.error("Could not save — try again"); }
  }, [data]);

  const todayLabel = new Date().toLocaleDateString("en-GB", {
    weekday: "long", day: "numeric", month: "long",
  });

  return (
    <div className="min-h-screen bg-background">
      {/* Zone 1: Focus Bar */}
      {loading ? <FocusBarSkeleton /> : data && <FocusBar focus={data.focus} simulated={data.simulated} />}

      {/* Header */}
      <div className="px-6 pt-5 pb-2 max-w-[1400px] mx-auto">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-lg font-bold text-foreground">{todayLabel}</h1>
            <p className="text-xs text-muted-foreground mt-0.5">Your prioritized actions for today</p>
          </div>
          {error && (
            <button onClick={load} className="flex items-center gap-1.5 text-xs text-destructive hover:text-destructive/80">
              <RefreshCw className="h-3.5 w-3.5" /> Retry
            </button>
          )}
        </div>
      </div>

      {/* Error */}
      {error && !loading && (
        <div className="px-6 max-w-[1400px] mx-auto mt-2">
          <div className="rounded-xl border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {error}
          </div>
        </div>
      )}

      {/* Main content: 2-column layout */}
      <div className="px-6 py-4 max-w-[1400px] mx-auto">
        <div className="flex gap-6">
          {/* Zone 2: Action Queue (left, ~65%) */}
          <div className="flex-1 min-w-0 space-y-6">
            {/* Active actions */}
            <section>
              <h2 className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-3 flex items-center gap-2">
                <Zap className="h-3.5 w-3.5 text-primary" />
                Action Queue
                {!loading && data && (
                  <span className="text-muted-foreground/40 font-normal normal-case">
                    · {data.actions.length} remaining
                  </span>
                )}
              </h2>
              <div className="space-y-2">
                {loading ? (
                  Array.from({ length: 5 }).map((_, i) => <ActionCardSkeleton key={i} />)
                ) : data?.actions.length ? (
                  data.actions.map(t => <ActionCard key={t.id} task={t} onToggle={handleToggle} />)
                ) : (
                  <div className="rounded-xl border border-border/20 bg-card/30 p-8 text-center">
                    <CheckCircle2 className="h-8 w-8 text-emerald-400 mx-auto mb-2" />
                    <p className="text-sm font-medium text-foreground">All actions completed!</p>
                    <p className="text-xs text-muted-foreground mt-1">Your pipeline is in great shape today.</p>
                  </div>
                )}
              </div>
            </section>

            {/* Completed today */}
            {data && data.completed_today.length > 0 && (
              <section>
                <h2 className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-3">
                  Completed Today
                </h2>
                <div className="space-y-1.5">
                  {data.completed_today.map(t => {
                    const Icon = TASK_ICON[t.task_type] ?? Circle;
                    return (
                      <div key={t.id} className="flex items-center gap-3 rounded-lg border border-border/20 bg-card/30 px-4 py-2.5 opacity-60">
                        <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
                        <Icon className="h-3.5 w-3.5 text-muted-foreground/40 shrink-0" />
                        <span className="text-xs text-muted-foreground line-through flex-1 truncate">{t.task_text}</span>
                        <span className="text-[11px] text-muted-foreground/40 shrink-0">{t.deal_name}</span>
                        {t.completed_at && (
                          <span className="text-[11px] text-muted-foreground/30 shrink-0">{formatTime(t.completed_at)}</span>
                        )}
                        <button
                          onClick={() => handleToggle(t.id)}
                          className="text-[11px] text-muted-foreground/40 hover:text-muted-foreground shrink-0"
                        >
                          Undo
                        </button>
                      </div>
                    );
                  })}
                </div>
              </section>
            )}
          </div>

          {/* Zone 3: Intelligence Sidebar (right, ~35%) */}
          <div className="w-[340px] shrink-0 hidden lg:block">
            {loading ? <SidebarSkeleton /> : data && (
              <IntelligenceSidebar intelligence={data.intelligence} calendar={data.calendar} />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
