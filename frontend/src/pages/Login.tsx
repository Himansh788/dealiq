import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  BarChart3, Zap, Activity, Brain, Shield, TrendingUp, Target, ArrowRight,
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

/* ── Abstracted dashboard preview ── */
function DashboardPreview() {
  return (
    <div className="relative w-full max-w-md mx-auto mt-10 rounded-xl border border-white/10 bg-white/5 backdrop-blur-sm overflow-hidden shadow-2xl">
      {/* mock header bar */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-white/10">
        <div className="h-2 w-2 rounded-full bg-white/20" />
        <div className="h-2 w-16 rounded-full bg-white/20" />
        <div className="ml-auto h-2 w-10 rounded-full bg-white/20" />
      </div>

      {/* mock health score row */}
      <div className="flex items-center gap-4 px-4 py-4 border-b border-white/10">
        {/* donut placeholder */}
        <div className="relative flex-shrink-0 h-16 w-16">
          <svg viewBox="0 0 36 36" className="rotate-[-90deg] h-16 w-16">
            <circle cx="18" cy="18" r="14" fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="3.5" />
            <circle
              cx="18" cy="18" r="14" fill="none"
              stroke="#3B82F6" strokeWidth="3.5"
              strokeDasharray="62 88" strokeLinecap="round"
            />
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

      {/* mock deal rows */}
      {[70, 55, 40].map((w, i) => (
        <div key={i} className="flex items-center gap-3 px-4 py-2.5 border-b border-white/5 last:border-0">
          <div className="h-7 w-7 rounded-md bg-white/10 flex-shrink-0" />
          <div className="flex-1 space-y-1.5">
            <div className={`h-2 rounded-full bg-white/20`} style={{ width: `${w}%` }} />
            <div className="h-1.5 w-16 rounded-full bg-white/10" />
          </div>
          <div
            className={`h-4 w-12 rounded-full text-[10px] flex items-center justify-center font-medium ${
              i === 0 ? "bg-emerald-500/20 text-emerald-400" :
              i === 1 ? "bg-amber-500/20 text-amber-400" :
                        "bg-rose-500/20 text-rose-400"
            }`}
          >
            {i === 0 ? "Healthy" : i === 1 ? "At Risk" : "Critical"}
          </div>
        </div>
      ))}

      {/* blurred overlay at bottom for depth */}
      <div className="absolute bottom-0 left-0 right-0 h-10 bg-gradient-to-t from-[#0d1b2e] to-transparent" />
    </div>
  );
}

/* ── Animated dot-grid background ── */
function BrandBackground() {
  return (
    <div className="absolute inset-0 overflow-hidden">
      {/* base gradient */}
      <div className="absolute inset-0" style={{
        background: "radial-gradient(ellipse 80% 60% at 30% 40%, #0f2a5c 0%, #060d1f 60%, #030b18 100%)"
      }} />
      {/* dot pattern via SVG data URI */}
      <div className="absolute inset-0 opacity-[0.18]" style={{
        backgroundImage: `url("data:image/svg+xml,%3Csvg width='24' height='24' viewBox='0 0 24 24' xmlns='http://www.w3.org/2000/svg'%3E%3Ccircle cx='2' cy='2' r='1' fill='%23ffffff'/%3E%3C/svg%3E")`,
        backgroundRepeat: "repeat",
      }} />
      {/* subtle glow orbs */}
      <div className="absolute top-1/4 left-1/3 h-64 w-64 rounded-full bg-blue-600/10 blur-3xl" />
      <div className="absolute bottom-1/4 right-1/4 h-48 w-48 rounded-full bg-blue-400/8 blur-3xl" />
    </div>
  );
}

export default function Login() {
  const { session, setSession } = useSession();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { toast } = useToast();
  const [loading, setLoading] = useState(false);

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
      toast({ title: "Login error", description: decodeURIComponent(errorParam), variant: "destructive" });
    }
  }, [searchParams, setSession, navigate, toast]);

  const handleZohoLogin = async () => {
    setLoading(true);
    try {
      const data = await api.getLoginUrl();
      window.location.href = data.auth_url;
    } catch (err: any) {
      toast({ title: "Login failed", description: err.message, variant: "destructive" });
      setLoading(false);
    }
  };

  const handleDemoLogin = async () => {
    setLoading(true);
    try {
      const data = await api.getDemoSession();
      setSession(data);
      navigate("/dashboard");
    } catch {
      setSession({ access_token: "DEMO_MODE", display_name: "Demo User", email: "demo@dealiq.ai" });
      navigate("/dashboard");
    }
  };

  return (
    <div className="flex min-h-screen bg-slate-50 dark:bg-[#060d1f]">

      {/* ── Left: Brand panel ── */}
      <div className="relative hidden lg:flex flex-col justify-between w-[55%] p-12 overflow-hidden">
        <BrandBackground />

        <div className="relative z-10">
          {/* Logo */}
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-500/20 border border-blue-400/20">
              <BarChart3 className="h-6 w-6 text-blue-400" />
            </div>
            <span className="text-2xl font-black tracking-tight text-slate-900 dark:text-white">DealIQ</span>
          </div>
        </div>

        {/* Hero content */}
        <div className="relative z-10">
          <h2 className="text-4xl font-bold text-slate-900 dark:text-white leading-tight mb-3 tracking-tight">
            Revenue without guesswork.
          </h2>
          <p className="text-slate-400 text-base leading-relaxed mb-8 max-w-sm">
            Score every deal, surface hidden risks, and close with confidence.
            Know exactly which deals need attention — before it's too late.
          </p>

          {/* Feature chips — 2×3 grid */}
          <div className="grid grid-cols-2 gap-2 max-w-xs">
            {FEATURES.map(({ icon: Icon, label }) => (
              <div
                key={label}
                className="flex items-center gap-2 rounded-lg border border-white/10 bg-white/5 px-3 py-2"
              >
                <Icon className="h-3.5 w-3.5 text-blue-400 flex-shrink-0" />
                <span className="text-xs font-medium text-slate-600 dark:text-slate-300">{label}</span>
              </div>
            ))}
          </div>

          {/* Dashboard preview */}
          <DashboardPreview />
        </div>

        <p className="relative z-10 text-slate-600 text-xs">
          © 2026 DealIQ · Revenue without guesswork.
        </p>
      </div>

      {/* ── Right: Sign-in panel ── */}
      <div className="flex flex-1 flex-col items-center justify-center p-8 bg-white dark:bg-slate-900">

        <div className="w-full max-w-sm">

          {/* Brand mark (desktop — reinforcement) */}
          <div className="hidden lg:flex items-center gap-2.5 mb-10">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-500/15 border border-blue-500/20">
              <BarChart3 className="h-4 w-4 text-blue-400" />
            </div>
            <span className="text-lg font-black tracking-tight text-white">DealIQ</span>
          </div>

          {/* Mobile logo */}
          <div className="lg:hidden flex items-center gap-2.5 mb-10">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-blue-500/15 border border-blue-500/20">
              <BarChart3 className="h-5 w-5 text-blue-400" />
            </div>
            <span className="text-2xl font-black tracking-tight text-slate-900 dark:text-white">DealIQ</span>
          </div>

          <div className="mb-8">
            <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Welcome back</h1>
            <p className="mt-1.5 text-sm text-slate-400">Sign in to your account to continue</p>
          </div>

          <div className="space-y-3">
            {/* Primary CTA */}
            <Button
              className="h-11 w-full text-sm font-semibold text-white bg-blue-500 hover:bg-blue-600 border-0 transition-all duration-150"
              onClick={handleZohoLogin}
              disabled={loading}
            >
              {loading ? (
                <span className="flex items-center gap-2">
                  <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                  Connecting…
                </span>
              ) : (
                <span className="flex items-center gap-2">
                  {/* Zoho "Z" badge */}
                  <span className="flex h-4 w-4 items-center justify-center rounded-sm bg-white/20 text-[10px] font-black leading-none">
                    Z
                  </span>
                  Sign in with Zoho CRM
                </span>
              )}
            </Button>

            {/* Divider */}
            <div className="relative py-1">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-slate-200 dark:border-slate-700" />
              </div>
              <div className="relative flex justify-center text-xs">
                <span className="bg-white dark:bg-slate-900 px-2 text-slate-500">or</span>
              </div>
            </div>

            {/* Demo — inviting treatment */}
            <button
              onClick={handleDemoLogin}
              disabled={loading}
              className="group w-full rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50/60 dark:bg-slate-800/60 px-4 py-3 text-left transition-all duration-150 hover:border-blue-500/40 hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-50"
            >
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-slate-700 dark:text-slate-200 group-hover:text-slate-900 dark:group-hover:text-white transition-colors">
                  Explore DealIQ Demo
                </span>
                <ArrowRight className="h-4 w-4 text-slate-500 group-hover:text-blue-400 group-hover:translate-x-0.5 transition-all duration-150" />
              </div>
              <p className="mt-0.5 text-xs text-slate-500">
                No account needed · Pre-loaded with sample deals
              </p>
            </button>
          </div>

          {/* Trust line */}
          <p className="mt-8 text-center text-xs text-slate-600">
            Built for B2B revenue teams on Zoho CRM
          </p>
        </div>
      </div>
    </div>
  );
}
