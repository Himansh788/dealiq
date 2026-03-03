import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";
import AskDealIQPanel from "@/components/deal/AskDealIQPanel";
import PipelineQABar from "@/components/PipelineQABar";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { Sparkles, LayoutDashboard, ChevronsUpDown, Check } from "lucide-react";

// ── Types ─────────────────────────────────────────────────────────────────────

interface Deal {
  id: string;
  name: string;
  company: string;
  health_score: number;
  health_label: string;
  stage: string;
  amount: number;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const HEALTH_DOT: Record<string, string> = {
  healthy:  "bg-health-green",
  watching: "bg-health-yellow",
  at_risk:  "bg-health-orange",
  critical: "bg-health-red",
};

// ── Component ─────────────────────────────────────────────────────────────────

export default function AskDealIQPage() {
  const { toast } = useToast();
  const [deals,          setDeals]          = useState<Deal[]>([]);
  const [selectedDealId, setSelectedDealId] = useState<string>("");
  const [loading,        setLoading]        = useState(true);
  const [open,           setOpen]           = useState(false);

  useEffect(() => {
    api.getAllDeals()
      .then((data) => {
        const list = Array.isArray(data) ? data : [];
        const mapped: Deal[] = list.map((d: any) => ({
          id:           d.id,
          name:         d.name ?? d.deal_name ?? "Unnamed Deal",
          company:      d.account_name ?? d.company ?? "—",
          stage:        d.stage ?? "Unknown",
          amount:       d.amount ?? 0,
          health_score: d.health_score ?? 0,
          health_label: d.health_label ?? "critical",
        }));
        setDeals(mapped);
      })
      .catch((err: Error) =>
        toast({ title: "Failed to load deals", description: err.message, variant: "destructive" })
      )
      .finally(() => setLoading(false));
  }, [toast]);

  const selectedDeal = deals.find((d) => d.id === selectedDealId);

  return (
    <div className="min-h-screen bg-background">

      {/* ── Header ── */}
      <div className="border-b border-border/40 px-6 py-4">
        <div className="flex items-center gap-3 max-w-5xl mx-auto">
          <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-violet-500/20">
            <Sparkles className="h-4 w-4 text-violet-400" />
          </div>
          <div>
            <h1 className="text-sm font-semibold text-foreground">Ask DealIQ</h1>
            <p className="text-xs text-muted-foreground">Query your pipeline with natural language</p>
          </div>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-6 py-6 space-y-8">

        {/* ── Pipeline Q&A ── */}
        <section>
          <p className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground/60 mb-3">
            Pipeline Q&amp;A
          </p>
          <PipelineQABar />
        </section>

        {/* ── Deal Q&A ── */}
        <section>
          <div className="flex items-center gap-3 mb-3">
            <p className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground/60">
              Deal Q&amp;A
            </p>

            {/* Deal selector */}
            <div>
              {loading ? (
                <Skeleton className="h-8 w-56 rounded-lg" />
              ) : (
                <Popover open={open} onOpenChange={setOpen}>
                  <PopoverTrigger asChild>
                    <Button
                      variant="outline"
                      role="combobox"
                      aria-expanded={open}
                      className="h-8 min-w-[220px] max-w-xs justify-between text-xs border-border/50 font-normal"
                    >
                      {selectedDeal
                        ? <span className="flex items-center gap-2 truncate">
                            <span className={cn("h-1.5 w-1.5 rounded-full shrink-0", HEALTH_DOT[selectedDeal.health_label] ?? "bg-muted-foreground")} />
                            <span className="truncate">{selectedDeal.name}</span>
                          </span>
                        : <span className="text-muted-foreground">Select a deal…</span>
                      }
                      <ChevronsUpDown className="ml-2 h-3 w-3 shrink-0 opacity-50" />
                    </Button>
                  </PopoverTrigger>
                  <PopoverContent className="w-[320px] p-0" align="start">
                    <Command>
                      <CommandInput placeholder="Search deals…" className="h-8 text-xs" />
                      <CommandList>
                        <CommandEmpty className="py-4 text-center text-xs text-muted-foreground">
                          No deals found.
                        </CommandEmpty>
                        <CommandGroup>
                          {deals.map((d) => (
                            <CommandItem
                              key={d.id}
                              value={`${d.name} ${d.stage}`}
                              onSelect={() => {
                                setSelectedDealId(d.id === selectedDealId ? "" : d.id);
                                setOpen(false);
                              }}
                              className="text-xs"
                            >
                              <span className={cn("mr-2 h-1.5 w-1.5 rounded-full shrink-0", HEALTH_DOT[d.health_label] ?? "bg-muted-foreground")} />
                              <span className="flex-1 truncate">{d.name}</span>
                              {d.stage && <span className="ml-2 text-muted-foreground/60 shrink-0">{d.stage}</span>}
                              <Check className={cn("ml-2 h-3 w-3 shrink-0", d.id === selectedDealId ? "opacity-100" : "opacity-0")} />
                            </CommandItem>
                          ))}
                        </CommandGroup>
                      </CommandList>
                    </Command>
                  </PopoverContent>
                </Popover>
              )}
            </div>

            {selectedDeal && (
              <Badge
                variant="outline"
                className="ml-auto text-[10px] border-border/40 text-muted-foreground"
              >
                <LayoutDashboard className="mr-1 h-2.5 w-2.5" />
                {selectedDeal.name}
                {selectedDeal.stage && (
                  <span className="ml-1 opacity-60">— {selectedDeal.stage}</span>
                )}
              </Badge>
            )}
          </div>

          {selectedDeal ? (
            <AskDealIQPanel dealId={selectedDeal.id} dealName={selectedDeal.name} />
          ) : (
            <div className="flex flex-col items-center gap-2 rounded-xl border border-border/30 bg-card/40 px-6 py-12">
              <Sparkles className="h-7 w-7 text-violet-400/40" />
              <p className="text-sm text-muted-foreground">Select a deal to start asking questions</p>
              <p className="text-xs text-muted-foreground/60">
                Get MEDDIC analysis, deal briefs, and AI-generated follow-up emails
              </p>
            </div>
          )}
        </section>

      </div>
    </div>
  );
}
