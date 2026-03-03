import { useState, useEffect, useCallback, useRef } from "react";
import DOMPurify from "dompurify";
import { api } from "@/lib/api";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";
import { format, formatDistanceToNow, parseISO, differenceInDays } from "date-fns";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "@/components/ui/dialog";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList,
} from "@/components/ui/command";
import {
  Mail, Send, RefreshCw, ChevronsUpDown, Check, AlertCircle,
  ChevronDown, ChevronRight, Lightbulb, ListChecks, HelpCircle,
  ArrowRight, Sparkles, Calendar, TrendingUp, TrendingDown, Minus,
  AlertTriangle, CheckCircle2, Users, MessageSquare, ArrowUpRight,
  Clock, Zap, Bell, ExternalLink, Copy, CheckSquare, Square,
  Handshake, Telescope, BarChart3,
} from "lucide-react";

// ── Types ──────────────────────────────────────────────────────────────────────

interface Deal {
  id: string;
  name: string;
  stage: string;
  health_label: string;
  amount: number;
}

interface EmailMessage {
  subject: string;
  from: string;
  to: string[];
  date: string;
  sent_at: string;
  snippet: string;
  body_preview: string;
  body_full?: string;
  html_content?: string;
  direction: string;
  status: string;
  thread_id?: string;
  message_id?: string;
}

interface Thread {
  thread_id: string;
  subject: string;
  message_count: number;
  latest_date: string;
  participants: string[];
  messages: EmailMessage[];
}

interface Commitment {
  by: string;
  what: string;
  deadline?: string | null;
  status: "pending" | "overdue" | "fulfilled";
}

interface Deadline {
  what: string;
  date: string;
  urgency: "high" | "medium" | "low";
}

interface KeyContact {
  name: string;
  role: string;
  email?: string;
  engagement: "high" | "medium" | "low";
}

interface Extracted {
  summary?: string | null;
  next_step?: string | null;
  sentiment?: string | null;
  momentum?: string | null;
  commitments?: (Commitment | string)[];
  open_questions?: string[];
  deadlines?: (Deadline | string)[];
  buying_signals?: string[];
  risk_signals?: string[];
  key_contacts?: KeyContact[];
  relationship_map?: string | null;
  sentiment_progression?: string | null;
  key_topics?: string[];
}

interface ThreadData {
  deal_id: string;
  thread_count: number;
  emails: EmailMessage[];
  threads?: Thread[];
  extracted?: Extracted | null;
  source?: string;
}

// ── Constants ──────────────────────────────────────────────────────────────────

const HEALTH_DOT: Record<string, string> = {
  healthy:  "bg-green-500",
  watching: "bg-yellow-500",
  at_risk:  "bg-orange-500",
  critical: "bg-red-500",
};

const OUR_DOMAIN = "vervotech.com";

const SIG_PATTERNS = [
  /^--\s*$/m,
  /^Best,?\s*$/im,
  /^Best Regards,?\s*$/im,
  /^Thanks\s*[&and]*\s*Regards,?\s*$/im,
  /^Kind Regards,?\s*$/im,
  /^Warm Regards,?\s*$/im,
  /^Sincerely,?\s*$/im,
  /^Cheers,?\s*$/im,
  /^Thanks,?\s*$/im,
  /^Thank you,?\s*$/im,
];

// ── Helpers ────────────────────────────────────────────────────────────────────

function isOurTeam(from: string): boolean {
  return from.toLowerCase().includes(OUR_DOMAIN);
}

function senderInitials(from: string): string {
  const name = from.replace(/<[^>]+>/, "").trim();
  return name.split(/\s+/).slice(0, 2).map(w => w[0] ?? "").join("").toUpperCase() || "?";
}

function senderName(from: string): string {
  const match = from.match(/^([^<]+)</);
  if (match) return match[1].trim();
  return from.split("@")[0] ?? from;
}

function formatDateTime(dateStr: string): string {
  if (!dateStr) return "";
  try { return format(parseISO(dateStr), "MMM d, yyyy · h:mm a"); }
  catch { return dateStr; }
}

function formatRelative(dateStr: string): string {
  if (!dateStr) return "";
  try { return formatDistanceToNow(parseISO(dateStr), { addSuffix: true }); }
  catch { return dateStr; }
}

function countdownLabel(dateStr: string): { label: string; overdue: boolean } {
  if (!dateStr) return { label: "", overdue: false };
  try {
    const d = parseISO(dateStr);
    const days = differenceInDays(d, new Date());
    if (days < 0) return { label: `Overdue by ${Math.abs(days)}d`, overdue: true };
    if (days === 0) return { label: "Due today", overdue: false };
    return { label: `${days}d left`, overdue: false };
  } catch {
    return { label: dateStr, overdue: false };
  }
}

function stripQuotedText(text: string): string {
  const forwardIdx = text.search(/^On .+wrote:\s*$/m);
  if (forwardIdx > 80) text = text.slice(0, forwardIdx);
  for (const pat of SIG_PATTERNS) {
    const m = text.search(pat);
    if (m > 40) { text = text.slice(0, m); break; }
  }
  return text.trim();
}

function sanitizeEmailHtml(html: string, stripQuoted = true): string {
  let h = html;
  if (stripQuoted) h = h.replace(/<blockquote[\s\S]*?<\/blockquote>/gi, "");
  h = h.replace(/\s*style="[^"]*"/gi, "");
  h = h.replace(/\s*color="[^"]*"/gi, "");
  h = h.replace(/\s*face="[^"]*"/gi, "");
  return DOMPurify.sanitize(h, {
    ALLOWED_TAGS: ["p","br","div","span","b","strong","i","em","u","a","ul","ol","li","h1","h2","h3","pre","table","tr","td","th","tbody","thead"],
    ALLOWED_ATTR: ["href","target"],
    FORCE_BODY: true,
  });
}

/** Derive signal type icon from text content. */
function signalIcon(signal: string) {
  const s = signal.toLowerCase();
  if (s.includes("introduc") || s.includes("referr") || s.includes("colleague") || s.includes("looped in"))
    return <Handshake className="h-3 w-3 text-green-400 shrink-0 mt-0.5" />;
  if (s.includes("schedul") || s.includes("meeting") || s.includes("call") || s.includes("demo") || s.includes("calendar"))
    return <Calendar className="h-3 w-3 text-blue-400 shrink-0 mt-0.5" />;
  return <Lightbulb className="h-3 w-3 text-green-400 shrink-0 mt-0.5" />;
}

