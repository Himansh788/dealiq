import Sidebar from "./Sidebar";

interface Props {
  children: React.ReactNode;
}

/**
 * Root layout for all authenticated pages.
 * Renders the 60px icon sidebar on the left; page content fills the rest.
 * Login page renders WITHOUT this layout (see App.tsx).
 */
export default function AppLayout({ children }: Props) {
  return (
    <div className="flex h-screen overflow-hidden bg-background text-foreground">
      <Sidebar />
      <main className="flex-1 overflow-y-auto">
        {children}
      </main>
    </div>
  );
}
