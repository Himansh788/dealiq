import React, { useState, useEffect, useCallback, useRef, useMemo } from "react";
import DOMPurify from "dompurify";
import EmailThreadView, { getChainStats } from "@/components/email/EmailThreadView";
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

// ── Email chain parser ─────────────────────────────────────────────────────────

interface ChainMessage {
  sender: string;   // raw "Name <email>" or extracted name
  date: string;   // raw date string as found in header, may be empty
  body: string;   // trimmed body text for this message only
}

/**
 * Split a flat plain-text email body into individual messages.
 * Handles both Outlook "From: ... Date: ... Subject: ..." and
 * Gmail "On Mon, 1 Dec 2025 at 12:00 PM Foo Bar <foo@bar.com> wrote:" delimiters.
 * Returns array newest-first; [0] is the outermost (newest) message.
 */
function parseEmailChain(raw: string): ChainMessage[] {
  if (!raw || raw.trim().length < 40) return [];

  // ── Normalise: collapse excessive blank lines ──────────────────────────────
  const text = raw.replace(/\r\n/g, "\n").replace(/\n{3,}/g, "\n\n");

  // ── Build a list of split positions ───────────────────────────────────────
  // headerEnd tracks the character position AFTER the full delimiter block so we
  // can correctly skip it when slicing the body text.
  type SplitPoint = { index: number; headerEnd: number; sender: string; date: string };
  const splits: SplitPoint[] = [];

  // Pattern A — Gmail / Apple Mail style:
  //   "On Mon, 1 Dec 2025 at 7:23 PM Darryl Ismail <darryl@innstant.travel> wrote:"
  const gmailRe =
    /On\s+(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun),?\s+\w+\s+\d{1,2}(?:,\s+\d{4})?.+?wrote:/gis;
  let m: RegExpExecArray | null;
  while ((m = gmailRe.exec(text)) !== null) {
    // Extract date + sender from the matched header
    const header = m[0];
    const dateMatch = header.match(/On\s+(.+?)\s+[A-Z][a-z]+ [A-Z][a-z]+\s+</i)
      ?? header.match(/On\s+(.+?)\s+wrote:/i);
    const senderMatch = header.match(/([\w\s]+)\s*<([^>]+)>\s+wrote:/i)
      ?? header.match(/([^<\n]+)\s+wrote:/i);
    splits.push({
      index: m.index,
      headerEnd: m.index + m[0].length,
      sender: senderMatch ? senderMatch[1].trim() : "",
      date: dateMatch ? dateMatch[1].trim() : "",
    });
  }

  // Pattern B — Outlook "From:" block (multi-line, terminated by "Subject: …" line):
  //   "From: Name <email>\nSent: date\nTo: ...\nSubject: ..."
  const outlookRe =
    /^From:\s*(.+?)[\r\n]+(?:Sent|Date):\s*(.+?)[\r\n]+(?:To|Cc):.*?[\r\n]+Subject:[^\n]*/gim;
  while ((m = outlookRe.exec(text)) !== null) {
    // Avoid double-counting a position already captured by gmailRe (within ±80 chars)
    const near = splits.some(s => Math.abs(s.index - m!.index) < 80);
    if (!near) {
      splits.push({
        index: m.index,
        headerEnd: m.index + m[0].length,
        sender: m[1].trim(),
        date: m[2].trim(),
      });
    }
  }

  if (splits.length === 0) {
    // Nothing to split — return the whole text as one message
    return [{ sender: "", date: "", body: text.trim() }];
  }

  // Sort by position ascending
  splits.sort((a, b) => a.index - b.index);

  // ── Slice the text at each split point ────────────────────────────────────
  const parts: ChainMessage[] = [];

  // First segment: text before the first split is the newest message
  const firstBody = text.slice(0, splits[0].index).trim();
  if (firstBody) parts.push({ sender: "", date: "", body: firstBody });

  for (let i = 0; i < splits.length; i++) {
    const sp = splits[i];
    const end = splits[i + 1]?.index ?? text.length;
    // Skip past the full matched header block, then advance to the next line start
    const afterHeader = text.indexOf("\n", sp.headerEnd);
    const bodyStart = afterHeader > -1 ? afterHeader + 1 : sp.headerEnd;
    const body = text.slice(bodyStart, end).trim();
    // Strip nested quoted lines (">") from this body slice
    const cleanBody = body
      .split("\n")
      .filter(line => !line.trimStart().startsWith(">"))
      .join("\n")
      .trim();
    if (cleanBody) {
      parts.push({ sender: sp.sender, date: sp.date, body: cleanBody });
    }
  }

  return parts;
}

