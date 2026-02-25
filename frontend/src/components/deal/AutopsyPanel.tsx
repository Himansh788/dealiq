import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Loader2, Skull, AlertTriangle, Lightbulb, Brain, BookOpen } from "lucide-react";
import { api } from "@/lib/api";

interface AutopsyData {
  cause_of_death: string;
  earliest_warning_sign: {
    signal: string;
    when: string;
    what_was_missed: string;
  };
  critical_moment: {
    description: string;
    what_happened: string;
    what_should_have_happened: string;
  };
  behavioral_pattern: string;
  what_would_have_saved_it: string;
  learnings: string[];
  similar_live_deals_risk: string;
  rep_coaching_note: string;
  generated: boolean;
}

interface AutopsyPanelProps {
  dealId: string;
  killReason?: string;
}

export default function AutopsyPanel({ dealId, killReason }: AutopsyPanelProps) {
  const [data, setData] = useState<AutopsyData | null>(null);
  const [loading, setLoading] = useState(false);
  const [loaded, setLoaded] = useState(false);

  const generateAutopsy = async () => {
    setLoading(true);
    try {
      const result = await api.getAutopsy(dealId, killReason);
      setData(result.autopsy || result);
      setLoaded(true);
    } catch {
      // silent error — user can retry
    }
    setLoading(false);
  };

  if (!loaded && !loading) {
    return (
      <div className="py-3 space-y-3">
        <p className="text-sm text-muted-foreground leading-relaxed">
          Extract pattern learnings from this deal to prevent the same failure repeating.
          {killReason && (
            <span className="block mt-1 text-xs text-muted-foreground/70 italic">
              Kill reason: "{killReason}"
            </span>
          )}
        </p>
        <Button
          className="w-full bg-health-red/80 hover:bg-health-red text-background font-semibold"
          onClick={generateAutopsy}
        >
          <Skull className="mr-2 h-4 w-4" />
          Run Deal Autopsy
        </Button>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center gap-2 py-8 text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        <span className="text-sm">Analyzing deal post-mortem...</span>
      </div>
    );
  }

  if (!data) return null;

  return (
    <div className="space-y-4 pb-4">

      {/* Cause of Death */}
      <Card className="border-health-red/30 bg-health-red/5">
        <CardContent className="p-4 space-y-1.5">
          <div className="flex items-center gap-2">
            <Skull className="h-4 w-4 text-health-red" />
            <span className="text-xs font-semibold text-health-red uppercase tracking-wider">Cause of Death</span>
          </div>
          <p className="text-sm text-foreground font-medium leading-relaxed">{data.cause_of_death}</p>
        </CardContent>
      </Card>

      {/* What Would Have Saved It */}
      <Card className="border-primary/30 bg-primary/5">
        <CardContent className="p-4 space-y-1.5">
          <div className="flex items-center gap-2">
            <Lightbulb className="h-4 w-4 text-primary" />
            <span className="text-xs font-semibold text-primary uppercase tracking-wider">What Would Have Saved It</span>
          </div>
          <p className="text-sm text-foreground leading-relaxed">{data.what_would_have_saved_it}</p>
        </CardContent>
      </Card>

      {/* Earliest Warning Sign */}
      {data.earliest_warning_sign?.signal && (
        <Card className="border-health-orange/30 bg-health-orange/5">
          <CardHeader className="pb-2 pt-4 px-4">
            <CardTitle className="text-xs font-semibold text-health-orange uppercase tracking-wider flex items-center gap-2">
              <AlertTriangle className="h-3.5 w-3.5" />
              Earliest Warning Sign
            </CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-4 space-y-2">
            <p className="text-sm text-foreground font-medium">{data.earliest_warning_sign.signal}</p>
            <p className="text-xs text-muted-foreground">
              <span className="font-medium text-foreground">When: </span>
              {data.earliest_warning_sign.when}
            </p>
            <p className="text-xs text-muted-foreground">
              <span className="font-medium text-foreground">What was missed: </span>
              {data.earliest_warning_sign.what_was_missed}
            </p>
          </CardContent>
        </Card>
      )}

      {/* Critical Moment */}
      {data.critical_moment?.description && (
        <Card className="border-health-yellow/30 bg-health-yellow/5">
          <CardHeader className="pb-2 pt-4 px-4">
            <CardTitle className="text-xs font-semibold text-health-yellow uppercase tracking-wider">
              Critical Moment
            </CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-4 space-y-2">
            <p className="text-sm text-foreground font-medium">{data.critical_moment.description}</p>
            <p className="text-xs text-muted-foreground">
              <span className="font-medium text-foreground">What happened: </span>
              {data.critical_moment.what_happened}
            </p>
            <p className="text-xs text-muted-foreground">
              <span className="font-medium text-foreground">Should have been: </span>
              {data.critical_moment.what_should_have_happened}
            </p>
          </CardContent>
        </Card>
      )}

      {/* Key Learnings */}
      {data.learnings && data.learnings.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <BookOpen className="h-3.5 w-3.5 text-primary" />
            <span className="text-xs font-semibold text-primary uppercase tracking-wider">Key Learnings</span>
          </div>
          {data.learnings.map((l, i) => (
            <div key={i} className="flex items-start gap-2.5 text-sm text-foreground leading-relaxed">
              <span className="shrink-0 mt-0.5 h-5 w-5 rounded-full bg-primary/10 text-primary text-xs font-bold flex items-center justify-center">
                {i + 1}
              </span>
              {l}
            </div>
          ))}
        </div>
      )}

      {/* Similar Live Deals Risk */}
      {data.similar_live_deals_risk && (
        <Card className="border-health-orange/20 bg-secondary/40">
          <CardContent className="p-4 space-y-1.5">
            <div className="flex items-center gap-2">
              <AlertTriangle className="h-3.5 w-3.5 text-health-orange" />
              <span className="text-xs font-semibold text-health-orange uppercase tracking-wider">Live Pipeline Risk</span>
            </div>
            <p className="text-sm text-foreground leading-relaxed">{data.similar_live_deals_risk}</p>
          </CardContent>
        </Card>
      )}

      {/* Behavioral Pattern */}
      {data.behavioral_pattern && (
        <div className="space-y-1">
          <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Behavioral Pattern</span>
          <p className="text-sm text-muted-foreground leading-relaxed italic">{data.behavioral_pattern}</p>
        </div>
      )}

      {/* Rep Coaching Note */}
      {data.rep_coaching_note && (
        <Card className="border-border/50 bg-secondary/30">
          <CardContent className="p-4 space-y-1.5">
            <div className="flex items-center gap-2">
              <Brain className="h-3.5 w-3.5 text-primary" />
              <span className="text-xs font-semibold text-primary uppercase tracking-wider">Coaching Note</span>
            </div>
            <p className="text-sm text-muted-foreground italic">"{data.rep_coaching_note}"</p>
          </CardContent>
        </Card>
      )}

      <Button
        variant="outline"
        size="sm"
        className="w-full text-xs"
        onClick={generateAutopsy}
        disabled={loading}
      >
        Regenerate Autopsy
      </Button>
    </div>
  );
}
