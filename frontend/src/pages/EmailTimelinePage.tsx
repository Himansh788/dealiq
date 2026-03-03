import { useState, useEffect, useCallback } from "react";
import DOMPurify from "dompurify";
import { api } from "@/lib/api";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";
import { format, formatDistanceToNow, parseISO, differenceInDays } from "date-fns";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList,
} from "@/components/ui/command";
import {
  Mail, Send, RefreshCw, ChevronsUpDown, Check, AlertCircle,
  ChevronDown, ChevronRight, Lightbulb, ListChecks, HelpCircle,
  ArrowRight, Sparkles, Calendar, TrendingUp, TrendingDown, Minus,
  AlertTriangle, CheckCircle2, Users, MessageSquare, ArrowUpRight,
  Clock, Zap,
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
  // legacy fields
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

// Vervotech domain — emails from this domain are "outbound" (our team)
const OUR_DOMAIN = "vervotech.com";

// Signature separators — strip everything below these
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
  try {
    const d = parseISO(dateStr);
    return format(d, "MMM d, yyyy · h:mm a");
  } catch {
    return dateStr;
  }
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

/** Strip the quoted/forwarded tail from plain text — keep only the new message. */
function stripQuotedText(text: string): string {
  // Remove "On <date>, <name> wrote:" forward markers
  const forwardIdx = text.search(/^On .+wrote:\s*$/m);
  if (forwardIdx > 80) text = text.slice(0, forwardIdx);

  // Remove sig patterns
  for (const pat of SIG_PATTERNS) {
    const m = text.search(pat);
    if (m > 40) { text = text.slice(0, m); break; }
  }
  return text.trim();
}

/** Sanitise HTML for safe inline rendering, stripping blockquotes (quoted replies). */
function sanitizeEmailHtml(html: string): string {
  // Remove blockquote chains (quoted previous messages in thread)
  const stripped = html.replace(/<blockquote[\s\S]*?<\/blockquote>/gi, "");
  return DOMPurify.sanitize(stripped, {
    ALLOWED_TAGS: ["p","br","div","span","b","strong","i","em","u","a","ul","ol","li","h1","h2","h3","pre","table","tr","td","th","tbody","thead"],
    ALLOWED_ATTR: ["href","target","style","class"],
    FORCE_BODY: true,
  });
}

// ── MessageBubble ──────────────────────────────────────────────────────────────

function MessageBubble({ email, defaultExpanded = false }: { email: EmailMessage; defaultExpanded?: boolean }) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const [showFull, setShowFull] = useState(false);

  const outbound = isOurTeam(email.from) || email.direction === "sent";
  const name = senderName(email.from);
  const initials = senderInitials(email.from);

  // Prefer HTML content rendered via DOMPurify; fall back to plain text processing
  const hasHtml = Boolean(email.html_content);
  const safeHtml = hasHtml ? sanitizeEmailHtml(email.html_content!) : null;

  // For plain text: strip quoted tail
  const plainBody = email.body_full || email.body_preview || email.snippet || "";
  const cleanPlain = stripQuotedText(plainBody);
  const previewText = cleanPlain.slice(0, 180);

  const hasBody = Boolean(safeHtml || cleanPlain);

  return (
    <div className={cn("flex gap-3", outbound ? "flex-row-reverse" : "flex-row")}>
      {/* Avatar */}
      <div className={cn(
        "h-7 w-7 rounded-full flex items-center justify-center text-[10px] font-bold shrink-0 mt-1",
        outbound ? "bg-primary/20 text-primary" : "bg-muted text-muted-foreground"
      )}>
        {initials}
      </div>

      {/* Bubble */}
      <div className={cn(
        "max-w-[82%] rounded-2xl border text-xs",
        outbound
          ? "rounded-tr-sm bg-primary/8 border-primary/20"
          : "rounded-tl-sm bg-card border-border/50"
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
            <p className="text-[10px] text-muted-foreground/60">
              {formatDateTime(email.date || email.sent_at)}
            </p>
          </div>
          {expanded
            ? <ChevronDown className="h-3 w-3 text-muted-foreground/40 shrink-0 mt-0.5" />
            : <ChevronRight className="h-3 w-3 text-muted-foreground/40 shrink-0 mt-0.5" />}
        </button>

        {/* Preview when collapsed */}
        {!expanded && hasBody && (
          <p className="px-4 pb-3 text-[11px] text-muted-foreground/70 line-clamp-2 leading-relaxed">
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
                      className="prose prose-xs dark:prose-invert max-w-none text-[11px] leading-relaxed text-foreground/90 [&_a]:text-primary [&_a]:underline"
                      dangerouslySetInnerHTML={{ __html: showFull ? DOMPurify.sanitize(email.html_content!, { FORCE_BODY: true }) : safeHtml }}
                    />
                  ) : (
                    <p className="text-[11px] leading-relaxed text-foreground/90 whitespace-pre-wrap">
                      {showFull ? plainBody : cleanPlain}
                    </p>
                  )}
                  <button
                    className="mt-2 text-[10px] text-muted-foreground/50 hover:text-muted-foreground underline"
                    onClick={e => { e.stopPropagation(); setShowFull(v => !v); }}
                  >
                    {showFull ? "Hide quoted thread" : "Show full thread including quoted replies"}
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

function ThreadView({ thread }: { thread: Thread }) {
  const [open, setOpen] = useState(true);

  return (
    <div className="rounded-xl border border-border/30 bg-card/20 overflow-hidden">
      <button
        className="w-full flex items-center gap-2.5 px-4 py-2.5 text-left bg-card/50 hover:bg-card/70 transition-colors"
        onClick={() => setOpen(v => !v)}
      >
        <Mail className="h-3.5 w-3.5 text-muted-foreground/50 shrink-0" />
        <span className="text-xs font-medium text-foreground flex-1 truncate">{thread.subject}</span>
        <span className="text-[10px] text-muted-foreground/50 shrink-0 mr-1">
          {thread.message_count} msg{thread.message_count !== 1 ? "s" : ""} · {formatRelative(thread.latest_date)}
        </span>
        {open ? <ChevronDown className="h-3 w-3 text-muted-foreground/40 shrink-0" />
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

function normaliseCommitment(c: Commitment | string): Commitment {
  if (typeof c === "string") return { by: "", what: c, deadline: null, status: "pending" };
  return c;
}

function normaliseDeadline(d: Deadline | string): Deadline {
  if (typeof d === "string") return { what: d, date: "", urgency: "medium" };
  return d;
}

function AIInsightsPanel({
  extracted, onReanalyse, analysing, onDraftEmail,
}: {
  extracted: Extracted;
  onReanalyse: () => void;
  analysing: boolean;
  onDraftEmail?: () => void;
}) {
  const [showOpenQ, setShowOpenQ]  = useState(false);
  const [showRelMap, setShowRelMap] = useState(false);

  const sentiment  = (extracted.sentiment || "").toLowerCase();
  const momentum   = (extracted.momentum  || "").toLowerCase();
  const sentCfg    = SENTIMENT_CONFIG[sentiment]  ?? SENTIMENT_CONFIG["neutral"];
  const momCfg     = MOMENTUM_CONFIG[momentum];
  const MomIcon    = momCfg?.Icon ?? Minus;

  const commitments = (extracted.commitments ?? []).map(normaliseCommitment);
  const deadlines   = (extracted.deadlines   ?? []).map(normaliseDeadline);
  const contacts    = extracted.key_contacts  ?? [];

  return (
    <div className="rounded-xl border border-violet-500/20 bg-violet-500/5 divide-y divide-violet-500/10 overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 flex items-center gap-2">
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
        </div>
      </div>

      {/* Summary */}
      {extracted.summary && (
        <div className="px-4 py-3">
          <p className="text-[11px] text-muted-foreground leading-relaxed">{extracted.summary}</p>
        </div>
      )}

      {/* Next step — most prominent */}
      {extracted.next_step && (
        <div className="px-4 py-3 bg-violet-500/5">
          <div className="flex items-start gap-2">
            <Zap className="h-3.5 w-3.5 text-violet-400 shrink-0 mt-0.5" />
            <div className="flex-1 min-w-0">
              <p className="text-[10px] font-bold text-violet-400 uppercase tracking-wider mb-1">Next step</p>
              <p className="text-xs font-medium text-foreground leading-relaxed">{extracted.next_step}</p>
            </div>
          </div>
          {onDraftEmail && (
            <Button
              size="sm"
              className="mt-2.5 h-7 text-xs w-full bg-violet-600 hover:bg-violet-700 text-white"
              onClick={onDraftEmail}
            >
              <ArrowUpRight className="mr-1.5 h-3 w-3" />
              Draft Email
            </Button>
          )}
        </div>
      )}

      {/* Buying signals */}
      {(extracted.buying_signals?.length ?? 0) > 0 && (
        <div className="px-4 py-3 space-y-1.5">
          <p className="text-[10px] font-semibold text-muted-foreground/60 uppercase tracking-wider">Buying signals</p>
          {extracted.buying_signals!.map((s, i) => (
            <div key={i} className="flex gap-2">
              <CheckCircle2 className="h-3 w-3 text-green-400 shrink-0 mt-0.5" />
              <p className="text-[11px] text-foreground/80">{s}</p>
            </div>
          ))}
        </div>
      )}

      {/* Risk signals */}
      {(extracted.risk_signals?.length ?? 0) > 0 && (
        <div className="px-4 py-3 space-y-1.5">
          <p className="text-[10px] font-semibold text-muted-foreground/60 uppercase tracking-wider">Risk signals</p>
          {extracted.risk_signals!.map((s, i) => (
            <div key={i} className="flex gap-2">
              <AlertTriangle className="h-3 w-3 text-red-400 shrink-0 mt-0.5" />
              <p className="text-[11px] text-foreground/80">{s}</p>
            </div>
          ))}
        </div>
      )}

      {/* Commitments */}
      {commitments.length > 0 && (
        <div className="px-4 py-3 space-y-2">
          <div className="flex items-center gap-1.5">
            <ListChecks className="h-3.5 w-3.5 text-violet-400" />
            <p className="text-[10px] font-semibold text-muted-foreground/60 uppercase tracking-wider">Commitments</p>
          </div>
          {commitments.map((c, i) => (
            <div key={i} className={cn(
              "flex gap-2 rounded-lg px-2.5 py-1.5 text-[11px]",
              c.status === "overdue" ? "bg-red-500/10 border border-red-500/20" : "bg-card/50"
            )}>
              {c.status === "fulfilled"
                ? <CheckCircle2 className="h-3 w-3 text-green-400 shrink-0 mt-0.5" />
                : c.status === "overdue"
                ? <AlertTriangle className="h-3 w-3 text-red-400 shrink-0 mt-0.5" />
                : <Clock className="h-3 w-3 text-yellow-400 shrink-0 mt-0.5" />}
              <div className="flex-1 min-w-0">
                {c.by && <span className="font-semibold text-foreground/70">{c.by}: </span>}
                <span className="text-foreground/80">{c.what}</span>
                {c.deadline && (
                  <span className={cn("ml-1.5 text-[10px]", c.status === "overdue" ? "text-red-400" : "text-muted-foreground/60")}>
                    · {c.deadline}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Deadlines */}
      {deadlines.length > 0 && (
        <div className="px-4 py-3 space-y-1.5">
          <div className="flex items-center gap-1.5">
            <Calendar className="h-3.5 w-3.5 text-violet-400" />
            <p className="text-[10px] font-semibold text-muted-foreground/60 uppercase tracking-wider">Deadlines</p>
          </div>
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
      )}

      {/* Key contacts */}
      {contacts.length > 0 && (
        <div className="px-4 py-3 space-y-2">
          <div className="flex items-center gap-1.5">
            <Users className="h-3.5 w-3.5 text-violet-400" />
            <p className="text-[10px] font-semibold text-muted-foreground/60 uppercase tracking-wider">Key contacts</p>
          </div>
          <div className="flex flex-wrap gap-2">
            {contacts.map((c, i) => (
              <div key={i} className="flex items-center gap-2 rounded-lg border border-border/30 bg-card/60 px-2.5 py-1.5">
                <div className={cn(
                  "h-6 w-6 rounded-full flex items-center justify-center text-[9px] font-bold shrink-0",
                  c.engagement === "high"   ? "bg-green-500/20 text-green-400"  :
                  c.engagement === "medium" ? "bg-yellow-500/20 text-yellow-400" :
                                              "bg-muted text-muted-foreground"
                )}>
                  {(c.name || "?").split(" ").slice(0, 2).map((w: string) => w[0]).join("")}
                </div>
                <div>
                  <p className="text-[11px] font-medium text-foreground">{c.name}</p>
                  {c.role && <p className="text-[10px] text-muted-foreground/60">{c.role}</p>}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Open questions — collapsed by default */}
      {(extracted.open_questions?.length ?? 0) > 0 && (
        <div className="px-4 py-2.5">
          <button
            className="w-full flex items-center gap-1.5 text-[10px] font-semibold text-muted-foreground/60 uppercase tracking-wider"
            onClick={() => setShowOpenQ(v => !v)}
          >
            <HelpCircle className="h-3 w-3" />
            Open questions ({extracted.open_questions!.length})
            {showOpenQ ? <ChevronDown className="h-3 w-3 ml-auto" /> : <ChevronRight className="h-3 w-3 ml-auto" />}
          </button>
          {showOpenQ && (
            <ul className="mt-2 space-y-1">
              {extracted.open_questions!.map((q, i) => (
                <li key={i} className="flex gap-1.5 text-[11px] text-foreground/70">
                  <span className="text-violet-400 shrink-0">·</span>{q}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Relationship map — collapsed by default */}
      {extracted.relationship_map && (
        <div className="px-4 py-2.5">
          <button
            className="w-full flex items-center gap-1.5 text-[10px] font-semibold text-muted-foreground/60 uppercase tracking-wider"
            onClick={() => setShowRelMap(v => !v)}
          >
            <MessageSquare className="h-3 w-3" />
            Relationship map
            {showRelMap ? <ChevronDown className="h-3 w-3 ml-auto" /> : <ChevronRight className="h-3 w-3 ml-auto" />}
          </button>
          {showRelMap && (
            <p className="mt-2 text-[11px] text-muted-foreground leading-relaxed">{extracted.relationship_map}</p>
          )}
        </div>
      )}

      {/* Re-analyse */}
      <div className="px-4 py-2.5">
        <button
          className="text-[10px] text-violet-400/60 hover:text-violet-400 flex items-center gap-1 disabled:opacity-40"
          onClick={onReanalyse}
          disabled={analysing}
        >
          <RefreshCw className={cn("h-2.5 w-2.5", analysing && "animate-spin")} />
          {analysing ? "Analysing…" : "Re-analyse thread"}
        </button>
      </div>
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

  const [viewMode, setViewMode] = useState<"grouped" | "flat">("grouped");

  const selectedDeal = deals.find(d => d.id === selectedDealId);

  useEffect(() => {
    api.getAllDeals()
      .then(data => setDeals(Array.isArray(data) ? data : []))
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

  const emails  = thread?.emails   ?? [];
  const threads = thread?.threads  ?? [];
  const sentCount     = emails.filter(e => isOurTeam(e.from) || e.direction === "sent").length;
  const receivedCount = emails.length - sentCount;

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

          {/* Stats badges */}
          {thread && !threadLoading && (
            <div className="flex items-center gap-2">
              <Badge variant="outline" className="text-[10px] h-6 px-2 border-border/40 text-muted-foreground gap-1">
                <Send className="h-2.5 w-2.5" />{sentCount} sent
              </Badge>
              <Badge variant="outline" className="text-[10px] h-6 px-2 border-border/40 text-muted-foreground gap-1">
                <Mail className="h-2.5 w-2.5" />{receivedCount} received
              </Badge>
            </div>
          )}

          {/* View toggle + Sync */}
          {selectedDealId && emails.length > 0 && (
            <div className="ml-auto flex items-center gap-2">
              <div className="flex rounded-lg border border-border/40 overflow-hidden text-[11px]">
                <button onClick={() => setViewMode("grouped")}
                  className={cn("px-2.5 py-1", viewMode === "grouped" ? "bg-primary/10 text-primary" : "text-muted-foreground hover:text-foreground")}>
                  Threads
                </button>
                <button onClick={() => setViewMode("flat")}
                  className={cn("px-2.5 py-1", viewMode === "flat" ? "bg-primary/10 text-primary" : "text-muted-foreground hover:text-foreground")}>
                  Flat
                </button>
              </div>
              <Button size="sm" variant="outline" className="h-8 text-xs border-border/50"
                onClick={handleSync} disabled={syncing}>
                <RefreshCw className={cn("mr-1.5 h-3 w-3", syncing && "animate-spin")} />
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
                ? threads.map((t, i) => <ThreadView key={t.thread_id || i} thread={t} />)
                : emails.map((e, i) => (
                    <MessageBubble key={e.message_id || i} email={e} defaultExpanded={i === 0} />
                  ))
              }
            </div>

            {/* Insights sidebar */}
            <div className="lg:col-span-2 space-y-4">
              <p className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground/60">Insights</p>

              {/* Quick stats */}
              <div className="rounded-xl border border-border/30 bg-card/60 p-4 grid grid-cols-3 gap-3 text-center">
                <div>
                  <p className="text-lg font-bold text-foreground">{emails.length}</p>
                  <p className="text-[10px] text-muted-foreground">Total</p>
                </div>
                <div>
                  <p className="text-lg font-bold text-primary">{sentCount}</p>
                  <p className="text-[10px] text-muted-foreground">Sent</p>
                </div>
                <div>
                  <p className="text-lg font-bold text-foreground">{receivedCount}</p>
                  <p className="text-[10px] text-muted-foreground">Received</p>
                </div>
              </div>

              {receivedCount === 0 && sentCount > 0 && (
                <div className="flex gap-2 rounded-lg border border-orange-500/20 bg-orange-500/10 px-3 py-2 text-[11px] text-orange-400">
                  <AlertCircle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
                  No buyer response yet — consider a different outreach approach
                </div>
              )}

              {/* AI analysis */}
              {thread?.extracted ? (
                <AIInsightsPanel
                  extracted={thread.extracted}
                  onReanalyse={handleReanalyse}
                  analysing={analysing}
                />
              ) : (
                <div className="rounded-xl border border-border/20 bg-card/30 p-4 space-y-3 text-center">
                  <Lightbulb className="h-5 w-5 text-muted-foreground/20 mx-auto" />
                  <p className="text-xs text-muted-foreground/60">
                    AI analysis not yet available. Click below to analyse the thread.
                  </p>
                  <Button size="sm" variant="outline" className="h-7 text-xs w-full"
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
    </div>
  );
}
