import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/hooks/use-toast";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Loader2, CheckCircle, Plus, X } from "lucide-react";
import EmailComposer from "@/components/email/EmailComposer";

// ── Types ─────────────────────────────────────────────────────────────────────

type Sentiment = "great" | "ok" | "concern";

interface PostMeetingFormProps {
  open: boolean;
  dealId: string;
  dealName: string;
  company?: string;
  contactName?: string;
  suggestedTopics?: string[];
  onClose: () => void;
}

// ── Config ────────────────────────────────────────────────────────────────────

const SENTIMENT_OPTIONS: { value: Sentiment; label: string; cls: string; activeCls: string }[] = [
  { value: "great",   label: "🟢 Great",   cls: "border-health-green/30  text-health-green",  activeCls: "bg-health-green/15 border-health-green  text-health-green" },
  { value: "ok",      label: "🟡 OK",      cls: "border-health-yellow/30 text-health-yellow", activeCls: "bg-health-yellow/15 border-health-yellow text-health-yellow" },
  { value: "concern", label: "🔴 Concern", cls: "border-health-red/30    text-health-red",    activeCls: "bg-health-red/15 border-health-red text-health-red" },
];

const DEFAULT_TOPICS = [
  "Pricing discussed",
  "Next step agreed",
  "Stakeholder introduced",
  "Timeline confirmed",
  "Technical requirements",
  "Competitor mentioned",
];

// ── Component ─────────────────────────────────────────────────────────────────

