import { useEffect, useState, useCallback } from "react";
import {
  CheckCircle2, Circle, Mail, Phone, MessageSquare, BookOpen,
  Calendar, FileText, Clock, AlertTriangle, ChevronDown, ChevronUp,
  Send, Copy, ExternalLink, Loader2, SkipForward, RefreshCw,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

// --------------------------------------------------------------------------- //
// Types
// --------------------------------------------------------------------------- //

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

interface Digest {
  date: string;
  tasks: DigestTask[];
  untouched_deals: UntouchedDeal[];
  progress: { completed: number; total: number };
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
  // email
  ready_to_send?: boolean;
  draft?: EmailDraft;
  can_send_via_outlook?: boolean;
  // call
  contact?: { name: string; phone: string | null };
  script?: {
    opening: string;
    if_positive: string;
    if_objection_price: string;
    if_objection_timing: string;
    close: string;
  };
  key_talking_points?: string[];
  // whatsapp
  message?: string;
  whatsapp_deep_link?: string;
  // meeting
  can_create_via_outlook?: boolean;
  // case_study
  recommended_content?: { title: string; type: string; url: string; relevance_reason: string; key_stats: string }[];
  draft_email?: EmailDraft;
  // error
  error?: string;
}

// --------------------------------------------------------------------------- //
// Task type icons & colours
// --------------------------------------------------------------------------- //

const TASK_ICON: Record<string, React.ElementType> = {
  email:      Mail,
  call:       Phone,
  whatsapp:   MessageSquare,
  case_study: BookOpen,
  meeting:    Calendar,
  contract:   FileText,
  re_engage:  RefreshCw,
};

const TASK_COLOR: Record<string, string> = {
  email:      "text-blue-400 bg-blue-500/10",
  call:       "text-emerald-400 bg-emerald-500/10",
  whatsapp:   "text-green-400 bg-green-500/10",
  case_study: "text-violet-400 bg-violet-500/10",
  meeting:    "text-amber-400 bg-amber-500/10",
  contract:   "text-orange-400 bg-orange-500/10",
  re_engage:  "text-pink-400 bg-pink-500/10",
};

// --------------------------------------------------------------------------- //
// Execution sub-panels
// --------------------------------------------------------------------------- //

function CopyButton({ text, label = "Copy" }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = async () => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <button
      onClick={handleCopy}
      className="flex items-center gap-1 rounded px-2 py-1 text-[11px] text-muted-foreground hover:text-foreground hover:bg-secondary/60 transition-colors"
    >
      <Copy className="h-3 w-3" />
      {copied ? "Copied!" : label}
    </button>
  );
}

