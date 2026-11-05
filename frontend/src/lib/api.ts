import type {
  EvaluationResult,
  Fixture,
  Gazetteer,
  Incident,
  IncidentDetail,
  LiveCallSummary,
  Paged,
  ProviderStatus,
  ReportDetail,
  ReportSummary,
  RuntimeConfig,
  Stats,
  Suggestion,
  SuggestionItem,
  VoiceAlertOptions,
  Acknowledgement,
} from "./types";

export const UNAUTHORIZED_EVENT = "aa:unauthorized";

export interface Session {
  authenticated: boolean;
  username: string | null;
  login_configured: boolean;
}

export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
  }
}

const API_BASE = import.meta.env.VITE_API_TARGET || "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    const url = API_BASE ? `${API_BASE}${path}` : path;
    res = await fetch(url, init);
  } catch {
    throw new ApiError("Backend unreachable — is the API server running on port 8000?", 0);
  }
  if (!res.ok) {
    // /api/auth answers for itself: a wrong password must show an error, not end a session.
    if (res.status === 401 && !path.startsWith("/api/auth/")) window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(detail, res.status);
  }
  return res.json() as Promise<T>;
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export function qs(params: Record<string, string | number | boolean | undefined | null>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : "";
}

export const api = {
  session: () => request<Session>("/api/auth/me"),
  liveCalls: () => request<{ items: LiveCallSummary[] }>("/api/live/calls"),
  alertOptions: (id: string) => request<VoiceAlertOptions>(`/api/incidents/${encodeURIComponent(id)}/alerts`),
  alertPreviewUrl: (id: string, template: string, language: string) =>
    `/api/incidents/${encodeURIComponent(id)}/alerts/preview${qs({ template, language })}`,
  sendAlert: (id: string, template: string, reviewer: string) =>
    request<{ sent: number; failed: number; voice: number; languages: string[] }>(
      `/api/incidents/${encodeURIComponent(id)}/alerts/send`,
      json({ template, reviewer }),
    ),
  login: (username: string, password: string) => request<Session>("/api/auth/login", json({ username, password })),
  logout: () => request<Session>("/api/auth/logout", { method: "POST" }),
  health: () => request<{ status: string; worker_queue: number; providers: ProviderStatus }>("/api/health"),
  stats: () => request<Stats>("/api/dashboard/stats"),
  reports: (params: Record<string, string | number | boolean | undefined> = {}) =>
    request<Paged<ReportSummary>>(`/api/reports${qs(params)}`),
  report: (id: string) => request<ReportDetail>(`/api/reports/${encodeURIComponent(id)}`),
  createReport: (body: { transcript: string; language_hint?: string | null; process: boolean }) =>
    request<ReportDetail>("/api/reports", json({ ...body, source: "manual_text" })),
  uploadReport: (file: Blob, filename: string, language: string | null, source: "upload" | "recording") => {
    const fd = new FormData();
    fd.append("file", file, filename);
    if (language) fd.append("language_hint", language);
    fd.append("source", source);
    return request<ReportDetail>("/api/reports/upload", { method: "POST", body: fd });
  },
  processReport: (id: string) => request<{ id: string; status: string }>(`/api/reports/${id}/process`, { method: "POST" }),
  submitTranscript: (id: string, text: string, reviewer: string, language_hint?: string | null) =>
    request<ReportDetail>(`/api/reports/${id}/transcript`, json({ text, reviewer, language_hint: language_hint || null, process: true })),
  acknowledge: (id: string) => request<Acknowledgement>(`/api/reports/${id}/acknowledgement?synthesize=true`, { method: "POST" }),
  incidents: (params: Record<string, string | number | undefined> = {}) =>
    request<Paged<Incident>>(`/api/incidents${qs(params)}`),
  incident: (id: string) => request<IncidentDetail>(`/api/incidents/${encodeURIComponent(id)}`),
  review: (id: string, body: Record<string, unknown>) => request<IncidentDetail>(`/api/incidents/${id}/review`, json(body)),
  merge: (id: string, sources: string[], reviewer: string, notes?: string) =>
    request<IncidentDetail>(`/api/incidents/${id}/merge`, json({ source_incident_ids: sources, reviewer, notes: notes || null })),
  split: (id: string, reportIds: string[], reviewer: string, notes?: string) =>
    request<{ original: IncidentDetail; new_incident: IncidentDetail }>(
      `/api/incidents/${id}/split`,
      json({ report_ids: reportIds, reviewer, notes: notes || null }),
    ),
  suggestions: (status = "pending") => request<{ total: number; pending: number; items: SuggestionItem[] }>(`/api/suggestions${qs({ status })}`),
  decideSuggestion: (id: number, confirm: boolean, reviewer: string, notes?: string) =>
    request<Suggestion>(`/api/suggestions/${id}/${confirm ? "confirm" : "reject"}`, json({ reviewer, notes: notes || null })),
  gazetteer: () => request<Gazetteer>("/api/gazetteer"),
  settings: () => request<{ config: RuntimeConfig; providers: ProviderStatus; environment: Record<string, unknown> }>("/api/settings"),
  saveSettings: (body: Partial<RuntimeConfig>) =>
    request<{ config: RuntimeConfig; providers: ProviderStatus; note: string }>("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  evaluation: () => request<EvaluationResult>("/api/evaluation"),
  runEvaluation: (includeStt: boolean) => request<EvaluationResult>(`/api/evaluation/run${qs({ include_stt: includeStt })}`, { method: "POST" }),
  fixtures: () => request<{ label: string; notice: string; items: Fixture[] }>("/api/demo/fixtures"),
  seed: (mode: "all" | "remaining") => request<{ created: number; skipped_existing: number; stats: Stats }>("/api/demo/seed", json({ mode })),
  inject: (fixture_id: string, use_audio = true) => request<ReportDetail>("/api/demo/inject", json({ fixture_id, use_audio })),
  reset: () => request<{ deleted: Record<string, number>; stats: Stats }>("/api/demo/reset", json({ reseed: false })),
};
