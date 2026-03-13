import { useEffect, useState } from "react";
import { useSearchParams, useLocation } from "react-router-dom";
import { TrendingUp, Map } from "lucide-react";
import { cn } from "@/lib/utils";
import ForecastBoard from "./ForecastBoard";
import RegionalAnalytics from "./RegionalAnalytics";

type Tab = "forecast" | "analytics";

const TABS: { id: Tab; label: string; icon: React.ElementType }[] = [
  { id: "forecast", label: "Forecast Board", icon: TrendingUp },
  { id: "analytics", label: "Regional Analytics", icon: Map },
];

export default function ForecastAnalyticsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const location = useLocation();
  const [activeTab, setActiveTab] = useState<Tab>(() => {
    const t = searchParams.get("tab");
    if (t === "analytics" || t === "forecast") return t;
    // Default to analytics tab when accessed via /analytics route
    if (location.pathname === "/analytics") return "analytics";
    return "forecast";
  });

  useEffect(() => {
    setSearchParams({ tab: activeTab }, { replace: true });
  }, [activeTab, setSearchParams]);

  return (
    <div className="min-h-screen bg-background">
      {/* Tab bar */}
      <div className="border-b border-border bg-background sticky top-0 z-10">
        <div className="mx-auto max-w-7xl px-4 sm:px-6">
          <div className="flex items-center gap-1 pt-3">
            {TABS.map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                onClick={() => setActiveTab(id)}
                className={cn(
                  "flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors",
                  activeTab === id
                    ? "border-primary text-primary"
                    : "border-transparent text-muted-foreground hover:text-foreground hover:border-border"
                )}
              >
                <Icon className="w-4 h-4" />
                {label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Tab content */}
      {activeTab === "forecast" ? <ForecastBoard /> : <RegionalAnalytics />}
    </div>
  );
}
