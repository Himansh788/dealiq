const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

// Abort any fetch that takes longer than this — prevents eternal spinners
const TIMEOUT_MS = 15_000;

/**
 * Wraps fetch with a 15s timeout controller, combined with an optional
 * caller-supplied AbortSignal (e.g. from a component cleanup).
 *
 * Combining two signals: if EITHER fires — timeout OR component unmount —
 * the request is cancelled. Without this, the timeout controller's signal
 * is the only one wired, so component unmounts can't cancel in-flight requests,
 * causing the "signal is aborted without reason" leak in the UI.
 */
function fetchWithTimeout(
  input: RequestInfo,
  init?: RequestInit & { signal?: AbortSignal },
): Promise<Response> {
  const timeoutController = new AbortController();
  const timeoutId = setTimeout(() => timeoutController.abort(), TIMEOUT_MS);

  // If a caller signal was provided, abort our timeout controller when it fires too
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

  return fetch(input, { ...init, signal: timeoutController.signal }).finally(() =>
    clearTimeout(timeoutId)
  );
}

/**
 * In-flight deduplication for GET requests.
 * Prevents the same URL from being fetched twice simultaneously —
 * second caller gets the same Promise as the first.
 * Entry is removed once the request settles (success or error).
 */
const _inflight = new Map<string, Promise<any>>();

function fetchDedup(url: string, init?: RequestInit & { signal?: AbortSignal }): Promise<any> {
  // Don't dedup requests that have a caller-owned abort signal —
  // each such request is intentionally independent (different component lifecycle).
  if (init?.signal) {
    return fetchWithTimeout(url, init).then(handleResponse);
  }
  const existing = _inflight.get(url);
  if (existing) return existing;
  const p = fetchWithTimeout(url, init)
    .then(handleResponse)
    .finally(() => _inflight.delete(url));
  _inflight.set(url, p);
  return p;
}

function authHeaders(): HeadersInit {
  const raw = localStorage.getItem("dealiq_session");
  if (!raw) return { "Content-Type": "application/json" };
  return {
    Authorization: `Bearer ${raw}`,
    "Content-Type": "application/json",
  };
}

async function handleResponse(res: Response) {
  if (!res.ok) {
    const text = await res.text().catch(() => "Request failed");
    throw new Error(text || `HTTP ${res.status}`);
  }
  return res.json();
}

export const api = {
  getLoginUrl: () =>
    fetchWithTimeout(`${API_URL}/auth/login`).then(handleResponse),

  getDemoSession: () =>
    fetchWithTimeout(`${API_URL}/auth/demo-session`).then(handleResponse),

  // ── Deals ─────────────────────────────────────────────────────────────────
  getMetrics: () =>
    fetchWithTimeout(`${API_URL}/deals/metrics`, { headers: authHeaders() }).then(handleResponse),

  getDeals: () =>
    fetchWithTimeout(`${API_URL}/deals/?per_page=20&page=1`, { headers: authHeaders() }).then(handleResponse),

  getDealsPage: (page: number, perPage: number = 20) =>
    fetchWithTimeout(`${API_URL}/deals/?page=${page}&per_page=${perPage}`, { headers: authHeaders() }).then(handleResponse),

  getAllDeals: async (): Promise<any[]> => {
    const res = await fetchWithTimeout(
      `${API_URL}/deals/?page=1&per_page=500`,
      { headers: authHeaders() }
    );
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    return data.deals ?? data ?? [];
  },

  getDealHealth: (id: string) =>
    fetchWithTimeout(`${API_URL}/deals/${id}/health`, { headers: authHeaders() }).then(handleResponse),

  // ── Analysis ──────────────────────────────────────────────────────────────
  getAck: (dealId: string) =>
    fetchWithTimeout(`${API_URL}/analysis/ack/${dealId}`, { headers: authHeaders() }).then(handleResponse),

  postDecision: (dealId: string, decision: string) =>
    fetchWithTimeout(`${API_URL}/analysis/ack/${dealId}/decide`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ deal_id: dealId, decision }),
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

  // ── Timeline ─────────────────────────────────────────────────────────────
  // signal: pass the AbortController.signal from the calling component so that
  // component unmounts cancel the in-flight request cleanly, preventing
  // "signal is aborted without reason" errors leaking to the UI.
  // fetchDedup prevents duplicate simultaneous fetches for the same dealId.
  getDealTimeline: (dealId: string, signal?: AbortSignal) => {
    const url = `${API_URL}/deals/${dealId}/timeline`;
    if (signal) {
      // Component-owned signal → bypass dedup (each mount lifecycle is independent)
      return fetchWithTimeout(url, { headers: authHeaders(), signal }).then(handleResponse);
    }
    return fetchDedup(url, { headers: authHeaders() });
  },

  // ── Live Email Coach ──────────────────────────────────────────────────────
  emailCoach: (emailDraft: string, dealId?: string, dealContext?: any) =>
    fetchWithTimeout(`${API_URL}/analysis/email-coach`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ email_draft: emailDraft, deal_id: dealId, deal_context: dealContext }),
    }).then(handleResponse),

  // ── Deal Autopsy ──────────────────────────────────────────────────────────
  getAutopsy: (dealId: string, killReason?: string) =>
    fetchWithTimeout(`${API_URL}/analysis/autopsy`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ deal_id: dealId, kill_reason: killReason }),
    }).then(handleResponse),

  // ── Pre-Call Intelligence Brief ───────────────────────────────────────────
  getCallBrief: (dealId: string, repName?: string) =>
    fetchWithTimeout(`${API_URL}/ai-rep/call-brief`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ deal_id: dealId, rep_name: repName || "the sales rep" }),
    }).then(handleResponse),

  // ── Alerts Digest ─────────────────────────────────────────────────────────
  getAlertsDigest: () =>
    fetchWithTimeout(`${API_URL}/alerts/digest`, { headers: authHeaders() }).then(handleResponse),

  // ── Forecast ─────────────────────────────────────────────────────────────
  getForecast: () =>
    fetchWithTimeout(`${API_URL}/forecast`, { headers: authHeaders() }).then(handleResponse),

  // ── Buying Signal Detector ────────────────────────────────────────────────
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

  // ── Smart Trackers ────────────────────────────────────────────────────────
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

  // ── Coaching / Transcript Analysis ───────────────────────────────────────
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

  // ── Activity Intelligence ─────────────────────────────────────────────────
  getDealActivities: (dealId: string) =>
    fetchWithTimeout(`${API_URL}/activities/${dealId}`, { headers: authHeaders() }).then(handleResponse),

  getTeamActivitySummary: () =>
    fetchWithTimeout(`${API_URL}/activities/team-summary`, { headers: authHeaders() }).then(handleResponse),

  // ── Ask DealIQ ───────────────────────────────────────────────────────────────
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

  // ── Actions (Today's AI action queue) ────────────────────────────────────
  getTodayActions: () =>
    fetchWithTimeout(`${API_URL}/actions/today`, { headers: authHeaders() }).then(handleResponse),

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

  // ── Meeting ───────────────────────────────────────────────────────────────
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

  getPendingCrmUpdates: () =>
    fetchWithTimeout(`${API_URL}/meeting/pending-updates`, { headers: authHeaders() }).then(handleResponse),

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

  // ── Email Intel ───────────────────────────────────────────────────────────
  getEmailThread: (dealId: string) =>
    fetchWithTimeout(`${API_URL}/email-intel/threads/${dealId}`, { headers: authHeaders() }).then(handleResponse),

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

  // ── Microsoft / Outlook Auth ──────────────────────────────────────────────
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