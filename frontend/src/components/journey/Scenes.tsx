import { motion } from "framer-motion";
import { AlertTriangle, Download, HelpCircle, Mic, Pause, Play, RotateCcw, Sparkles, Users, Volume2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api } from "../../lib/api";
import { useAudioUrl } from "../../lib/useAudioUrl";
import { usePoll } from "../../lib/usePoll";
import { cn } from "../../lib/cn";
import { PRIORITY_COLOR, label, langLabel, locationText, peopleText } from "../../lib/format";
import { CountUp, EASE } from "../../lib/motion";
import { getReviewer } from "../../lib/reviewer";
import type { Extraction, Priority } from "../../lib/types";
import { useTypewriter, type JourneyData } from "../../lib/useJourney";
import { Globe } from "../Globe";
import { AudioRecorder } from "../AudioRecorder";
import { Button, Textarea } from "../ui";

interface SceneProps {
  d: JourneyData;
  onDone: () => void;
  /** A follow-up answer was added to this report and it is being reprocessed. */
  onAnswered?: () => void;
}

/** Calls onDone once, `ms` after mount. */
function useDoneAfter(ms: number, onDone: () => void, enabled = true) {
  const cb = useRef(onDone);
  cb.current = onDone;
  useEffect(() => {
    if (!enabled) return;
    const t = window.setTimeout(() => cb.current(), ms);
    return () => window.clearTimeout(t);
  }, [ms, enabled]);
}

export function SceneFrame({ title, blurb, badge, children }: { title: string; blurb: string; badge?: ReactNode; children: ReactNode }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 18, filter: "blur(6px)" }}
      animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
      transition={{ duration: 0.45, ease: EASE }}
      className="flex h-full flex-col"
    >
      <div className="flex flex-wrap items-start justify-between gap-3 px-6 pt-6 md:px-8">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight md:text-3xl">{title}</h2>
          <p className="mt-1 max-w-xl text-sm text-ink-3">{blurb}</p>
        </div>
        {badge}
      </div>
      <div className="min-h-0 flex-1 px-6 pb-6 pt-5 md:px-8">{children}</div>
    </motion.div>
  );
}

function StageBadge({ provider, mode, ms }: { provider?: string | null; mode?: string | null; ms?: number | null }) {
  if (!provider) return null;
  const real = mode === "real";
  return (
    <div className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2 text-xs">
      <span className={cn("h-2 w-2 rounded-full", real ? "bg-status-good" : "bg-status-warning")} />
      <span className="text-ink-2">{label(provider)}</span>
      {mode && mode !== provider && <span className="text-ink-3">· {mode === "real" ? "live API" : mode}</span>}
      {ms != null && <span className="font-mono text-ink">· {Math.round(ms)} ms</span>}
    </div>
  );
}

/* 1 ─ Hear ─────────────────────────────────────────────────────────────── */
const BARS = Array.from({ length: 56 }, (_, i) => 0.25 + 0.75 * Math.abs(Math.sin(i * 1.7) * Math.cos(i * 0.45)));

