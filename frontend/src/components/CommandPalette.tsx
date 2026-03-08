import { useState, useEffect, useRef } from "react";
import { Search, TrendingUp, ScanSearch, Radar, Bell, X } from "lucide-react";
import { cn } from "@/lib/utils";

interface NavDeal {
  id: string;
  deal_name: string;
  health_score: number;
  health_label: string;
  stage: string;
}

interface NavAction {
  label: string;
  path: string | null;
  key: string | null;
  icon: React.ElementType;
  desc: string;
}

interface Props {
  open: boolean;
  onClose: () => void;
  deals?: NavDeal[];
  onSelectDeal: (id: string) => void;
  onNavigate: (path: string) => void;
  onOpenSignal: () => void;
  onOpenDigest: () => void;
}

const NAV_ACTIONS: NavAction[] = [
  { label: "Smart Trackers", path: "/trackers", key: null,     icon: ScanSearch,  desc: "Concept-based call analysis" },
  { label: "AI Forecast",    path: "/forecast", key: null,     icon: TrendingUp,  desc: "Pipeline forecast & scenario planning" },
  { label: "Signal Radar",   path: null,        key: "signal", icon: Radar,       desc: "Detect buying signals from any transcript" },
  { label: "Daily Digest",   path: null,        key: "digest", icon: Bell,        desc: "Pipeline alerts & daily actions" },
];

function scoreColor(score: number) {
  if (score >= 75) return "text-health-green";
  if (score >= 50) return "text-health-yellow";
  return "text-health-red";
}

export default function CommandPalette({
  open, onClose, deals, onSelectDeal, onNavigate, onOpenSignal, onOpenDigest,
}: Props) {
  const [query, setQuery]       = useState("");
  const [selected, setSelected] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setQuery("");
      setSelected(0);
      setTimeout(() => inputRef.current?.focus(), 40);
    }
  }, [open]);

  const filteredDeals = (deals ?? [])
    .filter(d => d.deal_name.toLowerCase().includes(query.toLowerCase()))
    .slice(0, 5);

  const filteredActions = NAV_ACTIONS.filter(a =>
    a.label.toLowerCase().includes(query.toLowerCase())
  );

  const allItems: Array<
    | { type: "deal";   deal: NavDeal }
    | { type: "action"; action: NavAction }
  > = [
    ...filteredDeals.map(d  => ({ type: "deal"   as const, deal: d })),
    ...filteredActions.map(a => ({ type: "action" as const, action: a })),
  ];

  useEffect(() => { setSelected(0); }, [query]);

  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") { onClose(); return; }
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setSelected(s => Math.min(s + 1, allItems.length - 1));
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setSelected(s => Math.max(s - 1, 0));
      }
      if (e.key === "Enter") {
        e.preventDefault();
        const item = allItems[selected];
        if (!item) return;
        if (item.type === "deal") {
          onSelectDeal(item.deal.id);
        } else {
          if (item.action.path)                onNavigate(item.action.path);
          else if (item.action.key === "signal") onOpenSignal();
          else if (item.action.key === "digest") onOpenDigest();
        }
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, allItems, selected, onClose, onSelectDeal, onNavigate, onOpenSignal, onOpenDigest]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh]"
      onClick={onClose}
    >
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />

      {/* Palette */}
      <div
        className="relative w-full max-w-lg rounded-xl border border-border/50 bg-card shadow-2xl shadow-black/60 animate-slide-up"
        onClick={e => e.stopPropagation()}
      >
        {/* Input row */}
        <div className="flex items-center gap-3 border-b border-border/40 px-4 py-3">
          <Search className="h-4 w-4 shrink-0 text-muted-foreground/60" />
          <input
            ref={inputRef}
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="Search deals or navigate…"
            className="flex-1 bg-transparent text-sm text-foreground placeholder:text-muted-foreground/50 outline-none"
          />
          {query && (
            <button onClick={() => setQuery("")} className="text-muted-foreground/40 hover:text-muted-foreground">
              <X className="h-3.5 w-3.5" />
            </button>
          )}
          <button
            onClick={onClose}
            className="flex items-center justify-center rounded-md border border-border/50 bg-background/50 p-1 text-muted-foreground/50 transition-colors hover:border-border hover:bg-secondary hover:text-foreground"
            aria-label="Close search"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>

        {/* Results */}
        <div className="max-h-80 overflow-y-auto p-2">
          {filteredDeals.length > 0 && (
            <div className="mb-1">
              <p className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/40">
                Deals
              </p>
              {filteredDeals.map((deal, i) => (
                <button
                  key={deal.id}
                  onClick={() => onSelectDeal(deal.id)}
                  onMouseEnter={() => setSelected(i)}
                  className={cn(
                    "flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left transition-colors",
                    selected === i
                      ? "bg-primary/10 text-foreground"
                      : "text-foreground/80 hover:bg-secondary/60"
                  )}
                >
                  <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-secondary/60 text-xs font-bold">
                    {deal.deal_name.charAt(0)}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">{deal.deal_name}</p>
                    <p className="text-[11px] text-muted-foreground/60">{deal.stage}</p>
                  </div>
                  <span className={cn("shrink-0 text-sm font-bold tabular-nums", scoreColor(deal.health_score))}>
                    {deal.health_score}
                  </span>
                </button>
              ))}
            </div>
          )}

          {filteredActions.length > 0 && (
            <div>
              <p className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/40">
                Navigate
              </p>
              {filteredActions.map((action, i) => {
                const idx = filteredDeals.length + i;
                const Icon = action.icon;
                const handleClick = () => {
                  if (action.path)              onNavigate(action.path);
                  else if (action.key === "signal") onOpenSignal();
                  else if (action.key === "digest") onOpenDigest();
                };
                return (
                  <button
                    key={action.label}
                    onClick={handleClick}
                    onMouseEnter={() => setSelected(idx)}
                    className={cn(
                      "flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left transition-colors",
                      selected === idx
                        ? "bg-primary/10 text-foreground"
                        : "text-foreground/80 hover:bg-secondary/60"
                    )}
                  >
                    <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-primary/10">
                      <Icon className="h-3.5 w-3.5 text-primary" />
                    </div>
                    <div className="min-w-0">
                      <p className="text-sm font-medium">{action.label}</p>
                      <p className="text-[11px] text-muted-foreground/60">{action.desc}</p>
                    </div>
                  </button>
                );
              })}
            </div>
          )}

          {allItems.length === 0 && (
            <div className="py-8 text-center">
              <p className="text-sm text-muted-foreground/60">No results for "{query}"</p>
            </div>
          )}
        </div>

        {!query && !deals?.length && (
          <div className="border-t border-border/40 px-4 py-2.5">
            <p className="text-[11px] text-muted-foreground/40">
              Deal search is available on the Dashboard where data is loaded.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
