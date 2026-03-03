import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";
import { formatDistanceToNow, parseISO } from "date-fns";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList,
} from "@/components/ui/command";
import {
  Mail, MailOpen, Send, RefreshCw, ChevronsUpDown, Check,
  AlertCircle, ChevronDown, ChevronRight, Lightbulb, ListChecks,
  HelpCircle, ArrowRight, Sparkles, Calendar, Tag,
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

interface Extracted {
  summary?: string | null;
  next_step?: string | null;
  commitments?: string[];
  open_questions?: string[];
  sentiment?: string | null;
  sentiment_progression?: string | null;
  key_topics?: string[];
  deadlines?: string[];
}

interface ThreadData {
  deal_id: string;
  thread_count: number;
  emails: EmailMessage[];
  threads?: Thread[];
  extracted?: Extracted | null;
  source?: string;
}

// ── Helpers ────────────────────────────────────────────────────────────────────

const HEALTH_DOT: Record<string, string> = {
  healthy:  "bg-health-green",
  watching: "bg-health-yellow",
  at_risk:  "bg-health-orange",
  critical: "bg-health-red",
};

const SENTIMENT_STYLE: Record<string, string> = {
  positive: "text-health-green  border-health-green/30  bg-health-green/10",
  neutral:  "text-muted-foreground border-border/50",
  negative: "text-health-red    border-health-red/30    bg-health-red/10",
  mixed:    "text-health-yellow border-health-yellow/30 bg-health-yellow/10",
};

const PROGRESSION_ICON: Record<string, string> = {
  improving: "↑",
  stable:    "→",
  declining: "↓",
};

function isOutbound(direction: string) {
  return direction === "sent" || direction === "outbound";
}

function formatRelative(dateStr: string): string {
  if (!dateStr) return "";
  try { return formatDistanceToNow(parseISO(dateStr), { addSuffix: true }); }
  catch { return dateStr; }
}

function formatShort(dateStr: string): string {
  if (!dateStr) return "";
  try {
    return new Date(dateStr).toLocaleDateString("en-US", {
      month: "short", day: "numeric", year: "numeric",
    });
  } catch { return dateStr; }
}

// ── EmailCard ──────────────────────────────────────────────────────────────────

function EmailCard({ email }: { email: EmailMessage }) {
  const [expanded, setExpanded] = useState(false);
  const outbound = isOutbound(email.direction);
  const body = email.body_preview || email.snippet || "";

  return (
    <div className={cn(
      "rounded-xl border transition-colors",
      outbound ? "border-primary/20 bg-primary/5" : "border-border/40 bg-card/60"
    )}>
      <button
        className="w-full flex items-start gap-3 px-4 py-3 text-left"
        onClick={() => setExpanded(v => !v)}
      >
        <div className={cn(
          "mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full",
          outbound ? "bg-primary/15" : "bg-muted/60"
        )}>
          {outbound
            ? <Send className="h-3 w-3 text-primary" />
            : <MailOpen className="h-3 w-3 text-muted-foreground" />}
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs font-medium text-foreground truncate">
              {email.subject || "(no subject)"}
            </span>
            <Badge variant="outline" className={cn(
              "text-[10px] h-4 px-1.5 shrink-0",
              outbound
                ? "text-primary border-primary/30 bg-primary/10"
                : "text-muted-foreground border-border/50"
            )}>
              {outbound ? "Sent" : "Received"}
            </Badge>
          </div>
          <div className="flex items-center gap-2 mt-0.5">
            <span className="text-[11px] text-muted-foreground truncate">{email.from}</span>
            <span className="text-[11px] text-muted-foreground/40 shrink-0">
              · {formatRelative(email.date || email.sent_at)}
            </span>
          </div>
          {/* Body preview line when collapsed */}
          {!expanded && body && (
            <p className="text-[11px] text-muted-foreground/60 mt-0.5 truncate">{body}</p>
          )}
        </div>

        <div className="shrink-0 text-muted-foreground/40 mt-0.5">
          {expanded ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
        </div>
      </button>

      {expanded && (
        <>
          <Separator className="opacity-40" />
          <div className="px-4 py-3 space-y-2">
            {email.to?.length > 0 && (
              <p className="text-[11px] text-muted-foreground/60">
                To: {email.to.join(", ")}
              </p>
            )}
            <p className="text-xs text-muted-foreground leading-relaxed whitespace-pre-wrap">
              {body || <span className="italic opacity-50">(no body available — re-auth Zoho to get email scope)</span>}
            </p>
            <p className="text-[10px] text-muted-foreground/40">{formatShort(email.date || email.sent_at)}</p>
          </div>
        </>
      )}
    </div>
  );
}

// ── ThreadGroup ────────────────────────────────────────────────────────────────

function ThreadGroup({ thread }: { thread: Thread }) {
  const [open, setOpen] = useState(true); // open by default for top thread

  return (
    <div className="rounded-xl border border-border/30 bg-card/30 overflow-hidden">
      <button
        className="w-full flex items-center gap-3 px-4 py-2.5 text-left bg-card/60 hover:bg-card/80 transition-colors"
        onClick={() => setOpen(v => !v)}
      >
        <Mail className="h-3.5 w-3.5 text-muted-foreground/60 shrink-0" />
        <span className="text-xs font-medium text-foreground flex-1 truncate">{thread.subject}</span>
        <span className="text-[10px] text-muted-foreground/50 shrink-0">
          {thread.message_count} message{thread.message_count !== 1 ? "s" : ""}
          {" · "}{formatRelative(thread.latest_date)}
        </span>
        {open ? <ChevronDown className="h-3 w-3 text-muted-foreground/40 shrink-0" />
               : <ChevronRight className="h-3 w-3 text-muted-foreground/40 shrink-0" />}
      </button>

      {open && (
        <div className="p-3 space-y-2">
          {thread.messages.map((msg, i) => (
            <EmailCard key={msg.message_id || i} email={msg} />
          ))}
        </div>
      )}
    </div>
  );
}

// ── AIInsightsPanel ────────────────────────────────────────────────────────────

function AIInsightsPanel({ extracted, onReanalyse, analysing }: {
  extracted: Extracted;
  onReanalyse: () => void;
  analysing: boolean;
}) {
  const sentiment = (extracted.sentiment || "").toLowerCase();
  const progression = (extracted.sentiment_progression || "").toLowerCase();

  return (
    <div className="rounded-xl border border-violet-500/20 bg-violet-500/5 p-4 space-y-3">
      <div className="flex items-center gap-2">
        <Sparkles className="h-3.5 w-3.5 text-violet-400" />
        <span className="text-[11px] font-semibold uppercase tracking-widest text-violet-400/80 flex-1">
          AI Analysis
        </span>
        {sentiment && (
          <Badge variant="outline" className={cn(
            "text-[10px] h-4 px-1.5 capitalize",
            SENTIMENT_STYLE[sentiment] ?? SENTIMENT_STYLE["neutral"]
          )}>
            {sentiment}
            {progression && PROGRESSION_ICON[progression] && (
              <span className="ml-0.5">{PROGRESSION_ICON[progression]}</span>
            )}
          </Badge>
        )}
      </div>

      {extracted.summary && (
        <p className="text-[11px] text-muted-foreground leading-relaxed">{extracted.summary}</p>
      )}

      {extracted.next_step && (
        <div className="flex gap-2">
          <ArrowRight className="h-3.5 w-3.5 text-violet-400 shrink-0 mt-0.5" />
          <div>
            <p className="text-[10px] font-semibold text-muted-foreground/60 uppercase tracking-wider mb-0.5">Next step</p>
            <p className="text-xs text-foreground">{extracted.next_step}</p>
          </div>
        </div>
      )}

      {(extracted.deadlines?.length ?? 0) > 0 && (
        <div className="flex gap-2">
          <Calendar className="h-3.5 w-3.5 text-violet-400 shrink-0 mt-0.5" />
          <div>
            <p className="text-[10px] font-semibold text-muted-foreground/60 uppercase tracking-wider mb-1">Deadlines</p>
            <ul className="space-y-0.5">
              {extracted.deadlines!.map((d, i) => (
                <li key={i} className="text-xs text-foreground flex gap-1.5">
                  <span className="text-violet-400 shrink-0">·</span>{d}
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {(extracted.commitments?.length ?? 0) > 0 && (
        <div className="flex gap-2">
          <ListChecks className="h-3.5 w-3.5 text-violet-400 shrink-0 mt-0.5" />
          <div>
            <p className="text-[10px] font-semibold text-muted-foreground/60 uppercase tracking-wider mb-1">Commitments</p>
            <ul className="space-y-0.5">
              {extracted.commitments!.map((c, i) => (
                <li key={i} className="text-xs text-foreground flex gap-1.5">
                  <span className="text-violet-400 shrink-0">·</span>{c}
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {(extracted.open_questions?.length ?? 0) > 0 && (
        <div className="flex gap-2">
          <HelpCircle className="h-3.5 w-3.5 text-violet-400 shrink-0 mt-0.5" />
          <div>
            <p className="text-[10px] font-semibold text-muted-foreground/60 uppercase tracking-wider mb-1">Open questions</p>
            <ul className="space-y-0.5">
              {extracted.open_questions!.map((q, i) => (
                <li key={i} className="text-xs text-foreground flex gap-1.5">
                  <span className="text-violet-400 shrink-0">·</span>{q}
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {(extracted.key_topics?.length ?? 0) > 0 && (
        <div className="flex gap-2 flex-wrap">
          <Tag className="h-3.5 w-3.5 text-violet-400 shrink-0 mt-0.5" />
          <div className="flex flex-wrap gap-1">
            {extracted.key_topics!.map((t, i) => (
              <Badge key={i} variant="outline" className="text-[10px] h-4 px-1.5 text-muted-foreground border-border/40 capitalize">
                {t}
              </Badge>
            ))}
          </div>
        </div>
      )}

      <button
        className="text-[10px] text-violet-400/60 hover:text-violet-400 flex items-center gap-1 mt-1"
        onClick={onReanalyse}
        disabled={analysing}
      >
        <RefreshCw className={cn("h-2.5 w-2.5", analysing && "animate-spin")} />
        {analysing ? "Analysing…" : "Re-analyse"}
      </button>
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

  // Thread view toggle: "flat" or "grouped"
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
      const updated = await api.getEmailThread(selectedDealId);
      setThread(updated);
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
  const sentCount     = emails.filter(e => isOutbound(e.direction)).length;
  const receivedCount = emails.filter(e => !isOutbound(e.direction)).length;

  return (
    <div className="min-h-screen bg-background">

      {/* Header */}
      <div className="border-b border-border/40 px-6 py-4">
        <div className="flex items-center gap-3 max-w-5xl mx-auto">
          <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-blue-500/15">
            <Mail className="h-4 w-4 text-blue-400" />
          </div>
          <div>
            <h1 className="text-sm font-semibold text-foreground">Email Timeline</h1>
            <p className="text-xs text-muted-foreground">Full thread history with AI analysis</p>
          </div>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-6 py-6 space-y-6">

        {/* Controls row */}
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

          {/* Stats */}
          {thread && !threadLoading && (
            <div className="flex items-center gap-2">
              <Badge variant="outline" className="text-[10px] h-6 px-2 border-border/40 text-muted-foreground gap-1">
                <Send className="h-2.5 w-2.5" />{sentCount} sent
              </Badge>
              <Badge variant="outline" className="text-[10px] h-6 px-2 border-border/40 text-muted-foreground gap-1">
                <Mail className="h-2.5 w-2.5" />{receivedCount} received
              </Badge>
              {threads.length > 1 && (
                <Badge variant="outline" className="text-[10px] h-6 px-2 border-border/40 text-muted-foreground gap-1">
                  {threads.length} threads
                </Badge>
              )}
            </div>
          )}

          {/* View toggle + Sync */}
          {selectedDealId && thread && emails.length > 0 && (
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

          {selectedDealId && !thread && !threadLoading && (
            <Button size="sm" variant="outline" className="ml-auto h-8 text-xs border-border/50"
              onClick={handleSync} disabled={syncing}>
              <RefreshCw className={cn("mr-1.5 h-3 w-3", syncing && "animate-spin")} />
              {syncing ? "Syncing…" : "Sync Zoho"}
            </Button>
          )}
        </div>

        {/* Content */}
        {!selectedDealId ? (
          <div className="flex flex-col items-center gap-3 rounded-xl border border-border/30 bg-card/40 px-6 py-16">
            <Mail className="h-8 w-8 text-muted-foreground/20" />
            <p className="text-sm font-medium text-muted-foreground">Select a deal to see its email history</p>
            <p className="text-xs text-muted-foreground/60">Full threads, body content, and AI-extracted insights</p>
          </div>
        ) : threadLoading ? (
          <div className="space-y-3">
            {[...Array(4)].map((_, i) => <Skeleton key={i} className="h-16 w-full rounded-xl" />)}
          </div>
        ) : emails.length === 0 ? (
          <div className="flex flex-col items-center gap-3 rounded-xl border border-border/30 bg-card/40 px-6 py-16">
            <AlertCircle className="h-8 w-8 text-muted-foreground/20" />
            <p className="text-sm font-medium text-muted-foreground">No emails found for this deal</p>
            <p className="text-xs text-muted-foreground/60 text-center max-w-sm">
              Emails must be visible in Zoho under this deal's Emails tab. If they are, re-login to refresh your OAuth token (adds <code>ZohoCRM.modules.emails.READ</code> scope).
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

            {/* Email list */}
            <div className="lg:col-span-2 space-y-3">
              <p className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground/60">
                {viewMode === "grouped"
                  ? `${threads.length} thread${threads.length !== 1 ? "s" : ""} · ${emails.length} messages`
                  : `${emails.length} email${emails.length !== 1 ? "s" : ""} · ${selectedDeal?.name}`}
              </p>

              {viewMode === "grouped"
                ? threads.map((t, i) => <ThreadGroup key={t.thread_id || i} thread={t} />)
                : emails.map((e, i) => <EmailCard key={e.message_id || i} email={e} />)
              }
            </div>

            {/* Insights sidebar */}
            <div className="space-y-4">
              <p className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground/60">Insights</p>

              {/* Stats card */}
              <div className="rounded-xl border border-border/30 bg-card/60 p-4 space-y-3">
                <div className="flex justify-between text-xs">
                  <span className="text-muted-foreground">Total emails</span>
                  <span className="font-semibold">{emails.length}</span>
                </div>
                <Separator className="opacity-40" />
                <div className="flex justify-between text-xs">
                  <span className="text-muted-foreground">Sent</span>
                  <span className="font-medium text-primary">{sentCount}</span>
                </div>
                <div className="flex justify-between text-xs">
                  <span className="text-muted-foreground">Received</span>
                  <span className="font-medium">{receivedCount}</span>
                </div>
                {threads.length > 0 && (
                  <>
                    <Separator className="opacity-40" />
                    <div className="flex justify-between text-xs">
                      <span className="text-muted-foreground">Threads</span>
                      <span className="font-medium">{threads.length}</span>
                    </div>
                  </>
                )}
                {receivedCount === 0 && sentCount > 0 && (
                  <>
                    <Separator className="opacity-40" />
                    <div className="flex gap-1.5 text-[11px] text-health-orange">
                      <AlertCircle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
                      No buyer response — consider a different outreach approach
                    </div>
                  </>
                )}
                {receivedCount > 0 && (
                  <>
                    <Separator className="opacity-40" />
                    <div className="flex justify-between text-xs">
                      <span className="text-muted-foreground">Response rate</span>
                      <span className="font-medium">{Math.round((receivedCount / emails.length) * 100)}%</span>
                    </div>
                  </>
                )}
              </div>

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
