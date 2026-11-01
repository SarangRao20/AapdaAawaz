import { useEffect, useRef, useState } from "react";
import { pollReport, triggerAck, uploadAudio } from "./api";
import type { ReportStatus } from "./api";

type Screen = "home" | "processing" | "done";
type Lang = "hi" | "mr" | "en";

const LANG_LABELS: Record<Lang, string> = { hi: "हिंदी", mr: "मराठी", en: "English" };
const PRIORITY_COLOR: Record<string, string> = {
  critical: "#ef4444", high: "#f97316", medium: "#eab308", low: "#22c55e",
};
const TERMINAL = ["processed", "needs_transcript", "failed"];

/* ── icons (inline SVG to keep bundle tiny) ─────────────────────────────── */
const MicIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-8 h-8">
    <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
    <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
    <line x1="12" y1="19" x2="12" y2="23" />
    <line x1="8" y1="23" x2="16" y2="23" />
  </svg>
);

const CheckIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="w-10 h-10">
    <polyline points="20 6 9 17 4 12" />
  </svg>
);

const VolumeIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5">
    <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
    <path d="M19.07 4.93a10 10 0 0 1 0 14.14" />
    <path d="M15.54 8.46a5 5 0 0 1 0 7.07" />
  </svg>
);

const AlertIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5">
    <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
    <line x1="12" y1="9" x2="12" y2="13" />
    <line x1="12" y1="17" x2="12.01" y2="17" />
  </svg>
);

/* ── recording format helpers ───────────────────────────────────────────── */
const MAX_SECONDS = 30; // Gnani Prisma accepts at most 30 s per request

/** MediaRecorder only produces webm/mp4/ogg; the API accepts WAV/MP3/M4A/OGG/FLAC. */
function encodeWav(samples: Float32Array, sampleRate: number): Blob {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const str = (off: number, s: string) => {
    for (let i = 0; i < s.length; i++) view.setUint8(off + i, s.charCodeAt(i));
  };
  str(0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  str(8, "WAVE");
  str(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  str(36, "data");
  view.setUint32(40, samples.length * 2, true);
  let off = 44;
  for (let i = 0; i < samples.length; i++, off += 2) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(off, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return new Blob([view], { type: "audio/wav" });
}

async function toWav(blob: Blob): Promise<Blob> {
  const ctx = new AudioContext();
  try {
    const decoded = await ctx.decodeAudioData(await blob.arrayBuffer());
    const len = decoded.length;
    const mono = new Float32Array(len);
    for (let c = 0; c < decoded.numberOfChannels; c++) {
      const ch = decoded.getChannelData(c);
      for (let i = 0; i < len; i++) mono[i] += ch[i] / decoded.numberOfChannels;
    }
    return encodeWav(mono, decoded.sampleRate);
  } finally {
    void ctx.close();
  }
}

const MIME_CANDIDATES = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/mp4",
  "audio/ogg;codecs=opus",
  "audio/ogg",
];

function pickMimeType(): string | undefined {
  if (typeof MediaRecorder === "undefined" || !MediaRecorder.isTypeSupported) return undefined;
  return MIME_CANDIDATES.find((t) => MediaRecorder.isTypeSupported(t));
}

function describeMicError(e: unknown): string {
  switch ((e as { name?: string } | null)?.name) {
    case "NotAllowedError":
    case "SecurityError":
      return "Microphone blocked. Settings → Apps → Aapda Awaaz → Permissions → allow Microphone, then try again.";
    case "NotFoundError":
    case "OverconstrainedError":
      return "No microphone found on this device.";
    case "NotReadableError":
      return "The microphone is busy in another app. Close it and try again.";
    default:
      return e instanceof Error ? e.message : "Could not start recording.";
  }
}

/* ── recorder hook ───────────────────────────────────────────────────────── */
function useRecorder() {
  const [recording, setRecording] = useState(false);
  const [wav, setWav] = useState<Blob | null>(null);
  const [preparing, setPreparing] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const mr = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  const timer = useRef<number | null>(null);
  const stopRef = useRef<() => void>(() => {});

  const stop = () => {
    if (timer.current) {
      clearInterval(timer.current);
      timer.current = null;
    }
    setRecording(false);
    if (mr.current && mr.current.state !== "inactive") mr.current.stop();
  };
  stopRef.current = stop;

  // Hard stop at the 30 s API limit.
  useEffect(() => {
    if (recording && seconds >= MAX_SECONDS) stopRef.current();
  }, [recording, seconds]);

  const start = async () => {
    setError(null);
    setWav(null);
    setSeconds(0);
    chunks.current = [];

    if (!navigator.mediaDevices?.getUserMedia) {
      setError("This app build cannot access the microphone. Install the latest APK.");
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true },
      });
      const mimeType = pickMimeType();
      const rec = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      mr.current = rec;
      rec.ondataavailable = (e) => {
        if (e.data.size > 0) chunks.current.push(e.data);
      };
      rec.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        const raw = new Blob(chunks.current, { type: rec.mimeType || "audio/webm" });
        if (raw.size === 0) {
          setError("That recording was too short. Hold the mic and speak for a few seconds.");
          return;
        }
        setPreparing(true);
        toWav(raw)
          .then((out) => setWav(out))
          .catch(() => setError("Could not process that recording. Please record again."))
          .finally(() => setPreparing(false));
      };
      rec.start(250);
      setRecording(true);
      timer.current = window.setInterval(() => setSeconds((s) => s + 1), 1000);
    } catch (e) {
      setError(describeMicError(e));
    }
  };

  return {
    recording,
    wav,
    preparing,
    seconds,
    error,
    start,
    stop,
    reset: () => {
      setWav(null);
      setSeconds(0);
      setError(null);
    },
  };
}