export function HearScene({ d, onDone }: SceneProps) {
  const r = d.report!;
  const audio = r.audio[0];
  const el = useRef<HTMLAudioElement>(null);
  const recording = useAudioUrl(audio?.url);
  const [playing, setPlaying] = useState(false);
  const [waitingForSTT, setWaitingForSTT] = useState(false);
  useDoneAfter(2600, () => { if (!d.ready[1]) setWaitingForSTT(true); onDone(); });
  useEffect(() => {
    if (d.ready[1]) setWaitingForSTT(false);
  }, [d.ready[1]]);
  useEffect(() => {
    if (recording.src) el.current?.play().then(() => setPlaying(true)).catch(() => undefined);
  }, [recording.src]);
  return (
    <SceneFrame title="A voice note arrives" blurb={audio ? "Raw audio from the caller, exactly as received." : "This report came in as text, so there is no audio to play."}>
      <div className="flex h-full flex-col justify-center gap-6">
        <div className="flex h-40 items-center justify-center gap-[3px]" aria-hidden>
          {BARS.map((h, i) => (
            <motion.span
              key={i}
              className="w-1.5 rounded-full bg-gradient-to-t from-accent to-accent-glow"
              style={{ height: `${h * 100}%`, originY: 0.5 }}
              animate={playing || !audio ? { scaleY: [0.35, 1, 0.5, 0.9, 0.35] } : { scaleY: 0.35 }}
              transition={{ duration: 1.4 + (i % 7) * 0.12, repeat: Infinity, delay: i * 0.025, ease: "easeInOut" }}
            />
          ))}
        </div>
        <div className="flex flex-wrap items-center justify-center gap-3 text-sm text-ink-2">
          {audio && (
            <>
              <audio ref={el} src={recording.src ?? undefined} onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} onEnded={() => setPlaying(false)} />
              <Button disabled={!recording.src} onClick={() => (playing ? el.current?.pause() : void el.current?.play())}>
                {playing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />} {playing ? "Pause" : recording.error ? "Audio unavailable" : "Play call"}
              </Button>
              {recording.src && (
                <a href={recording.src} download={audio.original_filename} className="inline-flex items-center gap-1 rounded-md border border-white/10 px-2 py-1 text-xs text-ink-2 hover:bg-white/5 hover:text-ink">
                  <Download className="h-3.5 w-3.5" aria-hidden /> Download
                </a>
              )}
              <span className="text-ink-3">
                {audio.original_filename} · {(audio.size_bytes / 1024).toFixed(0)} KB
              </span>
            </>
          )}
          {r.language_hint && <span className="rounded-full bg-white/5 px-2.5 py-1 text-xs">Language hint: {langLabel(r.language_hint)}</span>}
        </div>
        {waitingForSTT && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex items-center justify-center gap-2 text-xs text-ink-3">
            <motion.span animate={{ opacity: [0.4, 1, 0.4] }} transition={{ duration: 1.2, repeat: Infinity }} className="h-1.5 w-1.5 rounded-full bg-accent" />
            Sending to Gnani Prisma for transcription…
          </motion.div>
        )}
      </div>
    </SceneFrame>
  );
}

/* 2 ─ Transcribe ───────────────────────────────────────────────────────── */
export function TranscribeScene({ d, onDone }: SceneProps) {
  const r = d.report!;
  const has = d.ready[1];
  const { shown, done } = useTypewriter(r.transcript ?? "", has, 18);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useDoneAfter(1100, onDone, has && done);
  const job = d.jobs.transcription;

  const retrySTT = async () => {
    setRetrying(true);
    setErr(null);
    try {
      await api.processReport(r.id);
      d.reload();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setRetrying(false);
    }
  };

  return (
    <SceneFrame
      title="Speech becomes text"
      blurb="The recording is transcribed in the caller's own language — no translation yet."
      badge={<StageBadge provider={r.transcript_provider} mode={r.transcript_provider_mode} ms={job?.duration_ms} />}
    >
      {d.blocked === "needs_transcript" || d.blocked === "failed" ? (
        <div className="mx-auto max-w-xl space-y-4 rounded-2xl border border-status-warning/30 bg-status-warning/5 p-5">
          <div className="flex items-center gap-2 text-sm font-medium text-[#f6c75a]">
            <AlertTriangle className="h-4 w-4" /> No speech-to-text result for this audio
          </div>
          <p className="text-xs text-ink-3">
            {r.stt_error ?? "The speech service could not transcribe this clip (offline, or temporary connection issue)."}
          </p>

          {r.has_audio && (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-white/10 bg-surface-2 p-3">
              <div className="text-xs text-ink-2">
                <span className="font-medium text-ink">Audio recording is attached</span>
                <p className="text-2xs text-ink-3">Retry automatic transcription with Gnani Prisma</p>
              </div>
              <Button size="sm" variant="secondary" busy={retrying} onClick={() => void retrySTT()}>
                <RotateCcw className="h-3.5 w-3.5" /> Retry speech recognition
              </Button>
            </div>
          )}

          <div className="space-y-2">
            <label className="block text-2xs uppercase tracking-wider text-ink-3">
              Or type what the caller said to continue:
            </label>
            <Textarea rows={4} value={text} onChange={(e) => setText(e.target.value)} placeholder="Type the transcript…" />
          </div>

          {err && <p className="text-xs text-[#f3b0b0]">{err}</p>}
          <Button
            variant="primary"
            busy={busy}
            disabled={!text.trim()}
            onClick={async () => {
              setBusy(true);
              try {
                await api.submitTranscript(r.id, text.trim(), getReviewer(), r.language_hint);
                d.reload();
              } catch (e) {
                setErr(e instanceof Error ? e.message : String(e));
              } finally {
                setBusy(false);
              }
            }}
          >
            Continue the journey
          </Button>
        </div>
      ) : has ? (
        <p className="mx-auto max-w-3xl text-xl leading-relaxed text-ink md:text-2xl md:leading-relaxed">
          {shown}
          {!done && <span className="ml-0.5 inline-block h-6 w-0.5 translate-y-1 animate-pulse bg-accent" />}
        </p>
      ) : (
        <div className="mx-auto max-w-3xl space-y-3 pt-6" role="status" aria-label="Listening">
          <div className="skeleton h-6 w-11/12" />
          <div className="skeleton h-6 w-9/12" />
          <div className="skeleton h-6 w-10/12" />
          <p className="pt-2 text-sm text-ink-3">Listening…</p>
        </div>
      )}
    </SceneFrame>
  );
}