function EmailExecutionPanel({
  exec, onExecute, onSkip, executing,
}: {
  exec: ExecutionData;
  onExecute: (action: string, payload: Record<string, any>) => void;
  onSkip: () => void;
  executing: boolean;
}) {
  const draft = exec.draft;
  const [editMode, setEditMode] = useState(false);
  const [editedBody, setEditedBody] = useState(draft?.body_plain ?? "");
  const [editedSubject, setEditedSubject] = useState(draft?.subject ?? "");

  if (!draft) return null;

  const handleSend = () => {
    onExecute("send_email", {
      subject: editedSubject,
      body_html: editMode
        ? editedBody.replace(/\n/g, "<br/>")
        : draft.body_html,
      to: draft.to,
      cc: [],
    });
  };

  return (
    <div className="mt-3 space-y-3">
      {/* Draft preview */}
      <div className="rounded-lg border border-border/30 bg-background/50 overflow-hidden">
        <div className="flex items-center gap-2 border-b border-border/30 px-3 py-2">
          <span className="text-[11px] text-muted-foreground/60">To:</span>
          <span className="text-[11px] text-foreground">
            {draft.to.map(r => r.name || r.email || "Contact").join(", ")}
          </span>
        </div>
        <div className="flex items-center gap-2 border-b border-border/30 px-3 py-2">
          <span className="text-[11px] text-muted-foreground/60">Subject:</span>
          {editMode ? (
            <input
              value={editedSubject}
              onChange={e => setEditedSubject(e.target.value)}
              className="flex-1 bg-transparent text-[11px] text-foreground outline-none"
            />
          ) : (
            <span className="text-[11px] text-foreground font-medium">{draft.subject}</span>
          )}
        </div>
        <div className="px-3 py-3">
          {editMode ? (
            <Textarea
              value={editedBody}
              onChange={e => setEditedBody(e.target.value)}
              className="min-h-[120px] text-xs bg-transparent border-border/30 resize-none"
            />
          ) : (
            <div
              className="text-xs text-foreground/80 leading-relaxed prose prose-invert prose-xs max-w-none"
              dangerouslySetInnerHTML={{ __html: draft.body_html }}
            />
          )}
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2 flex-wrap">
        {exec.can_send_via_outlook ? (
          <Button
            size="sm"
            className="h-7 text-xs gap-1.5"
            onClick={handleSend}
            disabled={executing}
          >
            {executing ? <Loader2 className="h-3 w-3 animate-spin" /> : <Send className="h-3 w-3" />}
            {executing ? "Sending…" : "Send via Outlook"}
          </Button>
        ) : (
          <CopyButton text={`${editedSubject}\n\n${draft.body_plain}`} label="Copy email" />
        )}
        <Button
          size="sm"
          variant="outline"
          className="h-7 text-xs border-border/40"
          onClick={() => setEditMode(v => !v)}
        >
          {editMode ? "Preview" : "Edit Draft"}
        </Button>
        <button
          onClick={onSkip}
          className="flex items-center gap-1 text-[11px] text-muted-foreground/60 hover:text-muted-foreground transition-colors ml-auto"
        >
          <SkipForward className="h-3 w-3" />
          Skip
        </button>
      </div>
    </div>
  );
}

function CallScriptPanel({
  exec, onExecute, onSkip, executing,
}: {
  exec: ExecutionData;
  onExecute: (action: string, payload: Record<string, any>) => void;
  onSkip: () => void;
  executing: boolean;
}) {
  const script = exec.script;
  const [outcome, setOutcome] = useState("");
  const [notes, setNotes] = useState("");

  if (!script) return null;

  const ScriptLine = ({ label, text }: { label: string; text: string }) => (
    <div className="rounded-lg border border-border/20 bg-card/40 p-3">
      <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/50 mb-1">{label}</p>
      <p className="text-xs text-foreground/80 leading-relaxed">{text}</p>
      <div className="flex justify-end mt-1">
        <CopyButton text={text} />
      </div>
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

      <ScriptLine label="Opening" text={script.opening} />
      <ScriptLine label="If they're engaged" text={script.if_positive} />
      <ScriptLine label="If they push back on price" text={script.if_objection_price} />
      <ScriptLine label="If the timing isn't right" text={script.if_objection_timing} />
      <ScriptLine label="Close" text={script.close} />

      {/* Log call outcome */}
      <div className="rounded-lg border border-border/20 bg-card/30 p-3 space-y-2">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/50">Log call outcome</p>
        <div className="flex gap-2 flex-wrap">
          {["Connected", "Left voicemail", "No answer", "Not the right time"].map(o => (
            <button
              key={o}
              onClick={() => setOutcome(o)}
              className={cn(
                "rounded-md border px-2.5 py-1 text-[11px] transition-colors",
                outcome === o
                  ? "border-primary/50 bg-primary/10 text-primary"
                  : "border-border/30 text-muted-foreground hover:border-border/50"
              )}
            >{o}</button>
          ))}
        </div>
        <Textarea
          value={notes}
          onChange={e => setNotes(e.target.value)}
          placeholder="Add call notes (optional)…"
          className="min-h-[60px] text-xs bg-transparent border-border/30 resize-none"
        />
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            className="h-7 text-xs"
            onClick={() => onExecute("log_call", { outcome, notes })}
            disabled={executing}
          >
            {executing ? <Loader2 className="h-3 w-3 animate-spin" /> : <CheckCircle2 className="h-3 w-3" />}
            Log & Mark Done
          </Button>
          <button onClick={onSkip} className="flex items-center gap-1 text-[11px] text-muted-foreground/60 hover:text-muted-foreground transition-colors ml-auto">
            <SkipForward className="h-3 w-3" />Skip
          </button>
        </div>
      </div>
    </div>
  );
}

