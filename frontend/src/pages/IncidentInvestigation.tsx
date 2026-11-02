import { AlertTriangle, ArrowLeft, GitMerge, MapPin, Pause, Play, Scissors, Sparkles, Volume2, Zap } from "lucide-react";
import { Suspense, lazy, useRef, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ConfidenceBadge, LocationBadge, ModeBadge, PriorityBadge, ReviewBadge } from "../components/badges";
import { ExtractionView } from "../components/ExtractionView";
import { IncidentMap } from "../components/IncidentMap";
import { IncidentQueue } from "../components/IncidentQueue";
import { PriorityExplain } from "../components/PriorityExplain";
import { ReviewForm } from "../components/ReviewForm";
import { MatchEvidenceTable, SuggestionCard } from "../components/SuggestionCard";
import { Badge, Button, Card, CardHeader, Empty, ErrorBanner, Input, KV, Spinner } from "../components/ui";
import { api } from "../lib/api";
import { getReviewer } from "../lib/reviewer";
import { clock, isMappable, label, langLabel, locationText, peopleText, sortIncidents } from "../lib/format";
import type { Acknowledgement, IncidentDetail, MatchEvidence } from "../lib/types";
import { usePoll } from "../lib/usePoll";

const SiteView3D = lazy(() => import("../components/SiteView3D"));