/* 3 ─ Understand ───────────────────────────────────────────────────────── */
const FIELD_COLOR: Record<string, string> = { place: "#38bdf8", people: "#f59e0b", danger: "#ef4444", need: "#22c55e", vulnerable: "#a78bfa", other: "#737373" };
function fieldKind(f: string): keyof typeof FIELD_COLOR {
  const s = f.toLowerCase();
  if (s.includes("loc") || s.includes("place") || s.includes("landmark")) return "place";
  if (s.includes("people") || s.includes("count")) return "people";
  if (s.includes("danger") || s.includes("hazard") || s.includes("medical")) return "danger";
  if (s.includes("need")) return "need";
  if (s.includes("vuln")) return "vulnerable";
  return "other";
}

function Highlighted({ text, ext }: { text: string; ext: Extraction }) {
  const parts = useMemo(() => {
    const lower = text.toLowerCase();
    const taken: { s: number; e: number; kind: string }[] = [];
    for (const ev of ext.evidence ?? []) {
      if (ev.negated || !ev.text) continue;
      const i = lower.indexOf(ev.text.toLowerCase());
      if (i < 0 || taken.some((t) => i < t.e && i + ev.text.length > t.s)) continue;
      taken.push({ s: i, e: i + ev.text.length, kind: fieldKind(ev.field) });
    }
    taken.sort((a, b) => a.s - b.s);
    const out: ReactNode[] = [];
    let at = 0;
    taken.forEach((t, k) => {
      if (t.s > at) out.push(text.slice(at, t.s));
      out.push(
        <motion.mark
          key={k}
          className="rounded px-1 text-ink"
          style={{ background: `${FIELD_COLOR[t.kind]}33`, boxShadow: `inset 0 -2px 0 ${FIELD_COLOR[t.kind]}` }}
          initial={{ backgroundColor: "rgba(0,0,0,0)" }}
          animate={{ backgroundColor: `${FIELD_COLOR[t.kind]}33` }}
          transition={{ delay: 0.4 + k * 0.18, duration: 0.5 }}
        >
          {text.slice(t.s, t.e)}
        </motion.mark>,
      );
      at = t.e;
    });
    out.push(text.slice(at));
    return out;
  }, [text, ext]);
  return <p className="text-base leading-relaxed text-ink-2 md:text-lg">{parts}</p>;
}

function Fact({ i, kind, name, children, conf }: { i: number; kind: keyof typeof FIELD_COLOR; name: string; children: ReactNode; conf?: number | null }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16, scale: 0.95 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ delay: 0.5 + i * 0.22, duration: 0.45, ease: EASE }}
      className="rounded-2xl border border-white/[0.07] bg-white/[0.035] p-4"
    >
      <div className="flex items-center gap-2 text-2xs font-semibold uppercase tracking-wider" style={{ color: FIELD_COLOR[kind] }}>
        <span className="h-2 w-2 rounded-full" style={{ background: FIELD_COLOR[kind] }} /> {name}
      </div>
      <div className="mt-1.5 text-base font-medium text-ink">{children}</div>
      {conf != null && (
        <div className="mt-2.5 flex items-center gap-2 text-2xs text-ink-3">
          <div className="h-1 flex-1 overflow-hidden rounded-full bg-white/10">
            <motion.div className="h-full rounded-full" style={{ background: FIELD_COLOR[kind] }} initial={{ width: 0 }} animate={{ width: `${Math.round(conf * 100)}%` }} transition={{ delay: 0.8 + i * 0.22, duration: 0.8 }} />
          </div>
          {conf > 0 ? `${Math.round(conf * 100)}% sure` : "not stated"}
        </div>
      )}
    </motion.div>
  );
}

