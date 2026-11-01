import { AnimatePresence, motion } from "framer-motion";
import { AudioLines, Brain, Check, ChevronRight, FastForward, Flame, GitMerge, Gauge, Loader2, MapPin, Mic, MountainSnow, Pause, Play, RotateCcw, Volume2, Waves, type LucideIcon } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { AudioRecorder } from "../components/AudioRecorder";
import { FinaleStats, HearScene, LocateScene, MatchScene, PriorityScene, ReplyScene, TranscribeScene, UnderstandScene } from "../components/journey/Scenes";
import { Button, ErrorBanner, Textarea } from "../components/ui";
import { api } from "../lib/api";
import { cn } from "../lib/cn";
import { langLabel } from "../lib/format";
import { EASE } from "../lib/motion";
import { STEP_COUNT, useJourney } from "../lib/useJourney";
import { usePoll } from "../lib/usePoll";

const STEPS: { label: string; sub: string; icon: LucideIcon; stage?: string }[] = [
  { label: "Hear", sub: "Voice arrives", icon: Mic },
  { label: "Transcribe", sub: "Gnani Prisma STT", icon: AudioLines, stage: "transcription" },
  { label: "Understand", sub: "Fact extraction", icon: Brain, stage: "extraction" },
  { label: "Locate", sub: "Pin on the globe", icon: MapPin },
  { label: "Match", sub: "Same incident?", icon: GitMerge, stage: "deduplication" },
  { label: "Prioritise", sub: "How urgent", icon: Gauge, stage: "priority" },
  { label: "Reply", sub: "Gnani Timbre TTS", icon: Volume2, stage: "follow_up" },
];