/** Derive confidence level from signal text. */
function signalConfidence(signal: string): { label: string; cls: string } {
  const s = signal.toLowerCase();
  if (/(confirmed|agreed|scheduled|signed|committed|approved|ready to|will proceed)/.test(s))
    return { label: "High",   cls: "text-green-400 border-green-500/30 bg-green-500/10" };
  if (/(interested|considering|open to|requested|asked|exploring|evaluating)/.test(s))
    return { label: "Medium", cls: "text-yellow-400 border-yellow-500/30 bg-yellow-500/10" };
  return { label: "Low",    cls: "text-muted-foreground border-border/40 bg-muted/20" };
}

/** Derive thread health from sentiment + momentum. */
function threadHealthBadge(sentiment: string, momentum: string): { label: string; emoji: string; cls: string } {
  const s = sentiment.toLowerCase();
  const m = momentum.toLowerCase();
  if (s === "positive" && (m === "accelerating" || m === "steady"))
    return { label: "Progressing", emoji: "🟢", cls: "text-green-400 border-green-500/30 bg-green-500/10" };
  if (s === "positive" || m === "steady")
    return { label: "Active",      emoji: "🟡", cls: "text-yellow-400 border-yellow-500/30 bg-yellow-500/10" };
  return { label: "Stalled",    emoji: "🔴", cls: "text-red-400 border-red-500/30 bg-red-500/10" };
}

function normaliseCommitment(c: Commitment | string): Commitment {
  if (typeof c === "string") return { by: "", what: c, deadline: null, status: "pending" };
  return c;
}

function normaliseDeadline(d: Deadline | string): Deadline {
  if (typeof d === "string") return { what: d, date: "", urgency: "medium" };
  return d;
}

// Avatar colour palette — deterministic by name
const AVATAR_COLORS = [
  "bg-blue-500/20 text-blue-400",
  "bg-violet-500/20 text-violet-400",
  "bg-pink-500/20 text-pink-400",
  "bg-amber-500/20 text-amber-400",
  "bg-cyan-500/20 text-cyan-400",
  "bg-emerald-500/20 text-emerald-400",
];
function avatarColor(name: string) {
  const idx = (name || "?").charCodeAt(0) % AVATAR_COLORS.length;
  return AVATAR_COLORS[idx];
}

// ── InsightSection helper ──────────────────────────────────────────────────────

function InsightSection({
  icon, title, accentColor = "border-violet-500", count, children, defaultOpen = true,
}: {
  icon: React.ReactNode;
  title: string;
  accentColor?: string;
  count?: number;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border-t border-violet-500/10 transition-all duration-200">
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center gap-2 px-4 py-2.5 text-left hover:bg-violet-500/5 transition-colors"
      >
        <div className={cn("w-0.5 h-4 rounded-full shrink-0", accentColor.replace("border-", "bg-"))} />
        {icon}
        <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground/70 flex-1">
          {title}
          {count !== undefined && <span className="ml-1 opacity-60">({count})</span>}
        </span>
        {open
          ? <ChevronDown className="h-3 w-3 text-muted-foreground/40 shrink-0" />
          : <ChevronRight className="h-3 w-3 text-muted-foreground/40 shrink-0" />}
      </button>
      {open && <div className="px-4 pb-3">{children}</div>}
    </div>
  );
}

// ── Draft Email Modal ──────────────────────────────────────────────────────────