function WhatsAppPanel({
  exec, onExecute, onSkip, executing,
}: {
  exec: ExecutionData;
  onExecute: (action: string, payload: Record<string, any>) => void;
  onSkip: () => void;
  executing: boolean;
}) {
  const [msg, setMsg] = useState(exec.message ?? "");

  return (
    <div className="mt-3 space-y-3">
      <div className="rounded-lg border border-green-500/20 bg-green-500/5 p-3">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-green-400/70 mb-2">Pre-written message</p>
        <Textarea
          value={msg}
          onChange={e => setMsg(e.target.value)}
          className="min-h-[80px] text-xs bg-transparent border-border/30 resize-none text-foreground/80"
        />
        <p className="text-[10px] text-muted-foreground/40 mt-1">{msg.length}/280 chars</p>
      </div>
      <div className="flex items-center gap-2 flex-wrap">
        {exec.whatsapp_deep_link && (
          <Button
            size="sm"
            className="h-7 text-xs gap-1.5 bg-green-600 hover:bg-green-700 border-0"
            onClick={() => {
              const encoded = encodeURIComponent(msg);
              window.open(`https://wa.me/?text=${encoded}`, "_blank");
              onExecute("mark_sent", { notes: "WhatsApp message sent" });
            }}
            disabled={executing}
          >
            <ExternalLink className="h-3 w-3" />
            Open WhatsApp
          </Button>
        )}
        <CopyButton text={msg} label="Copy message" />
        <Button
          size="sm"
          variant="outline"
          className="h-7 text-xs border-border/40"
          onClick={() => onExecute("mark_sent", { notes: "WhatsApp message sent manually" })}
          disabled={executing}
        >
          {executing ? <Loader2 className="h-3 w-3 animate-spin" /> : <CheckCircle2 className="h-3 w-3" />}
          Mark Sent
        </Button>
        <button onClick={onSkip} className="flex items-center gap-1 text-[11px] text-muted-foreground/60 hover:text-muted-foreground transition-colors ml-auto">
          <SkipForward className="h-3 w-3" />Skip
        </button>
      </div>
    </div>
  );
}

function MeetingPanel({
  exec, onExecute, onSkip, executing,
}: {
  exec: ExecutionData;
  onExecute: (action: string, payload: Record<string, any>) => void;
  onSkip: () => void;
  executing: boolean;
}) {
  const draft = exec.draft as any;
  const [subject, setSubject] = useState(draft?.subject ?? "");

  return (
    <div className="mt-3 space-y-3">
      <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-3 space-y-2">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-amber-400/70">Invite draft</p>
        <div className="flex items-center gap-2">
          <span className="text-[11px] text-muted-foreground/60 w-16 shrink-0">Subject:</span>
          <input
            value={subject}
            onChange={e => setSubject(e.target.value)}
            className="flex-1 bg-transparent text-[11px] text-foreground outline-none border-b border-border/30 pb-0.5"
          />
        </div>
        {draft?.attendees?.length > 0 && (
          <div className="flex items-center gap-2">
            <span className="text-[11px] text-muted-foreground/60 w-16 shrink-0">Attendees:</span>
            <span className="text-[11px] text-foreground">
              {draft.attendees.map((a: any) => a.name || a.email || "Contact").join(", ")}
            </span>
          </div>
        )}
        <div className="flex items-center gap-2">
          <span className="text-[11px] text-muted-foreground/60 w-16 shrink-0">Duration:</span>
          <span className="text-[11px] text-foreground">{draft?.duration_minutes ?? 30} min</span>
        </div>
        {exec.can_create_via_outlook && (
          <p className="text-[10px] text-muted-foreground/40">Teams link will be auto-generated</p>
        )}
      </div>

      <div className="flex items-center gap-2 flex-wrap">
        {exec.can_create_via_outlook ? (
          <Button
            size="sm"
            className="h-7 text-xs gap-1.5"
            onClick={() => {
              const tomorrow = new Date();
              tomorrow.setDate(tomorrow.getDate() + 1);
              tomorrow.setHours(10, 0, 0, 0);
              onExecute("schedule_meeting", {
                subject,
                body_html: draft?.body_html ?? "",
                attendees: draft?.attendees ?? [],
                start_iso: tomorrow.toISOString(),
                duration_minutes: draft?.duration_minutes ?? 30,
              });
            }}
            disabled={executing}
          >
            {executing ? <Loader2 className="h-3 w-3 animate-spin" /> : <Calendar className="h-3 w-3" />}
            {executing ? "Creating…" : "Create Invite"}
          </Button>
        ) : (
          <Button
            size="sm"
            variant="outline"
            className="h-7 text-xs gap-1.5 border-border/40"
            onClick={() => onExecute("log_call", { outcome: "Meeting scheduled", notes: subject })}
            disabled={executing}
          >
            <CheckCircle2 className="h-3 w-3" />
            Mark Scheduled
          </Button>
        )}
        <CopyButton text={`Meeting: ${subject}\nDuration: ${draft?.duration_minutes ?? 30} minutes`} label="Copy details" />
        <button onClick={onSkip} className="flex items-center gap-1 text-[11px] text-muted-foreground/60 hover:text-muted-foreground transition-colors ml-auto">
          <SkipForward className="h-3 w-3" />Skip
        </button>
      </div>
    </div>
  );
}