export function UnderstandScene({ d, onDone }: SceneProps) {
  const r = d.report!;
  const ext = r.extraction_current;
  const job = d.jobs.extraction;
  useDoneAfter(4600, onDone, !!ext);
  if (!ext)
    return (
      <SceneFrame title="Finding the facts" blurb="Where, how many, what danger, what is needed.">
        <div className="space-y-3 pt-4">{[0, 1, 2].map((k) => <div key={k} className="skeleton h-16 w-full" />)}</div>
      </SceneFrame>
    );
  const vul = Object.entries(ext.vulnerable_people ?? {}).filter(([, v]) => v).map(([k]) => label(k));
  const loc = ext.location;
  const place = [loc.place_name, loc.landmark].filter(Boolean).join(" · ");
  let n = 0;
  return (
    <SceneFrame
      title="Understanding what happened"
      blurb="Key facts are pulled from the words — each one shows how sure the system is."
      badge={<StageBadge provider={r.extraction_provider} mode={r.extraction_mode} ms={job?.duration_ms} />}
    >
      <div className="space-y-5 overflow-y-auto">
        <div className="rounded-2xl border border-white/[0.06] bg-black/20 p-4">
          <Highlighted text={r.transcript ?? ""} ext={ext} />
        </div>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          <Fact i={n++} kind="place" name="Where" conf={loc.confidence}>
            {place || "Not stated"}
          </Fact>
          <Fact i={n++} kind="people" name="How many people" conf={ext.people_affected.confidence}>
            {ext.people_affected.count != null ? `${ext.people_affected.approximate ? "about " : ""}${ext.people_affected.count}` : "Unknown"}
          </Fact>
          <Fact i={n++} kind="danger" name="Danger">
            {ext.reported_danger.length ? ext.reported_danger.map(label).join(", ") : ext.medical_emergency ? "Medical emergency" : "None stated"}
          </Fact>
          <Fact i={n++} kind="need" name="Needs">
            {ext.immediate_needs.length ? ext.immediate_needs.map(label).join(", ") : "None stated"}
          </Fact>
          <Fact i={n++} kind="vulnerable" name="Vulnerable people">
            {vul.length ? vul.join(", ") : "None mentioned"}
          </Fact>
          <Fact i={n++} kind="other" name="Caller urgency · language">
            {label(ext.urgency)} · {langLabel(ext.language)}
          </Fact>
        </div>
      </div>
    </SceneFrame>
  );
}

/* 4 ─ Locate ───────────────────────────────────────────────────────────── */
export function LocateScene({ d, onDone }: SceneProps) {
  const inc = d.incident;
  const mappable = !!inc && inc.latitude != null && inc.longitude != null;
  useDoneAfter(4600, onDone, !!inc);
  const list = useMemo(() => (inc && !d.incidents.some((x) => x.id === inc.id) ? [...d.incidents, inc] : d.incidents), [d.incidents, inc]);
  return (
    <SceneFrame title="Pinpointing it" blurb={mappable ? "The location is matched to a known place and flown to on the globe." : "The place is unclear, so the system will not guess a position."}>
      <div className="relative h-[420px] overflow-hidden rounded-2xl border border-white/[0.06] bg-black/30">
        <div className="pointer-events-none absolute inset-0 bg-black/20" aria-hidden />
        <Globe className="h-full w-full" incidents={list} selectedId={mappable ? inc!.id : null} onSelect={() => undefined} />
        {!mappable && inc && (
          <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.8 }} className="absolute right-4 top-4 flex w-72 items-start gap-3 rounded-2xl border border-status-warning/30 bg-bg/85 p-3.5 backdrop-blur">
            <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-status-warning" />
            <div>
              <p className="text-sm font-medium">{locationText(inc)}</p>
              <p className="text-xs text-ink-3">The caller did not name a place the system can match, so no pin is placed. A dispatcher confirms the location — coordinates are never invented.</p>
            </div>
          </motion.div>
        )}
        {inc && (
          <motion.div initial={{ opacity: 0, x: -16 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 1.2, duration: 0.5 }} className="absolute left-4 top-4 max-w-[16rem] rounded-xl border border-white/10 bg-bg/80 p-3 backdrop-blur">
            <div className="text-2xs uppercase tracking-wider text-ink-3">Location</div>
            <div className="text-sm font-medium">{locationText(inc)}</div>
            {inc.coordinates_are_simulated && <div className="mt-1 text-2xs text-ink-3">Reference location (unverified).</div>}
          </motion.div>
        )}
      </div>
    </SceneFrame>
  );
}

