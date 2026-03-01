import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";
import AskDealIQPanel from "@/components/deal/AskDealIQPanel";
import PipelineQABar from "@/components/PipelineQABar";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Sparkles, LayoutDashboard } from "lucide-react";

// ── Types ─────────────────────────────────────────────────────────────────────

interface Deal {
  id: string;
  deal_name: string;
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

  useEffect(() => {
    api.getAllDeals()
      .then((data) => setDeals(Array.isArray(data) ? data : []))
      .catch((err: Error) =>
        toast({ title: "Failed to load deals", description: err.message, variant: "destructive" })
      )
      .finally(() => setLoading(false));
  }, []);

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
            <div className="max-w-xs">
              {loading ? (
                <Skeleton className="h-8 w-48 rounded-lg" />
              ) : (
                <Select value={selectedDealId} onValueChange={setSelectedDealId}>
                  <SelectTrigger className="h-8 text-xs border-border/50 min-w-[200px]">
                    <SelectValue placeholder="Select a deal…" />
                  </SelectTrigger>
                  <SelectContent>
                    {deals.map((d) => (
                      <SelectItem key={d.id} value={d.id} className="text-xs">
                        <div className="flex items-center gap-2">
                          <span className={cn(
                            "h-1.5 w-1.5 rounded-full shrink-0",
                            HEALTH_DOT[d.health_label] ?? "bg-muted-foreground"
                          )} />
                          <span>{d.deal_name}</span>
                          <span className="text-muted-foreground/60">{d.stage}</span>
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </div>

            {selectedDeal && (
              <Badge
                variant="outline"
                className="ml-auto text-[10px] border-border/40 text-muted-foreground"
              >
                <LayoutDashboard className="mr-1 h-2.5 w-2.5" />
                {selectedDeal.stage}
              </Badge>
            )}
          </div>

          {selectedDeal ? (
            <AskDealIQPanel dealId={selectedDeal.id} dealName={selectedDeal.deal_name} />
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
