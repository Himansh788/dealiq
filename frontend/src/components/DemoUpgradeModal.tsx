import { useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { BarChart3, ExternalLink, Zap } from "lucide-react";
import { api } from "@/lib/api";

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function DemoUpgradeModal({ open, onClose }: Props) {
  const [connecting, setConnecting] = useState(false);

  const handleConnect = async () => {
    setConnecting(true);
    try {
      const data = await api.getLoginUrl();
      if (data?.url) {
        window.location.href = data.url;
      }
    } catch {
      // Fallback — direct user to login
    } finally {
      setConnecting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-sm border-border/40 bg-card p-0 shadow-2xl">
        {/* Top gradient bar */}
        <div className="h-1 w-full rounded-t-lg bg-gradient-to-r from-primary via-accent to-primary" />

        <div className="px-6 pb-6 pt-5">
          <DialogHeader className="gap-3">
            {/* Icon */}
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-primary/20 to-accent/20 ring-1 ring-primary/20">
              <BarChart3 className="h-6 w-6 text-primary" />
            </div>

            <DialogTitle className="text-left text-lg font-bold text-foreground leading-snug">
              You're exploring Demo Mode
            </DialogTitle>
          </DialogHeader>

          <p className="mt-3 text-sm text-muted-foreground leading-relaxed">
            Connect your Zoho CRM to see real deal health scores, live mismatch
            detection, and pipeline metrics — based on your actual deals.
          </p>

          {/* Feature list */}
          <ul className="mt-4 space-y-2">
            {[
              "Live deal health scoring from real CRM data",
              "AI-powered mismatch detection on your emails",
              "Proactive alerts for stalled or at-risk deals",
            ].map((f) => (
              <li key={f} className="flex items-center gap-2.5 text-xs text-muted-foreground">
                <Zap className="h-3.5 w-3.5 shrink-0 text-primary" />
                {f}
              </li>
            ))}
          </ul>

          <div className="mt-6 space-y-2">
            <Button
              className="w-full gap-2 bg-primary font-semibold"
              onClick={handleConnect}
              disabled={connecting}
            >
              <ExternalLink className="h-4 w-4" />
              {connecting ? "Connecting…" : "Connect Zoho CRM →"}
            </Button>
            <Button
              variant="ghost"
              className="w-full text-muted-foreground hover:text-foreground"
              onClick={onClose}
            >
              Continue in Demo
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
