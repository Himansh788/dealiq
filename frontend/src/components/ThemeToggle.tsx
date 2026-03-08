import { Moon, Sun } from 'lucide-react';
import { useTheme } from '@/contexts/ThemeContext';
import { cn } from '@/lib/utils';

export function ThemeToggle({ compact = false }: { compact?: boolean }) {
  const { theme, toggleTheme } = useTheme();
  const isDark = theme === 'dark';

  return (
    <button
      onClick={toggleTheme}
      aria-label={`Switch to ${isDark ? 'light' : 'dark'} mode`}
      className={cn(
        "flex items-center gap-2 rounded-lg transition-colors focus-visible:outline-none",
        compact
          ? "h-10 w-10 justify-center hover:bg-secondary/70 text-muted-foreground hover:text-foreground"
          : "w-full px-3 py-2 hover:bg-secondary/70 text-muted-foreground hover:text-foreground"
      )}
    >
      {/* Toggle track */}
      <div className={cn(
        "relative shrink-0 h-5 w-9 rounded-full transition-colors duration-300",
        isDark ? "bg-primary/50" : "bg-muted border border-border"
      )}>
        <div className={cn(
          "absolute top-0.5 h-4 w-4 rounded-full shadow transition-all duration-300 flex items-center justify-center",
          isDark ? "left-[18px] bg-primary" : "left-0.5 bg-white border border-border/60"
        )}>
          {isDark
            ? <Moon className="h-2.5 w-2.5 text-white" />
            : <Sun className="h-2.5 w-2.5 text-amber-500" />}
        </div>
      </div>
      {!compact && (
        <span className="text-sm">{isDark ? 'Dark' : 'Light'}</span>
      )}
    </button>
  );
}
