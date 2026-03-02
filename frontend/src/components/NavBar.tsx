import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import {
  BarChart3, LogOut, Search,
  ChevronDown, Settings,
} from "lucide-react";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem,
  DropdownMenuSeparator, DropdownMenuTrigger, DropdownMenuLabel,
} from "@/components/ui/dropdown-menu";
import { useSession } from "@/contexts/SessionContext";
import { AlertsBell } from "@/components/AlertsDigestPanel";
import CommandPalette from "@/components/CommandPalette";

interface NavDeal {
  id: string;
  deal_name: string;
  health_score: number;
  health_label: string;
  stage: string;
}

interface NavBarProps {
  onOpenDigest: () => void;
  onOpenSignal: () => void;
  digestCriticalCount?: number;
  deals?: NavDeal[];
  onSelectDeal?: (dealId: string) => void;
}

export default function NavBar({
  onOpenDigest,
  onOpenSignal,
  digestCriticalCount,
  deals,
  onSelectDeal,
}: NavBarProps) {
  const { session, logout, isDemo } = useSession();
  const navigate  = useNavigate();
  const [cmdOpen, setCmdOpen] = useState(false);

  const userInitials = (session?.display_name ?? "U")
    .split(" ")
    .filter(Boolean)
    .map((n: string) => n[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

  const handleLogout = () => { logout(); navigate("/"); };

  // Cmd+K / Ctrl+K to open command palette
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setCmdOpen(v => !v);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  return (
    <>
      <header className="sticky top-0 z-40 border-b border-border/40 bg-background/90 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6">

          {/* Brand — clickable → dashboard */}
          <button
            onClick={() => navigate("/dashboard")}
            className="flex cursor-pointer items-center gap-3 transition-opacity hover:opacity-80"
          >
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-primary via-primary/80 to-accent shadow-lg shadow-primary/20">
              <BarChart3 className="h-5 w-5 text-white" />
            </div>
            <span className="text-xl font-bold tracking-tight text-foreground">DealIQ</span>
            {isDemo && (
              <span className="ml-1 rounded-full border border-health-orange/40 bg-health-orange/10 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-health-orange">
                Demo
              </span>
            )}
          </button>

          {/* Right-side nav */}
          <div className="flex items-center gap-2">

            {/* Cmd+K search trigger */}
            <button
              onClick={() => setCmdOpen(true)}
              className="flex items-center gap-2 rounded-md border border-border/40 bg-secondary/40 px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:border-border/70 hover:bg-secondary/60 hover:text-foreground"
            >
              <Search className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Search</span>
              <kbd className="hidden items-center rounded border border-border/50 bg-background/50 px-1.5 py-0.5 font-mono text-[10px] sm:inline-flex">
                ⌘K
              </kbd>
            </button>

            {/* Alerts bell with badge */}
            <AlertsBell onClick={onOpenDigest} criticalCount={digestCriticalCount} />

            {/* User menu */}
            <div className="ml-1 border-l border-border/40 pl-3">
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <button className="flex items-center gap-2 rounded-lg px-2 py-1 transition-colors hover:bg-secondary/60">
                    <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary/15 text-xs font-bold text-primary">
                      {userInitials}
                    </div>
                    <div className="hidden text-left sm:block">
                      <p className="text-sm font-semibold leading-tight text-foreground">
                        {session?.display_name ?? "User"}
                      </p>
                    </div>
                    <ChevronDown className="hidden h-3.5 w-3.5 text-muted-foreground/50 sm:block" />
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-52 border-border/40 bg-card shadow-xl">
                  <DropdownMenuLabel className="pb-1">
                    <p className="font-semibold text-foreground">{session?.display_name ?? "User"}</p>
                    <p className="text-xs font-normal text-muted-foreground/70">{session?.email ?? ""}</p>
                  </DropdownMenuLabel>
                  <DropdownMenuSeparator className="bg-border/40" />
                  <DropdownMenuItem className="cursor-default gap-2 text-muted-foreground focus:bg-transparent focus:text-muted-foreground">
                    <div className="h-2 w-2 rounded-full bg-health-green" />
                    <span className="text-xs">CRM: Zoho connected</span>
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    className="gap-2 text-muted-foreground opacity-50 focus:bg-transparent"
                    disabled
                  >
                    <Settings className="h-3.5 w-3.5" />
                    <span className="text-xs">Settings (coming soon)</span>
                  </DropdownMenuItem>
                  <DropdownMenuSeparator className="bg-border/40" />
                  <DropdownMenuItem
                    onClick={handleLogout}
                    className="gap-2 text-health-red focus:bg-health-red/10 focus:text-health-red"
                  >
                    <LogOut className="h-3.5 w-3.5" />
                    <span className="text-xs">Sign Out</span>
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </div>
        </div>
      </header>

      <CommandPalette
        open={cmdOpen}
        onClose={() => setCmdOpen(false)}
        deals={deals}
        onSelectDeal={(id) => {
          setCmdOpen(false);
          if (onSelectDeal) {
            onSelectDeal(id);
          } else {
            // Navigating from a non-dashboard page — go to dashboard and open deal
            navigate(`/dashboard?deal=${id}`);
          }
        }}
        onNavigate={(path) => {
          setCmdOpen(false);
          navigate(path);
        }}
        onOpenSignal={() => {
          setCmdOpen(false);
          onOpenSignal();
        }}
        onOpenDigest={() => {
          setCmdOpen(false);
          onOpenDigest();
        }}
      />
    </>
  );
}