function AckPanel({ reportId, initial }: { reportId: string; initial: Acknowledgement | null }) {
  const el = useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = useState(false);
  const [ack, setAck] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function generate() {
    setBusy(true);
    setErr(null);
    try {
      setAck(await api.acknowledge(reportId));
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  if (!ack) {
    return (
      <div className="flex flex-wrap items-center gap-2 rounded-xl border border-white/[0.06] bg-surface-2 px-3 py-2.5">
        <Volume2 className="h-4 w-4 shrink-0 text-ink-3" aria-hidden />
        <span className="flex-1 text-xs text-ink-3">No automated reply generated yet</span>
        {err && <span className="w-full text-2xs text-[#f3b0b0]">{err}</span>}
        <Button size="sm" busy={busy} onClick={() => void generate()}>
          <Sparkles className="h-3.5 w-3.5" /> Generate voice reply
        </Button>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-accent/20 bg-accent/[0.04] p-3 text-sm">
      <div className="mb-2 flex items-center gap-2 text-2xs font-semibold uppercase tracking-wider text-accent-glow">
        <Sparkles className="h-3.5 w-3.5" aria-hidden /> {ack.ai_generated_label}
      </div>
      <p className="text-ink-2 leading-relaxed">{ack.text}</p>
      {ack.audio_url ? (
        <div className="mt-2 flex items-center gap-2">
          <audio ref={el} src={ack.audio_url} onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} onEnded={() => setPlaying(false)} />
          <Button size="sm" onClick={() => (playing ? el.current?.pause() : void el.current?.play())}>
            {playing ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
            {playing ? "Pause" : "Play voice reply"}
          </Button>
          <span className="text-2xs text-ink-3">Timbre TTS · {ack.language}</span>
        </div>
      ) : (
        <p className="mt-1.5 flex items-center gap-1.5 text-2xs text-ink-3">
          <Volume2 className="h-3 w-3" aria-hidden /> Text only — voice synthesis needs a Gnani API key
        </p>
      )}
    </div>
  );
}

export function IncidentInvestigation() {
  const { id } = useParams();
  if (!id) return <IncidentIndex />;
  return <IncidentDetailPage key={id} id={id} />;
}

function IncidentIndex() {
  const list = usePoll(() => api.incidents({ limit: 500 }), 3000);
  const items = useMemo(() => sortIncidents(list.data?.items ?? []), [list.data]);
  const navigate = useNavigate();
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold">Incident Investigation</h1>
        <p className="text-xs text-ink-3">Pick an incident to inspect its evidence, linked reports, confidence and audit history.</p>
      </div>
      {list.error && <ErrorBanner offline message={list.error} />}
      <Card>{list.loading && !list.data ? <Spinner /> : <IncidentQueue items={items} onSelect={(i) => navigate(`/incidents/${i}`)} emptyText="No incidents yet — submit a report to begin." />}</Card>
    </div>
  );
}

function IncidentDetailPage({ id }: { id: string }) {
  const inc = usePoll(() => api.incident(id), 4000, [id]);
  const gaz = usePoll(api.gazetteer, 0);
  const [splitSel, setSplitSel] = useState<string[]>([]);
  const [mergeIds, setMergeIds] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  if (inc.loading && !inc.data) return <Spinner />;
  if (inc.error && !inc.data) return <ErrorBanner message={inc.error} />;
  const i = inc.data as IncidentDetail;
  const reviewer = getReviewer();
  const pending = i.suggestions.filter((s) => s.status === "pending");
  const resolved = i.suggestions.filter((s) => s.status !== "pending");

  async function act(key: string, fn: () => Promise<unknown>) {
    setBusy(key);
    setError(null);
    try {
      await fn();
      await inc.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-4">
      <Link to="/incidents" className="inline-flex items-center gap-1 text-xs text-ink-3 hover:text-ink">
        <ArrowLeft className="h-3.5 w-3.5" /> All incidents
      </Link>

      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="font-mono text-xl font-semibold">{i.id}</h1>
            <PriorityBadge value={i.priority_label} score={i.priority_score} />
            <ReviewBadge value={i.review_status} />
            <LocationBadge value={i.location_status} />
            <ConfidenceBadge value={i.info_confidence?.overall} />
            {i.status !== "active" && <Badge className="border-[#5a2323] text-[#f3b0b0]">{i.status}{i.merged_into_id ? ` → ${i.merged_into_id}` : ""}</Badge>}
          </div>
          <p className="max-w-3xl text-sm text-ink-2">{i.summary}</p>
        </div>
        {i.merged_into_id && (
          <Button onClick={() => navigate(`/incidents/${i.merged_into_id}`)}>
            Go to {i.merged_into_id}
          </Button>
        )}
      </div>
      {error && <ErrorBanner message={error} />}

      <div className="grid gap-4 xl:grid-cols-[1fr_420px]">
        <div className="space-y-4">
          <Card>
            <CardHeader title="Situation" subtitle="Aggregated from all linked reports; dispatcher overrides are marked" />

            {/* Quick-scan stat strip */}
            <div className="grid grid-cols-2 gap-px border-b border-white/[0.06] bg-white/[0.04] sm:grid-cols-4">
              {[
                { icon: MapPin, label: "Where", value: locationText(i) || "Unknown", dim: !i.latitude },
                { icon: Zap, label: "Hazard", value: label(i.disaster_type) || "Unknown", dim: i.disaster_type === "unknown" },
                { icon: AlertTriangle, label: "Urgency", value: label(i.urgency) || "Unknown", dim: i.urgency === "unknown" },
                { icon: null, label: "People", value: peopleText(i) || "Unknown", dim: !i.people_count },
              ].map(({ icon: Icon, label: lbl, value, dim }) => (
                <div key={lbl} className="flex flex-col gap-0.5 bg-surface-1 px-4 py-3">
                  <div className="flex items-center gap-1.5 text-2xs font-medium uppercase tracking-wider text-ink-3">
                    {Icon && <Icon className="h-3 w-3" aria-hidden />}
                    {lbl}
                  </div>
                  <div className={dim ? "text-sm text-ink-3" : "text-sm font-medium text-ink"}>{value}</div>
                </div>
              ))}
            </div>

            {i.recommended_action && (
              <div className="mx-4 mt-4 flex items-start gap-2 rounded-xl border border-accent/20 bg-accent/[0.05] px-3 py-2.5 text-xs text-ink-2">
                <Sparkles className="mt-0.5 h-3.5 w-3.5 shrink-0 text-accent-glow" aria-hidden />
                <span><span className="font-medium text-ink">Suggested action: </span>{i.recommended_action}</span>
              </div>
            )}

            <div className="grid gap-4 p-4 lg:grid-cols-2">
              <dl>
                <KV k="Location">
                  {locationText(i)}
                  <div className="text-2xs text-ink-3">
                    {i.location_status === "human_verified"
                      ? `Verified by ${i.location?.verified_by ?? "a dispatcher"}`
                      : i.location_status === "caller_gps"
                        ? "GPS shared by the caller; confirm it is the incident site"
                      : i.location_status === "simulated_reference"
                        ? i.location?.place_id?.startsWith("C")
                          ? "City-centre coordinates — exact incident location within city unknown"
                          : "Reference location (unverified)"
                        : "Not grounded — not shown on the map"}
                  </div>
                  {i.location?.stated_text?.length ? <div className="text-2xs text-ink-3">Caller said: {i.location.stated_text.map((t) => `"${t}"`).join(", ")}</div> : null}
                </KV>
                <KV k="People">
                  {peopleText(i)}
                  <div className="text-2xs text-ink-3">{i.people_detail?.basis}</div>
                  {i.people_detail?.per_report.map((p) => (
                    <div key={p.report_id} className="text-2xs text-ink-3">
                      {p.report_id}: {p.count ?? "—"}
                      {p.approximate ? " (approx.)" : ""}
                      {p.families ? ` · ${p.families} families` : ""}
                    </div>
                  ))}
                </KV>
                <KV k="Vulnerable">
                  {Object.keys(i.vulnerable).length
                    ? Object.entries(i.vulnerable).map(([k, v]) => (
                        <div key={k}>
                          {label(k)}
                          {v.count ? ` (${v.count})` : ""} <span className="text-2xs text-ink-3">— {v.evidence.map((e) => `"${e}"`).join(", ")}</span>
                        </div>
                      ))
                    : "None mentioned (unknown)"}
                </KV>
              </dl>
              <dl>
                <KV k="Dangers">{i.dangers.map(label).join(", ") || "—"}</KV>
                <KV k="Needs">{i.needs.map(label).join(", ") || "—"}</KV>
                <KV k="Medical">{i.medical_emergency ? "Medical emergency described" : "Not mentioned"}</KV>
                <KV k="Hazard">{label(i.disaster_type) || "—"}</KV>
                <KV k="Caller urgency">{label(i.urgency) || "—"}</KV>
                <KV k="Languages">{i.languages.map(langLabel).join(", ") || "—"}</KV>
                <KV k="Info confidence">
                  {i.info_confidence?.overall} <div className="text-2xs text-ink-3">{i.info_confidence?.basis.join("; ")}</div>
                </KV>
              </dl>
            </div>
            {i.contradictions.length > 0 && (
              <div className="mx-4 mb-4 rounded-md border border-[#5a2323] bg-[#2a1414] px-3 py-2 text-xs text-[#f3b0b0]">
                <b>Contradictions between reports:</b> {i.contradictions.join(" · ")}
              </div>
            )}
          </Card>

          <Card>
            <CardHeader title={`Linked reports (${i.reports.length})`} subtitle="Original reports are never deleted; merges and splits only move links." />
            <div className="divide-y divide-line">
              {i.reports.map((r) => {
                const ev = r.link_evidence as MatchEvidence | null;
                return (
                  <details key={r.id} className="group px-4 py-3" open={i.reports.length <= 2}>
                    <summary className="flex cursor-pointer list-none flex-wrap items-center gap-1.5">
                      <input
                        type="checkbox"
                        aria-label={`Select ${r.id} for split`}
                        checked={splitSel.includes(r.id)}
                        onClick={(e) => e.stopPropagation()}
                        onChange={(e) => setSplitSel((cur) => (e.target.checked ? [...cur, r.id] : cur.filter((x) => x !== r.id)))}
                      />
                      <Link to={`/reports?id=${r.id}`} className="font-mono text-xs text-accent hover:underline">
                        {r.id}
                      </Link>
                      <span className="text-2xs text-ink-3">{clock(r.received_at)}</span>
                      <Badge>{langLabel(r.language)}</Badge>
                      <Badge title={r.link_score != null ? `match score ${r.link_score}` : undefined}>{label(r.link_outcome)}</Badge>
                      <ModeBadge mode={r.transcript_provider_mode} provider={r.transcript_provider} />
                      {r.priority_label && <PriorityBadge value={r.priority_label} />}
                      <span className="w-full truncate text-xs text-ink-2 group-open:hidden">"{r.transcript}"</span>
                    </summary>
                    <div className="mt-3 space-y-3">
                      {r.audio[0] && <audio controls preload="none" src={r.audio[0].url} className="h-8 w-full" />}
                      <blockquote className="rounded-md border border-line bg-surface-2 px-3 py-2 text-sm text-ink" lang={r.language ?? undefined}>
                        {r.transcript}
                      </blockquote>
                      {r.extraction_current && <ExtractionView ext={r.extraction_current} assessment={r.field_assessment} />}
                      {ev?.evidence && (
                        <div>
                          <div className="mb-1 text-2xs uppercase tracking-wider text-ink-3">Why this report was linked (score {ev.score?.toFixed(2)})</div>
                          <MatchEvidenceTable evidence={ev.evidence} />
                        </div>
                      )}
                      <AckPanel reportId={r.id} initial={r.acknowledgement ?? null} />
                    </div>
                  </details>
                );
              })}
              {!i.reports.length && <Empty title="No active reports (merged or split away)" />}
            </div>
            <div className="flex flex-wrap items-center gap-2 border-t border-line px-4 py-3">
              <Button
                size="sm"
                disabled={!splitSel.length || splitSel.length >= i.reports.length}
                busy={busy === "split"}
                onClick={() =>
                  act("split", async () => {
                    const res = await api.split(i.id, splitSel, reviewer);
                    setSplitSel([]);
                    navigate(`/incidents/${res.new_incident.id}`);
                  })
                }
              >
                <Scissors className="h-3.5 w-3.5" /> Split selected into new incident
              </Button>
              <span className="text-2xs text-ink-3">|</span>
              <Input className="h-7 w-56 text-xs" placeholder="INC-0005, INC-0007" value={mergeIds} onChange={(e) => setMergeIds(e.target.value)} aria-label="Incidents to merge" />
              <Button
                size="sm"
                disabled={!mergeIds.trim()}
                busy={busy === "merge"}
                onClick={() =>
                  act("merge", async () => {
                    await api.merge(i.id, mergeIds.split(/[\s,]+/).filter(Boolean).map((x) => x.toUpperCase()), reviewer);
                    setMergeIds("");
                  })
                }
              >
                <GitMerge className="h-3.5 w-3.5" /> Merge into this incident
              </Button>
            </div>
          </Card>

          {(pending.length > 0 || resolved.length > 0) && (
            <Card>
              <CardHeader title="Similar / possibly duplicate reports" subtitle="Deterministic matching evidence; a human decides." />
              <div className="space-y-3 p-4">
                {pending.map((s) => (
                  <SuggestionCard key={s.id} s={s} onDone={() => void inc.refresh()} />
                ))}
                {resolved.length > 0 && (
                  <details>
                    <summary className="cursor-pointer text-xs text-ink-3">{resolved.length} resolved suggestion(s)</summary>
                    <div className="mt-2 space-y-2">
                      {resolved.map((s) => (
                        <SuggestionCard key={s.id} s={s} onDone={() => void inc.refresh()} />
                      ))}
                    </div>
                  </details>
                )}
              </div>
            </Card>
          )}
        </div>

        <div className="space-y-4">
          {isMappable(i) && (
            <Card className="overflow-hidden">
              <Suspense fallback={<div className="h-[380px]" />}>
                <SiteView3D incident={i} className="h-[380px]" compact />
              </Suspense>
            </Card>
          )}
          {i.latitude != null && (
            <IncidentMap className="h-[260px]" compactLegend incidents={[i]} places={gaz.data?.places ?? []} selectedId={i.id} />
          )}
          <Card>
            <CardHeader title="Priority score breakdown" />
            <div className="p-4">{i.priority_breakdown && <PriorityExplain b={i.priority_breakdown} />}</div>
          </Card>
          <Card>
            <CardHeader title="Human verification" subtitle={i.review_reasons.length ? `${i.review_reasons.length} open flag(s)` : "No open flags"} />
            <div className="space-y-3 p-4">
              {i.review_reasons.length > 0 && (
                <ul className="space-y-1 text-xs">
                  {i.review_reasons.map((r, idx) => (
                    <li key={idx} className="flex gap-2">
                      <Badge className="border-[#5b4413] text-[#f6c75a]">{r.code}</Badge>
                      <span className="text-ink-2">{r.message}</span>
                    </li>
                  ))}
                </ul>
              )}
              {Object.keys(i.human_overrides).length > 0 && (
                <div className="rounded border border-line bg-surface-2 p-2 text-2xs text-ink-2">
                  <div className="mb-1 font-semibold text-ink">Dispatcher overrides in effect</div>
                  <pre className="whitespace-pre-wrap">{JSON.stringify(i.human_overrides, null, 1)}</pre>
                </div>
              )}
              {i.status === "active" ? (
                <ReviewForm incident={i} gazetteer={gaz.data} onDone={() => void inc.refresh()} />
              ) : (
                <p className="text-xs text-ink-3">This incident is {i.status}; review the target incident instead.</p>
              )}
            </div>
          </Card>
          <Card>
            <CardHeader title="Review & audit history" subtitle="Original values are preserved alongside every correction" />
            <ul className="max-h-[420px] space-y-2 overflow-y-auto p-4 text-2xs">
              {[...i.audit].reverse().map((a) => (
                <li key={a.id} className="border-l-2 border-line pl-2">
                  <div className="text-ink-2">
                    <span className="font-mono text-ink-3">{clock(a.created_at)}</span> <b className="text-ink">{a.actor}</b> {a.action.replace(/_/g, " ")}
                    {a.field && <> · {a.field}</>} <span className="text-ink-3">({a.entity_type} {a.entity_id})</span>
                  </div>
                  {a.old_value != null && <div className="truncate text-ink-3">old: {JSON.stringify(a.old_value)}</div>}
                  {a.new_value != null && <div className="truncate text-ink-3">new: {JSON.stringify(a.new_value)}</div>}
                  {a.note && <div className="text-ink-2">note: {a.note}</div>}
                </li>
              ))}
            </ul>
          </Card>
        </div>
      </div>
    </div>
  );
}
