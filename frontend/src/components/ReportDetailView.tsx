import { Check, Loader2, RefreshCw, Volume2, X as XIcon } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { clock, label, langLabel } from "../lib/format";
import type { ReportDetail } from "../lib/types";
import { cn } from "../lib/cn";
import { ModeBadge, PriorityBadge, SyntheticTag } from "./badges";
import { ExtractionView, JobTimeline } from "./ExtractionView";
import { DedupPill, StatusPill } from "./LiveFeed";
import { PriorityExplain } from "./PriorityExplain";
import { Badge, Button, ErrorBanner, Input, Section, Select, Textarea } from "./ui";
import { WaveformPlayer } from "./WaveformPlayer";

const PIPELINE_STAGES = [
  { key: "transcription", label: "STT", desc: "Speech-to-text" },
  { key: "extraction", label: "Extract", desc: "Structured extraction" },
  { key: "priority", label: "Priority", desc: "Risk scoring" },
  { key: "deduplication", label: "Dedup", desc: "Deduplication" },
  { key: "acknowledgement", label: "Ack", desc: "Acknowledgement" },
] as const;

function PipelineVisualizer({ jobs }: { jobs: { stage: string; status: string; duration_ms?: number | null }[] }) {
  return (
    <div className="flex items-center gap-0 overflow-x-auto pb-1">
      {PIPELINE_STAGES.map((stage, idx) => {
        const job = jobs.find((j) => j.stage === stage.key || j.stage.startsWith(stage.key));
        const status = job?.status ?? "pending";
        const isLast = idx === PIPELINE_STAGES.length - 1;
        return (
          <div key={stage.key} className="flex items-center">
            <div className="flex flex-col items-center gap-1">
              <div
                className={cn(
                  "flex h-8 w-8 items-center justify-center rounded-full border-2 text-xs font-semibold transition-all",
                  status === "succeeded" && "border-status-good bg-status-good/15 text-status-good",
                  status === "failed" && "border-status-critical bg-status-critical/15 text-status-critical",
                  (status === "queued" || status === "in_progress" || status === "transcribing" || status === "extracting") && "border-status-warning bg-status-warning/15 text-status-warning",
                  status === "pending" && "border-line bg-surface-2 text-ink-3",
                )}
                title={`${stage.desc}: ${status}${job?.duration_ms != null ? ` · ${job.duration_ms.toFixed(0)} ms` : ""}`}
              >
                {status === "succeeded" && <Check className="h-3.5 w-3.5" />}
                {status === "failed" && <XIcon className="h-3.5 w-3.5" />}
                {(status === "in_progress" || status === "transcribing" || status === "extracting") && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                {(status === "pending" || status === "queued") && <span className="text-2xs">{idx + 1}</span>}
              </div>
              <span className="whitespace-nowrap text-2xs text-ink-3">{stage.label}</span>
            </div>
            {!isLast && (
              <div className={cn("mx-1 h-px w-8 flex-shrink-0", job?.status === "succeeded" ? "bg-status-good/40" : "bg-line")} />
            )}
          </div>
        );
      })}
    </div>
  );
}

const CONVERSATION_STATE: Record<string, { text: string; className: string }> = {
  new: { text: "Started", className: "border-line text-ink-2" },
  needs_text: { text: "Voice note not understood, asked to type", className: "border-[#5b4413] text-[#f6c75a]" },
  collecting: { text: "Waiting for the caller's answer", className: "border-[#5b4413] text-[#f6c75a]" },
  complete: { text: "All details collected", className: "border-[#1f5130] text-[#9fe0a8]" },
  incomplete: { text: "Stopped, caller did not answer", className: "border-[#6b2222] text-[#f59a9a]" },
};

const AUDIO_KIND: Record<string, string> = {
  caller_audio: "First voice note",
  caller_followup: "Answer to a follow-up question",
};

/** What the bot asked for and what is still open. Rendered only when a follow-up, Telegram chat or GPS exists. */
function FollowUpSection({ r }: { r: ReportDetail }) {
  const chat = r.telegram;
  const state = chat ? CONVERSATION_STATE[chat.state] : null;
  return (
    <Section title={chat ? "Telegram conversation" : "Follow-up"}>
      <div className="flex flex-wrap items-center gap-1.5 text-xs">
        {state ? <Badge className={state.className}>{state.text}</Badge> : <Badge>{label(r.follow_up_status)}</Badge>}
        {chat?.pending_field && <span className="text-ink-2">Asking for: {label(chat.pending_field)}</span>}
        {chat?.next_followup_at && <span className="text-ink-3">Next reminder {clock(chat.next_followup_at)}</span>}
      </div>
      {r.follow_up_missing_fields.length > 0 && (
        <p className="text-xs text-ink-2">Asked the caller for: {r.follow_up_missing_fields.map((f) => label(f)).join(", ")}</p>
      )}
      {chat && chat.skipped_fields.length > 0 && (
        <p className="text-xs text-[#f6c75a]">Caller answered "don't know" for: {chat.skipped_fields.map((f) => label(f)).join(", ")}</p>
      )}
      {r.caller_location && (
        <p className="text-xs text-ink-2">
          GPS shared by the caller (unverified):{" "}
          <span className="font-mono">
            {r.caller_location.latitude.toFixed(5)}, {r.caller_location.longitude.toFixed(5)}
          </span>
          {r.caller_location.accuracy_m != null && <> · accurate to about {Math.round(r.caller_location.accuracy_m)} m</>}
        </p>
      )}
    </Section>
  );
}

export function ReportDetailView({ report, onChanged }: { report: ReportDetail; onChanged: () => void }) {
  const r = report;
  const [text, setText] = useState(r.transcript ?? "");
  const [reviewer, setReviewer] = useState("dispatcher");
  const [lang, setLang] = useState<string>(r.language_hint ?? "");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(!r.transcript && r.status === "needs_transcript");
  const processing = ["queued", "transcribing", "extracting"].includes(r.status);

  async function act(key: string, fn: () => Promise<unknown>) {
    setBusy(key);
    setError(null);
    try {
      await fn();
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-5">
      <div className="space-y-1.5">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="font-mono text-base text-ink">{r.id}</span>
          <StatusPill status={r.status} />
          {r.priority_label && <PriorityBadge value={r.priority_label} score={r.priority_score ?? undefined} />}
          {r.is_synthetic && <SyntheticTag />}
          <DedupPill r={r} />
        </div>
        <div className="text-xs text-ink-3">
          Received {clock(r.received_at)} · source {label(r.source)} · language {langLabel(r.language)}
          {r.incident_id && (
            <>
              {" "}
              · incident{" "}
              <Link className="text-accent hover:underline" to={`/incidents/${r.incident_id}`}>
                {r.incident_id}
              </Link>
            </>
          )}
          {r.processing_ms != null && <> · processed in {r.processing_ms} ms</>}
        </div>
        {r.synthetic_label && <div className="text-2xs text-[#c4b5f5]">{r.synthetic_label}</div>}
      </div>

      {error && <ErrorBanner message={error} />}

      <Section title="Original audio">
        {r.audio.length ? (
          r.audio.map((a) => (
            <div key={a.id} className="space-y-1">
              <WaveformPlayer src={a.url} />
              <div className="text-2xs text-ink-3">
                {AUDIO_KIND[a.kind] ?? a.original_filename} · {a.mime_type} · {(a.size_bytes / 1024).toFixed(0)} KB {a.kind === "fixture" && "· synthetic fixture audio (computer-generated voice)"}
              </div>
            </div>
          ))
        ) : (
          <p className="text-xs text-ink-3">No audio — this report is a text transcript only.</p>
        )}
      </Section>

      <Section
        title="Transcript"
        right={
          <Button size="sm" variant="ghost" onClick={() => setEditing((v) => !v)} disabled={processing}>
            {editing ? "Cancel" : r.transcript ? "Correct transcript" : "Enter transcript"}
          </Button>
        }
      >
        <div className="flex flex-wrap items-center gap-1.5">
          <ModeBadge mode={r.transcript_provider_mode} provider={r.transcript_provider} />
          <span className="text-2xs text-ink-3">{label(r.transcript_source)}</span>
          {r.transcript_request_id && <span className="font-mono text-2xs text-ink-3">request {r.transcript_request_id}</span>}
        </div>
        {r.transcript ? (
          <blockquote className="whitespace-pre-line rounded-md border border-line bg-surface-2 px-3 py-2 text-sm leading-relaxed text-ink" lang={r.language ?? undefined}>
            {r.transcript}
          </blockquote>
        ) : (
          <p className="text-xs italic text-ink-3">No transcript.</p>
        )}
        {r.stt_error && <p className="text-xs text-[#f6c75a]">Speech-to-text: {r.stt_error}</p>}
        {editing && (
          <div className="space-y-2 rounded-md border border-line p-3">
            <p className="text-2xs text-ink-3">The previous transcript and AI extraction are kept in the audit log.</p>
            <Textarea rows={4} value={text} onChange={(e) => setText(e.target.value)} placeholder="Type exactly what the caller said…" />
            <div className="flex flex-wrap gap-2">
              <Input className="w-40" value={reviewer} onChange={(e) => setReviewer(e.target.value)} aria-label="Reviewer name" />
              <Select className="w-44" value={lang} onChange={(e) => setLang(e.target.value)} aria-label="Language">
                <option value="">Detect language</option>
                <option value="mr">Marathi</option>
                <option value="hi">Hindi</option>
                <option value="mixed">Hinglish / mixed</option>
                <option value="en">English</option>
              </Select>
              <Button
                variant="primary"
                busy={busy === "transcript"}
                disabled={!text.trim() || !reviewer.trim()}
                onClick={() =>
                  act("transcript", async () => {
                    await api.submitTranscript(r.id, text, reviewer, lang || null);
                    setEditing(false);
                  })
                }
              >
                Save & process
              </Button>
            </div>
          </div>
        )}
      </Section>

      {(r.telegram || r.follow_up_status !== "none" || r.caller_location) && <FollowUpSection r={r} />}

      <Section
        title="Processing stages (from job records)"
        right={
          <Button size="sm" variant="ghost" busy={busy === "process"} disabled={processing || (!r.transcript && !r.has_audio)} onClick={() => act("process", () => api.processReport(r.id))}>
            <RefreshCw className="h-3.5 w-3.5" /> Reprocess
          </Button>
        }
      >
        <PipelineVisualizer jobs={r.jobs} />
        <JobTimeline jobs={r.jobs} />
      </Section>

      {r.extraction_current && (
        <Section title="Structured extraction">
          <ExtractionView ext={r.extraction_current} assessment={r.field_assessment} />
        </Section>
      )}

      {r.review_reasons.length > 0 && (
        <Section title="Confidence gate">
          <ul className="space-y-1 text-xs">
            {r.review_reasons.map((x, i) => (
              <li key={i} className="flex gap-2">
                <Badge className="border-[#5b4413] text-[#f6c75a]">{x.code}</Badge>
                <span className="text-ink-2">{x.message}</span>
              </li>
            ))}
          </ul>
          {r.review_resolved && <p className="text-2xs text-[#9fe0a8]">Resolved by a reviewer (flags kept for the record).</p>}
        </Section>
      )}

      {r.priority_breakdown && (
        <Section title="Report-level priority">
          <PriorityExplain b={r.priority_breakdown} />
        </Section>
      )}

      {r.acknowledgement && (
        <Section title="Caller acknowledgement">
          <div className="space-y-1.5 rounded-md border border-line bg-surface-2 px-3 py-2">
            <div className="flex flex-wrap items-center gap-1.5">
              <Badge className="border-[#3d2f5c] text-[#c4b5f5]">{r.acknowledgement.ai_generated_label}</Badge>
              <Badge>{langLabel(r.acknowledgement.language)}</Badge>
              <Badge>{r.acknowledgement.status.replace("_", " ")}</Badge>
            </div>
            <p className="text-sm text-ink" lang={r.acknowledgement.language}>
              {r.acknowledgement.text}
            </p>
            {r.acknowledgement.audio_url ? (
              <audio controls src={r.acknowledgement.audio_url} className="h-8 w-full" />
            ) : (
              <div className="flex flex-wrap items-center gap-2">
                <Button size="sm" busy={busy === "ack"} onClick={() => act("ack", () => api.acknowledge(r.id))}>
                  <Volume2 className="h-3.5 w-3.5" /> Generate voice (Timbre)
                </Button>
                <span className="text-2xs text-ink-3">{r.acknowledgement.error ?? "Audio not generated yet."}</span>
              </div>
            )}
            <p className="text-2xs text-ink-3">Fixed wording: never promises rescue, arrival times or resolution. {r.source === "telegram" ? "The Telegram bot replies to the caller using this template." : "Not sent to anyone by this prototype."}</p>
          </div>
        </Section>
      )}

      {r.ground_truth && (
        <details className="text-xs">
          <summary className="cursor-pointer text-ink-3">Ground-truth label (evaluation)</summary>
          <pre className="mt-1 overflow-x-auto rounded bg-surface-2 p-2 text-2xs text-ink-2">{JSON.stringify(r.ground_truth, null, 2)}</pre>
        </details>
      )}

      {r.audit.length > 0 && (
        <Section title="Audit trail">
          <ul className="space-y-1 text-2xs text-ink-2">
            {r.audit.map((a) => (
              <li key={a.id}>
                <span className="font-mono text-ink-3">{clock(a.created_at)}</span> {a.actor} · {a.action}
                {a.field && <> · {a.field}</>}
                {a.new_value != null && <span className="text-ink-3"> → {JSON.stringify(a.new_value).slice(0, 120)}</span>}
              </li>
            ))}
          </ul>
        </Section>
      )}
    </div>
  );
}