function CaseStudyPanel({
  exec, onExecute, onSkip, executing,
}: {
  exec: ExecutionData;
  onExecute: (action: string, payload: Record<string, any>) => void;
  onSkip: () => void;
  executing: boolean;
}) {
  const items = exec.recommended_content ?? [];
  const draftEmail = exec.draft_email;

  return (
    <div className="mt-3 space-y-3">
      {/* Content cards */}
      <div className="space-y-2">
        {items.map((item, i) => (
          <div key={i} className="flex items-start gap-3 rounded-lg border border-border/20 bg-card/30 p-3">
            <div className={cn(
              "flex h-6 w-6 shrink-0 items-center justify-center rounded text-[10px] font-bold",
              item.type === "case_study" ? "bg-violet-500/15 text-violet-400" :
              item.type === "blog" ? "bg-blue-500/15 text-blue-400" :
              "bg-secondary/60 text-muted-foreground"
            )}>
              {item.type === "case_study" ? "CS" : item.type === "blog" ? "B" : "D"}
            </div>
            <div className="flex-1 min-w-0">
              <a
                href={item.url}
                target="_blank"
                rel="noreferrer"
                className="text-xs font-medium text-foreground hover:text-primary transition-colors line-clamp-1"
              >
                {item.title}
              </a>
              {item.relevance_reason && (
                <p className="text-[11px] text-muted-foreground/60 mt-0.5">{item.relevance_reason}</p>
              )}
              {item.key_stats && (
                <p className="text-[11px] text-emerald-400/80 font-medium mt-0.5">{item.key_stats}</p>
              )}
            </div>
            <a href={item.url} target="_blank" rel="noreferrer">
              <ExternalLink className="h-3.5 w-3.5 text-muted-foreground/40 hover:text-muted-foreground" />
            </a>
          </div>
        ))}
      </div>

      {draftEmail && (
        <div className="flex items-center gap-2 flex-wrap">
          {exec.can_send_via_outlook ? (
            <Button
              size="sm"
              className="h-7 text-xs gap-1.5"
              onClick={() => onExecute("send_resources", {
                subject: draftEmail.subject,
                body_html: draftEmail.body_html,
                to: draftEmail.to,
                cc: [],
              })}
              disabled={executing}
            >
              {executing ? <Loader2 className="h-3 w-3 animate-spin" /> : <Send className="h-3 w-3" />}
              {executing ? "Sending…" : "Send Resources via Outlook"}
            </Button>
          ) : (
            <CopyButton text={`${draftEmail.subject}\n\n${draftEmail.body_plain}`} label="Copy email" />
          )}
          <button onClick={onSkip} className="flex items-center gap-1 text-[11px] text-muted-foreground/60 hover:text-muted-foreground transition-colors ml-auto">
            <SkipForward className="h-3 w-3" />Skip
          </button>
        </div>
      )}
    </div>
  );
}

