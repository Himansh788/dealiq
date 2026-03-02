import React, { useState, useEffect } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/hooks/use-toast";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  Sparkles,
  Copy,
  X,
  CheckCircle,
  AlertTriangle,
  ArrowRight,
  Mail,
  FileText,
  MessageSquare,
  Users,
  Activity,
} from "lucide-react";

// ── Types ─────────────────────────────────────────────────────────────────────

interface Contact {
  name: string;
  email?: string;
  role?: string;
  engagement?: "active" | "quiet" | "disengaged";
}

interface ContextMeta {
  transcript_available: boolean;
  transcript_intel_extracted: boolean;
  email_history_available: boolean;
  email_count: number;
  contacts_available: number;
  rep_style_detected: string;
  deal_health: string;
  tone_applied: string;
}

interface CommitmentCoverage {
  commitment: string;
  covered: boolean;
}

interface EmailDraft {
  subject: string;
  body: string;
  commitments_included: string[];
  next_step: string;
  warnings: string[];
  health_impact?: string;
  context_meta?: ContextMeta;
  commitment_coverage?: CommitmentCoverage[];
}

interface Props {
  open: boolean;
  dealId: string;
  dealName: string;
  /** Primary contact for To field */
  contact?: Contact;
  onClose: () => void;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const ENGAGEMENT_DOT: Record<string, string> = {
  active:      "bg-health-green",
  quiet:       "bg-health-yellow",
  disengaged:  "bg-health-red",
};

// ── Component ─────────────────────────────────────────────────────────────────

export default function EmailComposer({ open, dealId, dealName, contact, onClose }: Props) {
  const [loading,  setLoading]  = useState(false);
  const [draft,    setDraft]    = useState<EmailDraft | null>(null);
  const [body,     setBody]     = useState("");
  const [subject,  setSubject]  = useState("");
  const [activeTab, setActiveTab] = useState<"contacts" | "context">("contacts");
  const { toast } = useToast();

  // Fetch draft whenever the dialog opens
  useEffect(() => {
    if (!open) return;
    setDraft(null);
    setLoading(true);
    api.askFollowUpEmail(dealId)
      .then((data) => {
        if (data.error) throw new Error(data.error);
        setDraft(data);
        setBody(data.body ?? "");
        setSubject(data.subject ?? "");
      })
      .catch((err: Error) => {
        toast({ title: "Couldn't generate email", description: err.message, variant: "destructive" });
      })
      .finally(() => setLoading(false));
  }, [open, dealId]);

  const regenerate = () => {
    setDraft(null);
    setLoading(true);
    api.askFollowUpEmail(dealId)
      .then((data) => {
        setDraft(data);
        setBody(data.body ?? "");
        setSubject(data.subject ?? "");
      })
      .catch((err: Error) =>
        toast({ title: "Regeneration failed", description: err.message, variant: "destructive" })
      )
      .finally(() => setLoading(false));
  };

  const copyEmail = () => {
    navigator.clipboard.writeText(`Subject: ${subject}\n\n${body}`);
    toast({ title: "Email copied to clipboard", description: "Paste it into your email client to send." });
    onClose();
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-5xl h-[85vh] p-0 gap-0 border-border/50 bg-background overflow-hidden flex flex-col">

        {/* ── Header ── */}
        <DialogHeader className="flex-row items-center justify-between border-b border-border/40 px-5 py-3 shrink-0">
          <div className="flex items-center gap-2.5">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-violet-500/20">
              <Sparkles className="h-3.5 w-3.5 text-violet-400" />
            </div>
            <DialogTitle className="text-sm font-semibold text-foreground">
              AI Follow-up Email — {dealName}
            </DialogTitle>
            <Badge variant="outline" className="text-[10px] border-violet-500/30 text-violet-400">
              AI generated
            </Badge>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground transition-colors">
            <X className="h-4 w-4" />
          </button>
        </DialogHeader>

        {/* ── Body (flex row) ── */}
        <div className="flex flex-1 min-h-0">

          {/* ── Left: Email editor ── */}
          <div className="flex flex-1 min-w-0 flex-col">

            {/* Fields */}
            <div className="border-b border-border/30 divide-y divide-border/30 shrink-0">
              {/* To */}
              <div className="flex items-center gap-3 px-5 py-2">
                <span className="w-14 shrink-0 text-xs font-semibold text-muted-foreground">To</span>
                <div className="flex flex-wrap gap-1.5 flex-1">
                  {contact ? (
                    <span className="flex items-center gap-1.5 rounded-full bg-primary/10 border border-primary/20 px-2.5 py-0.5 text-xs font-medium text-primary">
                      {contact.name}
                      {contact.email && <span className="text-primary/60">({contact.email})</span>}
                    </span>
                  ) : (
                    <span className="text-xs text-muted-foreground/50">Contact for {dealName}</span>
                  )}
                </div>
              </div>

              {/* From */}
              <div className="flex items-center gap-3 px-5 py-2">
                <span className="w-14 shrink-0 text-xs font-semibold text-muted-foreground">From</span>
                <span className="text-xs text-muted-foreground">you@yourcompany.com</span>
              </div>

              {/* Subject */}
              <div className="flex items-center gap-3 px-5 py-2">
                <span className="w-14 shrink-0 text-xs font-semibold text-muted-foreground">Subject</span>
                <input
                  value={subject}
                  onChange={(e) => setSubject(e.target.value)}
                  placeholder={loading ? "Generating subject…" : "Email subject"}
                  className="flex-1 bg-transparent text-sm text-foreground placeholder:text-muted-foreground/40 focus:outline-none"
                />
              </div>
            </div>

            {/* Body */}
            <div className="flex-1 overflow-y-auto px-5 py-4">
              {loading ? (
                <div className="space-y-3">
                  <div className="flex items-center gap-2 text-xs text-muted-foreground animate-pulse">
                    <Sparkles className="h-3.5 w-3.5 text-violet-400" />
                    Generating email from call context…
                  </div>
                  {[...Array(8)].map((_, i) => (
                    <Skeleton key={i} className={cn("h-4 rounded", i % 3 === 2 ? "w-2/3" : "w-full")} />
                  ))}
                </div>
              ) : (
                <textarea
                  value={body}
                  onChange={(e) => setBody(e.target.value)}
                  className="w-full h-full min-h-[240px] resize-none bg-transparent text-sm text-foreground leading-relaxed focus:outline-none placeholder:text-muted-foreground/40"
                  placeholder="AI-generated email will appear here…"
                />
              )}
            </div>

            {/* Warnings + commitments */}
            {draft && (
              <div className="shrink-0 border-t border-border/30 px-5 py-3 space-y-2">
                {draft.warnings.length > 0 && (
                  <div className="space-y-1">
                    {draft.warnings.map((w, i) => (
                      <div key={i} className="flex items-start gap-2 rounded-md border border-health-orange/30 bg-health-orange/5 px-2.5 py-1.5">
                        <AlertTriangle className="h-3 w-3 shrink-0 text-health-orange mt-0.5" />
                        <p className="text-[11px] text-health-orange">{w}</p>
                      </div>
                    ))}
                  </div>
                )}

                {draft.next_step && (
                  <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
                    <ArrowRight className="h-3 w-3 text-primary" />
                    <span className="font-medium text-primary">Next step:</span>
                    {draft.next_step}
                  </div>
                )}

                {draft.commitments_included.length > 0 && (
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/50">Covers:</span>
                    {draft.commitments_included.map((c, i) => (
                      <div key={i} className="flex items-center gap-1 text-[11px] text-muted-foreground">
                        <CheckCircle className="h-3 w-3 text-health-green" />
                        {c}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Toolbar */}
            <div className="shrink-0 flex items-center gap-2 border-t border-border/40 bg-secondary/20 px-4 py-3">
              <Button
                onClick={copyEmail}
                disabled={loading || !body}
                className="bg-primary hover:bg-primary/90 font-semibold h-8 text-xs px-4"
              >
                <Copy className="mr-1.5 h-3.5 w-3.5" />
                Copy &amp; Send
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="h-8 text-xs border-border/50"
                onClick={regenerate}
                disabled={loading}
              >
                <Sparkles className="mr-1.5 h-3.5 w-3.5 text-violet-400" />
                Regenerate
              </Button>
              <p className="ml-auto text-[10px] text-muted-foreground/50">
                ✦ Email is not sent — copy and send from your inbox
              </p>
            </div>
          </div>

          {/* ── Right: Contact/CRM sidebar ── */}
          <div className="w-[220px] shrink-0 border-l border-border/40 flex flex-col">

            {/* Deal info */}
            <div className="border-b border-border/40 px-4 py-3">
              <div className="flex items-start gap-2">
                <Mail className="h-4 w-4 text-muted-foreground mt-0.5 shrink-0" />
                <div className="min-w-0">
                  <p className="text-xs font-semibold text-foreground truncate">{dealName}</p>
                  <p className="text-[10px] text-muted-foreground">Follow-up composer</p>
                </div>
              </div>
            </div>

            {/* Tabs */}
            <div className="flex border-b border-border/40 shrink-0">
              {(["contacts", "context"] as const).map((t) => (
                <button
                  key={t}
                  onClick={() => setActiveTab(t)}
                  className={cn(
                    "flex-1 py-2 text-[11px] font-semibold uppercase tracking-wider transition-colors",
                    activeTab === t
                      ? "border-b-2 border-primary text-primary"
                      : "text-muted-foreground hover:text-foreground"
                  )}
                >
                  {t}
                </button>
              ))}
            </div>

            {/* Tab content */}
            <div className="flex-1 overflow-y-auto p-3 space-y-2">
              {activeTab === "contacts" && (
                <>
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/60 mb-2">
                    Deal contacts
                  </p>

                  {contact ? (
                    <ContactCard
                      name={contact.name}
                      role={contact.role}
                      engagement={contact.engagement ?? "active"}
                      isPrimary
                    />
                  ) : (
                    <p className="text-[11px] text-muted-foreground/60">
                      Open a real deal for contact data.
                    </p>
                  )}

                  {draft?.context_meta && draft.context_meta.contacts_available > 0 && (
                    <p className="text-[10px] text-muted-foreground/50 mt-1">
                      {draft.context_meta.contacts_available} contact{draft.context_meta.contacts_available !== 1 ? "s" : ""} used in generation
                    </p>
                  )}
                </>
              )}

              {activeTab === "context" && (
                <>
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/60 mb-2">
                    Data sources used
                  </p>

                  {draft?.context_meta ? (
                    <div className="space-y-1.5">
                      <ContextSource
                        icon={FileText}
                        label="Transcript"
                        available={draft.context_meta.transcript_available}
                        detail={draft.context_meta.transcript_intel_extracted ? "Intel extracted" : undefined}
                      />
                      <ContextSource
                        icon={MessageSquare}
                        label="Email thread"
                        available={draft.context_meta.email_history_available}
                        detail={draft.context_meta.email_count > 0 ? `${draft.context_meta.email_count} emails` : undefined}
                      />
                      <ContextSource
                        icon={Users}
                        label="Contacts"
                        available={draft.context_meta.contacts_available > 0}
                        detail={draft.context_meta.contacts_available > 0 ? `${draft.context_meta.contacts_available} contacts` : undefined}
                      />
                      <ContextSource
                        icon={Activity}
                        label="Health score"
                        available={draft.context_meta.deal_health !== "unknown"}
                        detail={draft.context_meta.deal_health}
                      />

                      <div className="pt-1.5 border-t border-border/30">
                        <p className="text-[10px] text-muted-foreground/60">Tone applied</p>
                        <p className="text-[11px] font-semibold text-foreground capitalize mt-0.5">
                          {draft.context_meta.tone_applied}
                        </p>
                      </div>
                    </div>
                  ) : (
                    <p className="text-[11px] text-muted-foreground/60">
                      Context details available after generation.
                    </p>
                  )}

                  {/* Commitment coverage */}
                  {draft?.commitment_coverage && draft.commitment_coverage.length > 0 && (
                    <div className="pt-2 border-t border-border/30">
                      <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/60 mb-1.5">
                        Commitment coverage
                      </p>
                      <div className="space-y-1">
                        {draft.commitment_coverage.map((c, i) => (
                          <div key={i} className="flex items-start gap-1.5">
                            {c.covered
                              ? <CheckCircle className="h-3 w-3 text-health-green shrink-0 mt-0.5" />
                              : <AlertTriangle className="h-3 w-3 text-health-orange shrink-0 mt-0.5" />
                            }
                            <p className="text-[10px] text-muted-foreground leading-tight">{c.commitment}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {draft?.health_impact && (
                    <div className="pt-2 border-t border-border/30">
                      <div className="rounded-lg border border-primary/20 bg-primary/5 px-2.5 py-2">
                        <p className="text-[11px] text-foreground leading-relaxed">{draft.health_impact}</p>
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ── Context source indicator ──────────────────────────────────────────────────

function ContextSource({
  icon: Icon,
  label,
  available,
  detail,
}: {
  icon: React.ElementType;
  label: string;
  available: boolean;
  detail?: string;
}) {
  return (
    <div className="flex items-center gap-2">
      <Icon className={cn("h-3.5 w-3.5 shrink-0", available ? "text-health-green" : "text-muted-foreground/30")} />
      <div className="flex-1 min-w-0">
        <span className={cn("text-[11px]", available ? "text-foreground" : "text-muted-foreground/40")}>{label}</span>
        {detail && <span className="text-[10px] text-muted-foreground ml-1">· {detail}</span>}
      </div>
    </div>
  );
}


// ── Contact card ─────────────────────────────────────────────────────────────

function ContactCard({
  name,
  role,
  engagement,
  isPrimary,
}: {
  name: string;
  role?: string;
  engagement: "active" | "quiet" | "disengaged";
  isPrimary?: boolean;
}) {
  return (
    <div className={cn(
      "flex items-start gap-2 rounded-lg border px-2.5 py-2",
      isPrimary ? "border-primary/30 bg-primary/5" : "border-border/30 bg-secondary/20"
    )}>
      <div className="relative mt-0.5">
        <div className="flex h-6 w-6 items-center justify-center rounded-full bg-secondary text-[10px] font-bold text-muted-foreground">
          {name.charAt(0)}
        </div>
        <span className={cn(
          "absolute -bottom-0.5 -right-0.5 h-2 w-2 rounded-full border border-background",
          ENGAGEMENT_DOT[engagement]
        )} />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-xs font-semibold text-foreground truncate">{name}</p>
        {role && <p className="text-[10px] text-muted-foreground truncate">{role}</p>}
      </div>
      {!isPrimary && (
        <button className="shrink-0 rounded border border-border/50 px-1.5 py-0.5 text-[9px] font-semibold text-muted-foreground hover:border-primary/40 hover:text-primary transition-colors">
          CC
        </button>
      )}
    </div>
  );
}
