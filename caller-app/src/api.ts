const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export interface ReportJob {
  stage: string;
  status: string;
}

export interface ReportStatus {
  id: string;
  status: string;
  transcript: string | null;
  disaster_type: string | null;
  location_text: string | null;
  people_count: number | null;
  priority_label: string | null;
  follow_up_needed: boolean;
  follow_up_questions: string[];
  acknowledgement: { text: string; audio_url: string | null } | null;
  error: string | null;
  jobs: ReportJob[];
}

export async function uploadAudio(file: File, languageHint: string): Promise<string> {
  const form = new FormData();
  form.append("file", file, file.name);
  form.append("language_hint", languageHint);
  form.append("process", "true");
  const r = await fetch(`${BASE}/api/reports/upload`, { method: "POST", body: form });
  if (!r.ok) throw new Error(`Upload failed: ${r.status}`);
  const d = await r.json();
  return d.id as string;
}

export async function submitText(transcript: string, languageHint: string): Promise<string> {
  const r = await fetch(`${BASE}/api/reports`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ transcript, language_hint: languageHint, process: true }),
  });
  if (!r.ok) throw new Error(`Submit failed: ${r.status}`);
  const d = await r.json();
  return d.id as string;
}

export async function pollReport(id: string): Promise<ReportStatus> {
  const r = await fetch(`${BASE}/api/reports/${id}`);
  if (!r.ok) throw new Error(`Poll failed: ${r.status}`);
  const d = await r.json();
  const ext = d.extraction_current ?? {};
  const loc = ext.location ?? {};
  const ppl = ext.people_affected ?? {};
  const ack = d.acknowledgement;
  // The API returns a root-relative path, which inside the APK would resolve
  // to the app's own localhost origin instead of the backend.
  const ackAudio = ack?.audio_url
    ? ack.audio_url.startsWith("http")
      ? ack.audio_url
      : `${BASE}${ack.audio_url}`
    : null;
  return {
    id: d.id,
    status: d.status,
    transcript: d.transcript ?? null,
    disaster_type: ext.disaster_type ?? null,
    location_text: loc.place_name ?? loc.landmark ?? null,
    people_count: ppl.count ?? null,
    priority_label: d.priority_label ?? null,
    follow_up_needed: d.follow_up_needed ?? false,
    follow_up_questions: d.follow_up_questions ?? [],
    acknowledgement: ack ? { text: ack.text, audio_url: ackAudio } : null,
    error: d.error ?? null,
    jobs: d.jobs ?? [],
  };
}

export async function triggerAck(id: string): Promise<void> {
  await fetch(`${BASE}/api/reports/${id}/acknowledgement`, { method: "POST" });
}