/* ───────────────────────────── start screen ───────────────────────────── */
function Start({ onStarted }: { onStarted: (reportId: string) => void }) {
  const fixtures = usePoll(api.fixtures, 0);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [drag, setDrag] = useState(false);
  const [typing, setTyping] = useState(false);
  const [text, setText] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const samples = (fixtures.data?.items ?? []).filter((f) => f.has_audio);

  async function run(key: string, fn: () => Promise<string>) {
    setBusy(key);
    setError(null);
    try {
      onStarted(await fn());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(null);
    }
  }
  const upload = (file: File) => run("upload", async () => (await api.uploadReport(file, file.name, null, "upload")).id);
  const sample = (id: string, loaded: boolean) =>
    run(id, async () => {
      if (loaded) {
        const all = await api.reports({ limit: 500 });
        const hit = all.items.find((r) => r.fixture_id === id);
        if (hit) return hit.id;
      }
      return (await api.inject(id, true)).id;
    });

  return (
    <div className="mx-auto max-w-4xl space-y-8 py-4">
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, ease: EASE }} className="text-center">
        <div className="mb-3 inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-white/[0.04] px-3 py-1 text-xs text-ink-3">
          <span className="h-1.5 w-1.5 rounded-full bg-status-good" />
          Gnani Prisma · Timbre
        </div>
        <h1 className="text-3xl font-semibold tracking-tight text-white md:text-5xl">
          A distress call comes in.
        </h1>
        <p className="mx-auto mt-3 max-w-lg text-base text-ink-3">
          Drop a recording — Prisma transcribes it, the key facts are extracted, it pins on the map, gets prioritised, and Timbre replies in the caller's language.
        </p>
      </motion.div>

      {error && <ErrorBanner message={error} />}

      <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1, duration: 0.5, ease: EASE }} className="grid gap-4 md:grid-cols-[1.4fr_1fr]">
        <div
          role="button"
          tabIndex={0}
          onClick={() => input.current?.click()}
          onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && input.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            setDrag(true);
          }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDrag(false);
            const f = e.dataTransfer.files[0];
            if (f) void upload(f);
          }}
          className={cn(
            "group flex min-h-[220px] cursor-pointer flex-col items-center justify-center gap-4 rounded-3xl border border-white/[0.08] bg-surface-1 p-8 text-center outline-none transition-all",
            drag ? "scale-[1.02] border-[#ff6b4a]/50 bg-[#ff6b4a]/[0.06] shadow-[0_0_40px_-8px_rgba(255,107,74,0.3)]" : "hover:border-white/[0.14] hover:bg-surface-2 focus-visible:border-accent",
          )}
        >
          <input ref={input} type="file" accept="audio/*,.wav,.mp3,.m4a,.aac,.ogg,.flac" className="hidden" onChange={(e) => e.target.files?.[0] && void upload(e.target.files[0])} />
          <div className="relative grid h-20 w-20 place-items-center">
            {[0, 1, 2].map((i) => (
              <motion.span
                key={i}
                className="absolute inset-0 rounded-full border border-[#ff6b4a]/40"
                animate={busy === "upload" ? {} : { scale: [1, 1.55, 2.1], opacity: [0.55, 0.2, 0] }}
                transition={{ duration: 2.2, repeat: Infinity, delay: i * 0.72, ease: "easeOut" }}
              />
            ))}
            <div className="relative grid h-14 w-14 place-items-center rounded-full border border-white/10 bg-surface-2">
              {busy === "upload"
                ? <Loader2 className="h-6 w-6 animate-spin text-accent-glow" aria-hidden />
                : <Mic className="h-6 w-6 text-[#ff6b4a]" aria-hidden />}
            </div>
          </div>
          <div className="text-base font-medium text-ink">{busy === "upload" ? "Processing call…" : "Drop a call recording"}</div>
          <div className="text-sm text-ink-3">{busy === "upload" ? "Sending to Gnani Prisma…" : "WAV · MP3 · M4A · or click to browse"}</div>
        </div>

        <div className="flex flex-col justify-between gap-4 rounded-3xl border border-white/[0.08] bg-surface-1 p-6">
          <div>
            <div className="flex items-center gap-2 text-sm font-medium">
              <Mic className="h-4 w-4 text-accent-glow" /> Record it live
            </div>
            <p className="mt-1 text-xs text-ink-3">Speak a short emergency report in Marathi, Hindi or English.</p>
          </div>
          <AudioRecorder onRecorded={async (wav) => onStarted((await api.uploadReport(wav, "recording.wav", null, "recording")).id)} />
          <button onClick={() => setTyping((v) => !v)} className="text-left text-xs text-ink-3 underline-offset-4 hover:text-ink hover:underline">
            {typing ? "Hide" : "No audio? Type the report instead"}
          </button>
        </div>
      </motion.div>

      <AnimatePresence>
        {typing && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }} className="overflow-hidden">
            <div className="space-y-3 rounded-3xl border border-white/[0.08] bg-surface-1 p-5">
              <Textarea rows={3} value={text} onChange={(e) => setText(e.target.value)} placeholder="e.g. पाणी वाढत आहे, कोठाळे गावात ५ लोक अडकले आहेत…" />
              <Button variant="primary" busy={busy === "text"} disabled={!text.trim()} onClick={() => run("text", async () => (await api.createReport({ transcript: text.trim(), process: true })).id)}>
                Start the journey
              </Button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {samples.length > 0 && (
        <motion.section initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.3 }}>
          <h2 className="mb-3 text-center text-sm font-medium text-ink-3">…or try a recorded call</h2>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {samples.map((f, k) => {
              const disasterTag = f.scenario_tags.find((t) => ["flood", "landslide", "fire", "earthquake"].includes(t)) ?? "other";
              const DISASTER_META: Record<string, { icon: LucideIcon; color: string; bg: string }> = {
                flood: { icon: Waves, color: "#38bdf8", bg: "rgba(56,189,248,0.12)" },
                landslide: { icon: MountainSnow, color: "#fab219", bg: "rgba(250,178,25,0.12)" },
                fire: { icon: Flame, color: "#ff6b6b", bg: "rgba(255,107,107,0.12)" },
                earthquake: { icon: MountainSnow, color: "#b794ff", bg: "rgba(183,148,255,0.12)" },
                other: { icon: Waves, color: "#8a909c", bg: "rgba(138,144,156,0.1)" },
              };
              const meta = DISASTER_META[disasterTag] ?? DISASTER_META.other;
              const Icon = meta.icon;
              const vulnerable = f.scenario_tags.filter((t) => ["children", "elderly", "pregnant", "injured", "disability"].includes(t));
              return (
                <motion.button
                  key={f.id}
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.35 + k * 0.08 }}
                  whileHover={{ y: -4 }}
                  whileTap={{ scale: 0.98 }}
                  onClick={() => void sample(f.id, f.loaded)}
                  disabled={!!busy}
                  className="group rounded-2xl border border-white/[0.08] bg-surface-1 p-4 text-left transition-colors hover:border-white/[0.15] hover:bg-surface-2 disabled:opacity-60"
                >
                  <div className="flex items-start justify-between gap-2">
                    <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl" style={{ background: meta.bg }}>
                      <Icon className="h-5 w-5" style={{ color: meta.color }} aria-hidden />
                    </span>
                    <div className="flex flex-col items-end gap-1">
                      <span className="rounded-full bg-white/5 px-2 py-0.5 text-2xs text-ink-2">{langLabel(f.language_hint)}</span>
                      {f.loaded && <span className="rounded-full bg-status-good/10 px-2 py-0.5 text-2xs text-status-good">loaded</span>}
                    </div>
                  </div>
                  <div className="mt-2.5 text-sm font-semibold capitalize" style={{ color: meta.color }}>
                    {disasterTag} · {f.id}
                  </div>
                  {vulnerable.length > 0 && (
                    <div className="mt-1 text-2xs text-ink-3">{vulnerable.map((v) => v.replace(/_/g, " ")).join(", ")}</div>
                  )}
                  <div className="mt-3 flex items-center gap-1 text-2xs text-accent-glow">
                    {busy === f.id ? "Starting…" : f.loaded ? "Replay journey" : "Play journey"} <ChevronRight className="h-3 w-3 transition-transform group-hover:translate-x-0.5" />
                  </div>
                </motion.button>
              );
            })}
          </div>
        </motion.section>
      )}
    </div>
  );
}

