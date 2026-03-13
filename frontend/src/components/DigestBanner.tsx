/**
 * DigestBanner — shown once per day when the app first loads.
 * Dismissed via localStorage key `dealiq_digest_banner_{YYYY-MM-DD}`.
 * Only renders on authenticated routes (caller must ensure that).
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Clock, ChevronRight, X, CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

const STORAGE_KEY_PREFIX = "dealiq_digest_banner_";

function todayKey() {
  return STORAGE_KEY_PREFIX + new Date().toISOString().slice(0, 10);
}

interface BannerDigest {
  tasks: Array<{ task_text: string; task_type: string }>;
  progress: { completed: number; total: number };
}

export default function DigestBanner() {
  const navigate = useNavigate();
  const [visible, setVisible] = useState(false);
  const [digest, setDigest] = useState<BannerDigest | null>(null);

  useEffect(() => {
    // Only show once per day
    if (localStorage.getItem(todayKey())) return;

    api.getTodayDigest()
      .then((data: BannerDigest) => {
        if (data?.tasks?.length > 0) {
          setDigest(data);
          setVisible(true);
        }
      })
      .catch(() => null); // silent fail — banner is optional
  }, []);

  function dismiss() {
    localStorage.setItem(todayKey(), "1");
    setVisible(false);
  }

  function openDigest() {
    dismiss();
    navigate("/digest");
  }

  if (!visible || !digest) return null;

  const pending = digest.tasks.filter(t => !(t as any).is_completed);
  const previewTasks = pending.slice(0, 3);

  return (
    <div className={cn(
      "fixed bottom-6 right-6 z-50 w-80 rounded-xl border border-primary/20 bg-card/95 shadow-xl backdrop-blur-sm",
      "animate-in slide-in-from-bottom-4 fade-in duration-300"
    )}>
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border/30 px-4 py-3">
        <div className="flex items-center gap-2">
          <Clock className="h-4 w-4 text-primary" />
          <span className="text-xs font-semibold text-primary uppercase tracking-wide">Daily Digest</span>
        </div>
        <button
          onClick={dismiss}
          className="flex h-6 w-6 items-center justify-center rounded-md text-muted-foreground hover:bg-secondary/60 hover:text-foreground transition-colors"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* Body */}
      <div className="px-4 py-3 space-y-2">
        <p className="text-sm font-medium text-foreground">
          {pending.length} task{pending.length !== 1 ? "s" : ""} waiting for you today
        </p>

        {previewTasks.map((t, i) => (
          <div key={i} className="flex items-start gap-2">
            <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground/30" />
            <p className="text-xs text-muted-foreground line-clamp-2">{t.task_text}</p>
          </div>
        ))}

        {pending.length > 3 && (
          <p className="text-[11px] text-muted-foreground/50 pl-5">
            +{pending.length - 3} more
          </p>
        )}
      </div>

      {/* Footer */}
      <div className="border-t border-border/30 px-4 py-3">
        <Button
          size="sm"
          className="w-full h-8 text-xs bg-primary hover:bg-primary/90"
          onClick={openDigest}
        >
          View full digest
          <ChevronRight className="ml-1 h-3.5 w-3.5" />
        </Button>
      </div>
    </div>
  );
}
