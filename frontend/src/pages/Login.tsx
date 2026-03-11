import React, { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  BarChart3, Zap, Activity, Brain, Shield, TrendingUp, Target, ArrowRight, ChevronRight,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useSession } from "@/contexts/SessionContext";
import { useToast } from "@/hooks/use-toast";
import { api } from "@/lib/api";

const FEATURES = [
  { icon: Activity,   label: "Live Deal Health" },
  { icon: Brain,      label: "AI Sales Coach" },
  { icon: Zap,        label: "Pipeline Intelligence" },
  { icon: Shield,     label: "Deal Autopsy" },
  { icon: TrendingUp, label: "Win/Loss Analysis" },
  { icon: Target,     label: "Forecast Board" },
];

// ── CRM provider definitions ──────────────────────────────────────────────────

type CRMProvider = "zoho" | "salesforce" | "hubspot";

function ZohoLogo({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect width="64" height="64" rx="10" fill="#E42527"/>
      <path d="M10 44L26.5 22H11.5V18H38L21.5 40H38V44H10Z" fill="white"/>
      <path d="M43 26C43 23.8 44.8 22 47 22C49.2 22 51 23.8 51 26C51 28.2 49.2 30 47 30C44.8 30 43 28.2 43 26Z" fill="white"/>
      <path d="M40 44C40 38.5 43 34 47 34C51 34 54 38.5 54 44H40Z" fill="white"/>
    </svg>
  );
}

function SalesforceLogo({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect width="64" height="64" rx="10" fill="#00A1E0"/>
      {/* Salesforce cloud icon */}
      <path
        d="M27.2 18.4C28.8 16.3 31.2 15 34 15C38.3 15 41.9 18 42.8 22C43.2 21.9 43.6 21.8 44 21.8C47.3 21.8 50 24.5 50 27.8C50 31.1 47.3 33.8 44 33.8H20C17.2 33.8 15 31.6 15 28.8C15 26.2 16.9 24.1 19.4 23.9C19.1 23.2 19 22.5 19 21.8C19 19.1 21.3 16.8 24 16.8C25.1 16.8 26.2 17.2 27.2 18.4Z"
        fill="white"
      />
      <path d="M22 38H42V42C42 43.1 41.1 44 40 44H24C22.9 44 22 43.1 22 42V38Z" fill="white" opacity="0.7"/>
      <rect x="29" y="33" width="6" height="6" fill="white" opacity="0.7"/>
    </svg>
  );
}

