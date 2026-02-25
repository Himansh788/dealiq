import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { Skull, X } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { api } from "@/lib/api";
import AutopsyPanel from "./AutopsyPanel";

interface AckData {
  recommendation: string;
  days_stalled: number;
  reasoning: string;
  supporting_signals: string[];
}

const DEMO_ACK: AckData = {
  recommendation: "escalate",
  days_stalled: 21,
  reasoning: "This deal has stalled with no meaningful engagement for 21 days. Without immediate intervention, this deal will likely die within 2 weeks.",
  supporting_signals: [
    "No meetings scheduled in 14+ days",
    "Champion email response time increased",
    "Close date already moved twice",
    "Discount mentioned 3 times without close signal",
  ],
};

function recColor(rec: string) {
  switch (rec.toLowerCase()) {
    case "advance":  return { bg: "bg-health-green/10 border-health-green/30",  text: "text-health-green",  badge: "bg-health-green/20 text-health-green border-health-green/30" };
    case "escalate": return { bg: "bg-health-orange/10 border-health-orange/30", text: "text-health-orange", badge: "bg-health-orange/20 text-health-orange border-health-orange/30" };
    case "kill":     return { bg: "bg-health-red/10 border-health-red/30",       text: "text-health-red",   badge: "bg-health-red/20 text-health-red border-health-red/30" };
    default:         return { bg: "bg-secondary", text: "text-foreground", badge: "bg-muted text-muted-foreground" };
  }
}

type Mode = "idle" | "kill_confirm" | "decided" | "killed";

export default function AckSection({ dealId }: { dealId: string }) {
  const [data, setData] = useState<AckData | null>(null);
  const [loading, setLoading] = useState(true);
  const [deciding, setDeciding] = useState(false);
  const [mode, setMode] = useState<Mode>("idle");
  const [killReason, setKillReason] = useState("");
  const [decisionMade, setDecisionMade] = useState("");
  const { toast } = useToast();

  useEffect(() => {
    setLoading(true);
    setData(null);
    setMode("idle");
    setKillReason("");
    api.getAck(dealId)
      .then((raw: any) => {
        setData({
          recommendation: raw.recommendation || "advance",
          days_stalled: raw.days_stalled || 0,
          reasoning: raw.reasoning || "",
          supporting_signals: raw.supporting_signals || raw.signals || [],
        });
      })
      .catch(() => setData(DEMO_ACK))
      .finally(() => setLoading(false));
  }, [dealId]);

  const handleDecision = async (decision: string) => {
    if (decision === "kill" && mode !== "kill_confirm") {
      setMode("kill_confirm");
      return;
    }
    setDeciding(true);
    try {
      await api.postDecision(dealId, decision);
    } catch {
      // log locally
    }
    setDecisionMade(decision);
    if (decision === "kill") {
      setMode("killed");
    } else {
      setMode("decided");
      toast({ title: "Decision recorded", description: `Deal marked as: ${decision}` });
    }
    setDeciding(false);
  };

  if (loading) return (
    <div className="space-y-3 py-4">
      {[...Array(3)].map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}
    </div>
  );

  if (!data) return null;

  const colors = recColor(data.recommendation);

  return (
    <div className="space-y-4 pb-4">
      <Card className={`border ${colors.bg}`}>
        <CardContent className="p-4 space-y-3">
          <div className="flex items-center justify-between">
            <Badge variant="outline" className={`font-bold text-sm uppercase ${colors.badge}`}>
              {data.recommendation}
            </Badge>
            <span className="text-sm text-muted-foreground">{data.days_stalled} days stalled</span>
          </div>
          <p className="text-sm text-foreground leading-relaxed">{data.reasoning}</p>
          {data.supporting_signals && data.supporting_signals.length > 0 && (
            <ul className="space-y-1">
              {data.supporting_signals.map((s, i) => (
                <li key={i} className="flex items-start gap-2 text-sm text-muted-foreground">
                  <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-muted-foreground/50" />
                  {s}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      {/* Kill confirmation flow */}
      {mode === "kill_confirm" && (
        <Card className="border-health-red/30 bg-health-red/5">
          <CardContent className="p-4 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Skull className="h-4 w-4 text-health-red" />
                <span className="text-sm font-semibold text-health-red">Confirm Kill</span>
              </div>
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6 text-muted-foreground hover:text-foreground"
                onClick={() => setMode("idle")}
              >
                <X className="h-3.5 w-3.5" />
              </Button>
            </div>
            <Textarea
              value={killReason}
              onChange={(e) => setKillReason(e.target.value)}
              placeholder="Reason for killing this deal (optional — helps generate a better autopsy)..."
              className="min-h-[80px] resize-none border-health-red/30 bg-background/50 text-foreground placeholder:text-muted-foreground text-sm"
            />
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                className="flex-1 text-muted-foreground"
                onClick={() => setMode("idle")}
              >
                Cancel
              </Button>
              <Button
                size="sm"
                className="flex-1 bg-health-red hover:bg-health-red/80 text-background font-semibold"
                disabled={deciding}
                onClick={() => handleDecision("kill")}
              >
                <Skull className="mr-1.5 h-3.5 w-3.5" />
                Confirm Kill
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Advance / Escalate / Kill buttons */}
      {mode === "idle" && (
        <div className="flex gap-2">
          <Button
            className="flex-1 bg-health-green hover:bg-health-green/80 text-background font-semibold"
            disabled={deciding}
            onClick={() => handleDecision("advance")}
          >
            Advance
          </Button>
          <Button
            className="flex-1 bg-health-orange hover:bg-health-orange/80 text-background font-semibold"
            disabled={deciding}
            onClick={() => handleDecision("escalate")}
          >
            Escalate
          </Button>
          <Button
            className="flex-1 bg-health-red hover:bg-health-red/80 text-background font-semibold"
            disabled={deciding}
            onClick={() => handleDecision("kill")}
          >
            Kill
          </Button>
        </div>
      )}

      {/* After non-kill decision */}
      {mode === "decided" && (
        <p className="text-sm text-center text-muted-foreground py-2">
          Decision recorded: <span className="font-semibold text-foreground capitalize">{decisionMade}</span>
        </p>
      )}

      {/* After kill — show autopsy */}
      {mode === "killed" && (
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-sm text-health-red">
            <Skull className="h-4 w-4" />
            <span className="font-medium">Deal killed.</span>
            <span className="text-muted-foreground">Run a post-mortem to extract learnings.</span>
          </div>
          <AutopsyPanel dealId={dealId} killReason={killReason || undefined} />
        </div>
      )}
    </div>
  );
}
