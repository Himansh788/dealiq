const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

// Abort any fetch that takes longer than this — prevents eternal spinners
const TIMEOUT_MS = 15_000;

// ── Per-request timeout wrapper ───────────────────────────────────────────────
//
// Creates a fresh AbortController (timeout controller) for EVERY request.
// No shared/global controller exists — each call is fully independent.
//
// If the caller also passes an AbortSignal (e.g. from a component useEffect
// cleanup), we wire it so EITHER signal firing cancels the request:
//   - timeout fires after 15s
//   - caller fires on component unmount
// Whichever comes first wins.  The timeout is always cleared on settle.

function fetchWithTimeout(
  input: RequestInfo,
  init?: RequestInit & { signal?: AbortSignal },
): Promise<Response> {
  const timeoutController = new AbortController();
  const timeoutId = setTimeout(() => timeoutController.abort(), TIMEOUT_MS);

  const callerSignal = init?.signal;
  if (callerSignal) {
    if (callerSignal.aborted) {
      clearTimeout(timeoutId);
      timeoutController.abort();
    } else {
      callerSignal.addEventListener("abort", () => {
        clearTimeout(timeoutId);
        timeoutController.abort();
      }, { once: true });
    }
  }

  // Spread init but override signal with our timeout controller's signal.
  // The caller signal is handled above via event listener — NOT by spreading it
  // into fetch(), which would ignore timeoutController entirely.
  return fetch(input, { ...init, signal: timeoutController.signal }).finally(() =>
    clearTimeout(timeoutId)
  );
}

// ── Response handler ──────────────────────────────────────────────────────────

async function handleResponse(res: Response) {
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(text || `HTTP ${res.status}`);
  }
  return res.json();
}

// ── In-flight deduplication ───────────────────────────────────────────────────
//
// Prevents the same GET URL from being fetched twice simultaneously.
// Each entry in the Map is a single in-flight Promise shared across callers.
// Entry is deleted once the request settles (success or error).
//
// IMPORTANT: Only requests WITHOUT a caller signal are deduplicated.
// Requests with a caller signal represent independent component lifecycles
// and must each get their own fetch so component cleanup can cancel only
// their own request without affecting other waiters.

const _inflight = new Map<string, Promise<any>>();

function fetchDedup(url: string, init?: RequestInit): Promise<any> {
  const existing = _inflight.get(url);
  if (existing) return existing;

  const p = fetchWithTimeout(url, init)
    .then(handleResponse)
    .finally(() => _inflight.delete(url));

  _inflight.set(url, p);
  return p;
}

// ── Auth headers ──────────────────────────────────────────────────────────────

function authHeaders(): HeadersInit {
  const raw = localStorage.getItem("dealiq_session");
  if (!raw) return { "Content-Type": "application/json" };
  return {
    Authorization: `Bearer ${raw}`,
    "Content-Type": "application/json",
  };
}

// ── Error message mapping ─────────────────────────────────────────────────────
//
// Maps raw server/network errors to user-friendly strings.
// Raw stack traces and HTTP status codes are never shown to users.

export function friendlyError(err: unknown): string {
  if (err instanceof DOMException && err.name === "AbortError") return "";
  if (err instanceof Error) {
    const msg = err.message.toLowerCase();
    if (msg.includes("networkerror") || msg.includes("failed to fetch")) return "Network error — check your connection.";
    if (msg.includes("timeout"))       return "Request timed out. Please try again.";
    if (msg.includes("401") || msg.includes("unauthorized")) return "Your session has expired. Please log in again.";
    if (msg.includes("403") || msg.includes("forbidden"))    return "You don't have permission to access this.";
    if (msg.includes("404") || msg.includes("not found"))    return "Data not found.";
    if (msg.includes("500") || msg.includes("502") || msg.includes("503")) return "Server error — please try again shortly.";
    // Don't surface raw backend text; use a generic fallback instead
    if (err.message.length < 80) return err.message;
  }
  return "Something went wrong. Please try again.";
}

// ── API surface ───────────────────────────────────────────────────────────────