function ExecutionPanel({
  exec, onExecute, onSkip, executing,
}: {
  exec: ExecutionData | null;
  onExecute: (action: string, payload: Record<string, any>) => void;
  onSkip: () => void;
  executing: boolean;
}) {
  if (!exec) return null;
  if (exec.type === "error") return (
    <div className="mt-3 rounded-lg border border-destructive/20 bg-destructive/5 px-3 py-2 text-xs text-destructive/70">
      Could not generate execution content — {exec.error}
    </div>
  );

  const emailTypes = ["email"];
  if (emailTypes.includes(exec.type)) return <EmailExecutionPanel exec={exec} onExecute={onExecute} onSkip={onSkip} executing={executing} />;
  if (exec.type === "call_script") return <CallScriptPanel exec={exec} onExecute={onExecute} onSkip={onSkip} executing={executing} />;
  if (exec.type === "whatsapp_message") return <WhatsAppPanel exec={exec} onExecute={onExecute} onSkip={onSkip} executing={executing} />;
  if (exec.type === "calendar_invite") return <MeetingPanel exec={exec} onExecute={onExecute} onSkip={onSkip} executing={executing} />;
  if (exec.type === "content_recommendation") return <CaseStudyPanel exec={exec} onExecute={onExecute} onSkip={onSkip} executing={executing} />;

  return null;
}

// --------------------------------------------------------------------------- //
// Task row (expandable)
// --------------------------------------------------------------------------- //