function HubSpotLogo({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect width="64" height="64" rx="10" fill="#FF7A59"/>
      {/* HubSpot sprocket/person icon */}
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

interface CRMOption {
  id: CRMProvider;
  name: string;
  logo: React.FC<{ className?: string }>;
  description: string;
}

const CRM_OPTIONS: CRMOption[] = [
  {
    id: "zoho",
    name: "Zoho CRM",
    logo: ZohoLogo,
    description: "Connect your Zoho CRM pipeline",
  },
  {
    id: "salesforce",
    name: "Salesforce",
    logo: SalesforceLogo,
    description: "Connect your Salesforce org",
  },
  {
    id: "hubspot",
    name: "HubSpot",
    logo: HubSpotLogo,
    description: "Connect your HubSpot portal",
  },
];

// ── Dashboard preview (unchanged) ────────────────────────────────────────────

function DashboardPreview() {
  return (
    <div className="relative w-full max-w-md mx-auto mt-10 rounded-xl border border-white/10 bg-white/5 backdrop-blur-sm overflow-hidden shadow-2xl">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-white/10">
        <div className="h-2 w-2 rounded-full bg-white/20" />
        <div className="h-2 w-16 rounded-full bg-white/20" />
        <div className="ml-auto h-2 w-10 rounded-full bg-white/20" />
      </div>
      <div className="flex items-center gap-4 px-4 py-4 border-b border-white/10">
        <div className="relative flex-shrink-0 h-16 w-16">
          <svg viewBox="0 0 36 36" className="rotate-[-90deg] h-16 w-16">
            <circle cx="18" cy="18" r="14" fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="3.5" />
            <circle cx="18" cy="18" r="14" fill="none" stroke="#3B82F6" strokeWidth="3.5"
              strokeDasharray="62 88" strokeLinecap="round" />
          </svg>
          <span className="absolute inset-0 flex items-center justify-center text-sm font-bold text-white">72</span>
        </div>
        <div className="flex-1 space-y-2">
          <div className="h-2 w-32 rounded-full bg-white/20" />
          <div className="h-2 w-20 rounded-full bg-white/10" />
        </div>
        <div className="text-right space-y-1">
          <div className="h-2 w-16 rounded-full bg-emerald-400/40" />
          <div className="h-2 w-12 rounded-full bg-white/10" />
        </div>
      </div>
      {[70, 55, 40].map((w, i) => (
        <div key={i} className="flex items-center gap-3 px-4 py-2.5 border-b border-white/5 last:border-0">
          <div className="h-7 w-7 rounded-md bg-white/10 flex-shrink-0" />
          <div className="flex-1 space-y-1.5">
            <div className="h-2 rounded-full bg-white/20" style={{ width: `${w}%` }} />
            <div className="h-1.5 w-16 rounded-full bg-white/10" />
          </div>
          <div className={`h-4 w-12 rounded-full text-[10px] flex items-center justify-center font-medium ${
            i === 0 ? "bg-emerald-500/20 text-emerald-400" :
            i === 1 ? "bg-amber-500/20 text-amber-400" :
                      "bg-rose-500/20 text-rose-400"
          }`}>
            {i === 0 ? "Healthy" : i === 1 ? "At Risk" : "Critical"}
          </div>
        </div>
      ))}
      <div className="absolute bottom-0 left-0 right-0 h-10 bg-gradient-to-t from-[#0d1b2e] to-transparent" />
    </div>
  );
}

function BrandBackground() {
  return (
    <div className="absolute inset-0 overflow-hidden">
      <div className="absolute inset-0" style={{
        background: "radial-gradient(ellipse 80% 60% at 30% 40%, #0f2a5c 0%, #060d1f 60%, #030b18 100%)"
      }} />
      <div className="absolute inset-0 opacity-[0.18]" style={{
        backgroundImage: `url("data:image/svg+xml,%3Csvg width='24' height='24' viewBox='0 0 24 24' xmlns='http://www.w3.org/2000/svg'%3E%3Ccircle cx='2' cy='2' r='1' fill='%23ffffff'/%3E%3C/svg%3E")`,
        backgroundRepeat: "repeat",
      }} />
      <div className="absolute top-1/4 left-1/3 h-64 w-64 rounded-full bg-blue-600/10 blur-3xl" />
      <div className="absolute bottom-1/4 right-1/4 h-48 w-48 rounded-full bg-blue-400/8 blur-3xl" />
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function Login() {
  const { session, setSession } = useSession();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { toast } = useToast();
  const [loadingProvider, setLoadingProvider] = useState<CRMProvider | "demo" | null>(null);

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
        toast({ title: "Login failed", description: "Invalid session data", variant: "destructive" });
      }
    } else if (errorParam) {
      const provider = searchParams.get("provider");
      const detail = searchParams.get("detail");
      toast({
        title: `${provider ? provider.charAt(0).toUpperCase() + provider.slice(1) + " " : ""}Login error`,
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
      toast({ title: "Login failed", description: err.message, variant: "destructive" });
      setLoadingProvider(null);
    }
  };

  const handleDemoLogin = async () => {
    setLoadingProvider("demo");
    try {
      const data = await api.getDemoSession();
      // Backend returns { session: base64string, message: string }
      // Decode the base64 session to extract access_token etc.
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
    <div className="flex min-h-screen bg-slate-50 dark:bg-[#060d1f]">

      {/* ── Left: Brand panel ── */}
      <div className="relative hidden lg:flex flex-col justify-between w-[55%] p-12 overflow-hidden">
        <BrandBackground />

        <div className="relative z-10">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-500/20 border border-blue-400/20">
              <BarChart3 className="h-6 w-6 text-blue-400" />
            </div>
            <span className="text-2xl font-black tracking-tight text-white">DealIQ</span>
          </div>
        </div>

        <div className="relative z-10">
          <h2 className="text-4xl font-bold text-white leading-tight mb-3 tracking-tight">
            Revenue without guesswork.
          </h2>
          <p className="text-slate-400 text-base leading-relaxed mb-8 max-w-sm">
            Score every deal, surface hidden risks, and close with confidence.
            Works with your CRM — Zoho, Salesforce, or HubSpot.
          </p>

          <div className="grid grid-cols-2 gap-2 max-w-xs">
            {FEATURES.map(({ icon: Icon, label }) => (
              <div
                key={label}
                className="flex items-center gap-2 rounded-lg border border-white/10 bg-white/5 px-3 py-2"
              >
                <Icon className="h-3.5 w-3.5 text-blue-400 flex-shrink-0" />
                <span className="text-xs font-medium text-slate-300">{label}</span>
              </div>
            ))}
          </div>

          <DashboardPreview />
        </div>

        <p className="relative z-10 text-white/50 text-xs">
          © 2026 DealIQ · Revenue without guesswork.
        </p>
      </div>

      {/* ── Right: Sign-in panel ── */}
      <div className="relative flex flex-1 flex-col items-center justify-center p-8 bg-white dark:bg-slate-900 overflow-hidden">

        {/* Subtle background decoration */}
        <div className="pointer-events-none absolute inset-0">
          {/* Dot grid */}
          <div className="absolute inset-0 opacity-[0.035] dark:opacity-[0.06]" style={{
            backgroundImage: `url("data:image/svg+xml,%3Csvg width='20' height='20' viewBox='0 0 20 20' xmlns='http://www.w3.org/2000/svg'%3E%3Ccircle cx='2' cy='2' r='1' fill='%236366f1'/%3E%3C/svg%3E")`,
            backgroundRepeat: "repeat",
          }} />
          {/* Floating orbs */}
          <div className="absolute -top-20 -right-20 h-72 w-72 rounded-full bg-blue-100/60 dark:bg-blue-900/20 blur-3xl" />
          <div className="absolute bottom-10 -left-16 h-56 w-56 rounded-full bg-indigo-100/50 dark:bg-indigo-900/15 blur-3xl" />
          <div className="absolute top-1/2 right-8 h-40 w-40 rounded-full bg-sky-100/40 dark:bg-sky-900/10 blur-2xl" />
        </div>
        <div className="w-full max-w-sm">

          {/* Brand mark */}
          <div className="hidden lg:flex items-center gap-2.5 mb-10">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-500/15 border border-blue-500/20">
              <BarChart3 className="h-4 w-4 text-blue-400" />
            </div>
            <span className="text-lg font-black tracking-tight text-slate-900 dark:text-white">DealIQ</span>
          </div>

          <div className="lg:hidden flex items-center gap-2.5 mb-10">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-blue-500/15 border border-blue-500/20">
              <BarChart3 className="h-5 w-5 text-blue-400" />
            </div>
            <span className="text-2xl font-black tracking-tight text-slate-900 dark:text-white">DealIQ</span>
          </div>

          <div className="mb-6">
            <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Connect your CRM</h1>
            <p className="mt-1.5 text-sm text-slate-400">Choose your CRM to get started</p>
          </div>

          {/* CRM buttons */}
          <div className="space-y-2.5 mb-4">
            {CRM_OPTIONS.map((crm) => {
              const isThisLoading = loadingProvider === crm.id;
              const Logo = crm.logo;
              return (
                <button
                  key={crm.id}
                  onClick={() => handleCrmLogin(crm.id)}
                  disabled={isLoading}
                  className="group w-full flex items-center gap-3 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 px-4 py-3 text-left transition-all duration-150 hover:border-blue-500/50 hover:bg-slate-100 dark:hover:bg-slate-700/80 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {/* CRM logo */}
                  <span className="flex h-9 w-9 flex-shrink-0 items-center justify-center">
                    {isThisLoading ? (
                      <span className="h-5 w-5 animate-spin rounded-full border-2 border-slate-300 border-t-slate-600 dark:border-slate-600 dark:border-t-slate-300" />
                    ) : (
                      <Logo className="h-9 w-9 rounded-lg" />
                    )}
                  </span>

                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold text-slate-800 dark:text-slate-100 group-hover:text-slate-900 dark:group-hover:text-white transition-colors">
                      {isThisLoading ? "Redirecting…" : `Sign in with ${crm.name}`}
                    </p>
                    <p className="text-xs text-slate-500 truncate">{crm.description}</p>
                  </div>

                  <ChevronRight className="h-4 w-4 text-slate-400 group-hover:text-slate-600 dark:group-hover:text-slate-300 flex-shrink-0 transition-colors" />
                </button>
              );
            })}
          </div>

          {/* Divider */}
          <div className="relative py-2">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-slate-200 dark:border-slate-700" />
            </div>
            <div className="relative flex justify-center text-xs">
              <span className="bg-white dark:bg-slate-900 px-2 text-slate-500">or</span>
            </div>
          </div>

          {/* Demo */}
          <button
            onClick={handleDemoLogin}
            disabled={isLoading}
            className="group w-full rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50/60 dark:bg-slate-800/60 px-4 py-3 text-left transition-all duration-150 hover:border-blue-500/40 hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-50"
          >
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-slate-700 dark:text-slate-200 group-hover:text-slate-900 dark:group-hover:text-white transition-colors">
                {loadingProvider === "demo" ? "Loading demo…" : "Explore DealIQ Demo"}
              </span>
              <ArrowRight className="h-4 w-4 text-slate-500 group-hover:text-blue-400 group-hover:translate-x-0.5 transition-all duration-150" />
            </div>
            <p className="mt-0.5 text-xs text-slate-500">
              No account needed · Pre-loaded with sample deals
            </p>
          </button>

          <p className="mt-8 text-center text-xs text-slate-500">
            Supports Zoho CRM · Salesforce · HubSpot
          </p>
        </div>
      </div>
    </div>
  );
}