// ── Plain-text email renderer ──────────────────────────────────────────────────

/** Detect URLs and wrap them in <a> tags, returning an array of strings + elements. */
function renderWithLinks(text: string): React.ReactNode[] {
  const urlRe = /https?:\/\/[^\s<>"')]+/g;
  const parts: React.ReactNode[] = [];
  let last = 0;
  let key = 0;
  let m: RegExpExecArray | null;
  while ((m = urlRe.exec(text)) !== null) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    const url = m[0].replace(/[.,;!?)\]]+$/, ""); // trim trailing punctuation
    const label = url.length > 55 ? url.slice(0, 55) + "…" : url;
    parts.push(
      <a
        key={key++}
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        className="text-primary underline underline-offset-2 hover:text-primary/70 break-all transition-colors"
        onClick={e => e.stopPropagation()}
      >
        {label}
      </a>
    );
    last = m.index + m[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

/** Collapsible signature block shown at the bottom of a message. */
function SignatureBlock({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-3 pt-2.5 border-t border-border/20">
      <button
        onClick={e => { e.stopPropagation(); setOpen(v => !v); }}
        className="flex items-center gap-1.5 text-[10px] text-muted-foreground/40 hover:text-muted-foreground/70 transition-colors"
      >
        <span className="font-mono tracking-widest">{open ? "▾" : "⋯"}</span>
        {!open && <span>Show signature</span>}
      </button>
      {open && (
        <p className="mt-2 text-[11px] text-muted-foreground/60 whitespace-pre-wrap leading-relaxed pl-2 border-l border-border/30">
          {text}
        </p>
      )}
    </div>
  );
}

/**
 * Render a plain-text email body properly:
 * - Splits double-newlines → paragraph blocks
 * - Single newlines within a paragraph → preserved line breaks
 * - URLs auto-linked
 * - Signature detected and collapsed behind a toggle
 */
function renderPlainBody(text: string, compact = false): React.ReactNode {
  if (!text) return null;

  // Split off signature
  let mainText = text;
  let sigText = "";
  for (const pat of SIG_PATTERNS) {
    const idx = mainText.search(pat);
    if (idx > 60) {
      sigText = mainText.slice(idx).trim();
      mainText = mainText.slice(0, idx).trim();
      break;
    }
  }

  // Split on double newlines → paragraphs
  const paras = mainText.split(/\n{2,}/).filter(p => p.trim());

  return (
    <>
      <div className={cn(compact ? "space-y-1.5" : "space-y-3")}>
        {paras.map((para, i) => {
          // Within each paragraph, split on single newlines to get line-break structure
          const lines = para.split("\n");
          return (
            <p
              key={i}
              className={cn(
                compact
                  ? "text-[11px] text-foreground/75 leading-relaxed"
                  : "text-[13px] text-foreground leading-[1.65]"
              )}
            >
              {lines.map((line, j) => (
                <span key={j}>
                  {renderWithLinks(line)}
                  {j < lines.length - 1 && <br />}
                </span>
              ))}
            </p>
          );
        })}
      </div>
      {sigText && <SignatureBlock text={sigText} />}
    </>
  );
}

// ── Constants ──────────────────────────────────────────────────────────────────

const HEALTH_DOT: Record<string, string> = {
  healthy: "bg-green-500",
  watching: "bg-yellow-500",
  at_risk: "bg-orange-500",
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

/**
 * Determine if an email was sent by our team.
 * Prioritises the `from` address (domain check) over Zoho's `direction` field,
 * because Zoho returns `direction: "sent"` for ALL emails on a Deal record —
 * including replies from the buyer — making that field unreliable for direction.
 */
function isOutbound(e: { from?: string; direction?: string }): boolean {
  if (e.from) return isOurTeam(e.from);
  return (e.direction ?? "") === "sent";
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
    ALLOWED_TAGS: ["p", "br", "div", "span", "b", "strong", "i", "em", "u", "a", "ul", "ol", "li", "h1", "h2", "h3", "pre", "table", "tr", "td", "th", "tbody", "thead"],
    ALLOWED_ATTR: ["href", "target"],
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
    return { label: "High", cls: "text-green-400 border-green-500/30 bg-green-500/10" };
  if (/(interested|considering|open to|requested|asked|exploring|evaluating)/.test(s))
    return { label: "Medium", cls: "text-yellow-400 border-yellow-500/30 bg-yellow-500/10" };
  return { label: "Low", cls: "text-muted-foreground border-border/40 bg-muted/20" };
}

/** Derive thread health from sentiment + momentum. */
function threadHealthBadge(sentiment: string, momentum: string): { label: string; emoji: string; cls: string } {
  const s = sentiment.toLowerCase();
  const m = momentum.toLowerCase();
  if (s === "positive" && (m === "accelerating" || m === "steady"))
    return { label: "Progressing", emoji: "🟢", cls: "text-green-400 border-green-500/30 bg-green-500/10" };
  if (s === "positive" || m === "steady")
    return { label: "Active", emoji: "🟡", cls: "text-yellow-400 border-yellow-500/30 bg-yellow-500/10" };
  return { label: "Stalled", emoji: "🔴", cls: "text-red-400 border-red-500/30 bg-red-500/10" };
}

function normaliseCommitment(c: Commitment | string): Commitment {
  if (typeof c === "string") return { by: "", what: c, deadline: null, status: "pending" };
  return c;
}

function normaliseDeadline(d: Deadline | string): Deadline {
  if (typeof d === "string") return { what: d, date: "", urgency: "medium" };
  return d;
}

// Per-thread accent colours — cycles for > 4 threads
const THREAD_COLORS = [
  { border: "border-l-4 border-purple-500", badgeCls: "bg-purple-500/10 text-purple-400 border-purple-500/30" },
  { border: "border-l-4 border-blue-500", badgeCls: "bg-blue-500/10 text-blue-400 border-blue-500/30" },
  { border: "border-l-4 border-teal-500", badgeCls: "bg-teal-500/10 text-teal-400 border-teal-500/30" },
  { border: "border-l-4 border-amber-500", badgeCls: "bg-amber-500/10 text-amber-400 border-amber-500/30" },
];

/** Returns true when a deadline string (ISO or human-readable) is in the past. */
function isDeadlineExpired(deadline: string | null | undefined): boolean {
  if (!deadline) return false;
  try {
    // ISO parse first
    const d = parseISO(deadline);
    if (!isNaN(d.getTime())) return d < new Date();
    // Human-readable fallback: strip ordinal suffixes ("31st" → "31")
    const cleaned = deadline.replace(/(\d+)(st|nd|rd|th)/i, "$1");
    const d2 = new Date(cleaned);
    if (!isNaN(d2.getTime())) return d2 < new Date();
    return false;
  } catch { return false; }
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
  open, onClose, nextStep, dealName, contactEmail, threadSubject,
}: {
  open: boolean;
  onClose: () => void;
  nextStep: string;
  dealName: string;
  contactEmail?: string;
  threadSubject?: string;
}) {
  const { toast } = useToast();
  const [copied, setCopied] = useState(false);

  const toField = contactEmail || "";
  const subject = threadSubject ? `Re: ${threadSubject}` : `Following up — ${dealName}`;
  const bodyInit = nextStep
    ? `Hi,\n\nFollowing up on our previous conversation.\n\nNext step: ${nextStep}\n\nWould love to connect — please let me know your availability.\n\nBest,`
    : `Hi,\n\nFollowing up on our previous conversation.\n\nWould love to connect — please let me know your availability.\n\nBest,`;

  const [body, setBody] = useState(bodyInit);
  // Reset body when modal opens with new content
  const prevOpen = useRef(false);
  useEffect(() => {
    if (open && !prevOpen.current) setBody(bodyInit);
    prevOpen.current = open;
  }, [open]);

  const copy = () => {
    const text = `To: ${toField}\nSubject: ${subject}\n\n${body}`;
    navigator.clipboard.writeText(text);
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
          {toField && (
            <div>
              <p className="text-[10px] font-semibold text-muted-foreground/60 uppercase tracking-wider mb-1">To</p>
              <p className="rounded-md border border-border/40 bg-secondary/30 px-3 py-2 text-xs text-foreground">{toField}</p>
            </div>
          )}
          <div>
            <p className="text-[10px] font-semibold text-muted-foreground/60 uppercase tracking-wider mb-1">Subject</p>
            <p className="rounded-md border border-border/40 bg-secondary/30 px-3 py-2 text-xs text-foreground">{subject}</p>
          </div>
          <div>
            <p className="text-[10px] font-semibold text-muted-foreground/60 uppercase tracking-wider mb-1">Body</p>
            <textarea
              className="w-full rounded-md border border-border/40 bg-secondary/30 px-3 py-2 text-xs text-foreground resize-none focus:outline-none focus:ring-1 focus:ring-primary/40"
              rows={8}
              value={body}
              onChange={e => setBody(e.target.value)}
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

// ── QuotedMessage (collapsed card inside the reply history) ───────────────────

function QuotedMessage({ msg, depth }: { msg: ChainMessage; depth: number }) {
  const [open, setOpen] = useState(false);
  const isOurs = msg.sender ? msg.sender.toLowerCase().includes(OUR_DOMAIN) : false;
  const preview = msg.body.slice(0, 120);

  return (
    <div className={cn(
      "rounded-lg border text-[11px] transition-colors",
      isOurs
        ? "border-primary/20 bg-primary/5"
        : "border-border/30 bg-muted/20",
    )}>
      <button
        className="w-full flex items-center gap-2 px-3 py-2 text-left"
        onClick={e => { e.stopPropagation(); setOpen(v => !v); }}
      >
        {/* Sender avatar */}
        <div className={cn(
          "h-5 w-5 rounded-full flex items-center justify-center text-[9px] font-bold shrink-0",
          isOurs ? "bg-primary/20 text-primary" : "bg-muted text-muted-foreground"
        )}>
          {msg.sender ? senderInitials(msg.sender) : "?"}
        </div>
        <div className="flex-1 min-w-0 space-y-0.5">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-foreground/80 truncate">
              {msg.sender ? senderName(msg.sender) : "Unknown"}
            </span>
            {msg.date && (
              <span className="text-[10px] text-muted-foreground/50 shrink-0">
                {msg.date.length > 30 ? msg.date.slice(0, 30) + "…" : msg.date}
              </span>
            )}
          </div>
          {!open && (
            <p className="text-muted-foreground/60 truncate">{preview}…</p>
          )}
        </div>
        {open
          ? <ChevronDown className="h-3 w-3 text-muted-foreground/40 shrink-0" />
          : <ChevronRight className="h-3 w-3 text-muted-foreground/40 shrink-0" />}
      </button>
      {open && (
        <div className="px-3 pb-3 border-t border-border/20 pt-2">
          {renderPlainBody(msg.body, true)}
        </div>
      )}
    </div>
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
  const [hoverDate, setHoverDate] = useState(false);

  const outbound = isOutbound(email);
  const name = senderName(email.from);
  const initials = senderInitials(email.from);

  const hasHtml = Boolean(email.html_content);
  const safeHtml = hasHtml ? sanitizeEmailHtml(email.html_content!) : null;

  const plainBody = email.body_full || email.body_preview || email.snippet || "";

  const previewText = stripQuotedText(plainBody).slice(0, 180);
  const hasBody = Boolean(safeHtml || plainBody);
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
          ? "rounded-tr-sm bg-primary/10 border-primary/30 border-l-[3px] border-l-primary/60"
          : "rounded-tl-sm bg-muted/40 border-border/50 border-l-[3px] border-l-border/60",
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

        {/* Preview when collapsed — only the newest message, no chain noise */}
        {!expanded && hasBody && (
          <p className="px-4 pb-3 text-[12px] text-muted-foreground line-clamp-2 leading-relaxed">
            {previewText}{previewText.length >= 180 ? "…" : ""}
          </p>
        )}

        {/* Full body when expanded */}
        {expanded && (
          <>
            <Separator className="opacity-30 mx-4" />
            <div className="px-4 py-3 space-y-3">
              {hasBody ? (
                <>
                  {/* ── Email body — HTML or plain-text thread ── */}
                  {safeHtml ? (
                    <div
                      className={cn(
                        "email-body text-[13px] leading-[1.65] text-foreground",
                        "[&_a]:text-primary [&_a]:underline [&_a]:underline-offset-2 [&_a:hover]:text-primary/70",
                        "[&_p]:mb-3 [&_p:last-child]:mb-0",
                        "[&_div]:mb-1",
                        "[&_br]:leading-none",
                        "[&_ul]:list-disc [&_ul]:pl-5 [&_ul]:mb-3 [&_ul]:space-y-1",
                        "[&_ol]:list-decimal [&_ol]:pl-5 [&_ol]:mb-3 [&_ol]:space-y-1",
                        "[&_li]:leading-relaxed",
                        "[&_h1]:text-base [&_h1]:font-semibold [&_h1]:mb-2 [&_h1]:mt-3",
                        "[&_h2]:text-sm [&_h2]:font-semibold [&_h2]:mb-1.5 [&_h2]:mt-2",
                        "[&_h3]:text-xs [&_h3]:font-semibold [&_h3]:mb-1 [&_h3]:mt-2",
                        "[&_strong]:font-semibold [&_b]:font-semibold",
                        "[&_em]:italic [&_i]:italic",
                        "[&_pre]:bg-muted [&_pre]:rounded-md [&_pre]:p-2.5 [&_pre]:text-[11px] [&_pre]:overflow-x-auto [&_pre]:my-2",
                        "[&_blockquote]:border-l-2 [&_blockquote]:border-border/40 [&_blockquote]:pl-3 [&_blockquote]:text-muted-foreground [&_blockquote]:my-2",
                        "[&_table]:w-full [&_table]:text-[11px] [&_table]:my-2",
                        "[&_td]:py-1 [&_td]:pr-4 [&_th]:py-1 [&_th]:pr-4 [&_th]:font-semibold [&_th]:text-left",
                        "[&_hr]:border-border/30 [&_hr]:my-3",
                      )}
                      dangerouslySetInnerHTML={{ __html: safeHtml }}
                    />
                  ) : (
                    /* Plain text: use EmailThreadView to parse & render the full reply chain */
                    <EmailThreadView
                      rawBody={plainBody}
                      senderName={name}
                      senderEmail={email.from}
                      internalDomains={[OUR_DOMAIN]}
                    />
                  )}
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
  thread, extracted, threadIndex = 0,
}: {
  thread: Thread;
  extracted?: Extracted | null;
  threadIndex?: number;
}) {
  const [open, setOpen] = useState(true);

  const sentiment = (extracted?.sentiment || "").toLowerCase();
  const momentum = (extracted?.momentum || "").toLowerCase();
  const health = sentiment && momentum ? threadHealthBadge(sentiment, momentum) : null;

  const color = THREAD_COLORS[threadIndex % THREAD_COLORS.length];

  // Red date if last activity was > 60 days ago
  const ageInDays = (() => {
    if (!thread.latest_date) return null;
    try { const d = parseISO(thread.latest_date); return isNaN(d.getTime()) ? null : differenceInDays(new Date(), d); }
    catch { return null; }
  })();
  const dateIsOld = ageInDays !== null && ageInDays > 60;

  // Sent/received indicator from messages
  const hasBuyerReply = thread.messages.some(m => !isOutbound(m));

  // Build unique participant initials for avatar stack (max 3)
  const uniqueParticipants = [...new Set(thread.participants ?? [])].slice(0, 4);

  // Style active (recently active) threads
  const isActiveThread = ageInDays !== null && ageInDays <= 3;

  return (
    <div className={cn(
      "rounded-xl border bg-card/20 overflow-hidden transition-all duration-200 hover:border-border/50",
      color.border,
      isActiveThread ? "border-l-[3px] border-l-blue-500 bg-blue-500/5 shadow-sm shadow-blue-500/5" : "border-border/30 border-l-[3px]"
    )}>
      <button
        className={cn("w-full flex items-center gap-2.5 px-4 py-3 text-left transition-colors", isActiveThread ? "bg-blue-500/10 hover:bg-blue-500/20" : "bg-card/50 hover:bg-card/70")}
        onClick={() => setOpen(v => !v)}
      >
        {/* Thread number badge */}
        <Badge
          variant="outline"
          className={cn("text-[9px] h-4 px-1.5 shrink-0 font-bold", color.badgeCls)}
        >
          Thread {threadIndex + 1}
        </Badge>

        {/* Subject */}
        <span className="text-xs font-medium text-foreground flex-1 truncate">{thread.subject}</span>

        {/* Health badge */}
        {health && (
          <Badge variant="outline" className={cn("text-[9px] h-4 px-1.5 gap-0.5 shrink-0", health.cls)}>
            {health.emoji} {health.label}
          </Badge>
        )}

        {/* Sent/received pill */}
        <Badge
          variant="outline"
          className={cn(
            "text-[9px] h-4 px-1.5 shrink-0",
            hasBuyerReply
              ? "text-green-400 border-green-500/30 bg-green-500/10"
              : "text-orange-400 border-orange-500/30 bg-orange-500/10"
          )}
        >
          {hasBuyerReply ? "Replied" : "No reply"}
        </Badge>

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

        <span className={cn(
          "text-[10px] shrink-0",
          dateIsOld ? "text-red-400/80" : "text-muted-foreground/50"
        )}>
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
  positive: { label: "Positive", cls: "text-green-400  border-green-500/30  bg-green-500/10" },
  neutral: { label: "Neutral", cls: "text-yellow-400 border-yellow-500/30 bg-yellow-500/10" },
  negative: { label: "Negative", cls: "text-red-400    border-red-500/30    bg-red-500/10" },
  at_risk: { label: "At Risk", cls: "text-orange-400 border-orange-500/30 bg-orange-500/10" },
  mixed: { label: "Mixed", cls: "text-yellow-400 border-yellow-500/30 bg-yellow-500/10" },
};

const MOMENTUM_CONFIG: Record<string, { label: string; Icon: any; cls: string }> = {
  accelerating: { label: "Accelerating", Icon: TrendingUp, cls: "text-green-400" },
  steady: { label: "Steady", Icon: Minus, cls: "text-yellow-400" },
  stalling: { label: "Stalling", Icon: TrendingDown, cls: "text-orange-400" },
  gone_cold: { label: "Gone cold", Icon: TrendingDown, cls: "text-red-400" },
};

const URGENCY_CLS: Record<string, string> = {
  high: "text-red-400",
  medium: "text-yellow-400",
  low: "text-muted-foreground",
};

function AIInsightsPanel({
  extracted, onReanalyse, analysing, onDraftEmail, dealName, dealId,
}: {
  extracted: Extracted;
  onReanalyse: () => void;
  analysing: boolean;
  onDraftEmail?: () => void;
  dealName?: string;
  dealId?: string;
}) {
  const [showOpenQ, setShowOpenQ] = useState(false);
  const [showRelMap, setShowRelMap] = useState(false);
  const [doneStep, setDoneStep] = useState(false);
  const [confirmingDone, setConfirmingDone] = useState(false);
  const [checkedCommitments, setCheckedCommitments] = useState<Set<number>>(new Set());

  const sentiment = (extracted.sentiment || "").toLowerCase();
  const momentum = (extracted.momentum || "").toLowerCase();
  const sentCfg = SENTIMENT_CONFIG[sentiment] ?? SENTIMENT_CONFIG["neutral"];
  const momCfg = MOMENTUM_CONFIG[momentum];
  const MomIcon = momCfg?.Icon ?? Minus;

  const commitments = (extracted.commitments ?? []).map(normaliseCommitment);
  const deadlines = (extracted.deadlines ?? []).map(normaliseDeadline);
  const contacts = extracted.key_contacts ?? [];

  const allCommitmentsChecked = commitments.length > 0 && checkedCommitments.size === commitments.length;

  const toggleCommitment = (i: number, commitment: Commitment) => {
    const alreadyChecked = checkedCommitments.has(i);
    setCheckedCommitments(prev => {
      const next = new Set(prev);
      next.has(i) ? next.delete(i) : next.add(i);
      return next;
    });
    if (!alreadyChecked && dealId) {
      api.postDecision(dealId, "commitment_met", commitment.what).catch(() => { });
    }
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
          {!doneStep && !confirmingDone && (
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
                onClick={() => setConfirmingDone(true)}
              >
                <Check className="h-3 w-3" />
                Mark Done
              </Button>
            </div>
          )}
          {confirmingDone && !doneStep && (
            <div className="mt-2.5 rounded-lg border border-green-500/30 bg-green-500/8 px-3 py-2 space-y-2">
              <p className="text-[11px] text-green-400/90">Mark this next step as complete?</p>
              <div className="flex gap-2">
                <Button
                  size="sm"
                  className="flex-1 h-6 text-[11px] bg-green-600 hover:bg-green-700 text-white"
                  onClick={() => {
                    setDoneStep(true);
                    setConfirmingDone(false);
                    if (dealId && extracted.next_step) {
                      api.postDecision(dealId, "next_step_completed", extracted.next_step).catch(() => { });
                    }
                  }}
                >
                  <CheckCircle2 className="h-3 w-3 mr-1" />
                  Confirm
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  className="flex-1 h-6 text-[11px] border-border/40"
                  onClick={() => setConfirmingDone(false)}
                >
                  Cancel
                </Button>
              </div>
            </div>
          )}
          {doneStep && (
            <p className="mt-2 flex items-center gap-1.5 text-[11px] text-green-400">
              <CheckCircle2 className="h-3 w-3" />
              ✓ Completed ·{" "}
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
                const expired = isDeadlineExpired(c.deadline);
                const isOverdue = c.status === "overdue" || expired;
                return (
                  <button
                    key={i}
                    onClick={() => toggleCommitment(i, c)}
                    className={cn(
                      "w-full flex gap-2 rounded-lg px-2.5 py-2 text-left text-[11px] transition-all duration-200 hover:bg-card/70",
                      isOverdue && !checked
                        ? "bg-red-500/10 border border-red-500/20"
                        : "bg-card/50 border border-transparent"
                    )}
                  >
                    {checked
                      ? <CheckSquare className="h-3.5 w-3.5 text-green-400 shrink-0 mt-0.5" />
                      : c.status === "fulfilled"
                        ? <CheckCircle2 className="h-3.5 w-3.5 text-green-400 shrink-0 mt-0.5" />
                        : isOverdue
                          ? <AlertTriangle className="h-3.5 w-3.5 text-red-400 shrink-0 mt-0.5" />
                          : <Square className="h-3.5 w-3.5 text-muted-foreground/40 shrink-0 mt-0.5" />}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        {c.by && (
                          <span className={cn("font-semibold", checked ? "text-muted-foreground/50 line-through" : "text-foreground/70")}>
                            {c.by}:{" "}
                          </span>
                        )}
                        <span className={cn(checked ? "text-muted-foreground/50 line-through" : "text-foreground/80")}>
                          {c.what}
                        </span>
                        {expired && !checked && (
                          <Badge variant="outline" className="text-[9px] h-4 px-1.5 text-red-400 border-red-500/40 bg-red-500/10 shrink-0">
                            ⚠ EXPIRED
                          </Badge>
                        )}
                      </div>
                      {c.deadline && (
                        <span className={cn("text-[10px]",
                          checked ? "text-muted-foreground/40" :
                            isOverdue ? "text-red-400" : "text-muted-foreground/60"
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
                    c.engagement === "high" ? "bg-green-500/20 text-green-400" :
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

  const [deals, setDeals] = useState<Deal[]>([]);
  const [dealsLoading, setDealsLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [selectedDealId, setSelectedDealId] = useState("");

  const [thread, setThread] = useState<ThreadData | null>(null);
  const [threadLoading, setThreadLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [analysing, setAnalysing] = useState(false);

  const [viewMode, setViewMode] = useState<"grouped" | "flat">("grouped");
  const [draftModalOpen, setDraftModalOpen] = useState(false);

  const selectedDeal = deals.find(d => d.id === selectedDealId);

  // Normalize deal names (deal_name vs name)
  useEffect(() => {
    let cancelled = false;

    api.getAllDeals()
      .then(data => {
        if (cancelled) return;
        const list = Array.isArray(data) ? data : [];
        setDeals(list.map((d: any) => ({
          id: d.id,
          name: d.name ?? d.deal_name ?? "Unnamed Deal",
          stage: d.stage ?? "Unknown",
          health_label: d.health_label ?? "critical",
          amount: d.amount ?? 0,
        })));
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof DOMException && err.name === "AbortError") return;
        if (err instanceof Error && err.name === "AbortError") return;
        toast({ title: "Couldn't load deals", description: "Please refresh to try again.", variant: "destructive" });
      })
      .finally(() => { if (!cancelled) setDealsLoading(false); });

    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!selectedDealId) { setThread(null); return; }

    const controller = new AbortController();
    let cancelled = false;
    setThreadLoading(true);
    setThread(null);

    api.getEmailThread(selectedDealId, controller.signal)
      .then(data => { if (!cancelled) setThread(data); })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof DOMException && err.name === "AbortError") return;
        if (err instanceof Error && err.name === "AbortError") return;
        toast({ title: "Couldn't load emails", description: "Please try again.", variant: "destructive" });
      })
      .finally(() => { if (!cancelled) setThreadLoading(false); });

    return () => { cancelled = true; controller.abort(); };
  }, [selectedDealId]);

  async function handleSync() {
    if (!selectedDealId) return;
    setSyncing(true);
    try {
      const result = await api.syncEmailsForDeal(selectedDealId);
      toast({ title: "Sync complete", description: `${result.threads_found ?? 0} email(s) found.` });
      setThread(await api.getEmailThread(selectedDealId));
    } catch {
      toast({ title: "Sync failed", description: "Couldn't sync emails. Please try again.", variant: "destructive" });
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
    } catch {
      toast({ title: "Analysis failed", description: "Couldn't re-analyse this thread. Please try again.", variant: "destructive" });
    } finally {
      setAnalysing(false);
    }
  }

  const emails = thread?.emails ?? [];
  const threads = thread?.threads ?? [];

  // sentCount: Zoho only returns outbound emails, so the flat list is already sent-only.
  // receivedCount: buyer replies are NOT separate Zoho records — they exist only as quoted
  // text inside body_full. Parse the richest email's chain to extract received messages.
  const sentCount = emails.filter(e => isOutbound(e)).length;
  const receivedCount = useMemo(() => {
    if (emails.length === 0) return 0;
    // Use the email with the longest body — it has the most complete reply chain
    const richest = emails.reduce((best, e) => {
      const len = (e.body_full || e.body_preview || "").length;
      const bestLen = (best?.body_full || best?.body_preview || "").length;
      return len > bestLen ? e : best;
    }, emails[0]);
    if (!richest) return 0;
    const body = richest.body_full || richest.body_preview || "";
    if (!body) return 0;
    return getChainStats(body, richest.from, [OUR_DOMAIN]).received;
  }, [emails]);
  const responseRate = sentCount > 0 ? Math.round((receivedCount / sentCount) * 100) : 0;

  // Days since last buyer response — check chain-parsed messages in the richest email
  const lastBuyerEmail = useMemo(() => {
    // First try the flat list (in case Zoho ever returns received emails)
    const fromFlat = [...emails].reverse().find(e => !isOutbound(e));
    if (fromFlat) return fromFlat;
    // Fallback: look through chains for external-sender messages with a date
    for (const email of [...emails].reverse()) {
      const body = email.body_full || email.body_preview || "";
      if (!body) continue;
      const chain = getChainStats(body, email.from, [OUR_DOMAIN]);
      if (chain.received > 0) {
        // Return a synthetic marker with the containing email's date as approximation
        return { ...email, _chain_received: true };
      }
    }
    return undefined;
  }, [emails]);
  const lastBuyerEmail_forDate = lastBuyerEmail as (EmailMessage & { _chain_received?: boolean }) | undefined;
  const daysSinceReply = (() => {
    if (!lastBuyerEmail_forDate) return null;
    const ds = lastBuyerEmail_forDate.date || lastBuyerEmail_forDate.sent_at || "";
    if (!ds) return null;
    try { const d = parseISO(ds); return isNaN(d.getTime()) ? null : differenceInDays(new Date(), d); }
    catch { return null; }
  })();

  const noReply = receivedCount === 0 && sentCount > 0;

  // Last sent email date for no-reply banner
  const lastSentEmail = [...emails]
    .reverse()
    .find(e => isOutbound(e));
  const lastSentAgo = (() => {
    if (!lastSentEmail) return null;
    const ds = lastSentEmail.date || lastSentEmail.sent_at || "";
    if (!ds) return null;
    try { const d = parseISO(ds); return isNaN(d.getTime()) ? null : formatDistanceToNow(d, { addSuffix: true }); }
    catch { return null; }
  })();

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
                    threadIndex={i}
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
                {/* Received — red bg + 📭 icon if 0 */}
                <div className={cn(
                  "space-y-0.5 rounded-lg px-1 py-0.5 transition-colors",
                  receivedCount === 0 && sentCount > 0 ? "bg-red-950/40" : ""
                )}>
                  <div className="flex items-center justify-center gap-1">
                    {receivedCount === 0 && sentCount > 0 && (
                      <span className="text-sm">📭</span>
                    )}
                    <p className={cn("text-lg font-bold", receivedCount === 0 && sentCount > 0 ? "text-red-400" : "text-foreground")}>
                      {receivedCount}
                    </p>
                  </div>
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
                      {lastSentAgo
                        ? `No buyer response · Last email sent ${lastSentAgo}`
                        : `${sentCount} emails sent with no reply. The buyer has gone quiet.`}
                    </p>
                    <Button
                      size="sm"
                      className="h-7 w-full text-xs bg-orange-500/20 text-orange-300 border border-orange-500/30 hover:bg-orange-600 hover:text-white transition-colors gap-1.5"
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
                  dealId={selectedDealId || undefined}
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
        contactEmail={
          // First non-our-team participant from threads[0]
          threads[0]?.participants?.find(p => !isOurTeam(p)) ?? undefined
        }
        threadSubject={threads[0]?.subject ?? undefined}
      />
    </div>
  );
}
