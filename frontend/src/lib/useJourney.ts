import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api";
import type { Acknowledgement, Incident, IncidentDetail, Job, ReportDetail } from "./types";
import { usePoll } from "./usePoll";

export const STEP_COUNT = 7;
const TERMINAL = ["processed", "needs_transcript", "failed"];

export interface JourneyData {
  report: ReportDetail | null;
  incident: IncidentDetail | null;
  incidents: Incident[];
  ack: Acknowledgement | null;
  ackFailed: boolean;
  jobs: Record<string, Job>;
  /** ready[i] === the real data for scene i exists (the UI may still pace the reveal). */
  ready: boolean[];
  blocked: "needs_transcript" | "failed" | null;
  error: string | null;
  reload: () => void;
}

/** Follows one report through the real pipeline; nothing here is simulated. */
export function useJourney(reportId: string): JourneyData {
  const [done, setDone] = useState(false);
  const report = usePoll(() => api.report(reportId), done ? 0 : 700, [reportId, done]);
  const r = report.data;
  const status = r?.status ?? "";
  useEffect(() => {
    setDone(TERMINAL.includes(status) && !!r);
  }, [status, r]);

  const incidentId = r?.incident_id ?? null;
  const [incident, setIncident] = useState<IncidentDetail | null>(null);
  const [incidents, setIncidents] = useState<Incident[]>([]);
  useEffect(() => {
    setIncident(null);
  }, [reportId]);
  useEffect(() => {
    if (!incidentId) return;
    let alive = true;
    void api.incident(incidentId).then((d) => alive && setIncident(d)).catch(() => undefined);
    void api.incidents({ limit: 500 }).then((d) => alive && setIncidents(d.items)).catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [incidentId, status]);

  const [ack, setAck] = useState<Acknowledgement | null>(null);
  const [ackFailed, setAckFailed] = useState(false);
  const askedAck = useRef<string | null>(null);
  useEffect(() => {
    setAck(null);
    setAckFailed(false);
    askedAck.current = null;
  }, [reportId]);
  useEffect(() => {
    if (status !== "processed" || askedAck.current === reportId) return;
    askedAck.current = reportId;
    if (r?.acknowledgement?.audio_url) {
      // Already synthesised — no need to hit the API again
      setAck(r.acknowledgement);
      return;
    }
    // Pipeline creates text-only ack; always call acknowledge to trigger Timbre synthesis
    void api.acknowledge(reportId).then(setAck).catch(() => setAckFailed(true));
  }, [status, reportId, r?.acknowledgement]);

  const jobs = useMemo(() => {
    const m: Record<string, Job> = {};
    for (const j of r?.jobs ?? []) m[j.stage] = j;
    return m;
  }, [r?.jobs]);

  const ready = useMemo(() => {
    const processed = status === "processed";
    return [
      !!r,
      !!r?.transcript,
      !!r?.extraction_current,
      processed && !!incident,
      processed && !!r?.dedup_outcome && !!incident,
      processed && !!incident,
      processed && (!!ack || ackFailed),
    ];
  }, [r, status, incident, ack, ackFailed]);

  const blocked = status === "needs_transcript" ? "needs_transcript" : status === "failed" ? "failed" : null;
  return { report: r, incident, incidents, ack, ackFailed, jobs, ready, blocked, error: report.error, reload: () => void report.refresh() };
}

/** Reveals `text` character by character; resets when the text changes. */
export function useTypewriter(text: string, active: boolean, msPerChar = 22) {
  const [n, setN] = useState(0);
  useEffect(() => {
    setN(0);
  }, [text]);
  useEffect(() => {
    if (!active || n >= text.length) return;
    const t = window.setTimeout(() => setN((v) => Math.min(text.length, v + 1 + Math.floor(text.length / 300))), msPerChar);
    return () => window.clearTimeout(t);
  }, [active, n, text, msPerChar]);
  return { shown: text.slice(0, n), done: n >= text.length };
}
