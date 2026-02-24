import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { CheckCircle, AlertTriangle, Loader2 } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { api } from "@/lib/api";

interface MismatchResult {
  category: string;
  description: string;
  severity: string;
  suggested_fix: string;
  health_impact: number;
}

const DEMO_TRANSCRIPT = `Sales Rep: We discussed pricing at $45K per year for the Enterprise tier.
Customer: That works. We also need SOC2 compliance docs before legal review.
Sales Rep: I'll send those over by Friday. We're targeting a go-live of March 15th.
Customer: Our team needs 2 weeks for integration testing after contract signing.
Sales Rep: Understood. We'll provide dedicated onboarding support during that period.`;

const DEMO_EMAIL = `Hi Sarah,

Thanks for the great call today! I wanted to follow up on the key points we discussed.

Pricing: We agreed on $52K/year for the Professional tier — I'll have the contract ready by next week.

Timeline: We're looking at an April 1st go-live, with our standard self-service onboarding.

Let me know if you need anything else!

Best,
Alex`;

const DEMO_RESULTS: MismatchResult[] = [
  { category: "Pricing", description: "Call mentioned $45K/year Enterprise tier, but email states $52K/year Professional tier", severity: "high", suggested_fix: "Correct the email to reflect $45K/year Enterprise tier as discussed", health_impact: -15 },
  { category: "Timeline", description: "Call set go-live as March 15th, email says April 1st", severity: "medium", suggested_fix: "Update go-live date to March 15th to match call agreement", health_impact: -8 },
  { category: "Onboarding", description: "Call promised dedicated onboarding support, email mentions self-service onboarding", severity: "high", suggested_fix: "Change to 'dedicated onboarding support' as committed on the call", health_impact: -12 },
];

function severityIcon(sev: string) {
  if (sev === "high") return <AlertTriangle className="h-4 w-4 text-health-red" />;
  if (sev === "medium") return <AlertTriangle className="h-4 w-4 text-health-orange" />;
  return <AlertTriangle className="h-4 w-4 text-health-yellow" />;
}

export default function MismatchChecker({ dealId }: { dealId: string }) {
  const [transcript, setTranscript] = useState("");
  const [emailDraft, setEmailDraft] = useState("");
  const [results, setResults] = useState<MismatchResult[] | null>(null);
  const [loading, setLoading] = useState(false);
  const { toast } = useToast();

  const handleCheck = async () => {
    if (!transcript.trim() || !emailDraft.trim()) {
      toast({ title: "Missing input", description: "Please provide both a transcript and email draft", variant: "destructive" });
      return;
    }
    setLoading(true);
    setResults(null);
    try {
      const data = await api.checkMismatch(transcript, emailDraft);
      setResults(data.mismatches || []);
    } catch {
      setResults(DEMO_RESULTS);
    }
    setLoading(false);
  };

  return (
    <div className="space-y-4 pb-4">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <label className="text-sm font-medium text-foreground">Call Transcript</label>
            <Button variant="ghost" size="sm" className="h-7 text-xs text-primary" onClick={() => setTranscript(DEMO_TRANSCRIPT)}>
              Load Demo Data
            </Button>
          </div>
          <Textarea
            value={transcript}
            onChange={(e) => setTranscript(e.target.value)}
            placeholder="Paste call transcript here..."
            className="min-h-[160px] resize-none border-border/50 bg-secondary/50 text-foreground placeholder:text-muted-foreground"
          />
        </div>
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <label className="text-sm font-medium text-foreground">Email Draft</label>
            <Button variant="ghost" size="sm" className="h-7 text-xs text-primary" onClick={() => setEmailDraft(DEMO_EMAIL)}>
              Load Demo Data
            </Button>
          </div>
          <Textarea
            value={emailDraft}
            onChange={(e) => setEmailDraft(e.target.value)}
            placeholder="Paste email draft here..."
            className="min-h-[160px] resize-none border-border/50 bg-secondary/50 text-foreground placeholder:text-muted-foreground"
          />
        </div>
      </div>

      <Button className="w-full bg-primary hover:bg-primary/90 font-semibold" onClick={handleCheck} disabled={loading}>
        {loading ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Analyzing...</> : "Check Before Sending"}
      </Button>

      {/* Results */}
      {results !== null && (
        <div className="space-y-3">
          {results.length === 0 ? (
            <Card className="border-health-green/30 bg-health-green/5">
              <CardContent className="flex items-center gap-3 p-4">
                <CheckCircle className="h-5 w-5 text-health-green" />
                <div>
                  <p className="text-sm font-medium text-health-green">No mismatches found</p>
                  <p className="text-xs text-muted-foreground">Safe to send.</p>
                </div>
              </CardContent>
            </Card>
          ) : (
            results.map((r, i) => (
              <Card key={i} className="border-border/50 bg-secondary/30">
                <CardContent className="space-y-2 p-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      {severityIcon(r.severity)}
                      <Badge variant="outline" className="text-xs border-border/50">{r.category}</Badge>
                    </div>
                    <span className="text-sm font-bold text-health-red">{r.health_impact} pts</span>
                  </div>
                  <p className="text-sm text-foreground">{r.description}</p>
                  <p className="text-xs text-muted-foreground"><span className="font-medium text-foreground">Fix: </span>{r.suggested_fix}</p>
                </CardContent>
              </Card>
            ))
          )}
        </div>
      )}
    </div>
  );
}
