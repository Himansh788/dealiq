import { useEffect, useState } from "react";
import { Settings, Mail, Calendar, Loader2, CheckCircle, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/hooks/use-toast";
import { api } from "@/lib/api";

interface OutlookStatus {
  connected: boolean;
  message?: string;
  email?: string;
}

export default function SettingsPage() {
  const { toast } = useToast();
  const [outlookStatus, setOutlookStatus] = useState<OutlookStatus | null>(null);
  const [loadingOutlook, setLoadingOutlook] = useState(true);
  const [connecting, setConnecting] = useState(false);

  useEffect(() => {
    api.getOutlookStatus()
      .then(setOutlookStatus)
      .catch(() => setOutlookStatus({ connected: false, message: "Failed to check status" }))
      .finally(() => setLoadingOutlook(false));

    // Handle redirect back from Microsoft OAuth
    const params = new URLSearchParams(window.location.search);
    if (params.get("outlook") === "connected") {
      toast({ title: "Outlook connected", description: "Email and calendar sync is now active." });
      window.history.replaceState({}, "", window.location.pathname);
      // Re-fetch status after OAuth redirect
      api.getOutlookStatus().then(setOutlookStatus).catch(() => null);
    }
  }, []);

  async function handleConnectOutlook() {
    setConnecting(true);
    try {
      const result = await api.connectOutlook();
      if (result.auth_url) {
        window.location.href = result.auth_url;
      } else {
        toast({ title: "Unable to start Microsoft OAuth", description: result.message, variant: "destructive" });
      }
    } catch (err: any) {
      const msg = err?.message || "Microsoft OAuth not configured";
      if (msg.includes("501") || msg.includes("not configured")) {
        toast({
          title: "Outlook not configured",
          description: "Set MICROSOFT_CLIENT_ID, MICROSOFT_CLIENT_SECRET, and MICROSOFT_TENANT_ID in your backend .env file.",
          variant: "destructive",
        });
      } else {
        toast({ title: "Connection failed", description: msg, variant: "destructive" });
      }
    } finally {
      setConnecting(false);
    }
  }

  async function handleDisconnectOutlook() {
    await api.disconnectOutlook().catch(() => null);
    setOutlookStatus({ connected: false, message: "Disconnected" });
    toast({ title: "Outlook disconnected" });
  }

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <div className="border-b border-border/40 px-6 py-4">
        <div className="flex items-center gap-3 max-w-5xl mx-auto">
          <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-secondary/60">
            <Settings className="h-4 w-4 text-muted-foreground" />
          </div>
          <div>
            <h1 className="text-sm font-semibold text-foreground">Settings</h1>
            <p className="text-xs text-muted-foreground">Account and integration settings</p>
          </div>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-6 py-6 space-y-4">

        {/* Microsoft Outlook & Calendar */}
        <div className="rounded-xl border border-border/30 bg-card/60 p-5">
          <div className="flex items-start gap-4">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-blue-500/15">
              <Mail className="h-5 w-5 text-blue-400" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <p className="text-sm font-semibold text-foreground">Outlook & Calendar</p>
                {loadingOutlook ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
                ) : outlookStatus?.connected ? (
                  <Badge variant="outline" className="text-[10px] h-4 px-1.5 text-health-green border-health-green/30 bg-health-green/10">
                    <CheckCircle className="h-2.5 w-2.5 mr-1" />
                    Connected{outlookStatus.email ? ` — ${outlookStatus.email}` : ""}
                  </Badge>
                ) : (
                  <Badge variant="outline" className="text-[10px] h-4 px-1.5 text-muted-foreground border-border/50">
                    <XCircle className="h-2.5 w-2.5 mr-1" />
                    Not connected
                  </Badge>
                )}
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                Connect your Microsoft account to sync email threads and upcoming meetings. DealIQ reads Outlook mail and calendar events — it never sends email on your behalf.
              </p>
              <div className="flex items-center gap-3 mt-3 flex-wrap">
                <div className="flex items-center gap-1 text-[11px] text-muted-foreground/60">
                  <Calendar className="h-3 w-3" />
                  Outlook Calendar (read-only)
                </div>
                <div className="flex items-center gap-1 text-[11px] text-muted-foreground/60">
                  <Mail className="h-3 w-3" />
                  Outlook Mail (read-only)
                </div>
              </div>
            </div>
            <div className="shrink-0">
              {!loadingOutlook && (
                outlookStatus?.connected ? (
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-8 text-xs text-destructive border-destructive/30 hover:bg-destructive/10"
                    onClick={handleDisconnectOutlook}
                  >
                    Disconnect
                  </Button>
                ) : (
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-8 text-xs hover:border-primary/40 hover:text-primary"
                    onClick={handleConnectOutlook}
                    disabled={connecting}
                  >
                    {connecting && <Loader2 className="mr-1.5 h-3 w-3 animate-spin" />}
                    Connect Outlook
                  </Button>
                )
              )}
            </div>
          </div>
        </div>

        {/* Zoho CRM — read-only info */}
        <div className="rounded-xl border border-border/30 bg-card/60 p-5 opacity-70">
          <div className="flex items-center gap-4">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-orange-500/15">
              <Settings className="h-5 w-5 text-orange-400" />
            </div>
            <div>
              <p className="text-sm font-semibold text-foreground">Zoho CRM</p>
              <p className="text-xs text-muted-foreground">Configured via environment variables (ZOHO_CLIENT_ID, ZOHO_CLIENT_SECRET). Contact your admin to update.</p>
            </div>
            <Badge variant="outline" className="ml-auto text-[10px] h-4 px-1.5 text-muted-foreground">
              Env-based
            </Badge>
          </div>
        </div>

        {/* ── Coming Soon Placeholders ── */}
        <div className="pt-4 space-y-4">
          <p className="text-xs font-semibold text-foreground px-1">Coming Soon</p>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {/* Salesforce */}
            <div className="rounded-xl border border-border/20 bg-card/20 p-5 opacity-60 grayscale transition-all hover:grayscale-0 hover:opacity-100">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-500/10 mb-3">
                <svg className="h-5 w-5 text-blue-400" viewBox="0 0 24 24" fill="currentColor">
                  {/* Simple cloud shape for demo */}
                  <path d="M17.5 19c2.48 0 4.5-2.02 4.5-4.5S19.98 10 17.5 10c-.3 0-.58.05-.85.11C15.65 7.14 13.06 5 10 5 6.13 5 3 8.13 3 12c0 3.87 3.13 7 7 7h7.5z" />
                </svg>
              </div>
              <p className="text-sm font-semibold text-foreground mb-1">Salesforce</p>
              <p className="text-[11px] text-muted-foreground mb-3">Two-way sync with Salesforce CRM</p>
              <Badge variant="outline" className="text-[9px] border-border/30">Q3 2026</Badge>
            </div>

            {/* Slack */}
            <div className="rounded-xl border border-border/20 bg-card/20 p-5 opacity-60 grayscale transition-all hover:grayscale-0 hover:opacity-100">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-purple-500/10 mb-3">
                <svg className="h-5 w-5 text-purple-400" viewBox="0 0 24 24" fill="currentColor">
                  {/* Simple hash for demo */}
                  <path d="M19.1 8.9H15V4.7h-2.1v4.2H8.7V4.7H6.6v4.2H2.5v2.1h4.1v4H2.5v2.1h4.1v4.2h2.1v-4.2h4.2v4.2h2.1v-4.2h4.1v-2.1h-4.1v-4h4.1V8.9zm-6.2 6.1H8.7v-4h4.2v4z" />
                </svg>
              </div>
              <p className="text-sm font-semibold text-foreground mb-1">Slack</p>
              <p className="text-[11px] text-muted-foreground mb-3">Deal alerts and deal rooms in Slack</p>
              <Badge variant="outline" className="text-[9px] border-border/30">Q3 2026</Badge>
            </div>

            {/* Gong */}
            <div className="rounded-xl border border-border/20 bg-card/20 p-5 opacity-60 grayscale transition-all hover:grayscale-0 hover:opacity-100">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-pink-500/10 mb-3">
                <svg className="h-5 w-5 text-pink-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
                  <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
                  <line x1="12" x2="12" y1="19" y2="22" />
                </svg>
              </div>
              <p className="text-sm font-semibold text-foreground mb-1">Gong</p>
              <p className="text-[11px] text-muted-foreground mb-3">Ingest call transcripts for analysis</p>
              <Badge variant="outline" className="text-[9px] border-border/30">Future</Badge>
            </div>
          </div>
        </div>

        <p className="text-[11px] text-muted-foreground/40 text-center pt-4">
          More settings — notification preferences, API keys, team management — coming soon.
        </p>

      </div>
    </div>
  );
}
