import React, { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ArrowRight, ChevronRight, CheckCircle2 } from "lucide-react";
import { useSession } from "@/contexts/SessionContext";
import { useToast } from "@/hooks/use-toast";
import { api } from "@/lib/api";

// ── Logos ─────────────────────────────────────────────────────────────────────

function OutlookLogo({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect width="64" height="64" rx="12" fill="#0078D4"/>
      <path d="M22 18C14.8 18 9 24.3 9 32C9 39.7 14.8 46 22 46C29.2 46 35 39.7 35 32C35 24.3 29.2 18 22 18ZM22 40C18.7 40 16 36.4 16 32C16 27.6 18.7 24 22 24C25.3 24 28 27.6 28 32C28 36.4 25.3 40 22 40Z" fill="white"/>
      <path d="M36 26L45.5 33L55 26V41C55 41.6 54.6 42 54 42H37C36.4 42 36 41.6 36 41V26Z" fill="white"/>
    </svg>
  );
}

function SalesforceLogo({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect width="64" height="64" rx="12" fill="#00A1E0"/>
      <path d="M27.2 18.4C28.8 16.3 31.2 15 34 15C38.3 15 41.9 18 42.8 22C43.2 21.9 43.6 21.8 44 21.8C47.3 21.8 50 24.5 50 27.8C50 31.1 47.3 33.8 44 33.8H20C17.2 33.8 15 31.6 15 28.8C15 26.2 16.9 24.1 19.4 23.9C19.1 23.2 19 22.5 19 21.8C19 19.1 21.3 16.8 24 16.8C25.1 16.8 26.2 17.2 27.2 18.4Z" fill="white"/>
      <path d="M22 38H42V42C42 43.1 41.1 44 40 44H24C22.9 44 22 43.1 22 42V38Z" fill="white" opacity="0.7"/>
      <rect x="29" y="33" width="6" height="6" fill="white" opacity="0.7"/>
    </svg>
  );
}

function HubSpotLogo({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect width="64" height="64" rx="12" fill="#FF7A59"/>
      <circle cx="39" cy="20" r="5" fill="white"/>
      <path d="M33 27.5C33 25.6 34.6 24 36.5 24H41.5C43.4 24 45 25.6 45 27.5V30H33V27.5Z" fill="white"/>
      <rect x="36" y="29" width="6" height="14" rx="1" fill="white"/>
      <circle cx="25" cy="36" r="7" fill="white"/>
      <circle cx="25" cy="36" r="3.5" fill="#FF7A59"/>
      <rect x="31" y="34" width="8" height="3" rx="1.5" fill="white"/>
      <rect x="17" y="34" width="8" height="3" rx="1.5" fill="white"/>
      <rect x="23" y="42" width="4" height="7" rx="2" fill="white"/>
    </svg>
  );
}

type CRMProvider = "salesforce" | "hubspot";

interface CRMOption {
  id: CRMProvider;
  name: string;
  logo: React.FC<{ className?: string }>;
  blurb: string;
}

const CRM_OPTIONS: CRMOption[] = [
  { id: "salesforce", name: "Salesforce", logo: SalesforceLogo, blurb: "Connect your Salesforce org" },
  { id: "hubspot",    name: "HubSpot",    logo: HubSpotLogo,    blurb: "Connect your HubSpot portal" },
];

// ── Sample-dashboard preview (Daylight) ───────────────────────────────────────