export const api = {
  getLoginUrl: () =>
    fetchWithTimeout(`${API_URL}/auth/login`).then(handleResponse),

  getCrmLoginUrl: (provider: "zoho" | "salesforce" | "hubspot") =>
    fetchWithTimeout(`${API_URL}/auth/${provider}/login`).then(handleResponse),

  getDemoSession: () =>
    fetchWithTimeout(`${API_URL}/auth/demo-session`).then(handleResponse),

  // ── Deals ─────────────────────────────────────────────────────────────────
  getMetrics: (signal?: AbortSignal) =>
    fetchWithTimeout(`${API_URL}/deals/metrics`, { headers: authHeaders(), signal }).then(handleResponse),

  getPipelineSummary: (signal?: AbortSignal) =>
    fetchWithTimeout(`${API_URL}/deals/pipeline-summary`, { headers: authHeaders(), signal }).then(handleResponse),

  /** Single call that returns metrics + AI summary together from the shared server cache. */
  getMetricsWithSummary: async (signal?: AbortSignal): Promise<{ metrics: any; summary: string }> => {
    const [metrics, summaryData] = await Promise.all([
      fetchWithTimeout(`${API_URL}/deals/metrics`, { headers: authHeaders(), signal }).then(handleResponse),
      fetchWithTimeout(`${API_URL}/deals/pipeline-summary`, { headers: authHeaders(), signal }).then(handleResponse),
    ]);
    return { metrics, summary: summaryData?.summary ?? "" };
  },

  getDeals: (signal?: AbortSignal) =>
    fetchWithTimeout(`${API_URL}/deals/?per_page=20&page=1`, { headers: authHeaders(), signal }).then(handleResponse),

  getDealsPage: (page: number, perPage: number = 15, search?: string, signal?: AbortSignal, filters?: { health_label?: string; owner?: string; stage?: string }) => {
    const url = new URL(`${API_URL}/deals/`);
    url.searchParams.set("page", String(page));
    url.searchParams.set("per_page", String(perPage));
    if (search) url.searchParams.set("search", search);
    if (filters?.health_label && filters.health_label !== "all") url.searchParams.set("health_label", filters.health_label);
    if (filters?.owner && filters.owner !== "all") url.searchParams.set("owner", filters.owner);
    if (filters?.stage && filters.stage !== "all") url.searchParams.set("stage", filters.stage);
    return fetchWithTimeout(url.toString(), { headers: authHeaders(), signal }).then(handleResponse);
  },

  getDealFilterOptions: (): Promise<{ owners: string[]; stages: string[] }> =>
    fetchWithTimeout(`${API_URL}/deals/filter-options`, { headers: authHeaders() }).then(handleResponse),

  // Fetches a capped first page of deals for deal-selector dropdowns.
  // Uses dedup so concurrent callers (e.g. EmailTimelinePage + AskDealIQPage
  // both mounted during a route transition) share the same in-flight request.
  getAllDeals: (): Promise<any[]> => {
    const url = `${API_URL}/deals/?page=1&per_page=50`;
    return fetchDedup(url, { headers: authHeaders() as Record<string, string> })
      .then((data: any) => data.deals ?? data ?? []);
  },

  getDealHealth: (id: string, signal?: AbortSignal) =>
    fetchWithTimeout(`${API_URL}/deals/${id}/health`, { headers: authHeaders(), signal }).then(handleResponse),

  updateDealField: (dealId: string, field: string, value: string | number | null) =>
    fetchWithTimeout(`${API_URL}/deals/${dealId}/update`, {
      method: "PUT",
      headers: { ...authHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify({ field, value }),
    }).then(handleResponse),

  // ── Battle Card ───────────────────────────────────────────────────────────
  generateBattleCard: (dealId: string, meetingContext?: string) =>
    fetchWithTimeout(`${API_URL}/battlecard/generate`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ deal_id: dealId, meeting_context: meetingContext ?? "" }),
    }).then(handleResponse),

  clearBattleCardCache: (dealId: string) =>
    fetchWithTimeout(`${API_URL}/battlecard/cache/${dealId}`, {
      method: "DELETE",
      headers: authHeaders(),
    }).then(handleResponse),

  // ── Analysis ──────────────────────────────────────────────────────────────
  getAck: (dealId: string) =>
    fetchWithTimeout(`${API_URL}/analysis/ack/${dealId}`, { headers: authHeaders() }).then(handleResponse),

  postDecision: (dealId: string, decision: string, notes?: string) =>
    fetchWithTimeout(`${API_URL}/analysis/ack/${dealId}/decide`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ deal_id: dealId, decision, notes: notes ?? null }),
    }).then(handleResponse),

  checkMismatch: (transcript: string, email_draft: string) =>
    fetchWithTimeout(`${API_URL}/analysis/mismatch`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ transcript, email_draft }),
    }).then(handleResponse),

  generateNBA: (dealId: string, repName: string) =>
    fetchWithTimeout(`${API_URL}/ai-rep/nba`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ deal_id: dealId, rep_name: repName }),
    }).then(handleResponse),

  approveActionPlan: (dealId: string, actionPlan: any, approved: boolean, feedback?: string) =>
    fetchWithTimeout(`${API_URL}/ai-rep/approve-action`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ deal_id: dealId, action_plan: actionPlan, approved, rep_feedback: feedback }),
    }).then(handleResponse),

  generateEmailDraft: (dealId: string, repName: string, actionContext?: string) =>
    fetchWithTimeout(`${API_URL}/ai-rep/draft-email`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({
        deal_id: dealId,
        rep_name: repName,
        email_objective: "Re-engage buyer and establish a clear next step",
        action_context: actionContext || "",
      }),
    }).then(handleResponse),

  approveEmail: (dealId: string, subject: string, body: string, repName: string, approved: boolean, edits?: string) =>
    fetchWithTimeout(`${API_URL}/ai-rep/approve-email`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ deal_id: dealId, subject, body, rep_name: repName, approved, edits }),
    }).then(handleResponse),

  handleObjection: (dealId: string, objection: string, repName: string) =>
    fetchWithTimeout(`${API_URL}/ai-rep/handle-objection`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ deal_id: dealId, objection, rep_name: repName }),
    }).then(handleResponse),

  // ── Timeline ──────────────────────────────────────────────────────────────
  // Pass signal from component useEffect so unmount cancels the in-flight
  // request cleanly.  Each call gets its own AbortController via fetchWithTimeout
  // — no shared controller, no cross-request cancellation.
  getDealTimeline: (dealId: string, signal?: AbortSignal) =>
    fetchWithTimeout(`${API_URL}/deals/${dealId}/timeline`, { headers: authHeaders(), signal }).then(handleResponse),

  // ── Live Email Coach ───────────────────────────────────────────────────────
  emailCoach: (emailDraft: string, dealId?: string, dealContext?: any) =>
    fetchWithTimeout(`${API_URL}/analysis/email-coach`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ email_draft: emailDraft, deal_id: dealId, deal_context: dealContext }),
    }).then(handleResponse),

  // ── Deal Autopsy ───────────────────────────────────────────────────────────
  getAutopsy: (dealId: string, killReason?: string) =>
    fetchWithTimeout(`${API_URL}/analysis/autopsy`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ deal_id: dealId, kill_reason: killReason }),
    }).then(handleResponse),

  // ── Pre-Call Intelligence Brief ────────────────────────────────────────────
  getCallBrief: (dealId: string, repName?: string) =>
    fetchWithTimeout(`${API_URL}/ai-rep/call-brief`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ deal_id: dealId, rep_name: repName || "the sales rep" }),
    }).then(handleResponse),

  // ── Alerts Digest ──────────────────────────────────────────────────────────
  getAlertsDigest: () =>
    fetchWithTimeout(`${API_URL}/alerts/digest`, { headers: authHeaders() }).then(handleResponse),

  // ── Forecast ──────────────────────────────────────────────────────────────
  getForecast: () =>
    fetchWithTimeout(`${API_URL}/forecast`, { headers: authHeaders() }).then(handleResponse),

  // ── Buying Signal Detector ─────────────────────────────────────────────────
  detectSignals: (transcript: string, researcherName?: string, companyContext?: string) =>
    fetchWithTimeout(`${API_URL}/signals/detect`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({
        transcript,
        researcher_name: researcherName || "the researcher",
        company_context: companyContext || "",
      }),
    }).then(handleResponse),

  getDemoSignals: () =>
    fetchWithTimeout(`${API_URL}/signals/demo`).then(handleResponse),

  // ── Smart Trackers ─────────────────────────────────────────────────────────
  listTrackers: () =>
    fetchWithTimeout(`${API_URL}/trackers/`, { headers: authHeaders() }).then(handleResponse),

  createTracker: (name: string, concept_description: string, severity: string) =>
    fetchWithTimeout(`${API_URL}/trackers/`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ name, concept_description, severity }),
    }).then(handleResponse),

  analyzeTranscript: (transcript: string, tracker_ids?: string[]) =>
    fetchWithTimeout(`${API_URL}/trackers/analyze`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ transcript, tracker_ids: tracker_ids ?? null }),
    }).then(handleResponse),

  getDemoTrackers: () =>
    fetchWithTimeout(`${API_URL}/trackers/analyze/demo`).then(handleResponse),

  // ── Coaching / Transcript Analysis ────────────────────────────────────────
  analyzeConversation: (transcript: string, rep_name?: string) =>
    fetchWithTimeout(`${API_URL}/coaching/analyze`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ transcript, rep_name: rep_name ?? null }),
    }).then(handleResponse),

  getDemoCoaching: () =>
    fetchWithTimeout(`${API_URL}/coaching/analyze/demo`).then(handleResponse),

  getCoachingBenchmarks: () =>
    fetchWithTimeout(`${API_URL}/coaching/benchmarks`).then(handleResponse),

  // ── Activity Intelligence ──────────────────────────────────────────────────
  getDealActivities: (dealId: string, signal?: AbortSignal) =>
    fetchWithTimeout(`${API_URL}/activities/${dealId}`, { headers: authHeaders(), signal }).then(handleResponse),

  getTeamActivitySummary: (signal?: AbortSignal) =>
    fetchWithTimeout(`${API_URL}/activities/team-summary`, { headers: authHeaders(), signal }).then(handleResponse),

  // ── Ask DealIQ ────────────────────────────────────────────────────────────
  getAskPresets: () =>
    fetchWithTimeout(`${API_URL}/ask/presets`, { headers: authHeaders() }).then(handleResponse),

  askDeal: (dealId: string, question: string) =>
    fetchWithTimeout(`${API_URL}/ask/deal`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ deal_id: dealId, question }),
    }).then(handleResponse),

  askMeddic: (dealId: string) =>
    fetchWithTimeout(`${API_URL}/ask/deal/meddic`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ deal_id: dealId }),
    }).then(handleResponse),

  askBrief: (dealId: string) =>
    fetchWithTimeout(`${API_URL}/ask/deal/brief`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ deal_id: dealId }),
    }).then(handleResponse),

  askFollowUpEmail: (
    dealId: string,
    options?: { tone_override?: string; additional_context?: string }
  ) =>
    fetchWithTimeout(`${API_URL}/ask/deal/follow-up-email`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ deal_id: dealId, ...options }),
    }).then(handleResponse),

  askPipeline: (question: string, filters?: Record<string, any>) =>
    fetchWithTimeout(`${API_URL}/ask/pipeline`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ question, filters: filters ?? null }),
    }).then(handleResponse),

  // ── Actions (Today's AI action queue) ─────────────────────────────────────
  getTodayActions: (signal?: AbortSignal) =>
    fetchWithTimeout(`${API_URL}/actions/today`, { headers: authHeaders(), signal }).then(handleResponse),

  executeAction: (id: string, payload: Record<string, any>) =>
    fetchWithTimeout(`${API_URL}/actions/${id}/execute`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify(payload),
    }).then(handleResponse),

  dismissAction: (id: string) =>
    fetchWithTimeout(`${API_URL}/actions/${id}/dismiss`, {
      method: "POST",
      headers: authHeaders(),
    }).then(handleResponse),

  snoozeAction: (id: string) =>
    fetchWithTimeout(`${API_URL}/actions/${id}/snooze`, {
      method: "POST",
      headers: authHeaders(),
    }).then(handleResponse),

  // ── Meeting ────────────────────────────────────────────────────────────────
  getMeetingPrep: (dealId: string) =>
    fetchWithTimeout(`${API_URL}/meeting/prep/${dealId}`, { headers: authHeaders() }).then(handleResponse),

  submitPostMeeting: (payload: {
    deal_id: string;
    sentiment: string;
    topics_confirmed?: string[];
    quick_notes?: string;
    duration_minutes?: number;
    attendees?: Record<string, any>[];
    calendar_event_id?: string;
  }) =>
    fetchWithTimeout(`${API_URL}/meeting/ended`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify(payload),
    }).then(handleResponse),

  getPendingCrmUpdates: (signal?: AbortSignal) =>
    fetchWithTimeout(`${API_URL}/meeting/pending-updates`, { headers: authHeaders(), signal }).then(handleResponse),

  approveCrmUpdate: (id: string) =>
    fetchWithTimeout(`${API_URL}/meeting/approve-update/${id}`, {
      method: "POST",
      headers: authHeaders(),
    }).then(handleResponse),

  rejectCrmUpdate: (id: string) =>
    fetchWithTimeout(`${API_URL}/meeting/reject-update/${id}`, {
      method: "POST",
      headers: authHeaders(),
    }).then(handleResponse),

  getMeetingHistory: (dealId: string) =>
    fetchWithTimeout(`${API_URL}/meeting/history/${dealId}`, { headers: authHeaders() }).then(handleResponse),

  // ── Email Intel ────────────────────────────────────────────────────────────
  getEmailThread: (dealId: string, signal?: AbortSignal) =>
    fetchWithTimeout(`${API_URL}/email-intel/threads/${dealId}`, { headers: authHeaders(), signal }).then(handleResponse),

  syncEmailsForDeal: (dealId: string, contactEmails: string[] = []) =>
    fetchWithTimeout(`${API_URL}/email-intel/sync`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ deal_id: dealId, contact_emails: contactEmails }),
    }).then(handleResponse),

  analyseEmailThread: (dealId: string) =>
    fetchWithTimeout(`${API_URL}/email-intel/analyse/${dealId}`, {
      method: "POST",
      headers: authHeaders(),
    }).then(handleResponse),

  // ── Debug / Diagnostics ───────────────────────────────────────────────────
  debugZohoTest: () =>
    fetchWithTimeout(`${API_URL}/deals/debug/zoho-test`, { headers: authHeaders() }).then(handleResponse),

  // ── Win/Loss Intelligence ──────────────────────────────────────────────────
  analyzeWinLoss: (dealId: string, outcome: "won" | "lost", notes?: string) =>
    fetchWithTimeout(`${API_URL}/winloss/analyze`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ deal_id: dealId, outcome, notes: notes ?? null }),
    }).then(handleResponse),

  getWinLossBoard: (signal?: AbortSignal) =>
    fetchWithTimeout(`${API_URL}/winloss/board`, { headers: authHeaders(), signal }).then(handleResponse),

  // ── Forecast Board ────────────────────────────────────────────────────────
  getForecastBoard: (signal?: AbortSignal) =>
    fetchWithTimeout(`${API_URL}/forecast/board`, { headers: authHeaders(), signal }).then(handleResponse),

  categorizeDeal: (dealId: string, category: string) =>
    fetchWithTimeout(`${API_URL}/forecast/categorize`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ deal_id: dealId, category }),
    }).then(handleResponse),

  submitForecast: (data: { commit_amount: number; best_case_amount: number; pipeline_amount: number; notes: string }) =>
    fetchWithTimeout(`${API_URL}/forecast/submit`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify(data),
    }).then(handleResponse),

  getForecastSubmissions: (signal?: AbortSignal) =>
    fetchWithTimeout(`${API_URL}/forecast/submissions`, { headers: authHeaders(), signal }).then(handleResponse),

  setForecastQuota: (quarterly_quota: number, period_label: string) =>
    fetchWithTimeout(`${API_URL}/forecast/quota`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ quarterly_quota, period_label }),
    }).then(handleResponse),

  // ── Warnings ───────────────────────────────────────────────────────────────
  getDealWarnings: (dealId: string, signal?: AbortSignal) =>
    fetchWithTimeout(`${API_URL}/warnings/${dealId}`, { headers: authHeaders(), signal }).then(handleResponse),

  batchDealWarnings: (dealIds: string[], signal?: AbortSignal) =>
    fetchWithTimeout(`${API_URL}/warnings/batch`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ deal_ids: dealIds }),
      signal,
    }).then(handleResponse),

  // ── Microsoft / Outlook Auth ───────────────────────────────────────────────
  getOutlookStatus: () =>
    fetchWithTimeout(`${API_URL}/ms-auth/status`, { headers: authHeaders() }).then(handleResponse),

  connectOutlook: () =>
    fetchWithTimeout(`${API_URL}/ms-auth/connect`, {
      method: "POST",
      headers: authHeaders(),
    }).then(handleResponse),

  disconnectOutlook: () =>
    fetchWithTimeout(`${API_URL}/ms-auth/disconnect`, {
      method: "DELETE",
      headers: authHeaders(),
    }).then(handleResponse),
};
