import React, { createContext, useContext, useState, useCallback } from "react";

export interface Session {
  access_token: string;
  display_name?: string;
  email?: string;
}

interface SessionContextType {
  session: Session | null;
  setSession: (session: Session | null) => void;
  logout: () => void;
  isDemo: boolean;
}

const SessionContext = createContext<SessionContextType | undefined>(undefined);

const STORAGE_KEY = "dealiq_session";

function getStoredSession(): Session | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    // Try base64 decode first (our format)
    try {
      const parsed = JSON.parse(atob(raw));
      return {
        access_token: parsed.access_token,
        display_name: parsed.display_name,
        email: parsed.email,
      };
    } catch {
      // Fall back to plain JSON
      return JSON.parse(raw);
    }
  } catch {
    return null;
  }
}

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [session, setSessionState] = useState<Session | null>(getStoredSession);

  const setSession = useCallback((s: Session | null) => {
    setSessionState(s);
    if (s) {
      // Always store as base64 encoded JSON so API headers work correctly
      const raw = btoa(JSON.stringify({
        user_id: s.email || "user",
        display_name: s.display_name || "User",
        email: s.email || "",
        access_token: s.access_token,
        refresh_token: "",
      }));
      localStorage.setItem(STORAGE_KEY, raw);
    } else {
      localStorage.removeItem(STORAGE_KEY);
    }
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY);
    setSessionState(null);
  }, []);

  const isDemo = session?.access_token === "DEMO_MODE";

  return (
    <SessionContext.Provider value={{ session, setSession, logout, isDemo }}>
      {children}
    </SessionContext.Provider>
  );
}

export function useSession() {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession must be used within SessionProvider");
  return ctx;
}