/* 5 ─ Match ────────────────────────────────────────────────────────────── */
export function MatchScene({ d, onDone }: SceneProps) {
  const r = d.report!;
  const inc = d.incident;
  useDoneAfter(4200, onDone, !!inc);
  const outcome = r.dedup_outcome ?? "new_incident";
  const others = (inc?.reports ?? []).filter((m) => m.id !== r.id);
  const count = inc?.report_count ?? 1;
  const headline =
    outcome === "likely_duplicate" || (outcome === "new_incident" && count > 1)
      ? `Matches ${inc?.id} — ${count} calls now describe one event`
      : outcome === "possible_duplicate"
        ? `Looks similar to ${r.suggestions[0]?.candidate_incident_id ?? "another incident"} — a human decides`
        : `New incident ${inc?.id ?? ""}`;
  return (
    <SceneFrame title="Is this a duplicate?" blurb="Many callers describe the same event. Similar reports are grouped so responders see one incident, not ten.">
      <div className="flex h-full flex-col items-center justify-center gap-8">
        <div className="relative flex w-full max-w-2xl items-center justify-between">
          <div className="flex flex-col gap-2">
            {others.slice(0, 3).map((m, k) => (
              <motion.div key={m.id} initial={{ opacity: 0, x: -30 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.2 + k * 0.2 }} className="rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2 text-xs text-ink-3">
                Earlier call <span className="font-mono text-ink-2">{m.id.slice(-6)}</span>
              </motion.div>
            ))}
            <motion.div initial={{ opacity: 0, x: -30 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.1 }} className="rounded-xl border border-accent/60 bg-accent/15 px-3 py-2 text-xs font-medium text-ink shadow-glow">
              This call
            </motion.div>
          </div>
          <motion.div className="mx-4 h-0.5 flex-1 origin-left bg-gradient-to-r from-accent/0 via-accent to-accent/0" initial={{ scaleX: 0 }} animate={{ scaleX: 1 }} transition={{ delay: 0.7, duration: 0.9 }} />
          <motion.div
            initial={{ scale: 0.4, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ delay: 1.2, type: "spring", stiffness: 180, damping: 14 }}
            className="grid h-36 w-36 shrink-0 place-items-center rounded-full border-2 text-center"
            style={{ borderColor: PRIORITY_COLOR[(inc?.priority_label ?? "low") as Priority], boxShadow: `0 0 50px -8px ${PRIORITY_COLOR[(inc?.priority_label ?? "low") as Priority]}` }}
          >
            <div>
              <div className="font-mono text-4xl font-semibold">
                <CountUp value={count} />
              </div>
              <div className="text-2xs uppercase tracking-wider text-ink-3">call{count === 1 ? "" : "s"} · 1 incident</div>
            </div>
          </motion.div>
        </div>
        <motion.p initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 1.8 }} className="max-w-xl text-center text-lg font-medium">
          {headline}
        </motion.p>
      </div>
    </SceneFrame>
  );
}

