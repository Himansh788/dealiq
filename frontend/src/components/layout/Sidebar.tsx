import { useLocation, useNavigate } from "react-router-dom";
import {
  BarChart3,
  Home,
  LayoutDashboard,
  Mail,
  Sparkles,
  Trophy,
  Settings,
  LogOut,
} from "lucide-react";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { useSession } from "@/contexts/SessionContext";

// ── Nav config ────────────────────────────────────────────────────────────────

const TOP_NAV = [
  { icon: Home,            label: "My Day",  path: "/home",      dot: false },
  { icon: LayoutDashboard, label: "Deals",   path: "/dashboard", dot: false },
  { icon: Mail,            label: "Email",   path: "/emails",    dot: true  },
  { icon: Sparkles,        label: "Ask AI",  path: "/ask",       dot: false },
  { icon: Trophy,          label: "Win/Loss", path: "/winloss",  dot: false },
] as const;

// ── Nav Item ─────────────────────────────────────────────────────────────────

function NavItem({
  icon: Icon,
  label,
  active,
  dot,
  onClick,
}: {
  icon: React.ElementType;
  label: string;
  active?: boolean;
  dot?: boolean;
  onClick: () => void;
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          onClick={onClick}
          aria-label={label}
          className={cn(
            "relative flex h-10 w-10 items-center justify-center rounded-lg transition-colors duration-150",
            active
              ? "bg-primary/15 text-primary"
              : "text-muted-foreground hover:bg-secondary/70 hover:text-foreground"
          )}
        >
          {/* Active left-edge indicator */}
          {active && (
            <span className="absolute -left-2 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-full bg-primary" />
          )}
          <Icon className="h-5 w-5" />
          {/* Notification dot */}
          {dot && !active && (
            <span className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-health-red ring-2 ring-background" />
          )}
        </button>
      </TooltipTrigger>
      <TooltipContent side="right" className="text-xs font-medium">
        {label}
      </TooltipContent>
    </Tooltip>
  );
}

// ── Sidebar ───────────────────────────────────────────────────────────────────

export default function Sidebar() {
  const location = useLocation();
  const navigate = useNavigate();
  const { logout } = useSession();

  const isActive = (path: string) =>
    location.pathname === path ||
    (path === "/dashboard" && location.pathname === "/deals");

  return (
    <aside className="flex h-screen w-[60px] shrink-0 flex-col items-center border-r border-border/40 bg-background py-3">

      {/* Logo */}
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            onClick={() => navigate("/home")}
            className="mb-4 flex h-10 w-10 items-center justify-center rounded-xl bg-primary/15 transition-colors hover:bg-primary/25"
            aria-label="DealIQ Home"
          >
            <BarChart3 className="h-5 w-5 text-primary" />
          </button>
        </TooltipTrigger>
        <TooltipContent side="right" className="text-xs font-medium">
          DealIQ
        </TooltipContent>
      </Tooltip>

      {/* Divider */}
      <div className="mb-3 h-px w-8 bg-border/50" />

      {/* Top nav */}
      <nav className="flex flex-1 flex-col items-center gap-1.5">
        {TOP_NAV.map((item) => (
          <NavItem
            key={item.path}
            icon={item.icon}
            label={item.label}
            dot={item.dot}
            active={isActive(item.path)}
            onClick={() => navigate(item.path)}
          />
        ))}
      </nav>

      {/* Bottom nav */}
      <div className="flex flex-col items-center gap-1.5">
        <NavItem
          icon={Settings}
          label="Settings"
          active={location.pathname === "/settings"}
          onClick={() => navigate("/settings")}
        />
        <NavItem
          icon={LogOut}
          label="Log out"
          onClick={logout}
        />
      </div>
    </aside>
  );
}
