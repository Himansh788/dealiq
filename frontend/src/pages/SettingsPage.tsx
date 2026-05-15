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

interface ZohoStatus {
  connected: boolean;
  message?: string;
  primary?: boolean;
  zoho_email?: string;
}

const CRM_META: Record<string, { label: string; badge: string; color: string; bg: string }> = {
  zoho:        { label: "Zoho CRM",   badge: "Z",  color: "text-[#E42527]",           bg: "bg-[#E42527]/12" },
  salesforce:  { label: "Salesforce", badge: "SF", color: "text-[#00A1E0]",           bg: "bg-[#00A1E0]/12" },
  hubspot:     { label: "HubSpot",    badge: "HS", color: "text-[#FF7A59]",           bg: "bg-[#FF7A59]/12" },
  demo:        { label: "Demo mode",  badge: "D",  color: "text-muted-foreground",    bg: "bg-secondary" },
};

export default function SettingsPage() {
  const { toast } = useToast();
  const { theme } = useTheme();
  const { session, logout } = useSession();

  const connectedCRM = session?.crm_provider ?? "zoho";
  const crmMeta = CRM_META[connectedCRM] ?? CRM_META["zoho"];
  const [outlookStatus, setOutlookStatus] = useState<OutlookStatus | null>(null);
  const [loadingOutlook, setLoadingOutlook] = useState(true);
  const [connecting, setConnecting] = useState(false);

  // ── Zoho mid-session integration ─────────────────────────────────────────
  const [zohoStatus, setZohoStatus] = useState<ZohoStatus | null>(null);
  const [loadingZoho, setLoadingZoho] = useState(true);
  const [connectingZoho, setConnectingZoho] = useState(false);

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

    api.getZohoStatus()
      .then(setZohoStatus)
      .catch(() => setZohoStatus({ connected: false, message: "Failed to check status" }))
      .finally(() => setLoadingZoho(false));

    // Handle redirect back from Microsoft OAuth
    const params = new URLSearchParams(window.location.search);
    if (params.get("outlook") === "connected") {
      toast({ title: "Outlook connected", description: "Email and calendar sync is now active." });
      window.history.replaceState({}, "", window.location.pathname);
      api.getOutlookStatus().then(setOutlookStatus).catch(() => null);
    }

    // Handle redirect back from Zoho OAuth (mid-session connect)
    if (params.get("zoho") === "connected") {
      toast({ title: "Zoho CRM connected", description: "DealIQ is now reading your live pipeline." });
      window.history.replaceState({}, "", window.location.pathname);
      api.getZohoStatus().then(setZohoStatus).catch(() => null);
    } else if (params.get("zoho_error")) {
      toast({
        title: "Zoho connection failed",
        description: decodeURIComponent(params.get("zoho_error") || ""),
        variant: "destructive",
      });
      window.history.replaceState({}, "", window.location.pathname);
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

  async function handleConnectZoho() {
    setConnectingZoho(true);
    try {
      const result: any = await api.connectZoho();
      if (result.auth_url) {
        window.location.href = result.auth_url;
      } else {
        toast({ title: "Couldn't start Zoho sign-in", description: result.message ?? "Unknown error", variant: "destructive" });
      }
    } catch (err: any) {
      const msg = err?.message || "Zoho OAuth not configured";
      if (msg.includes("501") || msg.includes("not configured")) {
        toast({
          title: "Zoho not configured",
          description: "Set ZOHO_CLIENT_ID and ZOHO_CLIENT_SECRET in your backend .env file.",
          variant: "destructive",
        });
      } else {
        toast({ title: "Couldn't connect Zoho", description: msg, variant: "destructive" });
      }
    } finally {
      setConnectingZoho(false);
    }
  }

  async function handleDisconnectZoho() {
    await api.disconnectZoho().catch(() => null);
    setZohoStatus({ connected: false, message: "Disconnected" });
    toast({ title: "Zoho disconnected" });
  }

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <div className="border-b border-border px-6 py-7">
        <div className="max-w-5xl mx-auto">
          <p className="inline-flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-muted-foreground font-medium mb-2">
            <Settings className="h-3.5 w-3.5 text-primary" />
            Settings
          </p>
          <h1 className="font-display text-3xl font-medium tracking-tight text-foreground leading-[1.1]">
            Your <span className="serif-accent">connections</span> & preferences
          </h1>
          <p className="text-sm text-muted-foreground mt-1.5 max-w-2xl">
            Hook DealIQ up to your inbox and CRM, and decide when it should write to you.
          </p>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-6 py-8 space-y-10">

        {/* ── INTEGRATIONS ── */}
        <section className="space-y-4">
          <h2 className="font-display text-xl font-semibold tracking-tight text-foreground flex items-center gap-2">
            <PlugZap className="h-4 w-4 text-primary" />
            Integrations
          </h2>

          {/* Microsoft Outlook & Calendar */}
          <div className="rounded-2xl border border-border bg-card p-6 shadow-sm">
            <div className="flex items-start gap-5">
              <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-[#0078D4]/12">
                <Mail className="h-5 w-5 text-[#0078D4]" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <p className="font-display text-base font-semibold text-foreground">Outlook & Calendar</p>
                  {loadingOutlook ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
                  ) : outlookStatus?.connected ? (
                    <Badge variant="outline" className="text-[10.5px] h-5 px-2 rounded-full text-health-green border-health-green/30 bg-health-green/10 gap-1">
                      <CheckCircle className="h-2.5 w-2.5" />
                      Connected{outlookStatus.email ? ` · ${outlookStatus.email}` : ""}
                    </Badge>
                  ) : (
                    <Badge variant="outline" className="text-[10.5px] h-5 px-2 rounded-full text-muted-foreground border-border gap-1">
                      <XCircle className="h-2.5 w-2.5" />
                      Not connected yet
                    </Badge>
                  )}
                </div>
                <p className="text-[13px] text-muted-foreground mt-1.5 leading-relaxed">
                  Connect your Microsoft account so DealIQ can read live email threads and upcoming meetings
                  for deal context. We never send email on your behalf.
                </p>
                <div className="flex items-center gap-4 mt-3 flex-wrap">
                  <span className="inline-flex items-center gap-1.5 text-[11.5px] text-muted-foreground">
                    <Calendar className="h-3 w-3" />
                    Outlook Calendar (read-only)
                  </span>
                  <span className="inline-flex items-center gap-1.5 text-[11.5px] text-muted-foreground">
                    <Mail className="h-3 w-3" />
                    Outlook Mail (read-only)
                  </span>
                </div>
              </div>
              <div className="shrink-0">
                {!loadingOutlook && (
                  outlookStatus?.connected ? (
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-9 text-xs rounded-full px-4 text-destructive border-destructive/30 hover:bg-destructive/10"
                      onClick={handleDisconnectOutlook}
                    >
                      Disconnect
                    </Button>
                  ) : (
                    <Button
                      size="sm"
                      className="h-9 text-xs rounded-full px-4 bg-primary hover:bg-primary/90 text-white"
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

          {/* Zoho CRM (mid-session integration) */}
          <div className="rounded-2xl border border-border bg-card p-6 shadow-sm">
            <div className="flex items-start gap-5">
              <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-[#E42527]/12">
                <span className="font-display text-base font-bold text-[#E42527]">Z</span>
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <p className="font-display text-base font-semibold text-foreground">Zoho CRM</p>
                  {loadingZoho ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
                  ) : zohoStatus?.connected ? (
                    <Badge variant="outline" className="text-[10.5px] h-5 px-2 rounded-full text-health-green border-health-green/30 bg-health-green/10 gap-1">
                      <CheckCircle className="h-2.5 w-2.5" />
                      Connected{zohoStatus.zoho_email ? ` · ${zohoStatus.zoho_email}` : ""}{zohoStatus.primary ? " · primary" : ""}
                    </Badge>
                  ) : (
                    <Badge variant="outline" className="text-[10.5px] h-5 px-2 rounded-full text-muted-foreground border-border gap-1">
                      <XCircle className="h-2.5 w-2.5" />
                      Not connected yet
                    </Badge>
                  )}
                </div>
                <p className="text-[13px] text-muted-foreground mt-1.5 leading-relaxed">
                  Connect Zoho CRM so DealIQ can read your live pipeline — deals, stages, owners, contacts.
                  Read-only access; we never write to your CRM without confirmation.
                </p>
              </div>
              <div className="shrink-0">
                {!loadingZoho && (
                  zohoStatus?.connected && !zohoStatus?.primary ? (
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-9 text-xs rounded-full px-4 text-destructive border-destructive/30 hover:bg-destructive/10"
                      onClick={handleDisconnectZoho}
                    >
                      Disconnect
                    </Button>
                  ) : zohoStatus?.primary ? (
                    <Badge variant="outline" className="text-[10.5px] h-5 px-2 rounded-full border-border text-muted-foreground">
                      Primary login
                    </Badge>
                  ) : (
                    <Button
                      size="sm"
                      className="h-9 text-xs rounded-full px-4 bg-primary hover:bg-primary/90 text-white"
                      onClick={handleConnectZoho}
                      disabled={connectingZoho}
                    >
                      {connectingZoho && <Loader2 className="mr-1.5 h-3 w-3 animate-spin" />}
                      Connect Zoho
                    </Button>
                  )
                )}
              </div>
            </div>
          </div>

          {/* Primary session — informational */}
          <div className="rounded-2xl border border-border bg-card/60 p-6 shadow-sm">
            <div className="flex items-start gap-5">
              <div className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-xl ${crmMeta.bg}`}>
                <span className={`font-display text-base font-bold ${crmMeta.color}`}>{crmMeta.badge}</span>
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <p className="font-display text-base font-semibold text-foreground">Signed in as {crmMeta.label}</p>
                  <Badge variant="outline" className="text-[10.5px] h-5 px-2 rounded-full text-health-green border-health-green/30 bg-health-green/10 gap-1">
                    <CheckCircle className="h-2.5 w-2.5" />
                    {session?.email ?? "Active"}
                  </Badge>
                </div>
                <p className="text-[13px] text-muted-foreground mt-1.5 leading-relaxed">
                  {connectedCRM === "demo"
                    ? "You're using sample data right now. Sign out and pick a real provider to read your live pipeline."
                    : "This is your primary sign-in. To switch to a different login provider, sign out and pick a new one."}
                </p>
              </div>
              <div className="shrink-0">
                <Button
                  size="sm"
                  variant="outline"
                  className="h-9 text-xs rounded-full px-4 border-border hover:border-foreground/30"
                  onClick={() => { logout(); window.location.href = "/"; }}
                >
                  <PlugZap className="h-3 w-3 mr-1.5" />
                  Switch sign-in
                </Button>
              </div>
            </div>
          </div>
        </section>

        {/* ── PREFERENCES ── */}
        <section className="space-y-4">
          <h2 className="font-display text-xl font-semibold tracking-tight text-foreground flex items-center gap-2">
            <Palette className="h-4 w-4 text-primary" />
            Preferences
          </h2>

        {/* Appearance */}
        <div className="rounded-2xl border border-border bg-card p-6 shadow-sm">
          <div className="flex items-start gap-5">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-secondary">
              <Palette className="h-5 w-5 text-foreground/70" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="font-display text-base font-semibold text-foreground">Appearance</p>
              <p className="text-[13px] text-muted-foreground mt-1.5">
                {theme === 'dark' ? "You're using dark mode — easier on the eyes after dusk." : "You're using light mode — bright and friendly."}
              </p>
            </div>
            <div className="shrink-0">
              <ThemeToggle />
            </div>
          </div>
        </div>

        {/* Daily Digest */}
        <div className="rounded-2xl border border-border bg-card p-6 shadow-sm">
          <div className="flex items-start gap-5">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-primary/10">
              <Clock className="h-5 w-5 text-primary" />
            </div>
            <div className="flex-1 min-w-0 space-y-5">
              <div>
                <p className="font-display text-base font-semibold text-foreground">Morning briefing</p>
                <p className="text-[13px] text-muted-foreground mt-1.5">
                  Pick when DealIQ should send you a short daily summary of what needs attention.
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
                  className="h-9 text-xs rounded-full px-4 bg-primary hover:bg-primary/90 text-white"
                  onClick={saveDigestPrefs}
                  disabled={digestPrefsSaving}
                >
                  {digestPrefsSaving && <Loader2 className="mr-1.5 h-3 w-3 animate-spin" />}
                  Save preferences
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  className="h-9 text-xs rounded-full px-4 border-border hover:border-foreground/30"
                  onClick={sendTestEmail}
                >
                  <Send className="mr-1.5 h-3 w-3" />
                  Send test email
                </Button>
              </div>
            </div>
          </div>
        </div>
        </section>

        {/* ── COMING SOON ── */}
        <section className="space-y-4">
          <h2 className="font-display text-xl font-semibold tracking-tight text-foreground">
            <span className="serif-accent">Coming soon</span>
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {/* Slack */}
            <div className="rounded-2xl border border-dashed border-border bg-card/40 p-5 opacity-70 transition-all hover:opacity-100 hover:border-border">
              <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-[#4A154B]/10 mb-3">
                <svg className="h-5 w-5 text-[#4A154B]" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M19.1 8.9H15V4.7h-2.1v4.2H8.7V4.7H6.6v4.2H2.5v2.1h4.1v4H2.5v2.1h4.1v4.2h2.1v-4.2h4.2v4.2h2.1v-4.2h4.1v-2.1h-4.1v-4h4.1V8.9zm-6.2 6.1H8.7v-4h4.2v4z" />
                </svg>
              </div>
              <p className="font-display text-[15px] font-semibold text-foreground mb-1">Slack</p>
              <p className="text-[12px] text-muted-foreground mb-3 leading-relaxed">Deal alerts and per-deal rooms — straight in Slack.</p>
              <Badge variant="outline" className="text-[10px] rounded-full border-border">Q3 2026</Badge>
            </div>
          </div>
        </section>

        <p className="text-[11.5px] text-muted-foreground/70 text-center pt-2 italic font-display">
          More to come — notifications, API keys, team — drop us a note if you'd like something added.
        </p>

      </div>
    </div>
  );
}