/* ───────────────────────────── the journey ───────────────────────────── */
function Rail({ scene, ready, jobs, onPick }: { scene: number; ready: boolean[]; jobs: Record<string, { duration_ms: number | null }>; onPick: (i: number) => void }) {
  return (
    <ol className="relative flex gap-2 overflow-x-auto pb-2 lg:flex-col lg:gap-0 lg:overflow-visible lg:pb-0" aria-label="Journey steps">
      {STEPS.map((s, i) => {
        const done = scene > i;
        const active = scene === i;
        const pending = i === scene + 1 && !ready[i];
        const ms = s.stage ? jobs[s.stage]?.duration_ms : null;
        return (
          <li key={s.label} className="relative lg:pb-7 lg:last:pb-0">
            {i < STEPS.length - 1 && (
              <span className="absolute left-[19px] top-10 hidden h-[calc(100%-2.5rem)] w-0.5 overflow-hidden rounded bg-white/10 lg:block">
                <motion.span className="block w-full bg-accent" initial={false} animate={{ height: done ? "100%" : "0%" }} transition={{ duration: 0.6 }} />
              </span>
            )}
            <button
              onClick={() => ready[i] && onPick(i)}
              disabled={!ready[i]}
              aria-current={active ? "step" : undefined}
              className={cn("relative flex min-w-[8.5rem] items-center gap-3 rounded-xl text-left transition-opacity lg:min-w-0", !ready[i] && !active && !pending && "opacity-40")}
            >
              <span
                className={cn(
                  "relative grid h-10 w-10 shrink-0 place-items-center rounded-full border transition-colors",
                  done ? "border-accent bg-accent text-white" : active ? "border-accent bg-accent/15 text-accent-glow shadow-glow" : pending ? "border-accent/40 bg-accent/5 text-accent/60" : "border-white/15 bg-white/[0.03] text-ink-3",
                )}
              >
                {active && <span className="absolute inset-0 animate-pulse-ring rounded-full border border-accent" />}
                {pending && <motion.span animate={{ opacity: [0.3, 1, 0.3] }} transition={{ duration: 1.2, repeat: Infinity }} className="absolute inset-0 rounded-full border border-accent/50" />}
                {done ? <Check className="h-4 w-4" /> : <s.icon className="h-[18px] w-[18px]" aria-hidden />}
              </span>
              <span className="min-w-0">
                <span className={cn("block text-sm font-medium", active ? "text-ink" : "text-ink-2")}>{s.label}</span>
                <span className={cn("block truncate text-2xs", pending ? "text-accent/60" : "text-ink-3")}>
                  {ms != null && done ? `${Math.round(ms)} ms` : pending ? "waiting…" : s.sub}
                </span>
              </span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}

function Journey({ reportId, onReset }: { reportId: string; onReset: () => void }) {
  const d = useJourney(reportId);
  const [scene, setScene] = useState(0);
  const [shown, setShown] = useState(0);
  const [fading, setFading] = useState(false);
  const [finished, setFinished] = useState(false);
  const [auto, setAuto] = useState(true);
  const FINALE = STEP_COUNT;

  useEffect(() => {
    setScene(0);
    setShown(0);
    setFinished(false);
  }, [reportId]);

  // Fade the old scene out, then swap. Done by hand because endless animations inside a scene
  // (the waveform) would otherwise keep an exit transition from ever completing.
  useEffect(() => {
    if (scene === shown) return;
    setFading(true);
    const t = window.setTimeout(() => {
      setShown(scene);
      setFading(false);
    }, 260);
    return () => window.clearTimeout(t);
  }, [scene, shown]);

  useEffect(() => {
    if (!auto || !finished || scene >= FINALE) return;
    // Advance when next step is ready, or when blocked (TranscribeScene shows manual-input form).
    if (scene + 1 === FINALE || d.ready[scene + 1] || (!!d.blocked && scene === 0)) {
      setScene((s) => s + 1);
      setFinished(false);
    }
  }, [auto, finished, scene, d.ready, d.blocked, FINALE]);

  const onDone = useCallback(() => setFinished(true), []);
  const pick = (i: number) => {
    setScene(i);
    setFinished(false);
  };
  const props = { d, onDone };
  const body = useMemo(() => {
    if (!d.report) return null;
    switch (shown) {
      case 0: return <HearScene key="0" {...props} />;
      case 1: return <TranscribeScene key="1" {...props} />;
      case 2: return <UnderstandScene key="2" {...props} />;
      case 3: return <LocateScene key="3" {...props} />;
      case 4: return <MatchScene key="4" {...props} />;
      case 5: return <PriorityScene key="5" {...props} />;
      case 6: return <ReplyScene key="6" {...props} />;
      default: return null;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shown, d]);

  const inc = d.incident;
  return (
    <div className="grid gap-6 lg:grid-cols-[230px_minmax(0,1fr)]">
      <aside className="lg:sticky lg:top-6 lg:self-start">
        <Rail scene={scene} ready={d.ready} jobs={d.jobs} onPick={pick} />
        <div className="mt-5 hidden gap-2 lg:flex">
          <Button size="sm" onClick={() => setAuto((a) => !a)} aria-label={auto ? "Pause autoplay" : "Resume autoplay"}>
            {auto ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />} {auto ? "Pause" : "Play"}
          </Button>
          <Button size="sm" variant="ghost" disabled={scene >= FINALE || !(scene + 1 === FINALE || d.ready[scene + 1])} onClick={() => pick(scene + 1)}>
            <FastForward className="h-3.5 w-3.5" /> Skip
          </Button>
        </div>
      </aside>

      <section className="relative min-h-[560px] overflow-hidden rounded-3xl border border-white/[0.06] bg-surface-1">
        {d.error && !d.report && <ErrorBanner offline message={d.error} />}
        <div className={cn("transition-all duration-[260ms]", fading && "translate-y-2 opacity-0 blur-[6px]")}>
          {shown < FINALE ? (
            body
          ) : (
            <motion.div key="finale" initial={{ opacity: 0, scale: 0.97 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.6, ease: EASE }} className="flex h-full min-h-[560px] flex-col items-center justify-center gap-6 p-8 text-center">
              <motion.div initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ type: "spring", delay: 0.2 }} className="grid h-20 w-20 place-items-center rounded-full bg-gradient-to-br from-status-good to-[#1a8f4a] shadow-[0_0_50px_-6px_rgba(47,208,107,0.7)]">
                <Check className="h-10 w-10 text-white" />
              </motion.div>
              <div>
                <h2 className="text-3xl font-semibold tracking-tight">{inc ? `${inc.id} is on the board` : "Report processed"}</h2>
                <p className="mt-1 text-ink-3">From a voice note to a ranked, located incident — ready for a human dispatcher.</p>
              </div>
              <div className="w-full max-w-2xl">
                <FinaleStats d={d} />
              </div>
              <div className="flex flex-wrap justify-center gap-3">
                <Link to={inc ? `/live?focus=${inc.id}` : "/live"}>
                  <Button variant="primary">
                    <MapPin className="h-4 w-4" /> See it on the live globe
                  </Button>
                </Link>
                {inc && (
                  <Link to={`/incidents/${inc.id}`}>
                    <Button>Open full details</Button>
                  </Link>
                )}
                <Button variant="ghost" onClick={onReset}>
                  <RotateCcw className="h-4 w-4" /> Try another call
                </Button>
              </div>
              <button onClick={() => pick(0)} className="text-xs text-ink-3 underline-offset-4 hover:text-ink hover:underline">
                Replay this journey
              </button>
            </motion.div>
          )}
        </div>
      </section>
    </div>
  );
}

export function JourneyPage() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const id = params.get("r");
  return id ? (
    <Journey reportId={id} onReset={() => navigate("/")} />
  ) : (
    <Start onStarted={(rid) => setParams({ r: rid })} />
  );
}
