import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Loader2, Phone, Target, Users, MessageSquare, AlertTriangle, Sparkles, HelpCircle } from "lucide-react";
import { api } from "@/lib/api";

interface CallBriefData {
  call_objective: string;
  situation_summary: string;
  what_was_promised: string;
  stakeholder_intel: string;
  talking_points: string[];
  risk_questions: string[];
  red_flags_to_watch: string[];
  opening_line: string;
}

interface CallBriefPanelProps {
  dealId: string;
  repName?: string;
}

export default function CallBriefPanel({ dealId, repName }: CallBriefPanelProps) {
  const [data, setData] = useState<CallBriefData | null>(null);
  const [loading, setLoading] = useState(false);

  const generateBrief = async () => {
    setLoading(true);
    try {
      const result = await api.getCallBrief(dealId, repName);
      setData(result.brief || result);
    } catch {
      // silent error
    }
    setLoading(false);
  };

  if (!data && !loading) {
    return (
      <div className="py-3 space-y-3">
        <p className="text-sm text-muted-foreground leading-relaxed">
          Get a personalized pre-call brief: opening line, talking points, stakeholder intel, and risk questions to ask.
        </p>
        <Button
          className="w-full bg-primary hover:bg-primary/90 font-semibold"
          onClick={generateBrief}
        >
          <Phone className="mr-2 h-4 w-4" />
          Generate Call Brief
        </Button>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center gap-2 py-8 text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        <span className="text-sm">Preparing your call brief...</span>
      </div>
    );
  }

  if (!data) return null;

  return (
    <div className="space-y-4 pb-4">

      {/* Suggested Opening Line */}
      {data.opening_line && (
        <Card className="border-primary/30 bg-primary/5">
          <CardContent className="p-4 space-y-1.5">
            <div className="flex items-center gap-2">
              <Sparkles className="h-3.5 w-3.5 text-primary" />
              <span className="text-xs font-semibold text-primary uppercase tracking-wider">Suggested Opening</span>
            </div>
            <p className="text-sm text-foreground italic leading-relaxed">"{data.opening_line}"</p>
          </CardContent>
        </Card>
      )}

      {/* Call Objective */}
      {data.call_objective && (
        <div className="space-y-1.5">
          <div className="flex items-center gap-2">
            <Target className="h-3.5 w-3.5 text-primary" />
            <span className="text-xs font-semibold text-primary uppercase tracking-wider">Call Objective</span>
          </div>
          <p className="text-sm text-foreground leading-relaxed">{data.call_objective}</p>
        </div>
      )}

      {/* Situation Summary */}
      {data.situation_summary && (
        <div className="space-y-1.5">
          <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Situation</span>
          <p className="text-sm text-foreground leading-relaxed">{data.situation_summary}</p>
        </div>
      )}

      {/* What Was Promised */}
      {data.what_was_promised && (
        <Card className="border-health-yellow/30 bg-health-yellow/5">
          <CardContent className="p-4 space-y-1.5">
            <span className="text-xs font-semibold text-health-yellow uppercase tracking-wider">What Was Promised</span>
            <p className="text-sm text-foreground leading-relaxed">{data.what_was_promised}</p>
          </CardContent>
        </Card>
      )}

      {/* Stakeholder Intel */}
      {data.stakeholder_intel && (
        <Card className="border-border/50 bg-secondary/30">
          <CardContent className="p-4 space-y-1.5">
            <div className="flex items-center gap-2">
              <Users className="h-3.5 w-3.5 text-primary" />
              <span className="text-xs font-semibold text-primary uppercase tracking-wider">Stakeholder Intel</span>
            </div>
            <p className="text-sm text-foreground leading-relaxed">{data.stakeholder_intel}</p>
          </CardContent>
        </Card>
      )}

      {/* Talking Points */}
      {data.talking_points && data.talking_points.length > 0 && (
        <div className="space-y-2.5">
          <div className="flex items-center gap-2">
            <MessageSquare className="h-3.5 w-3.5 text-primary" />
            <span className="text-xs font-semibold text-primary uppercase tracking-wider">Key Talking Points</span>
          </div>
          {data.talking_points.map((tp, i) => (
            <div key={i} className="flex items-start gap-2.5 text-sm text-foreground leading-relaxed">
              <span className="shrink-0 mt-0.5 h-5 w-5 rounded-full bg-primary/10 text-primary text-xs font-bold flex items-center justify-center">
                {i + 1}
              </span>
              {tp}
            </div>
          ))}
        </div>
      )}

      {/* Risk Questions */}
      {data.risk_questions && data.risk_questions.length > 0 && (
        <div className="space-y-2.5">
          <div className="flex items-center gap-2">
            <HelpCircle className="h-3.5 w-3.5 text-health-orange" />
            <span className="text-xs font-semibold text-health-orange uppercase tracking-wider">Questions to Ask</span>
          </div>
          {data.risk_questions.map((q, i) => (
            <div key={i} className="flex items-start gap-2.5 text-sm text-muted-foreground leading-relaxed">
              <span className="shrink-0 text-health-orange text-xs font-bold mt-0.5">Q{i + 1}</span>
              {q}
            </div>
          ))}
        </div>
      )}

      {/* Red Flags to Watch */}
      {data.red_flags_to_watch && data.red_flags_to_watch.length > 0 && (
        <Card className="border-health-red/30 bg-health-red/5">
          <CardHeader className="pb-2 pt-4 px-4">
            <CardTitle className="text-xs font-semibold text-health-red uppercase tracking-wider flex items-center gap-2">
              <AlertTriangle className="h-3.5 w-3.5" />
              Red Flags to Watch
            </CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-4 space-y-1.5">
            {data.red_flags_to_watch.map((flag, i) => (
              <p key={i} className="text-sm text-health-red/90">• {flag}</p>
            ))}
          </CardContent>
        </Card>
      )}

      <Button
        variant="outline"
        size="sm"
        className="w-full text-xs"
        onClick={generateBrief}
        disabled={loading}
      >
        Regenerate Brief
      </Button>
    </div>
  );
}