/* 6 ─ Prioritise ───────────────────────────────────────────────────────── */
export function PriorityScene({ d, onDone }: SceneProps) {
  const inc = d.incident;
  useDoneAfter(4600, onDone, !!inc);
  const score = inc?.priority_score ?? 0;
  const lab = (inc?.priority_label ?? "low") as Priority;
  const color = PRIORITY_COLOR[lab];
  const frac = Math.min(1, score / 120);
  const R = 120;
  const arc = Math.PI * R;
  const factors = inc?.priority_breakdown?.factors ?? [];
  const max = Math.max(1, ...factors.map((f) => f.points));
  return (
    <SceneFrame title="How urgent is it?" blurb="A transparent score — every point comes from something the caller actually said.">
      <div className="grid h-full items-center gap-8 md:grid-cols-[320px_1fr]">
        <div className="relative mx-auto w-[280px]">
          <svg viewBox="0 0 280 160" className="w-full" aria-hidden>
            <path d="M20 150 A120 120 0 0 1 260 150" fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="16" strokeLinecap="round" />
            <motion.path
              d="M20 150 A120 120 0 0 1 260 150"
              fill="none"
              stroke={color}
              strokeWidth="16"
              strokeLinecap="round"
              strokeDasharray={arc}
              initial={{ strokeDashoffset: arc }}
              animate={{ strokeDashoffset: arc * (1 - frac) }}
              transition={{ duration: 1.8, ease: EASE, delay: 0.3 }}
              style={{ filter: `drop-shadow(0 0 10px ${color})` }}
            />
          </svg>
          <div className="absolute inset-x-0 bottom-0 text-center">
            <div className="font-mono text-5xl font-semibold tabular-nums">
              <CountUp value={Math.round(score)} />
            </div>
            <motion.div initial={{ opacity: 0, scale: 0.8 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: 2 }} className="mt-1 text-lg font-semibold uppercase tracking-widest" style={{ color }}>
              {lab}
            </motion.div>
          </div>
        </div>
        <ul className="space-y-2.5">
          {factors.slice(0, 6).map((f, k) => (
            <motion.li key={f.key} initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.8 + k * 0.2 }} className="grid grid-cols-[1fr_auto] items-center gap-3">
              <div>
                <div className="text-sm text-ink">{f.label}</div>
                <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-white/10">
                  <motion.div className="h-full rounded-full" style={{ background: color }} initial={{ width: 0 }} animate={{ width: `${(f.points / max) * 100}%` }} transition={{ delay: 1 + k * 0.2, duration: 0.7 }} />
                </div>
              </div>
              <span className="font-mono text-sm text-ink-2">+{f.points}</span>
            </motion.li>
          ))}
          {!factors.length && <li className="text-sm text-ink-3">Not enough was stated to score this yet — it goes to a human.</li>}
        </ul>
      </div>
    </SceneFrame>
  );
}

const MISSING_LABEL: Record<string, string> = {
  location_missing: "Location not stated",
  disaster_unknown: "Disaster type unknown",
  people_unknown: "People count unknown",
};

