const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

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
    fetch(`${API_URL}/auth/login`).then(handleResponse),

  getDemoSession: () =>
    fetch(`${API_URL}/auth/demo-session`).then(handleResponse),

  // ── Deals ─────────────────────────────────────────────────────────────────
  getMetrics: () =>
    fetch(`${API_URL}/deals/metrics`, { headers: authHeaders() }).then(handleResponse),

  getDeals: () =>
    fetch(`${API_URL}/deals/?per_page=20&page=1`, { headers: authHeaders() }).then(handleResponse),

  getDealsPage: (page: number, perPage: number = 20) =>
    fetch(`${API_URL}/deals/?page=${page}&per_page=${perPage}`, { headers: authHeaders() }).then(handleResponse),

  getAllDeals: async (): Promise<any[]> => {
    const res = await fetch(
      `${API_URL}/deals/?page=1&per_page=500`,
      { headers: authHeaders() }
    );
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    return data.deals ?? data ?? [];
  },

  getDealHealth: (id: string) =>
    fetch(`${API_URL}/deals/${id}/health`, { headers: authHeaders() }).then(handleResponse),

  // ── Analysis ──────────────────────────────────────────────────────────────
  getAck: (dealId: string) =>
    fetch(`${API_URL}/analysis/ack/${dealId}`, { headers: authHeaders() }).then(handleResponse),

  postDecision: (dealId: string, decision: string) =>
    fetch(`${API_URL}/analysis/ack/${dealId}/decide`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ deal_id: dealId, decision }),
    }).then(handleResponse),

  checkMismatch: (transcript: string, email_draft: string) =>
    fetch(`${API_URL}/analysis/mismatch`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ transcript, email_draft }),
    }).then(handleResponse),

  generateNBA: (dealId: string, repName: string) =>
    fetch(`${API_URL}/ai-rep/nba`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ deal_id: dealId, rep_name: repName }),
    }).then(handleResponse),

  approveActionPlan: (dealId: string, actionPlan: any, approved: boolean, feedback?: string) =>
    fetch(`${API_URL}/ai-rep/approve-action`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ deal_id: dealId, action_plan: actionPlan, approved, rep_feedback: feedback }),
    }).then(handleResponse),

  generateEmailDraft: (dealId: string, repName: string, actionContext?: string) =>
    fetch(`${API_URL}/ai-rep/draft-email`, {
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
    fetch(`${API_URL}/ai-rep/approve-email`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ deal_id: dealId, subject, body, rep_name: repName, approved, edits }),
    }).then(handleResponse),

  handleObjection: (dealId: string, objection: string, repName: string) =>
    fetch(`${API_URL}/ai-rep/handle-objection`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ deal_id: dealId, objection, rep_name: repName }),
    }).then(handleResponse),

  // ── Timeline ─────────────────────────────────────────────────────────────
  getDealTimeline: (dealId: string) =>
    fetch(`${API_URL}/deals/${dealId}/timeline`, { headers: authHeaders() }).then(handleResponse),

  // ── Live Email Coach ──────────────────────────────────────────────────────
  emailCoach: (emailDraft: string, dealId?: string, dealContext?: any) =>
    fetch(`${API_URL}/analysis/email-coach`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ email_draft: emailDraft, deal_id: dealId, deal_context: dealContext }),
    }).then(handleResponse),

  // ── Deal Autopsy ──────────────────────────────────────────────────────────
  getAutopsy: (dealId: string, killReason?: string) =>
    fetch(`${API_URL}/analysis/autopsy`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ deal_id: dealId, kill_reason: killReason }),
    }).then(handleResponse),

  // ── Pre-Call Intelligence Brief ───────────────────────────────────────────
  getCallBrief: (dealId: string, repName?: string) =>
    fetch(`${API_URL}/ai-rep/call-brief`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ deal_id: dealId, rep_name: repName || "the sales rep" }),
    }).then(handleResponse),

  // ── Alerts Digest ─────────────────────────────────────────────────────────
  getAlertsDigest: () =>
    fetch(`${API_URL}/alerts/digest`, { headers: authHeaders() }).then(handleResponse),

  // ── Forecast ─────────────────────────────────────────────────────────────
  getForecast: () =>
    fetch(`${API_URL}/forecast`, { headers: authHeaders() }).then(handleResponse),

  // ── Buying Signal Detector ────────────────────────────────────────────────
  detectSignals: (transcript: string, researcherName?: string, companyContext?: string) =>
    fetch(`${API_URL}/signals/detect`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({
        transcript,
        researcher_name: researcherName || "the researcher",
        company_context: companyContext || "",
      }),
    }).then(handleResponse),

  getDemoSignals: () =>
    fetch(`${API_URL}/signals/demo`).then(handleResponse),
};