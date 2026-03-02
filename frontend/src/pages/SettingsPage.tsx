import { useEffect, useState } from "react";
import { Settings, Mail, Calendar, Loader2, CheckCircle, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/hooks/use-toast";
import { api } from "@/lib/api";

interface GoogleStatus {
  connected: boolean;
  message?: string;
  email?: string;
}

export default function SettingsPage() {
  const { toast } = useToast();
  const [googleStatus, setGoogleStatus] = useState<GoogleStatus | null>(null);
  const [loadingGoogle, setLoadingGoogle] = useState(true);
  const [connecting, setConnecting] = useState(false);

  useEffect(() => {
    api.getGoogleAuthStatus()
      .then(setGoogleStatus)
      .catch(() => setGoogleStatus({ connected: false, message: "Failed to check status" }))
      .finally(() => setLoadingGoogle(false));
  }, []);

  async function handleConnectGoogle() {
    setConnecting(true);
    try {
      const result = await api.connectGoogle();
      if (result.auth_url) {
        window.location.href = result.auth_url;
      } else {
        toast({ title: "Unable to start Google OAuth", description: result.message, variant: "destructive" });
      }
    } catch (err: any) {
      const msg = err?.message || "Google OAuth not configured";
      if (msg.includes("501") || msg.includes("not configured")) {
        toast({
          title: "Google not configured",
          description: "Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in your backend .env file.",
          variant: "destructive",
        });
      } else {
        toast({ title: "Connection failed", description: msg, variant: "destructive" });
      }
    } finally {
      setConnecting(false);
    }
  }

  async function handleDisconnectGoogle() {
    await api.disconnectGoogle().catch(() => null);
    setGoogleStatus({ connected: false, message: "Disconnected" });
    toast({ title: "Google disconnected" });
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

        {/* Google Calendar & Gmail */}
        <div className="rounded-xl border border-border/30 bg-card/60 p-5">
          <div className="flex items-start gap-4">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-blue-500/15">
              <Mail className="h-5 w-5 text-blue-400" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <p className="text-sm font-semibold text-foreground">Google Calendar & Gmail</p>
                {loadingGoogle ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
                ) : googleStatus?.connected ? (
                  <Badge variant="outline" className="text-[10px] h-4 px-1.5 text-health-green border-health-green/30 bg-health-green/10">
                    <CheckCircle className="h-2.5 w-2.5 mr-1" />
                    Connected{googleStatus.email ? ` — ${googleStatus.email}` : ""}
                  </Badge>
                ) : (
                  <Badge variant="outline" className="text-[10px] h-4 px-1.5 text-muted-foreground border-border/50">
                    <XCircle className="h-2.5 w-2.5 mr-1" />
                    Not connected
                  </Badge>
                )}
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                Connect your Google account to sync upcoming meetings and email threads. DealIQ reads calendar events and Gmail threads — it never sends email on your behalf.
              </p>
              <div className="flex items-center gap-2 mt-3 flex-wrap">
                <div className="flex items-center gap-1 text-[11px] text-muted-foreground/60">
                  <Calendar className="h-3 w-3" />
                  Calendar (read-only)
                </div>
                <div className="flex items-center gap-1 text-[11px] text-muted-foreground/60">
                  <Mail className="h-3 w-3" />
                  Gmail (read-only)
                </div>
              </div>
            </div>
            <div className="shrink-0">
              {!loadingGoogle && (
                googleStatus?.connected ? (
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-8 text-xs text-destructive border-destructive/30 hover:bg-destructive/10"
                    onClick={handleDisconnectGoogle}
                  >
                    Disconnect
                  </Button>
                ) : (
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-8 text-xs hover:border-primary/40 hover:text-primary"
                    onClick={handleConnectGoogle}
                    disabled={connecting}
                  >
                    {connecting && <Loader2 className="mr-1.5 h-3 w-3 animate-spin" />}
                    Connect Google
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

        {/* More settings placeholder */}
        <p className="text-[11px] text-muted-foreground/40 text-center pt-4">
          More settings — notification preferences, API keys, team management — coming soon.
        </p>

      </div>
    </div>
  );
}
