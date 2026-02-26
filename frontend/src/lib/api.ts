const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

// Abort any fetch that takes longer than this — prevents eternal spinners
const TIMEOUT_MS = 15_000;

function fetchWithTimeout(input: RequestInfo, init?: RequestInit): Promise<Response> {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), TIMEOUT_MS);
  return fetch(input, { ...init, signal: controller.signal }).finally(() =>
    clearTimeout(id)
  );
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
  getDealTimeline: (dealId: string) =>
    fetchWithTimeout(`${API_URL}/deals/${dealId}/timeline`, { headers: authHeaders() }).then(handleResponse),

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
};