import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { BarChart3, Zap, Activity, Brain, Shield } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useSession } from "@/contexts/SessionContext";
import { useToast } from "@/hooks/use-toast";
import { api } from "@/lib/api";

const FEATURES = [
  { icon: Activity, label: "Live Deal Health" },
  { icon: Brain, label: "AI Sales Coach" },
  { icon: Zap, label: "Pipeline Intelligence" },
  { icon: Shield, label: "Deal Autopsy" },
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
    <div className="relative flex min-h-screen items-center justify-center bg-background p-4 overflow-hidden">

      {/* Animated Mesh Gradient Background */}
      <div className="absolute inset-0 overflow-hidden bg-[#060a13] -z-10">
        <div className="absolute w-[80vw] h-[80vh] rounded-full bg-blue-600/20 blur-[100px] animate-mesh-1" />
        <div className="absolute w-[60vw] h-[60vh] rounded-full bg-teal-500/15 blur-[100px] animate-mesh-2" />
        <div className="absolute w-[70vw] h-[70vh] rounded-full bg-purple-600/20 blur-[100px] animate-mesh-3" />
      </div>

      {/* Card */}
      <Card className="relative w-full max-w-md border-border/50 bg-card/70 shadow-2xl shadow-black/40 backdrop-blur-md animate-slide-up">

        {/* Top accent */}
        <div className="absolute inset-x-0 top-0 h-px rounded-t-[inherit] bg-gradient-to-r from-transparent via-primary/60 to-transparent" />

        <CardContent className="flex flex-col items-center gap-7 px-8 py-10">

          {/* Logo */}
          <div className="flex items-center gap-3 fade-slide-in" style={{ animationDelay: '100ms' }}>
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-primary via-primary/80 to-accent shadow-lg shadow-primary/25">
              <BarChart3 className="h-7 w-7 text-white" />
            </div>
            <span className="text-3xl font-black tracking-tight text-foreground">DealIQ</span>
          </div>

          {/* Tagline */}
          <div className="text-center">
            <p className="text-lg font-semibold text-foreground fade-slide-in" style={{ animationDelay: '250ms' }}>Revenue without guesswork.</p>
            <p className="mt-1.5 text-sm text-muted-foreground/70 max-w-xs leading-relaxed fade-slide-in" style={{ animationDelay: '400ms' }}>
              AI-powered deal clarity for B2B SaaS revenue teams
            </p>
          </div>

          {/* CTA */}
          <div className="w-full space-y-3 relative z-10">
            <div className="fade-slide-in" style={{ animationDelay: '550ms' }}>
              <Button
                className="h-12 w-full text-base font-semibold border-0 text-white transition-all duration-300 transform hover:-translate-y-[2px] active:translate-y-0"
                style={{
                  background: 'linear-gradient(135deg, #3b82f6, #2563eb)',
                  boxShadow: '0 4px 20px rgba(59,130,246,0.3)',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.boxShadow = '0 6px 24px rgba(59,130,246,0.5)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.boxShadow = '0 4px 20px rgba(59,130,246,0.3)';
                }}
                onClick={handleZohoLogin}
                disabled={loading}
              >
                {loading ? (
                  <span className="flex items-center gap-2">
                    <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                    Connecting…
                  </span>
                ) : "Login with Zoho CRM"}
              </Button>
            </div>

            <div className="fade-slide-in" style={{ animationDelay: '700ms' }}>
              <button
                onClick={handleDemoLogin}
                disabled={loading}
                className="w-full text-center text-sm text-muted-foreground/60 transition-colors hover:text-muted-foreground"
              >
                Try demo without login →
              </button>
            </div>
          </div>

          {/* Feature chips */}
          <div className="flex flex-wrap justify-center gap-2 fade-slide-in" style={{ animationDelay: '850ms' }}>
            {FEATURES.map(({ icon: Icon, label }) => (
              <span
                key={label}
                className="flex items-center gap-1.5 rounded-full border border-border/40 bg-secondary/30 px-3 py-1 text-xs font-medium text-muted-foreground/70"
              >
                <Icon className="h-3 w-3 text-primary/60" />
                {label}
              </span>
            ))}
          </div>

        </CardContent>
      </Card>
    </div>
  );
}
