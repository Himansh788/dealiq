import { Settings } from "lucide-react";

export default function SettingsPage() {
  return (
    <div className="min-h-screen bg-background">
      <div className="border-b border-border/40 px-6 py-4">
        <div className="flex items-center gap-3 max-w-5xl mx-auto">
          <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-secondary/60">
            <Settings className="h-4 w-4 text-muted-foreground" />
          </div>
          <div>
            <h1 className="text-sm font-semibold text-foreground">Settings</h1>
            <p className="text-xs text-muted-foreground">Account and integration settings</p>
          </div>
        </div>
      </div>

      <div className="flex flex-col items-center gap-3 max-w-5xl mx-auto px-6 py-16">
        <Settings className="h-10 w-10 text-muted-foreground/20" />
        <p className="text-sm font-medium text-muted-foreground">Settings coming soon</p>
        <p className="text-xs text-muted-foreground/60">
          CRM connection, API keys, and notification preferences
        </p>
      </div>
    </div>
  );
}
