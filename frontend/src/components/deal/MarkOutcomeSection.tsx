import { useState } from "react";
import { Trophy, XCircle, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";
import { api } from "@/lib/api";

interface Props {
  dealId: string;
  dealName: string;
  onOutcomeMarked?: (outcome: "won" | "lost", primaryReason: string) => void;
}

export default function MarkOutcomeSection({ dealId, dealName, onOutcomeMarked }: Props) {
  const [pending, setPending] = useState<"won" | "lost" | null>(null);
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(false);

  function openModal(outcome: "won" | "lost") {
    setNotes("");
    setPending(outcome);
  }

  function closeModal() {
    if (!loading) setPending(null);
  }

  async function submit() {
    if (!pending) return;
    setLoading(true);
    try {
      const result = await api.analyzeWinLoss(dealId, pending, notes || undefined);
      toast.success(
        `✓ Deal analyzed — primary reason: ${result.primary_reason}`,
        {
          duration: 4000,
          style: {
            borderLeft: "3px solid #10b981",
          },
        }
      );
      onOutcomeMarked?.(pending, result.primary_reason);
      setPending(null);
    } catch {
      toast.error("Analysis failed — deal saved locally", { duration: 4000 });
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <div className="space-y-3">
        <p className="text-xs text-muted-foreground">
          Record the final outcome and get an AI-powered win/loss analysis.
        </p>
        <div className="flex gap-2">
          <Button
            size="sm"
            onClick={() => openModal("won")}
            className="flex-1 gap-1.5 bg-health-green/15 text-health-green border border-health-green/30 hover:bg-health-green/25 hover:text-health-green"
            variant="outline"
          >
            <Trophy className="h-3.5 w-3.5" />
            Mark Won
          </Button>
          <Button
            size="sm"
            onClick={() => openModal("lost")}
            className="flex-1 gap-1.5 bg-health-red/15 text-health-red border border-health-red/30 hover:bg-health-red/25 hover:text-health-red"
            variant="outline"
          >
            <XCircle className="h-3.5 w-3.5" />
            Mark Lost
          </Button>
        </div>
      </div>

      <Dialog open={!!pending} onOpenChange={(open) => !open && closeModal()}>
        <DialogContent className="border-border/50 bg-card sm:max-w-md">
          <DialogHeader>
            <DialogTitle className={pending === "won" ? "text-health-green" : "text-health-red"}>
              {pending === "won" ? "🎉 Mark as Won" : "Mark as Lost"} — {dealName}
            </DialogTitle>
            <DialogDescription className="text-muted-foreground">
              Optional: add context to improve the AI analysis.
            </DialogDescription>
          </DialogHeader>

          <Textarea
            placeholder={
              pending === "won"
                ? "What made this deal close? (e.g. strong champion, urgency, competitive pricing)"
                : "What happened? (e.g. lost to competitor, budget cut, champion left)"
            }
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={4}
            className="resize-none border-border/40 bg-background/60 text-sm placeholder:text-muted-foreground/50"
          />

          <DialogFooter className="gap-2">
            <Button variant="ghost" size="sm" onClick={closeModal} disabled={loading}>
              Cancel
            </Button>
            <Button
              size="sm"
              onClick={submit}
              disabled={loading}
              className={
                pending === "won"
                  ? "bg-health-green/20 text-health-green border border-health-green/40 hover:bg-health-green/30"
                  : "bg-health-red/20 text-health-red border border-health-red/40 hover:bg-health-red/30"
              }
              variant="outline"
            >
              {loading ? (
                <><Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> Analyzing…</>
              ) : (
                `Confirm ${pending === "won" ? "Win" : "Loss"}`
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
