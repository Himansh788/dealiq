import { useEffect, useState } from "react";
import { Settings, Mail, Calendar, Loader2, CheckCircle, XCircle, Palette, PlugZap, Clock, Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/hooks/use-toast";
import { api } from "@/lib/api";
import { ThemeToggle } from "@/components/ThemeToggle";
import { useTheme } from "@/contexts/ThemeContext";
import { useSession } from "@/contexts/SessionContext";

interface OutlookStatus {
  connected: boolean;
  message?: string;
  email?: string;
}

const CRM_META: Record<string, { label: string; badge: string; color: string; bg: string }> = {
  zoho:        { label: "Zoho CRM",   badge: "Z",  color: "text-[#E42527]", bg: "bg-[#E42527]/10" },
  salesforce:  { label: "Salesforce", badge: "SF", color: "text-[#00A1E0]", bg: "bg-[#00A1E0]/10" },
  hubspot:     { label: "HubSpot",    badge: "HS", color: "text-[#FF7A59]", bg: "bg-[#FF7A59]/10" },
  demo:        { label: "Demo Mode",  badge: "D",  color: "text-slate-400",  bg: "bg-slate-500/10" },
};

export default function SettingsPage() {
  const { toast } = useToast();
  const { theme } = useTheme();
  const { session } = useSession();

  const connectedCRM = session?.crm_provider ?? "zoho";
  const crmMeta = CRM_META[connectedCRM] ?? CRM_META["zoho"];
  const [outlookStatus, setOutlookStatus] = useState<OutlookStatus | null>(null);
  const [loadingOutlook, setLoadingOutlook] = useState(true);
  const [connecting, setConnecting] = useState(false);

  // Digest preferences
  const [digestPrefs, setDigestPrefs] = useState({
    digest_time: "09:00",
    digest_email_enabled: true,
    digest_language: "en",
    email_address: "",
    timezone: "UTC",
  });
  const [digestPrefsSaving, setDigestPrefsSaving] = useState(false);

  useEffect(() => {
    api.getDigestPreferences()
      .then((p: any) => setDigestPrefs({
        digest_time: p.digest_time ?? "09:00",
        digest_email_enabled: p.digest_email_enabled ?? true,
        digest_language: p.digest_language ?? "en",
        email_address: p.email_address ?? "",
        timezone: p.timezone ?? "UTC",
      }))
      .catch(() => null);
  }, []);

  async function saveDigestPrefs() {
    setDigestPrefsSaving(true);
    try {
      await api.updateDigestPreferences(digestPrefs);
      toast({ title: "Digest preferences saved" });
    } catch {
      toast({ title: "Failed to save", variant: "destructive" });
    } finally {
      setDigestPrefsSaving(false);
    }
  }

  async function sendTestEmail() {
    try {
      const result: any = await api.sendDigestEmailNow(digestPrefs.email_address || undefined);
      if (result.ok) {
        toast({ title: "Digest email sent", description: `Sent to ${result.sent_to}` });
      } else {
        toast({ title: "Email not sent", description: "Check RESEND_API_KEY and email address in settings.", variant: "destructive" });
      }
    } catch (e: any) {
      toast({ title: "Failed", description: e?.message || "Unknown error", variant: "destructive" });
    }
  }

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

        {/* Active CRM connection */}
        <div className="rounded-xl border border-border/30 bg-card/60 p-5">
          <div className="flex items-center gap-4">
            <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${crmMeta.bg}`}>
              <span className={`text-sm font-black ${crmMeta.color}`}>{crmMeta.badge}</span>
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <p className="text-sm font-semibold text-foreground">{crmMeta.label}</p>
                <Badge variant="outline" className="text-[10px] h-4 px-1.5 text-health-green border-health-green/30 bg-health-green/10">
                  <CheckCircle className="h-2.5 w-2.5 mr-1" />
                  Connected{session?.email ? ` — ${session.email}` : ""}
                </Badge>
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                {connectedCRM === "demo"
                  ? "Running in demo mode with sample data. Connect a real CRM to use live pipeline data."
                  : `Your ${crmMeta.label} pipeline is syncing with DealIQ. Re-authenticate from the login page to switch CRMs.`}
              </p>
            </div>
            <div className="shrink-0">
              <Button
                size="sm"
                variant="outline"
                className="h-8 text-xs hover:border-primary/40 hover:text-primary"
                onClick={() => window.location.href = "/login"}
              >
                <PlugZap className="h-3 w-3 mr-1.5" />
                Switch CRM
              </Button>
            </div>
          </div>
        </div>

        {/* Appearance */}
        <div className="rounded-xl border border-border/30 bg-card/60 p-5">
          <div className="flex items-start gap-4">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/10">
              <Palette className="h-5 w-5 text-primary" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-foreground">Appearance</p>
              <p className="text-xs text-muted-foreground mt-1">
                {theme === 'dark' ? 'Dark mode' : 'Light mode'} — switch to {theme === 'dark' ? 'reduce eye strain in bright environments' : 'reduce eye strain in dark environments'}
              </p>
            </div>
            <div className="shrink-0">
              <ThemeToggle />
            </div>
          </div>
        </div>

        {/* Daily Digest */}
        <div className="rounded-xl border border-border/30 bg-card/60 p-5">
          <div className="flex items-start gap-4">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/10">
              <Clock className="h-5 w-5 text-primary" />
            </div>
            <div className="flex-1 min-w-0 space-y-4">
              <div>
                <p className="text-sm font-semibold text-foreground">Daily Digest</p>
                <p className="text-xs text-muted-foreground mt-1">
                  Configure when and where you receive your personalised daily briefing.
                </p>
              </div>

              {/* Email notifications toggle */}
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs font-medium text-foreground">Email notifications</p>
                  <p className="text-[11px] text-muted-foreground">Receive digest by email each morning</p>
                </div>
                <button
                  onClick={() => setDigestPrefs(p => ({ ...p, digest_email_enabled: !p.digest_email_enabled }))}
                  className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors ${digestPrefs.digest_email_enabled ? "bg-primary" : "bg-secondary/60"}`}
                >
                  <span className={`pointer-events-none inline-block h-4 w-4 rounded-full bg-white shadow-sm transition-transform ${digestPrefs.digest_email_enabled ? "translate-x-4" : "translate-x-0"}`} />
                </button>
              </div>

              {/* Delivery time */}
              <div className="flex items-center justify-between flex-wrap gap-3">
                <div>
                  <p className="text-xs font-medium text-foreground">Delivery time</p>
                  <p className="text-[11px] text-muted-foreground">When to send your daily digest email</p>
                </div>
                <input
                  type="time"
                  value={digestPrefs.digest_time}
                  onChange={e => setDigestPrefs(p => ({ ...p, digest_time: e.target.value }))}
                  className="h-8 rounded-lg border border-border/40 bg-background px-3 text-xs text-foreground focus:border-primary/50 focus:outline-none"
                />
              </div>

              {/* Email address */}
              <div className="flex items-center justify-between flex-wrap gap-3">
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-medium text-foreground">Digest email address</p>
                  <p className="text-[11px] text-muted-foreground">Where to deliver the digest email</p>
                </div>
                <input
                  type="email"
                  value={digestPrefs.email_address}
                  onChange={e => setDigestPrefs(p => ({ ...p, email_address: e.target.value }))}
                  placeholder="you@company.com"
                  className="h-8 w-56 rounded-lg border border-border/40 bg-background px-3 text-xs text-foreground placeholder:text-muted-foreground/40 focus:border-primary/50 focus:outline-none"
                />
              </div>

              {/* Language */}
              <div className="flex items-center justify-between flex-wrap gap-3">
                <div>
                  <p className="text-xs font-medium text-foreground">Language</p>
                  <p className="text-[11px] text-muted-foreground">Digest language preference</p>
                </div>
                <select
                  value={digestPrefs.digest_language}
                  onChange={e => setDigestPrefs(p => ({ ...p, digest_language: e.target.value }))}
                  className="h-8 rounded-lg border border-border/40 bg-background px-3 text-xs text-foreground focus:border-primary/50 focus:outline-none"
                >
                  <option value="en">English</option>
                </select>
              </div>

              {/* Actions */}
              <div className="flex items-center gap-3 pt-1">
                <Button
                  size="sm"
                  className="h-8 text-xs bg-primary hover:bg-primary/90"
                  onClick={saveDigestPrefs}
                  disabled={digestPrefsSaving}
                >
                  {digestPrefsSaving && <Loader2 className="mr-1.5 h-3 w-3 animate-spin" />}
                  Save preferences
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  className="h-8 text-xs hover:border-primary/40 hover:text-primary"
                  onClick={sendTestEmail}
                >
                  <Send className="mr-1.5 h-3 w-3" />
                  Send test email
                </Button>
              </div>
            </div>
          </div>
        </div>

        {/* ── Coming Soon Placeholders ── */}
        <div className="pt-4 space-y-4">
          <p className="text-xs font-semibold text-foreground px-1">Coming Soon</p>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
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
          </div>
        </div>

        <p className="text-[11px] text-muted-foreground/40 text-center pt-4">
          More settings — notification preferences, API keys, team management — coming soon.
        </p>

      </div>
    </div>
  );
}