export default function PostMeetingForm({
  open,
  dealId,
  dealName,
  company,
  contactName,
  suggestedTopics = DEFAULT_TOPICS,
  onClose,
}: PostMeetingFormProps) {
  const { toast } = useToast();

  const [sentiment, setSentiment] = useState<Sentiment>("ok");
  const [confirmedTopics, setConfirmedTopics] = useState<Set<string>>(new Set());
  const [customTopic, setCustomTopic] = useState("");
  const [notes, setNotes] = useState("");
  const [durationMinutes, setDurationMinutes] = useState<string>("");
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState<{ summary: string; draft?: { subject: string; body: string } } | null>(null);
  const [showComposer, setShowComposer] = useState(false);

  function toggleTopic(topic: string) {
    setConfirmedTopics((prev) => {
      const next = new Set(prev);
      if (next.has(topic)) next.delete(topic);
      else next.add(topic);
      return next;
    });
  }

  function addCustomTopic() {
    const t = customTopic.trim();
    if (!t) return;
    setConfirmedTopics((prev) => new Set([...prev, t]));
    setCustomTopic("");
  }

  async function handleSubmit() {
    setSubmitting(true);
    try {
      const result = await api.submitPostMeeting({
        deal_id: dealId,
        sentiment,
        topics_confirmed: [...confirmedTopics],
        quick_notes: notes || undefined,
        duration_minutes: durationMinutes ? parseInt(durationMinutes) : undefined,
        attendees: contactName ? [{ name: contactName, company }] : [],
      });
      setDone({
        summary: result.ai_summary || "Meeting logged successfully.",
        draft: result.follow_up_email_draft,
      });
      toast({ title: "CRM updated", description: "Meeting summary saved and CRM updated." });
    } catch (err: any) {
      toast({ title: "Failed to save meeting", description: err.message, variant: "destructive" });
    } finally {
      setSubmitting(false);
    }
  }

  function handleClose() {
    setSentiment("ok");
    setConfirmedTopics(new Set());
    setNotes("");
    setDurationMinutes("");
    setDone(null);
    setShowComposer(false);
    onClose();
  }

  // Success state
  if (done) {
    return (
      <>
        <Dialog open={open} onOpenChange={handleClose}>
          <DialogContent className="max-w-lg">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2 text-sm">
                <CheckCircle className="h-4 w-4 text-health-green" />
                Meeting logged
              </DialogTitle>
            </DialogHeader>
            <div className="space-y-4 py-2">
              <p className="text-xs text-muted-foreground">{done.summary}</p>
              {done.draft && (
                <div className="rounded-lg border border-border/30 bg-card/40 p-3">
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/60 mb-1">Follow-up email draft ready</p>
                  <p className="text-xs font-medium text-foreground">{done.draft.subject}</p>
                  <p className="text-[11px] text-muted-foreground mt-1 line-clamp-3">{done.draft.body}</p>
                </div>
              )}
              <div className="flex gap-2">
                {done.draft && (
                  <Button size="sm" className="h-8 text-xs" onClick={() => setShowComposer(true)}>
                    Review & Send Email
                  </Button>
                )}
                <Button size="sm" variant="outline" className="h-8 text-xs" onClick={handleClose}>
                  Done
                </Button>
              </div>
            </div>
          </DialogContent>
        </Dialog>

        {showComposer && done.draft && (
          <EmailComposer
            open={showComposer}
            dealId={dealId}
            dealName={dealName}
            onClose={() => { setShowComposer(false); handleClose(); }}
          />
        )}
      </>
    );
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="text-sm font-semibold">
            Quick Post-Call Update
            {contactName && <span className="font-normal text-muted-foreground"> — {contactName}{company ? ` · ${company}` : ""}</span>}
          </DialogTitle>
          <p className="text-xs text-muted-foreground">{dealName}</p>
        </DialogHeader>

        <div className="space-y-5 py-2">

          {/* Sentiment */}
          <div>
            <p className="text-xs font-semibold text-foreground mb-2">How did it go?</p>
            <div className="flex gap-2">
              {SENTIMENT_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => setSentiment(opt.value)}
                  className={cn(
                    "flex-1 rounded-lg border px-3 py-2 text-xs font-medium transition-colors",
                    sentiment === opt.value ? opt.activeCls : `${opt.cls} bg-transparent hover:bg-secondary/50`
                  )}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          {/* Topics confirmed */}
          <div>
            <p className="text-xs font-semibold text-foreground mb-2">Topics covered</p>
            <div className="flex flex-wrap gap-1.5">
              {[...suggestedTopics, ...[...confirmedTopics].filter((t) => !suggestedTopics.includes(t))].map((topic) => (
                <button
                  key={topic}
                  onClick={() => toggleTopic(topic)}
                  className={cn(
                    "rounded-md border px-2 py-1 text-[11px] transition-colors",
                    confirmedTopics.has(topic)
                      ? "border-primary/50 bg-primary/10 text-primary"
                      : "border-border/40 text-muted-foreground hover:border-border hover:text-foreground"
                  )}
                >
                  {confirmedTopics.has(topic) && <span className="mr-1 text-[9px]">✓</span>}
                  {topic}
                </button>
              ))}
            </div>
            {/* Add custom topic */}
            <div className="flex items-center gap-1.5 mt-2">
              <input
                className="flex-1 rounded-md border border-border/40 bg-background px-2.5 py-1.5 text-xs placeholder:text-muted-foreground/50 focus:outline-none focus:border-primary/40"
                placeholder="Add topic…"
                value={customTopic}
                onChange={(e) => setCustomTopic(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && addCustomTopic()}
              />
              <button
                className="text-muted-foreground/50 hover:text-primary"
                onClick={addCustomTopic}
              >
                <Plus className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* Duration */}
          <div className="flex items-center gap-3">
            <p className="text-xs font-semibold text-foreground shrink-0">Duration (min)</p>
            <input
              type="number"
              min="1"
              max="480"
              className="w-24 rounded-md border border-border/40 bg-background px-2.5 py-1.5 text-xs focus:outline-none focus:border-primary/40"
              placeholder="e.g. 30"
              value={durationMinutes}
              onChange={(e) => setDurationMinutes(e.target.value)}
            />
          </div>

          {/* Notes */}
          <div>
            <p className="text-xs font-semibold text-foreground mb-1.5">Notes (optional)</p>
            <Textarea
              rows={3}
              className="text-xs resize-none"
              placeholder="Key moments, objections, decisions made…"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </div>

          {/* Submit */}
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              className="h-8 text-xs"
              onClick={handleSubmit}
              disabled={submitting}
            >
              {submitting && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
              Save & Update CRM
            </Button>
            <Button size="sm" variant="ghost" className="h-8 text-xs text-muted-foreground" onClick={handleClose}>
              Cancel
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
