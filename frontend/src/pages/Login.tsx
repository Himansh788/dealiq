import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { BarChart3 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useSession } from "@/contexts/SessionContext";
import { useToast } from "@/hooks/use-toast";
import { api } from "@/lib/api";

export default function Login() {
  const { session, setSession } = useSession();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { toast } = useToast();
  const [loading, setLoading] = useState(false);

  // If already logged in, go to dashboard
  useEffect(() => {
    if (session) navigate("/dashboard", { replace: true });
  }, [session, navigate]);

  // Handle OAuth callback params
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
    } catch (err: any) {
      // Fallback: create a local demo session
      setSession({ access_token: "DEMO_MODE", display_name: "Demo User", email: "demo@dealiq.ai" });
      navigate("/dashboard");
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4">
      <div className="absolute inset-0 overflow-hidden">
        <div className="absolute -top-40 -right-40 h-80 w-80 rounded-full bg-primary/10 blur-3xl" />
        <div className="absolute -bottom-40 -left-40 h-80 w-80 rounded-full bg-accent/10 blur-3xl" />
      </div>

      <Card className="relative w-full max-w-md border-border/50 bg-card/80 backdrop-blur-sm">
        <CardContent className="flex flex-col items-center gap-6 p-8 pt-10">
          {/* Logo */}
          <div className="flex items-center gap-3">
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br from-primary to-accent">
              <BarChart3 className="h-7 w-7 text-foreground" />
            </div>
            <span className="text-3xl font-bold tracking-tight text-foreground">DealIQ</span>
          </div>

          {/* Tagline */}
          <div className="text-center">
            <p className="text-lg font-medium text-foreground">Revenue without guesswork.</p>
            <p className="mt-1 text-sm text-muted-foreground">
              AI-powered deal clarity for B2B SaaS revenue teams
            </p>
          </div>

          {/* Login Button */}
          <Button
            className="w-full h-12 text-base font-semibold bg-primary hover:bg-primary/90"
            onClick={handleZohoLogin}
            disabled={loading}
          >
            {loading ? "Connecting..." : "Login with Zoho CRM"}
          </Button>

          {/* Demo Link */}
          <button
            onClick={handleDemoLogin}
            disabled={loading}
            className="text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            Try demo without login →
          </button>
        </CardContent>
      </Card>
    </div>
  );
}
