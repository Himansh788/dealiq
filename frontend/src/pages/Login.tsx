import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { BarChart3, Zap, Activity, Brain, Shield, TrendingUp, Target } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useSession } from "@/contexts/SessionContext";
import { useToast } from "@/hooks/use-toast";
import { api } from "@/lib/api";

const FEATURES = [
  { icon: Activity, label: "Live Deal Health" },
  { icon: Brain, label: "AI Sales Coach" },
  { icon: Zap, label: "Pipeline Intelligence" },
  { icon: Shield, label: "Deal Autopsy" },
  { icon: TrendingUp, label: "Win/Loss Analysis" },
  { icon: Target, label: "Forecast Board" },
];

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
    <div className="flex min-h-screen">

      {/* ── Left: Brand panel ── */}
      <div
        className="hidden lg:flex flex-col justify-between w-[45%] p-12"
        style={{ background: "linear-gradient(145deg, #020887 0%, #1368AA 100%)" }}
      >
        {/* Logo */}
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-white/20">
            <BarChart3 className="h-6 w-6 text-white" />
          </div>
          <span className="text-2xl font-black tracking-tight text-white">DealIQ</span>
        </div>

        {/* Headline */}
        <div>
          <h2 className="text-3xl font-bold text-white leading-tight mb-4">
            AI-powered deal intelligence for revenue teams
          </h2>
          <p className="text-blue-200/75 text-base leading-relaxed mb-8">
            Score every deal, surface hidden risks, and close with confidence. Know exactly which deals need attention — before it's too late.
          </p>
          {/* Feature chips */}
          <div className="flex flex-wrap gap-2">
            {FEATURES.map(({ icon: Icon, label }) => (
              <span
                key={label}
                className="flex items-center gap-1.5 rounded-full border border-white/20 bg-white/10 px-3 py-1 text-xs font-medium text-white/80"
              >
                <Icon className="h-3 w-3" />
                {label}
              </span>
            ))}
          </div>
        </div>

        <p className="text-blue-200/35 text-xs">© 2026 DealIQ · Revenue without guesswork.</p>
      </div>

      {/* ── Right: Sign-in panel ── */}
      <div className="flex flex-1 flex-col items-center justify-center p-8 bg-background">

        {/* Mobile logo */}
        <div className="lg:hidden flex items-center gap-2.5 mb-10">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary">
            <BarChart3 className="h-5 w-5 text-white" />
          </div>
          <span className="text-2xl font-black tracking-tight text-foreground">DealIQ</span>
        </div>

        <div className="w-full max-w-sm animate-slide-up">
          <div className="mb-8">
            <h1 className="text-2xl font-bold text-foreground">Welcome back</h1>
            <p className="mt-1.5 text-sm text-muted-foreground">Sign in to your account to continue</p>
          </div>

          <div className="space-y-3">
            {/* Primary CTA */}
            <Button
              className="h-11 w-full text-sm font-semibold text-white border-0 transition-all duration-150 hover:opacity-90"
              style={{ background: "#020887" }}
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
                  <Shield className="h-4 w-4" />
                  Sign in with Zoho CRM
                </span>
              )}
            </Button>

            {/* Divider */}
            <div className="relative py-1">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-border/40" />
              </div>
              <div className="relative flex justify-center text-xs">
                <span className="bg-background px-2 text-muted-foreground/50">or</span>
              </div>
            </div>

            {/* Demo */}
            <button
              onClick={handleDemoLogin}
              disabled={loading}
              className="w-full h-10 rounded-lg border border-border/50 bg-secondary/30 text-sm text-muted-foreground transition-colors hover:bg-secondary/60 hover:text-foreground disabled:opacity-50"
            >
              Try demo without login
            </button>
          </div>

          <p className="mt-8 text-center text-xs text-muted-foreground/40">
            Don't have an account? Contact your admin.
          </p>
        </div>
      </div>
    </div>
  );
}