/* 7 ─ Reply ────────────────────────────────────────────────────────────── */
export function ReplyScene({ d, onDone, onAnswered }: SceneProps) {
  const r = d.report!;
  const ack = d.ack;
  const { shown, done } = useTypewriter(ack?.text ?? "", !!ack, 24);
  const el = useRef<HTMLAudioElement>(null);
  const reply = useAudioUrl(ack?.audio_url);
  const [playing, setPlaying] = useState(false);
  const [answerSent, setAnswerSent] = useState(false);
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const followUp = r.follow_up_needed && (r.follow_up_questions?.length ?? 0) > 0;
  // While something is missing the scene waits for the dispatcher instead of racing on to the finale.
  useDoneAfter(1800, onDone, d.ready[6] && (done || !ack) && !followUp);
  useEffect(() => {
    if (reply.src) el.current?.play().then(() => setPlaying(true)).catch(() => undefined);
  }, [reply.src]);

  async function submit(answer: { audio?: Blob; text?: string }) {
    setBusy(true);
    setErr(null);
    try {
      // The answer is added to THIS report and it is reprocessed; a separate new report would restart the journey.
      await api.answerFollowup(r.id, answer);
      setAnswerSent(true);
      d.reload();
      onAnswered?.();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <SceneFrame
      title="Reply and open questions"
      blurb={
        followUp
          ? "Key details are still missing. Nobody has been contacted automatically: enter what you learn and this same report is updated."
          : "A calm reply is prepared in the caller's language so they know they were heard. It is not sent automatically, and dispatch stays a human decision."
      }
      badge={ack && <StageBadge provider={ack.provider} mode={ack.provider_mode} />}
    >
      <div className="mx-auto flex h-full max-w-2xl flex-col justify-center gap-5">
        {ack ? (
          <>
            <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-5">
              <div className="mb-2 flex items-center gap-2 text-2xs font-semibold uppercase tracking-wider text-accent-glow">
                <Sparkles className="h-3.5 w-3.5" /> {ack.ai_generated_label}
              </div>
              <p className="text-xl leading-relaxed">
                {shown}
                {!done && <span className="ml-0.5 inline-block h-5 w-0.5 translate-y-0.5 animate-pulse bg-accent" />}
              </p>
            </div>

            {ack.audio_url ? (
              <div className="flex items-center gap-3">
                <audio ref={el} src={reply.src ?? undefined} onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} onEnded={() => setPlaying(false)} />
                <Button disabled={!reply.src} onClick={() => (playing ? el.current?.pause() : void el.current?.play())}>
                  <Volume2 className="h-4 w-4" /> {playing ? "Pause" : reply.error ? "Audio unavailable" : "Hear the reply"}
                </Button>
              </div>
            ) : (
              <p className="text-xs text-ink-3">Text only — voice playback needs the speech service.</p>
            )}

            {followUp && (
              <motion.div
                initial={{ opacity: 0, y: 14 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.6, duration: 0.5 }}
                className="overflow-hidden rounded-2xl border border-[#f59e0b]/30 bg-[#f59e0b]/[0.05]"
              >
                <div className="border-b border-[#f59e0b]/15 px-4 pb-3 pt-4">
                  <div className="mb-2.5 flex items-center gap-2 text-2xs font-semibold uppercase tracking-wider text-[#f59e0b]">
                    <HelpCircle className="h-3.5 w-3.5" /> Missing information
                  </div>
                  <div className="mb-3 flex flex-wrap gap-1.5">
                    {(r.follow_up_missing_fields ?? []).map((f) => (
                      <span key={f} className="rounded-full border border-[#f59e0b]/30 bg-[#f59e0b]/10 px-2.5 py-0.5 text-2xs text-[#f59e0b]">
                        {MISSING_LABEL[f] ?? f}
                      </span>
                    ))}
                  </div>
                  <p className="mb-1.5 text-2xs uppercase tracking-wider text-ink-3">Questions to ask</p>
                  <ul className="space-y-2">
                    {(r.follow_up_questions ?? []).map((q, i) => (
                      <li key={i} className="flex items-start gap-2 text-sm text-ink-2">
                        <span className="mt-0.5 h-4 w-4 shrink-0 rounded-full bg-[#f59e0b]/20 text-center text-2xs leading-4 text-[#f59e0b]">{i + 1}</span>
                        {q}
                      </li>
                    ))}
                  </ul>
                </div>

                <div className="space-y-3 px-4 py-4">
                  {answerSent ? (
                    <div className="flex items-center gap-2 text-sm text-[#f59e0b]">
                      <span className="h-2 w-2 animate-pulse rounded-full bg-[#f59e0b]" />
                      Answer added to {r.id} — updating the results…
                    </div>
                  ) : (
                    <>
                      <p className="text-xs text-ink-3">
                        <Mic className="mb-0.5 mr-1 inline h-3 w-3" />
                        Record the answer, or type it. It is merged into this report and the pipeline runs again on it.
                      </p>
                      <AudioRecorder onRecorded={(wav) => submit({ audio: wav })} />
                      <div className="flex gap-2">
                        <Textarea rows={2} value={typed} onChange={(e) => setTyped(e.target.value)} placeholder="…or type the answer" />
                        <Button variant="primary" busy={busy} disabled={!typed.trim()} onClick={() => void submit({ text: typed.trim() })}>
                          Add
                        </Button>
                      </div>
                      {err && <p className="text-xs text-[#f3b0b0]">{err}</p>}
                      <button onClick={onDone} className="text-xs text-ink-3 underline-offset-4 hover:text-ink hover:underline">
                        Skip — show the results without answering
                      </button>
                    </>
                  )}
                </div>
              </motion.div>
            )}
          </>
        ) : (
          <p className="text-center text-sm text-ink-3">{d.ackFailed ? "Reply could not be generated." : "Writing a reply…"}</p>
        )}
      </div>
    </SceneFrame>
  );
}

/* Finale ───────────────────────────────────────────────────────────────── */
const STAGE_NAMES: Record<string, string> = {
  audio_prep: "Audio clean-up",
  transcription: "Speech to text",
  extraction: "Fact extraction",
  confidence_gate: "Confidence check",
  deduplication: "Duplicate matching",
  priority: "Priority scoring",
  follow_up: "Missing-info check",
};

