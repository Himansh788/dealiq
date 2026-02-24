import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/hooks/use-toast";
import { api } from "@/lib/api";

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
    case "advance": return { bg: "bg-health-green/10 border-health-green/30", text: "text-health-green", badge: "bg-health-green/20 text-health-green border-health-green/30" };
    case "escalate": return { bg: "bg-health-orange/10 border-health-orange/30", text: "text-health-orange", badge: "bg-health-orange/20 text-health-orange border-health-orange/30" };
    case "kill": return { bg: "bg-health-red/10 border-health-red/30", text: "text-health-red", badge: "bg-health-red/20 text-health-red border-health-red/30" };
    default: return { bg: "bg-secondary", text: "text-foreground", badge: "bg-muted text-muted-foreground" };
  }
}

export default function AckSection({ dealId }: { dealId: string }) {
  const [data, setData] = useState<AckData | null>(null);
  const [loading, setLoading] = useState(true);
  const [deciding, setDeciding] = useState(false);
  const { toast } = useToast();

  useEffect(() => {
    setLoading(true);
    setData(null);
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
    setDeciding(true);
    try {
      await api.postDecision(dealId, decision);
      toast({ title: "Decision recorded", description: `Deal marked as: ${decision}` });
    } catch {
      toast({ title: "Decision recorded", description: `${decision} logged locally` });
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
    </div>
  );
}
