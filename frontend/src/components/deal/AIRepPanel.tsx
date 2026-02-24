import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/hooks/use-toast";
import { api } from "@/lib/api";
import {
  Brain,
  Mail,
  CheckCircle,
  XCircle,
  ChevronRight,
  AlertTriangle,
  Zap,
  Edit3,
  Copy,
  RefreshCw,
  MessageSquare,
  ArrowRight,
} from "lucide-react";

interface Props {
  dealId: string;
  dealName: string;
  repName?: string;
}

type Step = "idle" | "loading_nba" | "nba_ready" | "nba_approved" | "loading_email" | "email_ready" | "email_approved" | "objection";

interface NBAData {
  situation_read: string;
  urgency_level: string;
  primary_action: {
    what: string;
    why: string;
    how: string;
    expected_outcome: string;
  };
  secondary_actions: Array<{
    action: string;
    timeline: string;
    trigger: string;
  }>;
  risk_if_no_action: string;
  confidence_score: number;
  rep_note: string;
}

interface EmailData {
  subject: string;
  body: string;
  tone: string;
  cta: string;
  why_this_approach: string;
}

const urgencyColors: Record<string, string> = {
  low: "bg-health-green/20 text-health-green border-health-green/30",
  medium: "bg-health-yellow/20 text-health-yellow border-health-yellow/30",
  high: "bg-health-orange/20 text-health-orange border-health-orange/30",
  critical: "bg-health-red/20 text-health-red border-health-red/30",
};