function Tile({ k, v, hint, icon }: { k: string; v: string; hint?: string; icon?: ReactNode }) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.04] px-4 py-3 text-left">
      <div className="text-2xs uppercase tracking-wider text-ink-3">{k}</div>
      <div className="mt-0.5 flex items-center gap-1 font-mono text-xl font-semibold">
        {icon}
        {v}
      </div>
      {hint && <div className="mt-0.5 truncate text-2xs text-ink-3">{hint}</div>}
    </div>
  );
}

/** What this call produced, from the real job records and facts. Nothing here is simulated. */
export function FinaleStats({ d }: { d: JourneyData }) {
  const stats = usePoll(api.stats, 0);
  const r = d.report;
  const inc = d.incident;
  const ext = r?.extraction_current;
  const jobs = Object.values(d.jobs).filter((j) => j.duration_ms != null);
  const total = jobs.reduce((a, j) => a + (j.duration_ms ?? 0), 0);
  const slowest = Math.max(1, ...jobs.map((j) => j.duration_ms ?? 0));
  const missing = r?.follow_up_missing_fields ?? [];
  const facts: [string, boolean, string][] = ext
    ? [
        ["Where", !!(ext.location.place_name || ext.location.landmark), [ext.location.place_name, ext.location.landmark].filter(Boolean).join(" · ") || "Not stated"],
        ["What happened", ext.disaster_type !== "unknown", label(ext.disaster_type)],
        ["How many people", ext.people_affected.count != null, ext.people_affected.count != null ? String(ext.people_affected.count) : "Unknown"],
      ]
    : [];
  return (
    <div className="space-y-4 text-left">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Tile k="Pipeline time" v={`${(total / 1000).toFixed(1)} s`} hint={`${jobs.length} stages`} />
        <Tile k="Priority" v={(inc?.priority_label ?? "—").toUpperCase()} hint={inc ? `score ${Math.round(inc.priority_score)}` : undefined} />
        <Tile k="People" v={inc ? peopleText(inc) : "—"} icon={<Users className="h-4 w-4 text-ink-3" />} />
        <Tile k="Calls grouped" v={String(inc?.report_count ?? 1)} hint={inc?.id} />
      </div>

      {facts.length > 0 && (
        <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
          <div className="mb-2 text-2xs uppercase tracking-wider text-ink-3">What the system understood</div>
          <ul className="grid gap-2 sm:grid-cols-3">
            {facts.map(([name, ok, value]) => (
              <li key={name} className="flex items-start gap-2 text-sm">
                <span className={cn("mt-1.5 h-2 w-2 shrink-0 rounded-full", ok ? "bg-status-good" : "bg-status-warning")} />
                <span>
                  <span className="block text-2xs text-ink-3">{name}</span>
                  <span className={ok ? "text-ink" : "text-ink-3"}>{value}</span>
                </span>
              </li>
            ))}
          </ul>
          {missing.length > 0 && (
            <p className="mt-3 text-xs text-[#f6c75a]">
              Still missing: {missing.map((f) => MISSING_LABEL[f] ?? f).join(", ")}.
              {r?.follow_up_channel ? "" : " No one has contacted the caller; a dispatcher needs to find this out."}
            </p>
          )}
        </div>
      )}

      {jobs.length > 0 && (
        <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
          <div className="mb-2 text-2xs uppercase tracking-wider text-ink-3">Where the time went</div>
          <ul className="space-y-2">
            {jobs.map((j) => (
              <li key={j.id} className="grid grid-cols-[9.5rem_1fr_4.5rem] items-center gap-3 text-xs">
                <span className="truncate text-ink-2">{STAGE_NAMES[j.stage] ?? label(j.stage)}</span>
                <span className="h-1.5 overflow-hidden rounded-full bg-white/10">
                  <span className="block h-full rounded-full bg-accent" style={{ width: `${Math.max(2, ((j.duration_ms ?? 0) / slowest) * 100)}%` }} />
                </span>
                <span className="text-right font-mono text-ink-2">{Math.round(j.duration_ms ?? 0)} ms</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {stats.data && (
        <div className="grid grid-cols-3 gap-3">
          <Tile k="Active incidents" v={String(stats.data.unique_incidents)} hint="right now" />
          <Tile k="Critical" v={String(stats.data.critical_incidents)} hint="right now" />
          <Tile k="Reports received" v={String(stats.data.total_reports)} hint="all time" />
        </div>
      )}
    </div>
  );
}