function DraftEmailModal({
  open, onClose, nextStep, dealName,
}: {
  open: boolean;
  onClose: () => void;
  nextStep: string;
  dealName: string;
}) {
  const { toast } = useToast();
  const [copied, setCopied] = useState(false);
  const subject = `Following up — ${dealName}`;
  const body = `Hi,\n\nFollowing up on our previous conversation.\n\n${nextStep}\n\nWould love to connect — please let me know your availability.\n\nBest,`;

  const copy = () => {
    navigator.clipboard.writeText(`Subject: ${subject}\n\n${body}`);
    setCopied(true);
    toast({ title: "Copied to clipboard" });
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <Dialog open={open} onOpenChange={v => !v && onClose()}>
      <DialogContent className="max-w-lg border-border/40 bg-card">
        <DialogHeader>
          <DialogTitle className="text-sm font-semibold">Draft Follow-up Email</DialogTitle>
          <DialogDescription className="text-xs text-muted-foreground">
            Pre-filled based on the AI-suggested next step. Edit before sending.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3 mt-1">
          <div>
            <p className="text-[10px] font-semibold text-muted-foreground/60 uppercase tracking-wider mb-1">Subject</p>
            <p className="rounded-md border border-border/40 bg-secondary/30 px-3 py-2 text-xs text-foreground">{subject}</p>
          </div>
          <div>
            <p className="text-[10px] font-semibold text-muted-foreground/60 uppercase tracking-wider mb-1">Body</p>
            <textarea
              className="w-full rounded-md border border-border/40 bg-secondary/30 px-3 py-2 text-xs text-foreground resize-none focus:outline-none focus:ring-1 focus:ring-primary/40"
              rows={8}
              defaultValue={body}
            />
          </div>
          <div className="flex gap-2">
            <Button size="sm" className="flex-1 gap-2 h-8 text-xs" onClick={copy}>
              {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
              {copied ? "Copied!" : "Copy to clipboard"}
            </Button>
            <Button size="sm" variant="outline" className="h-8 text-xs border-border/40" onClick={onClose}>
              Close
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ── MessageBubble ──────────────────────────────────────────────────────────────

function MessageBubble({
  email, defaultExpanded = false,
}: {
  email: EmailMessage;
  defaultExpanded?: boolean;
}) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const [showFull, setShowFull] = useState(false);
  const [hoverDate, setHoverDate] = useState(false);

  const outbound = isOurTeam(email.from) || email.direction === "sent";
  const name = senderName(email.from);
  const initials = senderInitials(email.from);

  const hasHtml = Boolean(email.html_content);
  const safeHtml = hasHtml ? sanitizeEmailHtml(email.html_content!) : null;

  const plainBody = email.body_full || email.body_preview || email.snippet || "";
  const cleanPlain = stripQuotedText(plainBody);
  const previewText = cleanPlain.slice(0, 180);

  const hasBody = Boolean(safeHtml || cleanPlain);
  const dateStr = email.date || email.sent_at;

  return (
    <div className={cn("flex gap-3 transition-all duration-200", outbound ? "flex-row-reverse" : "flex-row")}>
      {/* Avatar */}
      <div className={cn(
        "h-7 w-7 rounded-full flex items-center justify-center text-[10px] font-bold shrink-0 mt-1",
        outbound ? "bg-primary/20 text-primary" : "bg-muted text-muted-foreground"
      )}>
        {initials}
      </div>

      {/* Bubble */}
      <div className={cn(
        "max-w-[82%] rounded-2xl border text-xs transition-all duration-200",
        outbound
          ? "rounded-tr-sm bg-primary/10 border-primary/30 border-l-2 border-l-primary/60"
          : "rounded-tl-sm bg-muted/40 border-border/50 border-l-2 border-l-border/60",
        "hover:shadow-md"
      )}>
        {/* Header */}
        <button
          className="w-full flex items-start justify-between gap-3 px-4 pt-3 pb-2 text-left"
          onClick={() => setExpanded(v => !v)}
        >
          <div className="space-y-0.5">
            <div className="flex items-center gap-2">
              <span className="font-semibold text-foreground">{name}</span>
              {outbound
                ? <Badge variant="outline" className="text-[9px] h-3.5 px-1 text-primary border-primary/30 bg-primary/10">Sent</Badge>
                : <Badge variant="outline" className="text-[9px] h-3.5 px-1 text-muted-foreground border-border/40">Received</Badge>}
            </div>
            {/* Timestamp with full datetime on hover */}
            <div
              className="relative inline-block"
              onMouseEnter={() => setHoverDate(true)}
              onMouseLeave={() => setHoverDate(false)}
            >
              <p className="text-[11px] text-muted-foreground cursor-default">
                {formatRelative(dateStr)}
              </p>
              {hoverDate && dateStr && (
                <div className="absolute bottom-full left-0 mb-1 whitespace-nowrap rounded-md border border-border/50 bg-card px-2 py-1 text-[10px] text-foreground shadow-lg z-10">
                  {formatDateTime(dateStr)}
                </div>
              )}
            </div>
          </div>
          {expanded
            ? <ChevronDown className="h-3 w-3 text-muted-foreground/40 shrink-0 mt-0.5" />
            : <ChevronRight className="h-3 w-3 text-muted-foreground/40 shrink-0 mt-0.5" />}
        </button>

        {/* Preview when collapsed */}
        {!expanded && hasBody && (
          <p className="px-4 pb-3 text-[12px] text-muted-foreground line-clamp-2 leading-relaxed">
            {previewText}…
          </p>
        )}

        {/* Full body when expanded */}
        {expanded && (
          <>
            <Separator className="opacity-30 mx-4" />
            <div className="px-4 py-3">
              {hasBody ? (
                <>
                  {safeHtml ? (
                    <div
                      className="email-body text-[12px] leading-relaxed text-foreground [&_a]:text-primary [&_a]:underline [&_p]:mb-2 [&_div]:mb-1"
                      dangerouslySetInnerHTML={{ __html: showFull ? sanitizeEmailHtml(email.html_content!, false) : safeHtml }}
                    />
                  ) : (
                    <p className="text-[12px] leading-relaxed text-foreground whitespace-pre-wrap">
                      {showFull ? plainBody : cleanPlain}
                    </p>
                  )}
                  <button
                    className="mt-2 text-[10px] text-muted-foreground/50 hover:text-muted-foreground underline transition-colors"
                    onClick={e => { e.stopPropagation(); setShowFull(v => !v); }}
                  >
                    {showFull ? "Hide quoted thread ▴" : "Show quoted text ▾"}
                  </button>
                </>
              ) : (
                <p className="text-[11px] italic text-muted-foreground/40">
                  Body not available — re-login to Zoho to refresh email scope.
                </p>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ── ThreadView ─────────────────────────────────────────────────────────────────

function ThreadView({
  thread, extracted,
}: {
  thread: Thread;
  extracted?: Extracted | null;
}) {
  const [open, setOpen] = useState(true);

  const sentiment = (extracted?.sentiment || "").toLowerCase();
  const momentum  = (extracted?.momentum  || "").toLowerCase();
  const health    = sentiment && momentum ? threadHealthBadge(sentiment, momentum) : null;

  // Build unique participant initials for avatar stack (max 3)
  const uniqueParticipants = [...new Set(thread.participants ?? [])].slice(0, 4);

  return (
    <div className="rounded-xl border border-border/30 bg-card/20 overflow-hidden transition-all duration-200 hover:border-border/50">
      <button
        className="w-full flex items-center gap-2.5 px-4 py-3 text-left bg-card/50 hover:bg-card/70 transition-colors"
        onClick={() => setOpen(v => !v)}
      >
        <Mail className="h-3.5 w-3.5 text-muted-foreground/50 shrink-0" />

        {/* Subject */}
        <span className="text-xs font-medium text-foreground flex-1 truncate">{thread.subject}</span>

        {/* Health badge */}
        {health && (
          <Badge variant="outline" className={cn("text-[9px] h-4 px-1.5 gap-0.5 shrink-0", health.cls)}>
            {health.emoji} {health.label}
          </Badge>
        )}

        {/* Participant avatar stack */}
        {uniqueParticipants.length > 0 && (
          <div className="flex -space-x-1.5 shrink-0">
            {uniqueParticipants.map((p, i) => {
              const ini = senderInitials(p);
              return (
                <div
                  key={i}
                  title={senderName(p)}
                  className={cn(
                    "h-5 w-5 rounded-full border border-background flex items-center justify-center text-[8px] font-bold",
                    avatarColor(ini)
                  )}
                >
                  {ini.slice(0, 1)}
                </div>
              );
            })}
          </div>
        )}

        <span className="text-[10px] text-muted-foreground/50 shrink-0">
          {thread.message_count} msg{thread.message_count !== 1 ? "s" : ""} · {formatRelative(thread.latest_date)}
        </span>
        {open
          ? <ChevronDown className="h-3 w-3 text-muted-foreground/40 shrink-0" />
          : <ChevronRight className="h-3 w-3 text-muted-foreground/40 shrink-0" />}
      </button>

      {open && (
        <div className="p-4 space-y-4">
          {thread.messages.map((msg, i) => (
            <MessageBubble
              key={msg.message_id || i}
              email={msg}
              defaultExpanded={i === thread.messages.length - 1}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ── AIInsightsPanel ────────────────────────────────────────────────────────────

const SENTIMENT_CONFIG: Record<string, { label: string; cls: string }> = {
  positive: { label: "Positive",  cls: "text-green-400  border-green-500/30  bg-green-500/10"  },
  neutral:  { label: "Neutral",   cls: "text-yellow-400 border-yellow-500/30 bg-yellow-500/10" },
  negative: { label: "Negative",  cls: "text-red-400    border-red-500/30    bg-red-500/10"    },
  at_risk:  { label: "At Risk",   cls: "text-orange-400 border-orange-500/30 bg-orange-500/10" },
  mixed:    { label: "Mixed",     cls: "text-yellow-400 border-yellow-500/30 bg-yellow-500/10" },
};

const MOMENTUM_CONFIG: Record<string, { label: string; Icon: any; cls: string }> = {
  accelerating: { label: "Accelerating", Icon: TrendingUp,   cls: "text-green-400"  },
  steady:       { label: "Steady",       Icon: Minus,        cls: "text-yellow-400" },
  stalling:     { label: "Stalling",     Icon: TrendingDown, cls: "text-orange-400" },
  gone_cold:    { label: "Gone cold",    Icon: TrendingDown, cls: "text-red-400"    },
};

const URGENCY_CLS: Record<string, string> = {
  high:   "text-red-400",
  medium: "text-yellow-400",
  low:    "text-muted-foreground",
};

function AIInsightsPanel({
  extracted, onReanalyse, analysing, onDraftEmail, dealName,
}: {
  extracted: Extracted;
  onReanalyse: () => void;
  analysing: boolean;
  onDraftEmail?: () => void;
  dealName?: string;
}) {
  const [showOpenQ,  setShowOpenQ]  = useState(false);
  const [showRelMap, setShowRelMap] = useState(false);
  const [doneStep,   setDoneStep]   = useState(false);
  const [checkedCommitments, setCheckedCommitments] = useState<Set<number>>(new Set());

  const sentiment  = (extracted.sentiment || "").toLowerCase();
  const momentum   = (extracted.momentum  || "").toLowerCase();
  const sentCfg    = SENTIMENT_CONFIG[sentiment]  ?? SENTIMENT_CONFIG["neutral"];
  const momCfg     = MOMENTUM_CONFIG[momentum];
  const MomIcon    = momCfg?.Icon ?? Minus;

  const commitments = (extracted.commitments ?? []).map(normaliseCommitment);
  const deadlines   = (extracted.deadlines   ?? []).map(normaliseDeadline);
  const contacts    = extracted.key_contacts  ?? [];

  const allCommitmentsChecked = commitments.length > 0 && checkedCommitments.size === commitments.length;

  const toggleCommitment = (i: number) => {
    setCheckedCommitments(prev => {
      const next = new Set(prev);
      next.has(i) ? next.delete(i) : next.add(i);
      return next;
    });
  };

  return (
    <div className="rounded-xl border border-violet-500/20 bg-violet-500/5 overflow-hidden">
      {/* Header row — with Re-analyse at top */}
      <div className="px-4 py-3 flex items-center gap-2 border-b border-violet-500/10">
        <Sparkles className="h-3.5 w-3.5 text-violet-400 shrink-0" />
        <span className="text-[11px] font-semibold uppercase tracking-widest text-violet-400/80 flex-1">
          AI Analysis
        </span>
        <div className="flex items-center gap-1.5">
          {sentiment && (
            <Badge variant="outline" className={cn("text-[10px] h-5 px-1.5 capitalize", sentCfg.cls)}>
              {sentCfg.label}
            </Badge>
          )}
          {momCfg && (
            <Badge variant="outline" className={cn("text-[10px] h-5 px-1.5 gap-0.5", momCfg.cls, "border-current/30 bg-current/5")}>
              <MomIcon className="h-2.5 w-2.5" />
              {momCfg.label}
            </Badge>
          )}
          {/* Re-analyse moved to top */}
          <button
            className="flex items-center gap-1 rounded border border-violet-500/30 bg-violet-500/10 px-2 py-0.5 text-[10px] text-violet-400 hover:bg-violet-500/20 transition-colors disabled:opacity-40"
            onClick={onReanalyse}
            disabled={analysing}
            title="Re-analyse thread"
          >
            <RefreshCw className={cn("h-2.5 w-2.5", analysing && "animate-spin")} />
            {analysing ? "…" : "Refresh"}
          </button>
        </div>
      </div>

      {/* Summary */}
      {extracted.summary && (
        <div className="px-4 py-3 border-b border-violet-500/10">
          <p className="text-[11px] text-muted-foreground leading-relaxed">{extracted.summary}</p>
        </div>
      )}

      {/* ── Next Step ── */}
      {extracted.next_step && (
        <InsightSection
          icon={<Zap className="h-3 w-3 text-violet-400 shrink-0" />}
          title="Next step"
          accentColor="border-violet-500"
          defaultOpen={true}
        >
          <div className={cn(
            "rounded-lg border px-3 py-2.5 mt-1 transition-all duration-200",
            doneStep
              ? "border-green-500/30 bg-green-500/10"
              : "border-violet-500/20 bg-violet-500/8"
          )}>
            <p className={cn(
              "text-xs font-medium leading-relaxed",
              doneStep ? "line-through text-muted-foreground/50" : "text-foreground"
            )}>
              {extracted.next_step}
            </p>
          </div>
          {!doneStep && (
            <div className="flex gap-2 mt-2.5">
              {onDraftEmail && (
                <Button
                  size="sm"
                  className="flex-1 h-7 text-xs bg-violet-600 hover:bg-violet-700 text-white gap-1.5"
                  onClick={onDraftEmail}
                >
                  <Mail className="h-3 w-3" />
                  Draft Email
                </Button>
              )}
              <Button
                size="sm"
                variant="outline"
                className="flex-1 h-7 text-xs border-green-500/30 text-green-400 hover:bg-green-500/10 gap-1.5"
                onClick={() => setDoneStep(true)}
              >
                <Check className="h-3 w-3" />
                Mark Done
              </Button>
            </div>
          )}
          {doneStep && (
            <p className="mt-2 flex items-center gap-1.5 text-[11px] text-green-400">
              <CheckCircle2 className="h-3 w-3" />
              Marked as done ·{" "}
              <button className="underline hover:no-underline" onClick={() => setDoneStep(false)}>
                Undo
              </button>
            </p>
          )}
        </InsightSection>
      )}

      {/* ── Buying Signals ── */}
      {(extracted.buying_signals?.length ?? 0) > 0 && (
        <InsightSection
          icon={<TrendingUp className="h-3 w-3 text-green-400 shrink-0" />}
          title="Buying signals"
          accentColor="border-green-500"
          count={extracted.buying_signals!.length}
          defaultOpen={true}
        >
          <div className="space-y-2 mt-1">
            {extracted.buying_signals!.map((s, i) => {
              const conf = signalConfidence(s);
              return (
                <div
                  key={i}
                  className="flex items-start gap-2 rounded-lg border border-border/20 bg-card/40 px-2.5 py-2 animate-fade-in transition-all duration-200 hover:bg-card/70"
                  style={{ animationDelay: `${i * 60}ms` }}
                >
                  {signalIcon(s)}
                  <p className="text-[11px] text-foreground/80 flex-1 leading-relaxed">{s}</p>
                  <Badge variant="outline" className={cn("text-[9px] h-4 px-1.5 shrink-0", conf.cls)}>
                    {conf.label}
                  </Badge>
                </div>
              );
            })}
          </div>
        </InsightSection>
      )}

      {/* ── Risk Signals ── */}
      {(extracted.risk_signals?.length ?? 0) > 0 && (
        <InsightSection
          icon={<AlertTriangle className="h-3 w-3 text-red-400 shrink-0" />}
          title="Risk signals"
          accentColor="border-red-500"
          count={extracted.risk_signals!.length}
          defaultOpen={true}
        >
          <div className="space-y-1.5 mt-1">
            {extracted.risk_signals!.map((s, i) => (
              <div key={i} className="flex gap-2 rounded-lg border border-red-500/20 bg-red-500/5 px-2.5 py-2">
                <AlertTriangle className="h-3 w-3 text-red-400 shrink-0 mt-0.5" />
                <p className="text-[11px] text-foreground/80">{s}</p>
              </div>
            ))}
          </div>
        </InsightSection>
      )}

      {/* ── Commitments ── */}
      {commitments.length > 0 && (
        <InsightSection
          icon={<ListChecks className="h-3 w-3 text-violet-400 shrink-0" />}
          title="Commitments"
          accentColor="border-violet-500"
          count={commitments.length}
          defaultOpen={true}
        >
          <div className="space-y-2 mt-1">
            {allCommitmentsChecked ? (
              <div className="flex items-center gap-2 rounded-lg border border-green-500/30 bg-green-500/10 px-3 py-2.5">
                <CheckCircle2 className="h-4 w-4 text-green-400 shrink-0" />
                <span className="text-xs font-semibold text-green-400">All commitments met ✓</span>
                <button
                  className="ml-auto text-[10px] text-muted-foreground underline"
                  onClick={() => setCheckedCommitments(new Set())}
                >
                  Reset
                </button>
              </div>
            ) : (
              commitments.map((c, i) => {
                const checked = checkedCommitments.has(i);
                return (
                  <button
                    key={i}
                    onClick={() => toggleCommitment(i)}
                    className={cn(
                      "w-full flex gap-2 rounded-lg px-2.5 py-2 text-left text-[11px] transition-all duration-200 hover:bg-card/70",
                      c.status === "overdue" && !checked
                        ? "bg-red-500/10 border border-red-500/20"
                        : "bg-card/50 border border-transparent"
                    )}
                  >
                    {checked
                      ? <CheckSquare className="h-3.5 w-3.5 text-green-400 shrink-0 mt-0.5" />
                      : c.status === "fulfilled"
                      ? <CheckCircle2 className="h-3.5 w-3.5 text-green-400 shrink-0 mt-0.5" />
                      : c.status === "overdue"
                      ? <AlertTriangle className="h-3.5 w-3.5 text-red-400 shrink-0 mt-0.5" />
                      : <Square className="h-3.5 w-3.5 text-muted-foreground/40 shrink-0 mt-0.5" />}
                    <div className="flex-1 min-w-0">
                      {c.by && (
                        <span className={cn("font-semibold", checked ? "text-muted-foreground/50 line-through" : "text-foreground/70")}>
                          {c.by}:{" "}
                        </span>
                      )}
                      <span className={cn(checked ? "text-muted-foreground/50 line-through" : "text-foreground/80")}>
                        {c.what}
                      </span>
                      {c.deadline && (
                        <span className={cn("ml-1.5 text-[10px]",
                          checked ? "text-muted-foreground/40" :
                          c.status === "overdue" ? "text-red-400" : "text-muted-foreground/60"
                        )}>
                          · {c.deadline}
                        </span>
                      )}
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </InsightSection>
      )}

      {/* ── Deadlines ── */}
      {deadlines.length > 0 && (
        <InsightSection
          icon={<Calendar className="h-3 w-3 text-violet-400 shrink-0" />}
          title="Deadlines"
          accentColor="border-amber-500"
          count={deadlines.length}
        >
          <div className="space-y-1.5 mt-1">
            {deadlines.map((d, i) => {
              const { label, overdue } = countdownLabel(d.date);
              return (
                <div key={i} className="flex items-start justify-between gap-2">
                  <p className={cn("text-[11px]", URGENCY_CLS[d.urgency])}>{d.what}</p>
                  {label && (
                    <Badge variant="outline" className={cn(
                      "text-[9px] h-4 px-1.5 shrink-0 whitespace-nowrap",
                      overdue ? "text-red-400 border-red-500/30 bg-red-500/10" : "text-muted-foreground border-border/40"
                    )}>
                      {label}
                    </Badge>
                  )}
                </div>
              );
            })}
          </div>
        </InsightSection>
      )}

      {/* ── Key Contacts ── */}
      {contacts.length > 0 && (
        <InsightSection
          icon={<Users className="h-3 w-3 text-violet-400 shrink-0" />}
          title="Key contacts"
          accentColor="border-blue-500"
          count={contacts.length}
        >
          <div className="space-y-2 mt-1">
            {contacts.map((c, i) => (
              <div key={i}>
                {/* VS divider between contacts from different companies */}
                {i > 0 && (
                  <div className="flex items-center gap-2 my-2">
                    <div className="flex-1 h-px bg-border/30" />
                    <span className="text-[9px] font-bold text-muted-foreground/40 uppercase tracking-widest">
                      {contacts[i - 1]?.email?.split("@")[1] !== c.email?.split("@")[1] ? "vs" : "·"}
                    </span>
                    <div className="flex-1 h-px bg-border/30" />
                  </div>
                )}
                <div className="flex items-center gap-2.5 rounded-lg border border-border/30 bg-card/60 px-3 py-2.5 hover:bg-card/80 transition-colors">
                  {/* Avatar */}
                  <div className={cn(
                    "h-8 w-8 rounded-full flex items-center justify-center text-[11px] font-bold shrink-0",
                    c.engagement === "high"   ? "bg-green-500/20 text-green-400"  :
                    c.engagement === "medium" ? "bg-yellow-500/20 text-yellow-400" :
                                                "bg-muted text-muted-foreground"
                  )}>
                    {(c.name || "?").split(" ").slice(0, 2).map((w: string) => w[0]).join("")}
                  </div>

                  {/* Info */}
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-semibold text-foreground truncate">{c.name}</p>
                    <div className="flex items-center gap-1.5 mt-0.5">
                      {c.role && (
                        <span className="text-[10px] text-muted-foreground/60 truncate">{c.role}</span>
                      )}
                      {c.email && (
                        <Badge variant="outline" className="text-[9px] h-3.5 px-1 border-border/30 text-muted-foreground/50 shrink-0">
                          {c.email.split("@")[1]}
                        </Badge>
                      )}
                    </div>
                    {/* Engagement */}
                    <div className="flex items-center gap-1 mt-0.5">
                      <div className={cn(
                        "h-1.5 w-1.5 rounded-full",
                        c.engagement === "high" ? "bg-green-400" :
                        c.engagement === "medium" ? "bg-yellow-400" : "bg-muted-foreground/40"
                      )} />
                      <span className="text-[9px] text-muted-foreground/50 capitalize">{c.engagement} engagement</span>
                    </div>
                  </div>

                  {/* Quick actions */}
                  <div className="flex items-center gap-1 shrink-0">
                    {c.email && (
                      <a
                        href={`mailto:${c.email}`}
                        onClick={e => e.stopPropagation()}
                        title={`Email ${c.name}`}
                        className="flex h-6 w-6 items-center justify-center rounded-md border border-border/30 bg-card/60 text-muted-foreground/60 hover:text-primary hover:border-primary/30 transition-colors"
                      >
                        <Mail className="h-3 w-3" />
                      </a>
                    )}
                    <a
                      href={`https://www.linkedin.com/search/results/people/?keywords=${encodeURIComponent(c.name)}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={e => e.stopPropagation()}
                      title={`Find ${c.name} on LinkedIn`}
                      className="flex h-6 w-6 items-center justify-center rounded-md border border-border/30 bg-card/60 text-muted-foreground/60 hover:text-blue-400 hover:border-blue-400/30 transition-colors"
                    >
                      <ExternalLink className="h-3 w-3" />
                    </a>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </InsightSection>
      )}

      {/* ── Open Questions ── */}
      {(extracted.open_questions?.length ?? 0) > 0 && (
        <InsightSection
          icon={<HelpCircle className="h-3 w-3 text-muted-foreground/60 shrink-0" />}
          title="Open questions"
          accentColor="border-muted-foreground"
          count={extracted.open_questions!.length}
          defaultOpen={false}
        >
          <ul className="space-y-1 mt-1">
            {extracted.open_questions!.map((q, i) => (
              <li key={i} className="flex gap-1.5 text-[11px] text-foreground/70">
                <span className="text-violet-400 shrink-0">·</span>{q}
              </li>
            ))}
          </ul>
        </InsightSection>
      )}

      {/* ── Relationship Map ── */}
      {extracted.relationship_map && (
        <InsightSection
          icon={<MessageSquare className="h-3 w-3 text-muted-foreground/60 shrink-0" />}
          title="Relationship map"
          accentColor="border-muted-foreground"
          defaultOpen={false}
        >
          <p className="mt-1 text-[11px] text-muted-foreground leading-relaxed">{extracted.relationship_map}</p>
        </InsightSection>
      )}
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────────

export default function EmailTimelinePage() {
  const { toast } = useToast();

  const [deals,          setDeals]          = useState<Deal[]>([]);
  const [dealsLoading,   setDealsLoading]   = useState(true);
  const [open,           setOpen]           = useState(false);
  const [selectedDealId, setSelectedDealId] = useState("");

  const [thread,         setThread]         = useState<ThreadData | null>(null);
  const [threadLoading,  setThreadLoading]  = useState(false);
  const [syncing,        setSyncing]        = useState(false);
  const [analysing,      setAnalysing]      = useState(false);

  const [viewMode,       setViewMode]       = useState<"grouped" | "flat">("grouped");
  const [draftModalOpen, setDraftModalOpen] = useState(false);

  const selectedDeal = deals.find(d => d.id === selectedDealId);

  // Normalize deal names (deal_name vs name)
  useEffect(() => {
    api.getAllDeals()
      .then(data => {
        const list = Array.isArray(data) ? data : [];
        setDeals(list.map((d: any) => ({
          id:           d.id,
          name:         d.name ?? d.deal_name ?? "Unnamed Deal",
          stage:        d.stage ?? "Unknown",
          health_label: d.health_label ?? "critical",
          amount:       d.amount ?? 0,
        })));
      })
      .catch((err: Error) => toast({ title: "Failed to load deals", description: err.message, variant: "destructive" }))
      .finally(() => setDealsLoading(false));
  }, []);

  useEffect(() => {
    if (!selectedDealId) { setThread(null); return; }
    setThreadLoading(true);
    setThread(null);
    api.getEmailThread(selectedDealId)
      .then(setThread)
      .catch((err: Error) => toast({ title: "Failed to load emails", description: err.message, variant: "destructive" }))
      .finally(() => setThreadLoading(false));
  }, [selectedDealId]);

  async function handleSync() {
    if (!selectedDealId) return;
    setSyncing(true);
    try {
      const result = await api.syncEmailsForDeal(selectedDealId);
      toast({ title: "Sync complete", description: `${result.threads_found ?? 0} email(s) found.` });
      setThread(await api.getEmailThread(selectedDealId));
    } catch (err: any) {
      toast({ title: "Sync failed", description: err.message, variant: "destructive" });
    } finally {
      setSyncing(false);
    }
  }

  async function handleReanalyse() {
    if (!selectedDealId) return;
    setAnalysing(true);
    try {
      const result = await api.analyseEmailThread(selectedDealId);
      if (result.extracted) {
        setThread(prev => prev ? { ...prev, extracted: result.extracted } : prev);
        toast({ title: "Analysis updated" });
      }
    } catch (err: any) {
      toast({ title: "Analysis failed", description: err.message, variant: "destructive" });
    } finally {
      setAnalysing(false);
    }
  }

  const emails        = thread?.emails   ?? [];
  const threads       = thread?.threads  ?? [];
  const sentCount     = emails.filter(e => isOurTeam(e.from) || e.direction === "sent").length;
  const receivedCount = emails.length - sentCount;
  const responseRate  = sentCount > 0 ? Math.round((receivedCount / sentCount) * 100) : 0;

  // Days since last buyer response
  const lastBuyerEmail = [...emails]
    .reverse()
    .find(e => !isOurTeam(e.from) && e.direction !== "sent");
  const daysSinceReply = lastBuyerEmail
    ? differenceInDays(new Date(), parseISO(lastBuyerEmail.date || lastBuyerEmail.sent_at || ""))
    : null;

  const noReply = receivedCount === 0 && sentCount > 0;

  return (
    <div className="min-h-screen bg-background">

      {/* Header */}
      <div className="border-b border-border/40 px-6 py-4">
        <div className="flex items-center gap-3 max-w-6xl mx-auto">
          <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-blue-500/15">
            <Mail className="h-4 w-4 text-blue-400" />
          </div>
          <div>
            <h1 className="text-sm font-semibold text-foreground">Email Timeline</h1>
            <p className="text-xs text-muted-foreground">Full thread history with AI deal analysis</p>
          </div>
        </div>
      </div>

      <div className="max-w-6xl mx-auto px-6 py-6 space-y-6">

        {/* Controls */}
        <div className="flex items-center gap-3 flex-wrap">

          {/* Deal selector */}
          {dealsLoading ? <Skeleton className="h-8 w-56 rounded-lg" /> : (
            <Popover open={open} onOpenChange={setOpen}>
              <PopoverTrigger asChild>
                <Button variant="outline" role="combobox" aria-expanded={open}
                  className="h-8 min-w-[220px] max-w-xs justify-between text-xs border-border/50 font-normal">
                  {selectedDeal
                    ? <span className="flex items-center gap-2 truncate">
                        <span className={cn("h-1.5 w-1.5 rounded-full shrink-0", HEALTH_DOT[selectedDeal.health_label] ?? "bg-muted-foreground")} />
                        <span className="truncate">{selectedDeal.name}</span>
                      </span>
                    : <span className="text-muted-foreground">Select a deal…</span>}
                  <ChevronsUpDown className="ml-2 h-3 w-3 shrink-0 opacity-50" />
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-[320px] p-0" align="start">
                <Command>
                  <CommandInput placeholder="Search deals…" className="h-8 text-xs" />
                  <CommandList>
                    <CommandEmpty className="py-4 text-center text-xs text-muted-foreground">No deals found.</CommandEmpty>
                    <CommandGroup>
                      {deals.map(d => (
                        <CommandItem key={d.id} value={`${d.name} ${d.stage}`} className="text-xs"
                          onSelect={() => { setSelectedDealId(d.id === selectedDealId ? "" : d.id); setOpen(false); }}>
                          <span className={cn("mr-2 h-1.5 w-1.5 rounded-full shrink-0", HEALTH_DOT[d.health_label] ?? "bg-muted-foreground")} />
                          <span className="flex-1 truncate">{d.name}</span>
                          {d.stage && <span className="ml-2 text-muted-foreground/60 shrink-0">{d.stage}</span>}
                          <Check className={cn("ml-2 h-3 w-3 shrink-0", d.id === selectedDealId ? "opacity-100" : "opacity-0")} />
                        </CommandItem>
                      ))}
                    </CommandGroup>
                  </CommandList>
                </Command>
              </PopoverContent>
            </Popover>
          )}

          {/* View toggle + Sync */}
          {selectedDealId && emails.length > 0 && (
            <div className="ml-auto flex items-center gap-2">
              <div className="flex rounded-lg border border-border/40 overflow-hidden text-[11px]">
                <button onClick={() => setViewMode("grouped")}
                  className={cn("px-2.5 py-1 transition-colors", viewMode === "grouped" ? "bg-primary/10 text-primary" : "text-muted-foreground hover:text-foreground")}>
                  Threads
                </button>
                <button onClick={() => setViewMode("flat")}
                  className={cn("px-2.5 py-1 transition-colors", viewMode === "flat" ? "bg-primary/10 text-primary" : "text-muted-foreground hover:text-foreground")}>
                  Flat
                </button>
              </div>
              <Button size="sm" variant="outline" className="h-8 text-xs border-border/50 transition-colors hover:bg-secondary/60"
                onClick={handleSync} disabled={syncing}>
                <RefreshCw className={cn("mr-1.5 h-3 w-3 transition-transform", syncing && "animate-spin")} />
                {syncing ? "Syncing…" : "Sync"}
              </Button>
            </div>
          )}
        </div>

        {/* Content */}
        {!selectedDealId ? (
          <div className="flex flex-col items-center gap-3 rounded-xl border border-border/30 bg-card/40 px-6 py-16">
            <Mail className="h-8 w-8 text-muted-foreground/20" />
            <p className="text-sm font-medium text-muted-foreground">Select a deal to see its email history</p>
            <p className="text-xs text-muted-foreground/60">Full threads, rendered HTML, and AI-extracted insights</p>
          </div>
        ) : threadLoading ? (
          <div className="space-y-3">
            {[...Array(4)].map((_, i) => <Skeleton key={i} className="h-20 w-full rounded-xl" />)}
          </div>
        ) : emails.length === 0 ? (
          <div className="flex flex-col items-center gap-3 rounded-xl border border-border/30 bg-card/40 px-6 py-16">
            <AlertCircle className="h-8 w-8 text-muted-foreground/20" />
            <p className="text-sm font-medium text-muted-foreground">No emails found for this deal</p>
            <p className="text-xs text-muted-foreground/60 text-center max-w-sm">
              Emails must be visible under this deal's Emails tab in Zoho. Re-login if you recently added the email scope.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">

            {/* Email thread — wider column */}
            <div className="lg:col-span-3 space-y-4">
              <p className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground/60">
                {viewMode === "grouped"
                  ? `${threads.length} thread${threads.length !== 1 ? "s" : ""} · ${emails.length} messages`
                  : `${emails.length} email${emails.length !== 1 ? "s" : ""}`}
              </p>

              {viewMode === "grouped"
                ? threads.map((t, i) => (
                    <ThreadView
                      key={t.thread_id || i}
                      thread={t}
                      extracted={thread?.extracted}
                    />
                  ))
                : emails.map((e, i) => (
                    <MessageBubble key={e.message_id || i} email={e} defaultExpanded={i === 0} />
                  ))
              }
            </div>

            {/* Insights sidebar */}
            <div className="lg:col-span-2 space-y-4">
              <p className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground/60">Insights</p>

              {/* ── Metrics card ── */}
              <div className="rounded-xl border border-border/30 bg-card/60 p-4 grid grid-cols-3 gap-3 text-center">
                {/* Total */}
                <div className="space-y-0.5">
                  <p className="text-lg font-bold text-foreground">{emails.length}</p>
                  <p className="text-[10px] text-muted-foreground">Total</p>
                  <p className="text-[9px] text-muted-foreground/50">in thread</p>
                </div>
                {/* Sent */}
                <div className="space-y-0.5">
                  <p className="text-lg font-bold text-primary">{sentCount}</p>
                  <p className="text-[10px] text-muted-foreground">Sent</p>
                  <p className="text-[9px] text-muted-foreground/50">by our team</p>
                </div>
                {/* Received — red if 0 */}
                <div className="space-y-0.5">
                  <p className={cn("text-lg font-bold", receivedCount === 0 && sentCount > 0 ? "text-red-400" : "text-foreground")}>
                    {receivedCount}
                  </p>
                  <p className={cn("text-[10px]", receivedCount === 0 && sentCount > 0 ? "text-red-400/70" : "text-muted-foreground")}>
                    Received
                  </p>
                  {/* Response rate */}
                  <p className={cn(
                    "text-[9px] font-semibold",
                    responseRate === 0 ? "text-red-400/80" : responseRate < 50 ? "text-yellow-400/80" : "text-green-400/80"
                  )}>
                    {responseRate}% reply rate
                  </p>
                </div>
              </div>

              {/* One-sided conversation warning */}
              {noReply && (
                <p className="text-[10px] text-center text-red-400/70 -mt-2">
                  One-sided conversation detected. Consider a different approach.
                </p>
              )}

              {/* ── No-reply alert banner ── */}
              {noReply && (
                <div className={cn(
                  "relative overflow-hidden rounded-xl border px-4 py-3.5",
                  "border-orange-500/40 bg-orange-500/10",
                  "animate-pulse-slow"
                )}>
                  {/* Pulsing left accent */}
                  <div className="absolute left-0 top-0 bottom-0 w-1 bg-orange-500/60 animate-pulse" />
                  <div className="pl-2 space-y-2">
                    <div className="flex items-center gap-2">
                      <Bell className="h-4 w-4 text-orange-400 shrink-0 animate-bounce" style={{ animationDuration: "2s" }} />
                      <span className="text-xs font-bold text-orange-400">No buyer response yet</span>
                    </div>
                    <p className="text-[11px] text-orange-300/80 leading-relaxed">
                      {daysSinceReply !== null
                        ? `No reply in ${daysSinceReply} day${daysSinceReply !== 1 ? "s" : ""}. The buyer has gone quiet.`
                        : `${sentCount} emails sent with no reply. The buyer has gone quiet.`}
                    </p>
                    <Button
                      size="sm"
                      className="h-7 w-full text-xs bg-orange-500/20 text-orange-300 border border-orange-500/30 hover:bg-orange-500/30 gap-1.5"
                      variant="outline"
                      onClick={() => setDraftModalOpen(true)}
                    >
                      <Mail className="h-3 w-3" />
                      Send Follow-up →
                    </Button>
                  </div>
                </div>
              )}

              {/* Days since last reply (when there are replies but it's been a while) */}
              {!noReply && daysSinceReply !== null && daysSinceReply > 7 && (
                <div className="flex items-center gap-2 rounded-lg border border-yellow-500/20 bg-yellow-500/5 px-3 py-2">
                  <Clock className="h-3.5 w-3.5 text-yellow-400 shrink-0" />
                  <p className="text-[11px] text-yellow-400/80">
                    Last reply was {daysSinceReply} days ago
                  </p>
                </div>
              )}

              {/* AI analysis */}
              {thread?.extracted ? (
                <AIInsightsPanel
                  extracted={thread.extracted}
                  onReanalyse={handleReanalyse}
                  analysing={analysing}
                  onDraftEmail={() => setDraftModalOpen(true)}
                  dealName={selectedDeal?.name}
                />
              ) : (
                <div className="rounded-xl border border-border/20 bg-card/30 p-4 space-y-3 text-center">
                  <Lightbulb className="h-5 w-5 text-muted-foreground/20 mx-auto" />
                  <p className="text-xs text-muted-foreground/60">
                    AI analysis not yet available. Click below to analyse the thread.
                  </p>
                  <Button size="sm" variant="outline" className="h-7 text-xs w-full hover:bg-secondary/60 transition-colors"
                    onClick={handleReanalyse} disabled={analysing}>
                    <Sparkles className={cn("mr-1.5 h-3 w-3", analysing && "animate-spin")} />
                    {analysing ? "Analysing…" : "Analyse Thread"}
                  </Button>
                </div>
              )}
            </div>

          </div>
        )}
      </div>

      {/* Draft email modal */}
      <DraftEmailModal
        open={draftModalOpen}
        onClose={() => setDraftModalOpen(false)}
        nextStep={thread?.extracted?.next_step ?? ""}
        dealName={selectedDeal?.name ?? "this deal"}
      />
    </div>
  );
}