export default function AIRepPanel({ dealId, dealName, repName }: Props) {
  const [step, setStep] = useState<Step>("idle");
  const [nba, setNba] = useState<NBAData | null>(null);
  const [email, setEmail] = useState<EmailData | null>(null);
  const [editedBody, setEditedBody] = useState("");
  const [editedSubject, setEditedSubject] = useState("");
  const [isEditing, setIsEditing] = useState(false);
  const [objection, setObjection] = useState("");
  const [objectionResponse, setObjectionResponse] = useState<any>(null);
  const [loadingObjection, setLoadingObjection] = useState(false);
  const [repFeedback, setRepFeedback] = useState("");
  const { toast } = useToast();

  const effectiveRepName = repName || "the sales rep";

  // Step 1: Generate NBA
  const handleGenerateNBA = async () => {
    setStep("loading_nba");
    setNba(null);
    setEmail(null);
    try {
      const data = await api.generateNBA(dealId, effectiveRepName);
      setNba(data.action_plan);
      setStep("nba_ready");
    } catch (err: any) {
      toast({ title: "Error", description: err.message, variant: "destructive" });
      setStep("idle");
    }
  };

  // Step 2: Approve or reject NBA
  const handleApproveNBA = async (approved: boolean) => {
    if (!approved) {
      toast({ title: "Action plan rejected", description: "AI will not take any action." });
      setStep("idle");
      setNba(null);
      return;
    }
    setStep("loading_email");
    try {
      const actionContext = nba
        ? `Primary action: ${nba.primary_action.what}. Approach: ${nba.primary_action.how}`
        : "";
      const data = await api.generateEmailDraft(dealId, effectiveRepName, actionContext);
      setEmail(data.email);
      setEditedBody(data.email.body);
      setEditedSubject(data.email.subject);
      setStep("email_ready");
    } catch (err: any) {
      toast({ title: "Error generating email", description: err.message, variant: "destructive" });
      setStep("nba_approved");
    }
  };

  // Step 3: Approve or reject email
  const handleApproveEmail = async (approved: boolean) => {
    if (!approved) {
      toast({ title: "Email rejected", description: "No email will be sent." });
      setStep("nba_approved");
      return;
    }
    try {
      await api.approveEmail(dealId, editedSubject, editedBody, effectiveRepName, true);
      setStep("email_approved");
      toast({ title: "✓ Email approved", description: "Copy the email below and send from your inbox." });
    } catch (err: any) {
      toast({ title: "Error", description: err.message, variant: "destructive" });
    }
  };

  // Objection handler
  const handleObjection = async () => {
    if (!objection.trim()) return;
    setLoadingObjection(true);
    try {
      const data = await api.handleObjection(dealId, objection, effectiveRepName);
      setObjectionResponse(data.response);
    } catch (err: any) {
      toast({ title: "Error", description: err.message, variant: "destructive" });
    } finally {
      setLoadingObjection(false);
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    toast({ title: "Copied to clipboard" });
  };

  const reset = () => {
    setStep("idle");
    setNba(null);
    setEmail(null);
    setObjectionResponse(null);
    setObjection("");
    setRepFeedback("");
  };

  return (
    <div className="space-y-4 pb-4">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/20">
            <Brain className="h-4 w-4 text-primary" />
          </div>
          <div>
            <p className="text-sm font-semibold text-foreground">AI Sales Rep Clone</p>
            <p className="text-xs text-muted-foreground">Acting as {effectiveRepName}</p>
          </div>
        </div>
        {step !== "idle" && (
          <Button variant="ghost" size="sm" onClick={reset} className="text-xs text-muted-foreground">
            <RefreshCw className="mr-1 h-3 w-3" /> Reset
          </Button>
        )}
      </div>

      {/* Progress Steps */}
      {step !== "idle" && (
        <div className="flex items-center gap-1 text-xs text-muted-foreground">
          <span className={step !== "idle" ? "text-primary font-medium" : ""}>1. Analyse</span>
          <ChevronRight className="h-3 w-3" />
          <span className={["nba_approved", "loading_email", "email_ready", "email_approved"].includes(step) ? "text-primary font-medium" : ""}>2. Approve Plan</span>
          <ChevronRight className="h-3 w-3" />
          <span className={["email_ready", "email_approved"].includes(step) ? "text-primary font-medium" : ""}>3. Draft Email</span>
          <ChevronRight className="h-3 w-3" />
          <span className={step === "email_approved" ? "text-primary font-medium" : ""}>4. Send</span>
        </div>
      )}

      {/* IDLE STATE */}
      {step === "idle" && (
        <div className="space-y-3">
          <Card className="border-primary/20 bg-primary/5">
            <CardContent className="p-4 space-y-2">
              <p className="text-xs text-muted-foreground leading-relaxed">
                The AI will analyse <span className="font-medium text-foreground">{dealName}</span>, 
                think like {effectiveRepName}, and generate a specific action plan. 
                Nothing happens until you approve.
              </p>
              <Button
                className="w-full bg-primary hover:bg-primary/90 font-semibold"
                onClick={handleGenerateNBA}
              >
                <Zap className="mr-2 h-4 w-4" />
                Generate Next Best Action
              </Button>
            </CardContent>
          </Card>

          {/* Objection Handler — always available */}
          <Card className="border-border/50">
            <CardContent className="p-4 space-y-3">
              <div className="flex items-center gap-2">
                <MessageSquare className="h-4 w-4 text-muted-foreground" />
                <p className="text-sm font-medium text-foreground">Objection Handler</p>
              </div>
              <Textarea
                value={objection}
                onChange={(e) => setObjection(e.target.value)}
                placeholder='e.g. "The price is too high" or "We need to think about it"'
                className="min-h-[80px] resize-none border-border/50 bg-secondary/50 text-sm"
              />
              <Button
                variant="outline"
                size="sm"
                className="w-full border-border/50"
                onClick={handleObjection}
                disabled={!objection.trim() || loadingObjection}
              >
                {loadingObjection ? "Thinking..." : "How should I respond?"}
              </Button>
              {objectionResponse && (
                <div className="space-y-3 pt-1">
                  <div className="flex items-center justify-between">
                    <Badge variant="outline" className="text-xs border-border/50 capitalize">
                      {objectionResponse.objection_type?.replace("_", " ")}
                    </Badge>
                    <span className="text-xs text-muted-foreground">Objection type</span>
                  </div>
                  <div className="space-y-1">
                    <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">What they really mean</p>
                    <p className="text-sm text-foreground">{objectionResponse.real_concern_behind_objection}</p>
                  </div>
                  <Card className="border-primary/20 bg-primary/5">
                    <CardContent className="p-3 space-y-2">
                      <p className="text-xs font-medium text-primary uppercase tracking-wider">Say this</p>
                      <p className="text-sm text-foreground leading-relaxed italic">"{objectionResponse.exact_response}"</p>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-6 text-xs text-primary p-0"
                        onClick={() => copyToClipboard(objectionResponse.exact_response)}
                      >
                        <Copy className="mr-1 h-3 w-3" /> Copy
                      </Button>
                    </CardContent>
                  </Card>
                  <div className="space-y-1">
                    <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Then ask</p>
                    <p className="text-sm text-foreground italic">"{objectionResponse.follow_up_question}"</p>
                  </div>
                  {objectionResponse.danger_signs && (
                    <div className="flex items-start gap-2 rounded-md border border-health-red/20 bg-health-red/5 p-2">
                      <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0 text-health-red" />
                      <p className="text-xs text-health-red">{objectionResponse.danger_signs}</p>
                    </div>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {/* LOADING NBA */}
      {step === "loading_nba" && (
        <div className="space-y-3">
          <p className="text-xs text-muted-foreground text-center animate-pulse">
            🧠 AI is reading the deal and thinking like {effectiveRepName}...
          </p>
          {[...Array(4)].map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}
        </div>
      )}

      {/* NBA READY — Show plan, ask for approval */}
      {step === "nba_ready" && nba && (
        <div className="space-y-4">
          {/* Situation Read */}
          <Card className="border-border/50 bg-secondary/30">
            <CardContent className="p-4 space-y-2">
              <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">AI Situation Read</p>
              <p className="text-sm text-foreground leading-relaxed">{nba.situation_read}</p>
              <div className="flex items-center gap-2 pt-1">
                <Badge variant="outline" className={`text-xs capitalize ${urgencyColors[nba.urgency_level] || ""}`}>
                  {nba.urgency_level} urgency
                </Badge>
                <span className="text-xs text-muted-foreground">Confidence: {nba.confidence_score}%</span>
              </div>
            </CardContent>
          </Card>

          {/* Primary Action */}
          <Card className="border-primary/30 bg-primary/5">
            <CardContent className="p-4 space-y-3">
              <div className="flex items-center gap-2">
                <Zap className="h-4 w-4 text-primary" />
                <p className="text-xs font-semibold uppercase tracking-wider text-primary">Primary Action — Do This Today</p>
              </div>
              <p className="text-base font-semibold text-foreground">{nba.primary_action.what}</p>
              <div className="space-y-2 text-sm">
                <div>
                  <span className="font-medium text-muted-foreground">Why: </span>
                  <span className="text-foreground">{nba.primary_action.why}</span>
                </div>
                <div>
                  <span className="font-medium text-muted-foreground">How exactly: </span>
                  <span className="text-foreground">{nba.primary_action.how}</span>
                </div>
                <div>
                  <span className="font-medium text-muted-foreground">Expected outcome: </span>
                  <span className="text-foreground">{nba.primary_action.expected_outcome}</span>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Secondary Actions */}
          {nba.secondary_actions?.length > 0 && (
            <div className="space-y-2">
              <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">If-Then Actions</p>
              {nba.secondary_actions.map((action, i) => (
                <Card key={i} className="border-border/40 bg-secondary/20">
                  <CardContent className="p-3 space-y-1">
                    <p className="text-sm font-medium text-foreground">{action.action}</p>
                    <p className="text-xs text-muted-foreground">
                      <span className="font-medium">When: </span>{action.timeline}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      <span className="font-medium">Trigger: </span>{action.trigger}
                    </p>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}

          {/* Risk */}
          <div className="flex items-start gap-2 rounded-md border border-health-red/20 bg-health-red/5 p-3">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-health-red" />
            <div>
              <p className="text-xs font-semibold text-health-red">Risk if no action taken</p>
              <p className="text-xs text-foreground mt-0.5">{nba.risk_if_no_action}</p>
            </div>
          </div>

          {/* Rep Note */}
          <div className="rounded-md border border-border/30 bg-secondary/30 p-3">
            <p className="text-xs text-muted-foreground italic">
              💬 {effectiveRepName}: "{nba.rep_note}"
            </p>
          </div>

          {/* Rep Feedback before approving */}
          <Textarea
            value={repFeedback}
            onChange={(e) => setRepFeedback(e.target.value)}
            placeholder="Optional: Add your thoughts or corrections before approving..."
            className="min-h-[60px] resize-none border-border/50 bg-secondary/50 text-sm"
          />

          {/* Approval Buttons */}
          <div className="flex gap-2">
            <Button
              className="flex-1 bg-health-green hover:bg-health-green/80 text-background font-semibold"
              onClick={() => handleApproveNBA(true)}
            >
              <CheckCircle className="mr-2 h-4 w-4" />
              Approve — Draft Email
            </Button>
            <Button
              variant="outline"
              className="flex-1 border-health-red/50 text-health-red hover:bg-health-red/10"
              onClick={() => handleApproveNBA(false)}
            >
              <XCircle className="mr-2 h-4 w-4" />
              Reject Plan
            </Button>
          </div>
        </div>
      )}

      {/* LOADING EMAIL */}
      {step === "loading_email" && (
        <div className="space-y-3">
          <p className="text-xs text-muted-foreground text-center animate-pulse">
            ✍️ {effectiveRepName} is drafting the email...
          </p>
          {[...Array(3)].map((_, i) => <Skeleton key={i} className="h-12 w-full" />)}
        </div>
      )}

      {/* EMAIL READY — Show draft, allow edits, ask for approval */}
      {step === "email_ready" && email && (
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <Mail className="h-4 w-4 text-primary" />
            <p className="text-sm font-semibold text-foreground">Email Draft</p>
            <Badge variant="outline" className="text-xs border-border/50 capitalize">
              {email.tone}
            </Badge>
          </div>

          {/* Why this approach */}
          <div className="rounded-md border border-border/30 bg-secondary/30 p-3">
            <p className="text-xs text-muted-foreground">
              <span className="font-medium text-foreground">Strategy: </span>
              {email.why_this_approach}
            </p>
          </div>

          {/* Subject line */}
          <div className="space-y-1">
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Subject</p>
            <div className="flex items-center gap-2">
              <input
                value={editedSubject}
                onChange={(e) => setEditedSubject(e.target.value)}
                className="flex-1 rounded-md border border-border/50 bg-secondary/50 px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>
          </div>

          {/* Email body */}
          <div className="space-y-1">
            <div className="flex items-center justify-between">
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Body</p>
              <Button
                variant="ghost"
                size="sm"
                className="h-6 text-xs text-primary p-0"
                onClick={() => setIsEditing(!isEditing)}
              >
                <Edit3 className="mr-1 h-3 w-3" />
                {isEditing ? "Done editing" : "Edit"}
              </Button>
            </div>
            <Textarea
              value={editedBody}
              onChange={(e) => setEditedBody(e.target.value)}
              readOnly={!isEditing}
              className={`min-h-[200px] resize-none border-border/50 text-sm leading-relaxed ${
                isEditing ? "bg-background border-primary/50" : "bg-secondary/50"
              }`}
            />
          </div>

          {/* CTA highlight */}
          <div className="flex items-center gap-2 rounded-md border border-primary/20 bg-primary/5 p-2">
            <ArrowRight className="h-3 w-3 text-primary" />
            <p className="text-xs text-foreground">
              <span className="font-medium text-primary">CTA: </span>{email.cta}
            </p>
          </div>

          {/* Approval buttons */}
          <div className="flex gap-2">
            <Button
              className="flex-1 bg-health-green hover:bg-health-green/80 text-background font-semibold"
              onClick={() => handleApproveEmail(true)}
            >
              <CheckCircle className="mr-2 h-4 w-4" />
              Approve Email
            </Button>
            <Button
              variant="outline"
              className="flex-1 border-border/50"
              onClick={() => handleApproveEmail(false)}
            >
              <XCircle className="mr-2 h-4 w-4" />
              Reject
            </Button>
          </div>
        </div>
      )}

      {/* EMAIL APPROVED — Final copy */}
      {step === "email_approved" && (
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <CheckCircle className="h-5 w-5 text-health-green" />
            <p className="text-sm font-semibold text-health-green">Email Approved — Ready to Send</p>
          </div>

          <Card className="border-health-green/30 bg-health-green/5">
            <CardContent className="p-4 space-y-3">
              <div className="space-y-1">
                <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Subject</p>
                <div className="flex items-center justify-between">
                  <p className="text-sm font-medium text-foreground">{editedSubject}</p>
                  <Button variant="ghost" size="sm" className="h-6 text-xs p-0" onClick={() => copyToClipboard(editedSubject)}>
                    <Copy className="h-3 w-3" />
                  </Button>
                </div>
              </div>
              <div className="space-y-1">
                <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Body</p>
                <pre className="whitespace-pre-wrap text-sm text-foreground font-sans leading-relaxed">{editedBody}</pre>
              </div>
              <Button
                className="w-full"
                variant="outline"
                onClick={() => copyToClipboard(`Subject: ${editedSubject}\n\n${editedBody}`)}
              >
                <Copy className="mr-2 h-4 w-4" />
                Copy Full Email
              </Button>
            </CardContent>
          </Card>

          <p className="text-xs text-muted-foreground text-center">
            Open your email client, paste the subject and body, and send to your contact at {dealName}.
          </p>

          <Button variant="ghost" size="sm" className="w-full text-xs" onClick={reset}>
            Start new action plan
          </Button>
        </div>
      )}
    </div>
  );
}
