import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { CheckCircle2, XCircle, Mail, User, Building2, Loader2, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";

interface ZohoContact {
  email: string;
  name: string;
  role: string;
  source: "zoho";
  status: "confirmed";
}

interface Persona {
  email: string;
  display_name: string;
  last_seen_at: string;
  email_count: number;
  source: "outlook_discovered";
  status: "pending" | "confirmed" | "rejected";
  confirmed_by?: string;
  confirmed_at?: string;
}

interface ContactsData {
  zoho_contacts: ZohoContact[];
  potential_personas: Persona[];
  confirmed_personas: Persona[];
}

interface Props {
  dealId: string | null;
}

function _formatDate(iso: string): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
  } catch {
    return "";
  }
}

export default function ContactsPanel({ dealId }: Props) {
  const [data, setData] = useState<ContactsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<Record<string, boolean>>({});

  useEffect(() => {
    if (!dealId) return;
    setLoading(true);
    setError(null);
    api.getDealContacts(dealId)
      .then(setData)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [dealId]);

  async function handleConfirm(email: string, status: "confirmed" | "rejected") {
    if (!dealId) return;
    setConfirming((prev) => ({ ...prev, [email]: true }));
    try {
      await api.confirmPersona(dealId, email, status);
      setData((prev) => {
        if (!prev) return prev;
        const updated = prev.potential_personas.map((p) =>
          p.email === email ? { ...p, status } : p
        );
        const stillPending = updated.filter((p) => p.status === "pending");
        const nowConfirmed = [
          ...prev.confirmed_personas,
          ...updated.filter((p) => p.email === email && p.status === "confirmed"),
        ];
        return {
          ...prev,
          potential_personas: stillPending,
          confirmed_personas: nowConfirmed,
        };
      });
    } catch {
      // silently fail — UI stays as is
    } finally {
      setConfirming((prev) => ({ ...prev, [email]: false }));
    }
  }

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-4 text-sm text-slate-500">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading contacts...
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="flex items-center gap-2 py-4 text-sm text-red-500">
        <AlertCircle className="h-4 w-4" />
        {error ?? "Failed to load contacts"}
      </div>
    );
  }

  const { zoho_contacts, potential_personas, confirmed_personas } = data;
  const hasAny = zoho_contacts.length + potential_personas.length + confirmed_personas.length > 0;

  return (
    <div className="space-y-4">

      {/* ── Zoho CRM Contacts ────────────────────────────────── */}
      {zoho_contacts.length > 0 && (
        <div>
          <p className="text-[10px] font-bold uppercase tracking-widest text-slate-500 mb-2">
            CRM Contacts ({zoho_contacts.length})
          </p>
          <div className="space-y-1.5">
            {zoho_contacts.map((c) => (
              <div
                key={c.email}
                className="flex items-center gap-3 rounded-md bg-emerald-50/60 dark:bg-emerald-900/10 border border-emerald-200 dark:border-emerald-800/40 px-3 py-2"
              >
                <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-emerald-100 dark:bg-emerald-900/30">
                  <User className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-slate-800 dark:text-slate-100 truncate">
                    {c.name || c.email}
                  </p>
                  <p className="text-xs text-slate-500 truncate">{c.email}</p>
                </div>
                {c.role && (
                  <span className="shrink-0 text-[10px] font-semibold bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-300 px-2 py-0.5 rounded-full">
                    {c.role}
                  </span>
                )}
                <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-500" />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Confirmed Outlook Personas ───────────────────────── */}
      {confirmed_personas.length > 0 && (
        <div>
          <p className="text-[10px] font-bold uppercase tracking-widest text-slate-500 mb-2">
            Confirmed Personas ({confirmed_personas.length})
          </p>
          <div className="space-y-1.5">
            {confirmed_personas.map((p) => (
              <div
                key={p.email}
                className="flex items-center gap-3 rounded-md bg-blue-50/60 dark:bg-blue-900/10 border border-blue-200 dark:border-blue-800/40 px-3 py-2"
              >
                <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-blue-100 dark:bg-blue-900/30">
                  <Mail className="h-3.5 w-3.5 text-blue-600 dark:text-blue-400" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-slate-800 dark:text-slate-100 truncate">
                    {p.display_name || p.email}
                  </p>
                  <p className="text-xs text-slate-500 truncate">{p.email}</p>
                </div>
                {p.email_count > 0 && (
                  <span className="shrink-0 text-[10px] text-slate-400">
                    {p.email_count} email{p.email_count !== 1 ? "s" : ""}
                  </span>
                )}
                <span className="shrink-0 text-[10px] font-semibold bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 px-2 py-0.5 rounded-full">
                  Outlook
                </span>
                <CheckCircle2 className="h-4 w-4 shrink-0 text-blue-500" />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Potential Personas (needs rep review) ────────────── */}
      {potential_personas.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-2">
            <p className="text-[10px] font-bold uppercase tracking-widest text-slate-500">
              Potential Personas ({potential_personas.length})
            </p>
            <span className="text-[10px] text-amber-600 dark:text-amber-400 font-medium">
              — found in Outlook, not in CRM
            </span>
          </div>
          <div className="space-y-2">
            {potential_personas.map((p) => (
              <div
                key={p.email}
                className="rounded-md border border-amber-200 dark:border-amber-800/50 bg-amber-50/40 dark:bg-amber-900/10 px-3 py-2.5"
              >
                <div className="flex items-center gap-3">
                  <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-amber-100 dark:bg-amber-900/30">
                    <Building2 className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-slate-800 dark:text-slate-100 truncate">
                      {p.display_name || p.email}
                    </p>
                    <p className="text-xs text-slate-500 truncate">{p.email}</p>
                  </div>
                  <div className="flex shrink-0 items-center gap-1.5">
                    {p.last_seen_at && (
                      <span className="text-[10px] text-slate-400 hidden sm:block">
                        Last: {_formatDate(p.last_seen_at)}
                      </span>
                    )}
                    <span className="text-[10px] text-slate-400">
                      {p.email_count}×
                    </span>
                  </div>
                </div>
                <div className="mt-2.5 flex items-center gap-2 pl-10">
                  <p className="text-[11px] text-slate-500 flex-1">
                    Is this person part of this deal?
                  </p>
                  <button
                    onClick={() => handleConfirm(p.email, "confirmed")}
                    disabled={confirming[p.email]}
                    className={cn(
                      "flex items-center gap-1 rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
                      "bg-emerald-100 hover:bg-emerald-200 text-emerald-700 dark:bg-emerald-900/30 dark:hover:bg-emerald-900/50 dark:text-emerald-300",
                      confirming[p.email] && "opacity-50 cursor-not-allowed"
                    )}
                  >
                    {confirming[p.email] ? (
                      <Loader2 className="h-3 w-3 animate-spin" />
                    ) : (
                      <CheckCircle2 className="h-3 w-3" />
                    )}
                    Yes, add
                  </button>
                  <button
                    onClick={() => handleConfirm(p.email, "rejected")}
                    disabled={confirming[p.email]}
                    className={cn(
                      "flex items-center gap-1 rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
                      "bg-slate-100 hover:bg-slate-200 text-slate-600 dark:bg-slate-800 dark:hover:bg-slate-700 dark:text-slate-400",
                      confirming[p.email] && "opacity-50 cursor-not-allowed"
                    )}
                  >
                    <XCircle className="h-3 w-3" />
                    No
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Empty state ───────────────────────────────────────── */}
      {!hasAny && (
        <div className="py-6 text-center">
          <User className="h-8 w-8 mx-auto text-slate-300 mb-2" />
          <p className="text-sm text-slate-500">No contacts found</p>
          <p className="text-xs text-slate-400 mt-1">Connect Outlook to discover personas from email threads</p>
        </div>
      )}
    </div>
  );
}