/* ── processing dots ─────────────────────────────────────────────────────── */
function Dots() {
  return (
    <div className="flex gap-2 items-center">
      {[0, 1, 2].map((i) => (
        <span key={i} className="bounce-dot w-2.5 h-2.5 rounded-full bg-[#f97316]" style={{ animationDelay: `${i * 0.2}s` }} />
      ))}
    </div>
  );
}

/* ── stage row ───────────────────────────────────────────────────────────── */
const STAGES = [
  { key: "transcription",   label: "Transcribing speech" },
  { key: "extraction",      label: "Extracting facts" },
  { key: "priority",        label: "Assigning priority" },
  { key: "confidence_gate", label: "Checking confidence" },
  { key: "deduplication",   label: "Checking for duplicate reports" },
];
function StageRow({ label, done }: { label: string; done: boolean }) {
  return (
    <div className="flex items-center gap-3 text-sm">
      <span className={`w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0 text-xs ${done ? "bg-[#22c55e]" : "bg-white/10"}`}>
        {done ? "✓" : ""}
      </span>
      <span className={done ? "text-[#a3a3a3]" : "text-[#f2f2f2]"}>{label}</span>
    </div>
  );
}

/* ── main ─────────────────────────────────────────────────────────────────── */
export default function App() {
  const [screen, setScreen] = useState<Screen>("home");
  const [lang, setLang] = useState<Lang>("hi");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [reportId, setReportId] = useState<string | null>(null);
  const [status, setStatus] = useState<ReportStatus | null>(null);
  const [playing, setPlaying] = useState(false);
  const audioEl = useRef<HTMLAudioElement>(null);
  const rec = useRecorder();
  const pollRef = useRef<number | null>(null);

  // Poll backend until processed
  useEffect(() => {
    if (!reportId || screen !== "processing") return;
    const poll = async () => {
      try {
        const s = await pollReport(reportId);
        setStatus(s);
        if (TERMINAL.includes(s.status)) {
          clearInterval(pollRef.current!);
          // Trigger Timbre synthesis
          if (s.status === "processed") {
            await triggerAck(reportId).catch(() => undefined);
            const s2 = await pollReport(reportId);
            setStatus(s2);
          }
          setScreen("done");
        }
      } catch {
        // transient error — keep polling
      }
    };
    void poll();
    pollRef.current = window.setInterval(poll, 1200);
    return () => clearInterval(pollRef.current!);
  }, [reportId, screen]);

  const submit = async (file?: File) => {
    setBusy(true);
    setErr(null);
    try {
      let id: string;
      if (file) {
        id = await uploadAudio(file, lang);
      } else if (rec.wav) {
        const wav = new File([rec.wav], "recording.wav", { type: "audio/wav" });
        id = await uploadAudio(wav, lang);
      } else {
        throw new Error("No audio");
      }
      setReportId(id);
      setScreen("processing");
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const reset = () => {
    setScreen("home");
    setReportId(null);
    setStatus(null);
    setErr(null);
    setPlaying(false);
    rec.reset();
  };

  /* ── HOME ─────────────────────────────────────────────────────────────── */
  if (screen === "home") {
    return (
      <div className="h-full flex flex-col">
        {/* header */}
        <div className="px-5 pt-10 pb-6 text-center">
          <div className="text-[10px] font-semibold tracking-[0.2em] uppercase text-[#f97316] mb-2">Aapda Awaaz</div>
          <h1 className="text-2xl font-bold text-[#f2f2f2] leading-tight">आपातकाल रिपोर्ट करें<br /><span className="text-[#a3a3a3] text-xl font-normal">Report an Emergency</span></h1>
        </div>

        {/* lang selector */}
        <div className="px-5 mb-5">
          <div className="flex rounded-xl overflow-hidden border border-white/10 bg-[#111]">
            {(Object.entries(LANG_LABELS) as [Lang, string][]).map(([k, v]) => (
              <button key={k} onClick={() => setLang(k)} className={`flex-1 py-2.5 text-sm font-medium transition-colors ${lang === k ? "bg-[#f97316] text-white" : "text-[#a3a3a3] hover:text-[#f2f2f2]"}`}>{v}</button>
            ))}
          </div>
        </div>

        {/* record button */}
        <div className="flex-1 flex flex-col items-center justify-center gap-6 px-5">
          <div className="relative flex items-center justify-center">
            {rec.recording && (
              <>
                <span className="pulse-ring absolute w-32 h-32 rounded-full border-2 border-[#f97316]/40" />
                <span className="pulse-ring absolute w-32 h-32 rounded-full border-2 border-[#f97316]/20" style={{ animationDelay: "0.5s" }} />
              </>
            )}
            <button
              onClick={() => (rec.recording ? rec.stop() : void rec.start())}
              disabled={rec.preparing}
              className={`relative w-28 h-28 rounded-full flex items-center justify-center transition-all shadow-lg disabled:opacity-60 ${rec.recording ? "bg-[#ef4444] scale-110" : "bg-[#f97316] hover:scale-105 active:scale-95"}`}
              aria-label={rec.recording ? "Stop recording" : "Start recording"}
            >
              <MicIcon />
            </button>
          </div>

          {rec.recording && (
            <div className="text-[#ef4444] text-sm font-mono animate-pulse">
              ● REC {String(Math.floor(rec.seconds / 60)).padStart(2, "0")}:{String(rec.seconds % 60).padStart(2, "0")} / 00:{MAX_SECONDS}
            </div>
          )}

          {rec.preparing && (
            <div className="text-sm text-[#a3a3a3]">Preparing audio…</div>
          )}

          {rec.wav && !rec.recording && !rec.preparing && (
            <div className="w-full max-w-xs space-y-3">
              <div className="text-center text-sm text-[#22c55e]">Recording ready ({rec.seconds}s)</div>
              <button
                onClick={() => void submit()}
                disabled={busy}
                className="w-full py-3.5 rounded-2xl bg-[#f97316] text-white font-semibold text-base disabled:opacity-60 active:scale-95 transition-transform"
              >
                {busy ? "Sending…" : "Send to Aapda Awaaz"}
              </button>
              <button onClick={rec.reset} className="w-full py-2.5 rounded-2xl border border-white/10 text-[#a3a3a3] text-sm">
                Record again
              </button>
            </div>
          )}

          {!rec.recording && !rec.wav && !rec.preparing && (
            <p className="text-[#525252] text-sm text-center max-w-[220px]">
              Tap the mic to record your emergency report in {LANG_LABELS[lang]}
            </p>
          )}
        </div>

        {/* upload fallback */}
        <div className="px-5 pb-8">
          <label className="block w-full py-3 rounded-2xl border border-white/10 text-[#525252] text-sm text-center cursor-pointer hover:border-white/20 hover:text-[#a3a3a3] transition-colors">
            Or upload an audio file
            <input type="file" accept="audio/*" className="hidden" onChange={(e) => e.target.files?.[0] && void submit(e.target.files[0])} />
          </label>
          {(err || rec.error) && (
            <div className="mt-3 flex items-start gap-2 text-[#ef4444] text-xs">
              <span className="mt-0.5 flex-shrink-0"><AlertIcon /></span> {err ?? rec.error}
            </div>
          )}
        </div>
      </div>
    );
  }

  /* ── PROCESSING ───────────────────────────────────────────────────────── */
  if (screen === "processing") {
    // A skipped stage is finished too: e.g. transcription when the transcript already exists.
    const doneStages = new Set(
      (status?.jobs ?? []).filter((j) => j.status === "succeeded" || j.status === "skipped").map((j) => j.stage),
    );
    return (
      <div className="h-full flex flex-col items-center justify-center px-5 gap-8">
        <div className="text-center">
          <Dots />
          <p className="mt-4 text-base font-semibold text-[#f2f2f2]">Processing your report</p>
          <p className="mt-1 text-sm text-[#525252]">Please keep this screen open…</p>
        </div>
        <div className="w-full max-w-sm space-y-3 bg-[#111] rounded-2xl border border-white/8 p-4">
          {STAGES.map((s) => <StageRow key={s.key} label={s.label} done={doneStages.has(s.key)} />)}
        </div>
        {reportId && <p className="text-[#525252] text-xs font-mono">{reportId.slice(-12)}</p>}
      </div>
    );
  }

  /* ── DONE ─────────────────────────────────────────────────────────────── */
  const s = status;
  const failed = s?.status === "failed";
  const priority = s?.priority_label ?? "low";
  const color = PRIORITY_COLOR[priority] ?? "#22c55e";

  return (
    <div className="h-full flex flex-col">
      {/* status banner */}
      <div className="px-5 pt-10 pb-5 flex flex-col items-center gap-3">
        <div className={`w-16 h-16 rounded-full flex items-center justify-center ${failed ? "bg-[#ef4444]/20" : "bg-[#22c55e]/20"}`} style={failed ? {} : { boxShadow: "0 0 40px -8px rgba(34,197,94,0.5)" }}>
          {failed ? <AlertIcon /> : <CheckIcon />}
        </div>
        <h2 className="text-lg font-bold text-[#f2f2f2]">{failed ? "Could not process" : "Report received"}</h2>
        {!failed && s?.priority_label && (
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ background: color }} />
            <span className="text-sm font-semibold uppercase tracking-wider" style={{ color }}>{priority} priority</span>
          </div>
        )}
      </div>

      {/* extracted facts */}
      {!failed && s && (
        <div className="flex-1 overflow-y-auto px-5 space-y-3 pb-4">
          {[
            ["Type", s.disaster_type],
            ["Location", s.location_text],
            ["People", s.people_count != null ? String(s.people_count) : null],
          ].filter(([, v]) => v).map(([k, v]) => (
            <div key={k} className="flex items-start justify-between gap-3 bg-[#111] rounded-xl border border-white/8 px-4 py-3">
              <span className="text-xs text-[#525252] uppercase tracking-wider mt-0.5">{k}</span>
              <span className="text-sm font-medium text-[#f2f2f2] text-right">{v}</span>
            </div>
          ))}

          {s.transcript && (
            <div className="bg-[#111] rounded-xl border border-white/8 px-4 py-3">
              <div className="text-xs text-[#525252] uppercase tracking-wider mb-2">What you said</div>
              <p className="text-sm text-[#a3a3a3] leading-relaxed">{s.transcript}</p>
            </div>
          )}

          {s.acknowledgement && (
            <div className="bg-[#111] rounded-xl border border-[#f97316]/20 px-4 py-3">
              <div className="text-xs text-[#f97316] uppercase tracking-wider mb-2">Response from Aapda Awaaz</div>
              <p className="text-sm text-[#f2f2f2] leading-relaxed">{s.acknowledgement.text}</p>
              {s.acknowledgement.audio_url && (
                <div className="mt-3">
                  <audio ref={audioEl} src={s.acknowledgement.audio_url} onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} onEnded={() => setPlaying(false)} />
                  <button
                    onClick={() => playing ? audioEl.current?.pause() : void audioEl.current?.play()}
                    className="flex items-center gap-2 text-sm text-[#f97316] font-medium"
                  >
                    <VolumeIcon /> {playing ? "Pause reply" : "Hear the reply"}
                  </button>
                </div>
              )}
            </div>
          )}

          {s.follow_up_needed && s.follow_up_questions.length > 0 && (
            <div className="bg-[#111] rounded-xl border border-[#eab308]/20 px-4 py-3">
              <div className="text-xs text-[#eab308] uppercase tracking-wider mb-2">We need more information</div>
              {s.follow_up_questions.map((q, i) => (
                <p key={i} className="text-sm text-[#f2f2f2] leading-relaxed mb-1">• {q}</p>
              ))}
            </div>
          )}
        </div>
      )}

      {/* footer */}
      <div className="px-5 pb-8 pt-2">
        <button onClick={reset} className="w-full py-3.5 rounded-2xl border border-white/10 text-[#a3a3a3] text-sm font-medium hover:border-white/20 transition-colors">
          Report another emergency
        </button>
        {reportId && <p className="text-center text-[#525252] text-xs mt-2 font-mono">{reportId.slice(-12)}</p>}
      </div>
    </div>
  );
}