function DashboardPreview() {
  return (
    <div className="relative w-full max-w-md mx-auto mt-10 rounded-2xl border border-border bg-card overflow-hidden shadow-xl shadow-foreground/10">
      {/* mock title bar */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-border bg-secondary/40">
        <div className="h-1.5 w-1.5 rounded-full bg-foreground/15" />
        <div className="h-1.5 w-12 rounded-full bg-foreground/15" />
        <div className="ml-auto h-1.5 w-8 rounded-full bg-foreground/15" />
      </div>
      {/* hero row */}
      <div className="flex items-center gap-4 px-4 py-4 border-b border-border">
        <div className="relative h-14 w-14 flex-shrink-0">
          <svg viewBox="0 0 36 36" className="rotate-[-90deg] h-14 w-14">
            <circle cx="18" cy="18" r="14" fill="none" stroke="hsl(var(--secondary))" strokeWidth="3.5" />
            <circle cx="18" cy="18" r="14" fill="none" stroke="hsl(var(--primary))" strokeWidth="3.5"
              strokeDasharray="62 88" strokeLinecap="round" />
          </svg>
          <span className="absolute inset-0 flex items-center justify-center font-display text-base font-semibold text-foreground">72</span>
        </div>
        <div className="flex-1 space-y-1.5">
          <div className="font-display text-sm font-semibold text-foreground">Acme Corp · Enterprise</div>
          <div className="h-1.5 w-20 rounded-full bg-foreground/10" />
        </div>
        <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-[hsl(var(--health-orange))]/10 text-[hsl(var(--health-orange))]">
          Needs help
        </span>
      </div>
      {/* rows */}
      {[
        { label: "CloudSync Annual", state: "good" },
        { label: "TechFlow Platform", state: "warn" },
        { label: "DataVault Migration", state: "bad" },
      ].map((row, i) => (
        <div key={i} className="flex items-center gap-3 px-4 py-2.5 border-b border-border last:border-0">
          <div className="h-7 w-7 rounded-md bg-secondary flex-shrink-0" />
          <div className="flex-1 space-y-1">
            <div className="text-xs font-medium text-foreground">{row.label}</div>
            <div className="h-1 w-14 rounded-full bg-foreground/10" />
          </div>
          <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${
            row.state === "good" ? "bg-[hsl(var(--health-green))]/12 text-[hsl(var(--health-green))]" :
            row.state === "warn" ? "bg-[hsl(var(--health-yellow))]/12 text-[hsl(var(--health-yellow))]" :
                                   "bg-[hsl(var(--health-orange))]/12 text-[hsl(var(--health-orange))]"
          }`}>
            {row.state === "good" ? "Going great" : row.state === "warn" ? "Needs a nudge" : "Needs help"}
          </span>
        </div>
      ))}
      <div className="absolute bottom-0 left-0 right-0 h-12 bg-gradient-to-t from-background to-transparent pointer-events-none" />
    </div>
  );
}

// ── Main component ───────────────────────────────────────────────────────────

export default function Login() {
  const { session, setSession } = useSession();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { toast } = useToast();
  const [loadingProvider, setLoadingProvider] = useState<CRMProvider | "outlook" | "demo" | null>(null);

  useEffect(() => {
    if (session) navigate("/dashboard", { replace: true });
  }, [session, navigate]);

  useEffect(() => {
    const sessionParam = searchParams.get("session");
    const errorParam = searchParams.get("error");

    if (sessionParam) {
      try {
        const parsed = JSON.parse(atob(sessionParam));
        setSession(parsed);
        navigate("/dashboard", { replace: true });
      } catch {
        toast({ title: "Sign-in failed", description: "We couldn't read your session — please try again.", variant: "destructive" });
      }
    } else if (errorParam) {
      const provider = searchParams.get("provider");
      const detail = searchParams.get("detail");
      toast({
        title: `${provider ? provider.charAt(0).toUpperCase() + provider.slice(1) + " " : ""}sign-in problem`,
        description: detail ? decodeURIComponent(detail) : decodeURIComponent(errorParam),
        variant: "destructive",
      });
    }
  }, [searchParams, setSession, navigate, toast]);

  const handleCrmLogin = async (provider: CRMProvider) => {
    setLoadingProvider(provider);
    try {
      const data = await api.getCrmLoginUrl(provider);
      window.location.href = data.auth_url;
    } catch (err: any) {
      toast({ title: "Sign-in failed", description: err.message, variant: "destructive" });
      setLoadingProvider(null);
    }
  };

  const handleOutlookLogin = async () => {
    setLoadingProvider("outlook");
    try {
      const data = await api.getOutlookLoginUrl();
      window.location.href = data.auth_url;
    } catch (err: any) {
      toast({ title: "Sign-in failed", description: err.message, variant: "destructive" });
      setLoadingProvider(null);
    }
  };

  const handleDemoLogin = async () => {
    setLoadingProvider("demo");
    try {
      const data = await api.getDemoSession();
      if (data.session) {
        const decoded = JSON.parse(atob(data.session));
        setSession({
          access_token: decoded.access_token || "DEMO_MODE",
          display_name: decoded.display_name || "Demo User",
          email: decoded.email || "demo@dealiq.ai",
          crm_provider: "demo",
        });
      } else {
        setSession({ access_token: "DEMO_MODE", display_name: "Demo User", email: "demo@dealiq.ai", crm_provider: "demo" });
      }
      navigate("/dashboard");
    } catch {
      setSession({ access_token: "DEMO_MODE", display_name: "Demo User", email: "demo@dealiq.ai", crm_provider: "demo" });
      navigate("/dashboard");
    }
  };

  const isLoading = loadingProvider !== null;

  return (
    <div className="flex min-h-screen bg-background relative overflow-hidden">

      {/* Soft warm wash behind everything */}
      <div className="pointer-events-none absolute inset-0 -z-0">
        <div className="absolute -top-40 -right-32 h-[520px] w-[520px] rounded-full bg-accent/15 blur-3xl" />
        <div className="absolute -bottom-32 -left-32 h-[520px] w-[520px] rounded-full bg-primary/10 blur-3xl" />
      </div>

      {/* ── Left: editorial brand panel ── */}
      <div className="relative hidden lg:flex flex-col justify-between w-[55%] p-14 z-10">

        {/* Brand */}
        <div className="flex items-center gap-3">
          <div className="relative h-11 w-11 rounded-2xl bg-foreground grid place-items-center">
            <span className="font-display text-background text-xl font-semibold -tracking-wider">d</span>
            <span className="absolute bottom-1.5 right-1.5 h-2 w-2 rounded-full bg-primary ring-2 ring-foreground" />
          </div>
          <span className="font-display text-2xl font-semibold tracking-tight text-foreground">DealIQ</span>
        </div>

        {/* Pitch */}
        <div className="max-w-lg">
          <p className="inline-flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-primary font-semibold mb-4">
            <span className="w-1.5 h-1.5 rounded-full bg-primary" />
            Quiet revenue intelligence
          </p>

          <h2 className="font-display text-5xl xl:text-6xl font-medium leading-[1.02] tracking-tight text-foreground mb-5">
            Revenue without <br /> <span className="serif-accent">the guesswork.</span>
          </h2>
          <p className="text-base text-muted-foreground leading-relaxed max-w-md mb-9">
            Sign in with Outlook so DealIQ can read your inbox for context — then connect your CRM (Salesforce, HubSpot or Zoho) for the deal data.
          </p>

          {/* Promise list */}
          <ul className="space-y-2.5 mb-6">
            {[
              "Plain-English nudges instead of jargon",
              "Spot deals slipping before month-end",
              "One clear next step per deal",
            ].map(item => (
              <li key={item} className="flex items-start gap-3 text-[15px] text-foreground/85">
                <CheckCircle2 className="w-4 h-4 text-primary mt-1 flex-shrink-0" />
                {item}
              </li>
            ))}
          </ul>

          <DashboardPreview />
        </div>

        <p className="text-foreground/45 text-xs font-medium">
          © 2026 DealIQ · made with care.
        </p>
      </div>

      {/* ── Right: sign-in panel ── */}
      <div className="relative flex flex-1 flex-col items-center justify-center p-8 z-10 lg:bg-card lg:border-l lg:border-border">

        <div className="w-full max-w-sm">

          {/* Mobile brand mark */}
          <div className="lg:hidden flex items-center gap-3 mb-10">
            <div className="relative h-10 w-10 rounded-xl bg-foreground grid place-items-center">
              <span className="font-display text-background text-lg font-semibold -tracking-wider">d</span>
              <span className="absolute bottom-1 right-1 h-1.5 w-1.5 rounded-full bg-primary ring-2 ring-foreground" />
            </div>
            <span className="font-display text-2xl font-semibold tracking-tight text-foreground">DealIQ</span>
          </div>

          {/* Headline */}
          <div className="mb-7">
            <h1 className="font-display text-3xl font-medium tracking-tight text-foreground leading-[1.1]">
              Welcome back.
            </h1>
            <p className="mt-2 text-sm text-muted-foreground leading-relaxed">
              Start by signing in with Outlook — that's how DealIQ reads your live email context.
              You'll connect your CRM right after.
            </p>
          </div>

          {/* Outlook — primary */}
          <button
            onClick={handleOutlookLogin}
            disabled={isLoading}
            className="group w-full flex items-center gap-3 rounded-2xl border-2 border-primary/25 bg-primary/[0.04] hover:bg-primary/[0.08] hover:border-primary/45 px-4 py-4 text-left transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed mb-5"
          >
            <span className="flex h-11 w-11 flex-shrink-0 items-center justify-center">
              {loadingProvider === "outlook" ? (
                <span className="h-5 w-5 animate-spin rounded-full border-2 border-foreground/20 border-t-foreground/70" />
              ) : (
                <OutlookLogo className="h-11 w-11 rounded-xl" />
              )}
            </span>
            <div className="flex-1 min-w-0">
              <p className="font-display text-base font-semibold text-foreground tracking-tight">
                {loadingProvider === "outlook" ? "Redirecting…" : "Sign in with Outlook"}
              </p>
              <p className="text-xs text-muted-foreground mt-0.5">
                Recommended · reads your inbox for live deal context
              </p>
            </div>
            <ChevronRight className="h-5 w-5 text-muted-foreground group-hover:text-foreground group-hover:translate-x-0.5 transition-all flex-shrink-0" />
          </button>

          {/* Divider — Or connect a CRM */}
          <div className="flex items-center gap-3 mb-4">
            <div className="flex-1 border-t border-border" />
            <span className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground font-medium">
              Or just your CRM
            </span>
            <div className="flex-1 border-t border-border" />
          </div>

          {/* CRM buttons */}
          <div className="space-y-2 mb-7">
            {CRM_OPTIONS.map((crm) => {
              const isThisLoading = loadingProvider === crm.id;
              const Logo = crm.logo;
              return (
                <button
                  key={crm.id}
                  onClick={() => handleCrmLogin(crm.id)}
                  disabled={isLoading}
                  className="group w-full flex items-center gap-3 rounded-xl border border-border bg-card hover:border-foreground/20 hover:bg-secondary/30 px-4 py-3 text-left transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <span className="flex h-9 w-9 flex-shrink-0 items-center justify-center">
                    {isThisLoading ? (
                      <span className="h-5 w-5 animate-spin rounded-full border-2 border-foreground/20 border-t-foreground/70" />
                    ) : (
                      <Logo className="h-9 w-9 rounded-lg" />
                    )}
                  </span>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold text-foreground">
                      {isThisLoading ? "Redirecting…" : `Sign in with ${crm.name}`}
                    </p>
                    <p className="text-xs text-muted-foreground truncate">{crm.blurb}</p>
                  </div>
                  <ChevronRight className="h-4 w-4 text-muted-foreground group-hover:text-foreground group-hover:translate-x-0.5 transition-all flex-shrink-0" />
                </button>
              );
            })}
            <p className="text-[11px] text-muted-foreground/80 px-1 pt-1">
              Zoho CRM can be connected inside Settings → Integrations once you're signed in.
            </p>
          </div>

          {/* Demo */}
          <button
            onClick={handleDemoLogin}
            disabled={isLoading}
            className="group w-full rounded-xl border border-dashed border-border hover:border-foreground/30 bg-transparent hover:bg-secondary/40 px-4 py-3 text-left transition-all duration-200 disabled:opacity-50"
          >
            <div className="flex items-center justify-between">
              <span className="text-sm font-semibold text-foreground">
                {loadingProvider === "demo" ? "Loading demo…" : "Just browsing? Try the demo"}
              </span>
              <ArrowRight className="h-4 w-4 text-muted-foreground group-hover:text-primary group-hover:translate-x-0.5 transition-all" />
            </div>
            <p className="mt-0.5 text-xs text-muted-foreground">
              No account · pre-loaded with sample deals
            </p>
          </button>

          {/* Trust footer */}
          <p className="mt-9 text-center text-[11px] text-muted-foreground">
            We never store your CRM password · Secure OAuth 2.0
          </p>
        </div>
      </div>
    </div>
  );
}