function TaskRow({
  task,
  onToggle,
}: {
  task: DigestTask;
  onToggle: (id: string) => void;
}) {
  const Icon = TASK_ICON[task.task_type] ?? Circle;
  const colorClass = TASK_COLOR[task.task_type] ?? "text-muted-foreground bg-secondary/50";

  const [expanded, setExpanded] = useState(false);
  const [execData, setExecData] = useState<ExecutionData | null | undefined>(undefined); // undefined = not loaded yet
  const [execLoading, setExecLoading] = useState(false);
  const [executing, setExecuting] = useState(false);

  const handleExpand = async () => {
    if (task.is_completed) return;
    const next = !expanded;
    setExpanded(next);
    if (next && execData === undefined) {
      setExecLoading(true);
      try {
        const res = await api.getTaskExecution(task.id, {
          deal_name: task.deal_name,
          company:   task.company,
          stage:     task.stage,
          task_type: task.task_type,
          task_text: task.task_text,
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
        toast.error(res?.error || "Action failed — try again");
      }
    } catch (e: any) {
      toast.error(e?.message || "Action failed");
    } finally {
      setExecuting(false);
    }
  };

  const handleSkip = async () => {
    try {
      await api.skipDigestTask(task.id, "skipped by rep");
      onToggle(task.id);
      setExpanded(false);
    } catch {
      // optimistic — mark done locally
      onToggle(task.id);
    }
  };

  return (
    <div
      className={cn(
        "rounded-xl border transition-all duration-200",
        task.is_completed
          ? "border-border/20 bg-card/20 opacity-60"
          : expanded
            ? "border-border/50 bg-card/80 shadow-sm"
            : "border-border/30 bg-card/60 hover:border-border/50"
      )}
    >
      {/* Main row */}
      <div className="flex items-start gap-3 p-4">
        {/* Complete button */}
        <button
          onClick={() => onToggle(task.id)}
          className="mt-0.5 shrink-0 transition-colors"
          aria-label={task.is_completed ? "Mark incomplete" : "Mark done"}
        >
          {task.is_completed
            ? <CheckCircle2 className="h-5 w-5 text-health-green" />
            : <Circle className="h-5 w-5 text-muted-foreground/40 hover:text-muted-foreground" />
          }
        </button>

        {/* Task type badge */}
        <div className={cn("mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg", colorClass)}>
          <Icon className="h-3.5 w-3.5" />
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <span className={cn(
              "text-[11px] font-semibold uppercase tracking-wide",
              task.is_completed ? "text-muted-foreground/50" : colorClass.split(" ")[0]
            )}>
              {task.task_type_label}
            </span>
            <span className="text-[11px] text-muted-foreground/60">{task.company}</span>
            {task.amount_fmt && (
              <Badge variant="outline" className="text-[10px] h-4 px-1.5 border-border/30 text-muted-foreground/60">
                {task.amount_fmt}
              </Badge>
            )}
            {task.stage && (
              <Badge variant="outline" className="text-[10px] h-4 px-1.5 border-border/30 text-muted-foreground/40">
                {task.stage}
              </Badge>
            )}
          </div>
          <p className={cn(
            "text-sm leading-relaxed",
            task.is_completed ? "line-through text-muted-foreground/40" : "text-foreground"
          )}>
            {task.task_text}
          </p>
          {task.is_completed && task.completed_at && (
            <p className="text-[11px] text-muted-foreground/40 mt-1">
              Completed {new Date(task.completed_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
            </p>
          )}
        </div>

        {/* Expand toggle */}
        {!task.is_completed && (
          <button
            onClick={handleExpand}
            className="mt-0.5 shrink-0 text-muted-foreground/40 hover:text-muted-foreground transition-colors"
            aria-label={expanded ? "Collapse" : "Expand"}
          >
            {expanded
              ? <ChevronUp className="h-4 w-4" />
              : <ChevronDown className="h-4 w-4" />
            }
          </button>
        )}
      </div>

      {/* Execution panel */}
      {expanded && !task.is_completed && (
        <div className="px-4 pb-4">
          {execLoading ? (
            <div className="flex items-center gap-2 py-4 justify-center">
              <Loader2 className="h-4 w-4 animate-spin text-muted-foreground/50" />
              <span className="text-xs text-muted-foreground/50">Preparing your action…</span>
            </div>
          ) : (
            <ExecutionPanel
              exec={execData ?? null}
              onExecute={handleExecute}
              onSkip={handleSkip}
              executing={executing}
            />
          )}
        </div>
      )}
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Untouched deal row
// --------------------------------------------------------------------------- //

function UntouchedRow({ deal }: { deal: UntouchedDeal }) {
  const urgency = deal.days_since_contact >= 60 ? "text-health-red" : "text-amber-400";

  return (
    <div className="flex items-start gap-3 rounded-xl border border-border/20 bg-card/30 p-4">
      <AlertTriangle className={cn("mt-0.5 h-4 w-4 shrink-0", urgency)} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap mb-1">
          <span className="text-sm font-semibold text-foreground">{deal.deal_name}</span>
          {deal.amount_fmt && (
            <Badge variant="outline" className="text-[10px] h-4 px-1.5 border-border/30 text-muted-foreground/60">
              {deal.amount_fmt}
            </Badge>
          )}
          <Badge variant="outline" className="text-[10px] h-4 px-1.5 border-border/30 text-muted-foreground/40">
            {deal.stage}
          </Badge>
        </div>
        <div className="flex items-center gap-2 mb-1.5 flex-wrap">
          <span className="text-xs text-muted-foreground">{deal.company}</span>
          {deal.owner && <span className="text-xs text-muted-foreground/50">· {deal.owner}</span>}
          <span className={cn("text-xs font-semibold", urgency)}>
            {deal.days_since_contact} days silent
          </span>
        </div>
        <p className="text-xs text-muted-foreground/70">{deal.suggested_action}</p>
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Progress bar
// --------------------------------------------------------------------------- //

function ProgressBar({ completed, total }: { completed: number; total: number }) {
  const pct = total > 0 ? Math.round((completed / total) * 100) : 0;
  return (
    <div className="flex items-center gap-3">
      <span className="text-sm text-muted-foreground">
        <span className="font-semibold text-foreground">{completed}</span> of{" "}
        <span className="font-semibold text-foreground">{total}</span> tasks completed today
      </span>
      <div className="flex-1 max-w-48 h-1.5 rounded-full bg-secondary/60 overflow-hidden">
        <div
          className="h-full rounded-full bg-primary transition-all duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs text-muted-foreground">{pct}%</span>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Skeleton
// --------------------------------------------------------------------------- //

function SkeletonRow() {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-border/20 bg-card/40 p-4 animate-pulse">
      <div className="mt-0.5 h-5 w-5 rounded-full bg-secondary/60 shrink-0" />
      <div className="mt-0.5 h-7 w-7 rounded-lg bg-secondary/60 shrink-0" />
      <div className="flex-1 space-y-2">
        <div className="h-3 w-32 rounded bg-secondary/60" />
        <div className="h-4 w-3/4 rounded bg-secondary/40" />
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Page
// --------------------------------------------------------------------------- //

export default function DigestPage() {
  const [digest, setDigest] = useState<Digest | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getTodayDigest();
      setDigest(data);
    } catch (e: any) {
      setError(e?.message || "Failed to load digest");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleToggle = useCallback(async (taskId: string) => {
    if (!digest) return;

    setDigest(prev => {
      if (!prev) return prev;
      const tasks = prev.tasks.map(t =>
        t.id === taskId
          ? { ...t, is_completed: !t.is_completed, completed_at: !t.is_completed ? new Date().toISOString() : null }
          : t
      );
      const completed = tasks.filter(t => t.is_completed).length;
      return { ...prev, tasks, progress: { ...prev.progress, completed } };
    });

    try {
      await api.completeDigestTask(taskId);
    } catch {
      setDigest(prev => {
        if (!prev) return prev;
        const tasks = prev.tasks.map(t =>
          t.id === taskId
            ? { ...t, is_completed: !t.is_completed, completed_at: t.is_completed ? null : t.completed_at }
            : t
        );
        const completed = tasks.filter(t => t.is_completed).length;
        return { ...prev, tasks, progress: { ...prev.progress, completed } };
      });
      toast.error("Could not save — try again");
    }
  }, [digest]);

  const todayLabel = new Date().toLocaleDateString("en-GB", {
    weekday: "long", day: "numeric", month: "long", year: "numeric",
  });

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <div className="border-b border-border/40 px-6 py-4">
        <div className="max-w-3xl mx-auto flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <Clock className="h-4 w-4 text-primary" />
              <span className="text-xs font-semibold text-primary uppercase tracking-wide">Daily Digest</span>
            </div>
            <h1 className="text-xl font-bold text-foreground">{todayLabel}</h1>
            {digest && !loading && (
              <div className="mt-2">
                <ProgressBar completed={digest.progress.completed} total={digest.progress.total} />
              </div>
            )}
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {digest?.simulated && (
              <Badge variant="outline" className="text-[10px] border-amber-500/30 text-amber-400/70">
                Demo data
              </Badge>
            )}
          </div>
        </div>
      </div>

      <div className="max-w-3xl mx-auto px-6 py-6 space-y-8">
        {error && (
          <div className="rounded-xl border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {error} — <button className="underline" onClick={load}>retry</button>
          </div>
        )}

        {/* Section 1 — Tasks */}
        <section>
          <div className="flex items-center gap-2 mb-3">
            <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
              Today's Tasks
            </h2>
            {!loading && digest && (
              <span className="text-[10px] text-muted-foreground/50">
                · Click a task to expand and execute
              </span>
            )}
          </div>
          <div className="space-y-2">
            {loading
              ? Array.from({ length: 5 }).map((_, i) => <SkeletonRow key={i} />)
              : digest?.tasks.length
                ? digest.tasks.map(t => (
                    <TaskRow key={t.id} task={t} onToggle={handleToggle} />
                  ))
                : (
                    <div className="rounded-xl border border-border/20 bg-card/30 p-6 text-center">
                      <CheckCircle2 className="h-8 w-8 text-health-green mx-auto mb-2" />
                      <p className="text-sm text-muted-foreground">No tasks generated — your pipeline looks healthy.</p>
                    </div>
                  )
            }
          </div>
        </section>

        {/* Section 2 — Untouched deals */}
        {(loading || (digest?.untouched_deals?.length ?? 0) > 0) && (
          <section>
            <div className="flex items-center gap-2 mb-3">
              <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                Deals needing attention — no contact in 30+ days
              </h2>
              {!loading && digest && (
                <Badge variant="outline" className="text-[10px] h-4 px-1.5 border-amber-500/30 text-amber-400/70">
                  {digest.untouched_deals.length}
                </Badge>
              )}
            </div>
            <div className="space-y-2">
              {loading
                ? Array.from({ length: 4 }).map((_, i) => <SkeletonRow key={i} />)
                : digest?.untouched_deals.map(d => (
                    <UntouchedRow key={d.deal_id} deal={d} />
                  ))
              }
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
