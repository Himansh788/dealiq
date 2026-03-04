import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { SessionProvider } from "@/contexts/SessionContext";
import AppLayout from "@/components/layout/AppLayout";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import NotFound from "./pages/NotFound";
import ForecastPage from "./pages/ForecastPage";
import TrackersPage from "./pages/TrackersPage";
import Home from "./pages/Home";
import AskDealIQPage from "./pages/AskDealIQPage";
import AlertsPage from "./pages/AlertsPage";
import TrendsPage from "./pages/TrendsPage";
import EmailTimelinePage from "./pages/EmailTimelinePage";
import SettingsPage from "./pages/SettingsPage";
import WinLossPage from "./pages/WinLossPage";

const queryClient = new QueryClient();

const App = () => (
  <QueryClientProvider client={queryClient}>
    <SessionProvider>
      <TooltipProvider>
        <Toaster />
        <Sonner />
        <BrowserRouter>
          <Routes>
            {/* Login — no sidebar */}
            <Route path="/" element={<Login />} />

            {/* Authenticated pages — all wrapped with AppLayout (60px sidebar) */}
            <Route path="/home"      element={<AppLayout><Home /></AppLayout>} />
            <Route path="/dashboard" element={<AppLayout><Dashboard /></AppLayout>} />
            <Route path="/forecast"  element={<AppLayout><ForecastPage /></AppLayout>} />
            <Route path="/trackers"  element={<AppLayout><TrackersPage /></AppLayout>} />
            <Route path="/ask"       element={<AppLayout><AskDealIQPage /></AppLayout>} />
            <Route path="/alerts"    element={<AppLayout><AlertsPage /></AppLayout>} />
            <Route path="/trends"    element={<AppLayout><TrendsPage /></AppLayout>} />
            <Route path="/emails"    element={<AppLayout><EmailTimelinePage /></AppLayout>} />
            <Route path="/settings"  element={<AppLayout><SettingsPage /></AppLayout>} />
            <Route path="/winloss"   element={<AppLayout><WinLossPage /></AppLayout>} />

            <Route path="*" element={<NotFound />} />
          </Routes>
        </BrowserRouter>
      </TooltipProvider>
    </SessionProvider>
  </QueryClientProvider>
);

export default App;
