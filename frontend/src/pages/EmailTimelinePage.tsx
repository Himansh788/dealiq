import { Mail } from "lucide-react";

export default function EmailTimelinePage() {
  return (
    <div className="min-h-screen bg-background">
      <div className="border-b border-border/40 px-6 py-4">
        <div className="flex items-center gap-3 max-w-5xl mx-auto">
          <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-primary/10">
            <Mail className="h-4 w-4 text-primary" />
          </div>
          <div>
            <h1 className="text-sm font-semibold text-foreground">Emails</h1>
            <p className="text-xs text-muted-foreground">Email timeline and outreach history</p>
          </div>
        </div>
      </div>

      <div className="flex flex-col items-center gap-3 max-w-5xl mx-auto px-6 py-16">
        <Mail className="h-10 w-10 text-muted-foreground/20" />
        <p className="text-sm font-medium text-muted-foreground">Email timeline coming soon</p>
        <p className="text-xs text-muted-foreground/60">
          Connect your inbox to see outreach history across deals
        </p>
      </div>
    </div>
  );
}
