import { useEffect, useRef, useState } from "react";
import { pollReport, triggerAck, uploadAudio } from "./api";
import type { ReportStatus } from "./api";

type Screen = "home" | "processing" | "done" | "followup";
type Lang = "hi" | "mr" | "en";

const LANG_LABELS: Record<Lang, string> = { hi: "हिंदी", mr: "मराठी", en: "English" };
const PRIORITY_COLOR: Record<string, string> = {
  critical: "#ef4444", high: "#f97316", medium: "#eab308", low: "#22c55e",
};
const PRIORITY_BG: Record<string, string> = {
  critical: "rgba(239,68,68,0.12)", high: "rgba(249,115,22,0.12)",
  medium: "rgba(234,179,8,0.12)", low: "rgba(34,197,94,0.12)",
};
const TERMINAL = ["processed", "needs_transcript", "failed"];
const MAX_SECONDS = 30;

/* ── icons ─────────────────────────────────────────────────────────────────── */
const MicIcon = ({ size = 32 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
    <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
    <line x1="12" y1="19" x2="12" y2="23" />
    <line x1="8" y1="23" x2="16" y2="23" />
  </svg>
);

const StopIcon = () => (
  <svg width="28" height="28" viewBox="0 0 24 24" fill="currentColor">
    <rect x="4" y="4" width="16" height="16" rx="3" />
  </svg>
);

const PlayIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
    <polygon points="5 3 19 12 5 21 5 3" />
  </svg>
);

const PauseIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
    <rect x="6" y="4" width="4" height="16" rx="1" />
    <rect x="14" y="4" width="4" height="16" rx="1" />
  </svg>
);

const CheckCircle = () => (
  <svg width="56" height="56" viewBox="0 0 24 24" fill="none" stroke="#22c55e" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="10" />
    <polyline points="8 12 11 15 16 9" />
  </svg>
);

const AlertCircle = () => (
  <svg width="56" height="56" viewBox="0 0 24 24" fill="none" stroke="#ef4444" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="10" />
    <line x1="12" y1="8" x2="12" y2="12" />
    <line x1="12" y1="16" x2="12.01" y2="16" />
  </svg>
);

const QuestionIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="10" />
    <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
    <line x1="12" y1="17" x2="12.01" y2="17" />
  </svg>
);

const RefreshIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="1 4 1 10 7 10" />
    <path d="M3.51 15a9 9 0 1 0 .49-5" />
  </svg>
);

/* ── WAV encoder ────────────────────────────────────────────────────────────── */
function encodeWav(samples: Float32Array, sampleRate: number): Blob {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const str = (off: number, s: string) => {
    for (let i = 0; i < s.length; i++) view.setUint8(off + i, s.charCodeAt(i));
  };
  str(0, "RIFF"); view.setUint32(4, 36 + samples.length * 2, true);
  str(8, "WAVE"); str(12, "fmt ");
  view.setUint32(16, 16, true); view.setUint16(20, 1, true);
  view.setUint16(22, 1, true); view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true); view.setUint16(32, 2, true);
  view.setUint16(34, 16, true); str(36, "data");
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

const MIME_CANDIDATES = ["audio/webm;codecs=opus","audio/webm","audio/mp4","audio/ogg;codecs=opus","audio/ogg"];
function pickMimeType(): string | undefined {
  if (typeof MediaRecorder === "undefined" || !MediaRecorder.isTypeSupported) return undefined;
  return MIME_CANDIDATES.find((t) => MediaRecorder.isTypeSupported(t));
}

function describeMicError(e: unknown): string {
  switch ((e as { name?: string } | null)?.name) {
    case "NotAllowedError": case "SecurityError":
      return "Microphone blocked. Settings → Apps → Aapda Awaaz → Permissions → allow Microphone.";
    case "NotFoundError": case "OverconstrainedError":
      return "No microphone found on this device.";
    case "NotReadableError":
      return "Microphone busy in another app. Close it and try again.";
    default:
      return e instanceof Error ? e.message : "Could not start recording.";
  }
}

/* ── recorder hook ──────────────────────────────────────────────────────────── */
function useRecorder() {
  const [recording, setRecording] = useState(false);
  const [wav, setWav] = useState<Blob | null>(null);
  const [wavUrl, setWavUrl] = useState<string | null>(null);
  const [preparing, setPreparing] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const mr = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  const timer = useRef<number | null>(null);
  const stopRef = useRef<() => void>(() => {});
  const prevUrl = useRef<string | null>(null);

  const stop = () => {
    if (timer.current) { clearInterval(timer.current); timer.current = null; }
    setRecording(false);
    if (mr.current && mr.current.state !== "inactive") mr.current.stop();
  };
  stopRef.current = stop;

  useEffect(() => {
    if (recording && seconds >= MAX_SECONDS) stopRef.current();
  }, [recording, seconds]);

  // Revoke old object URL when wav changes
  useEffect(() => {
    if (prevUrl.current) URL.revokeObjectURL(prevUrl.current);
    if (wav) {
      const url = URL.createObjectURL(wav);
      prevUrl.current = url;
      setWavUrl(url);
    } else {
      setWavUrl(null);
    }
  }, [wav]);

  const start = async () => {
    setError(null); setWav(null); setSeconds(0); chunks.current = [];
    if (!navigator.mediaDevices?.getUserMedia) {
      setError("Microphone not accessible. Install the latest APK."); return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true },
      });
      const mimeType = pickMimeType();
      const rec = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      mr.current = rec;
      rec.ondataavailable = (e) => { if (e.data.size > 0) chunks.current.push(e.data); };
      rec.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        const raw = new Blob(chunks.current, { type: rec.mimeType || "audio/webm" });
        if (raw.size === 0) { setError("Recording too short. Speak for a few seconds."); return; }
        setPreparing(true);
        toWav(raw)
          .then((out) => setWav(out))
          .catch(() => setError("Could not process recording. Try again."))
          .finally(() => setPreparing(false));
      };
      rec.start(250);
      setRecording(true);
      timer.current = window.setInterval(() => setSeconds((s) => s + 1), 1000);
    } catch (e) { setError(describeMicError(e)); }
  };

  return {
    recording, wav, wavUrl, preparing, seconds, error, start, stop,
    reset: () => { setWav(null); setWavUrl(null); setSeconds(0); setError(null); },
  };
}

/* ── processing stages ──────────────────────────────────────────────────────── */
const STAGES = [
  { key: "transcription",  label: "Transcribing speech",     sub: "Gnani Prisma" },
  { key: "extraction",     label: "Extracting facts",         sub: "Rule engine" },
  { key: "priority",       label: "Assigning priority",       sub: "Gate model" },
  { key: "follow_up",      label: "Checking missing info",    sub: "Agentic" },
  { key: "acknowledgement",label: "Preparing reply",          sub: "Gnani Timbre" },
];

/* ── main ───────────────────────────────────────────────────────────────────── */
export default function App() {
  const [screen, setScreen] = useState<Screen>("home");
  const [lang, setLang] = useState<Lang>("hi");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [reportId, setReportId] = useState<string | null>(null);
  const [status, setStatus] = useState<ReportStatus | null>(null);

  // Ack audio state — tracked separately so we never interrupt mid-play
  const [ackUrl, setAckUrl] = useState<string | null>(null);
  const [ackPlaying, setAckPlaying] = useState(false);
  const [ackPlayedOnce, setAckPlayedOnce] = useState(false);
  const ackRef = useRef<HTMLAudioElement>(null);

  // Recorded audio preview
  const [previewPlaying, setPreviewPlaying] = useState(false);
  const previewRef = useRef<HTMLAudioElement>(null);

  const rec = useRecorder();
  const pollRef = useRef<number | null>(null);

  /* ── auto-play recorded audio once ready ─────────────────────────────── */
  useEffect(() => {
    if (rec.wavUrl && previewRef.current) {
      setPreviewPlaying(true);
      previewRef.current.play().catch(() => setPreviewPlaying(false));
    }
  }, [rec.wavUrl]);

  /* ── poll backend ─────────────────────────────────────────────────────── */
  useEffect(() => {
    if (!reportId || screen !== "processing") return;
    const poll = async () => {
      try {
        const s = await pollReport(reportId);
        setStatus(s);
        if (TERMINAL.includes(s.status)) {
          clearInterval(pollRef.current!);
          if (s.status === "processed") {
            // Trigger Timbre synthesis
            await triggerAck(reportId).catch(() => undefined);
            const s2 = await pollReport(reportId);
            setStatus(s2);
            if (s2.acknowledgement?.audio_url) setAckUrl(s2.acknowledgement.audio_url);
          }
          setScreen("done");
        }
      } catch { /* keep polling on transient errors */ }
    };
    void poll();
    pollRef.current = window.setInterval(poll, 1200);
    return () => clearInterval(pollRef.current!);
  }, [reportId, screen]);

  /* ── auto-play ack audio on done screen ──────────────────────────────── */
  useEffect(() => {
    if (screen === "done" && ackUrl && ackRef.current && !ackPlayedOnce) {
      // Small delay so the done screen has rendered
      const t = setTimeout(() => {
        ackRef.current?.play()
          .then(() => setAckPlaying(true))
          .catch(() => {});
      }, 600);
      return () => clearTimeout(t);
    }
  }, [screen, ackUrl, ackPlayedOnce]);

  /* ── submit ───────────────────────────────────────────────────────────── */
  const submit = async (file?: File) => {
    setBusy(true); setErr(null);
    setAckUrl(null); setAckPlaying(false); setAckPlayedOnce(false);
    try {
      let id: string;
      if (file) {
        id = await uploadAudio(file, lang);
      } else if (rec.wav) {
        id = await uploadAudio(new File([rec.wav], "recording.wav", { type: "audio/wav" }), lang);
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

  /* ── submit follow-up answer ─────────────────────────────────────────── */
  const submitFollowUp = async () => {
    if (!rec.wav) return;
    setBusy(true); setErr(null);
    setAckUrl(null); setAckPlaying(false); setAckPlayedOnce(false);
    try {
      const id = await uploadAudio(new File([rec.wav], "followup.wav", { type: "audio/wav" }), lang);
      setReportId(id);
      setStatus(null);
      setScreen("processing");
      rec.reset();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const reset = () => {
    setScreen("home"); setReportId(null); setStatus(null); setErr(null);
    setAckUrl(null); setAckPlaying(false); setAckPlayedOnce(false);
    rec.reset();
  };

  /* ── HOME ─────────────────────────────────────────────────────────────── */
  if (screen === "home") {
    return (
      <div className="h-full flex flex-col overflow-hidden">
        {/* header */}
        <div className="px-6 pt-12 pb-4 text-center">
          <div className="inline-flex items-center gap-2 mb-3">
            <div className="w-2 h-2 rounded-full bg-[#f97316] shadow-[0_0_8px_#f97316]" />
            <span className="text-[10px] font-bold tracking-[0.25em] uppercase text-[#f97316]">Aapda Awaaz</span>
            <div className="w-2 h-2 rounded-full bg-[#f97316] shadow-[0_0_8px_#f97316]" />
          </div>
          <h1 className="text-2xl font-bold text-[#f2f2f2] leading-snug">
            आपातकाल रिपोर्ट करें
          </h1>
          <p className="text-sm text-[#525252] mt-1">Report an Emergency</p>
        </div>

        {/* lang selector */}
        <div className="px-6 mb-6">
          <div className="flex rounded-2xl overflow-hidden border border-white/8 bg-[#111]">
            {(Object.entries(LANG_LABELS) as [Lang, string][]).map(([k, v]) => (
              <button
                key={k}
                onClick={() => setLang(k)}
                className={`flex-1 py-3 text-sm font-semibold transition-all ${lang === k ? "bg-[#f97316] text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.15)]" : "text-[#525252] hover:text-[#a3a3a3]"}`}
              >
                {v}
              </button>
            ))}
          </div>
        </div>

        {/* record area */}
        <div className="flex-1 flex flex-col items-center justify-center gap-5 px-6">
          {/* mic button */}
          <div className="relative flex items-center justify-center">
            {rec.recording && (
              <>
                <span className="pulse-ring absolute w-36 h-36 rounded-full border border-[#ef4444]/30" />
                <span className="pulse-ring absolute w-36 h-36 rounded-full border border-[#ef4444]/15" style={{ animationDelay: "0.6s" }} />
              </>
            )}
            <button
              onClick={() => rec.recording ? rec.stop() : void rec.start()}
              disabled={rec.preparing}
              className={`relative w-32 h-32 rounded-full flex items-center justify-center transition-all duration-200 disabled:opacity-50
                ${rec.recording
                  ? "bg-[#ef4444] shadow-[0_0_48px_-6px_#ef4444] scale-105"
                  : "bg-[#f97316] shadow-[0_0_48px_-8px_#f97316] hover:scale-105 active:scale-95"
                }`}
              aria-label={rec.recording ? "Stop recording" : "Start recording"}
            >
              {rec.recording ? <StopIcon /> : <MicIcon size={34} />}
            </button>
          </div>

          {/* timer */}
          {rec.recording && (
            <div className="flex items-center gap-2 text-[#ef4444] text-sm font-mono">
              <span className="w-2 h-2 rounded-full bg-[#ef4444] animate-pulse" />
              {String(Math.floor(rec.seconds / 60)).padStart(2, "0")}:{String(rec.seconds % 60).padStart(2, "0")}
              <span className="text-[#525252]">/ 00:{MAX_SECONDS}</span>
            </div>
          )}

          {rec.preparing && (
            <div className="flex items-center gap-2 text-[#a3a3a3] text-sm">
              <span className="spin w-4 h-4 rounded-full border-2 border-[#f97316] border-t-transparent" />
              Encoding audio…
            </div>
          )}

          {/* recorded audio preview */}
          {rec.wavUrl && !rec.recording && !rec.preparing && (
            <div className="w-full max-w-xs space-y-3">
              {/* preview player */}
              <div className="flex items-center gap-3 bg-[#111] border border-white/8 rounded-2xl px-4 py-3">
                <audio
                  ref={previewRef}
                  src={rec.wavUrl}
                  onPlay={() => setPreviewPlaying(true)}
                  onPause={() => setPreviewPlaying(false)}
                  onEnded={() => setPreviewPlaying(false)}
                />
                <button
                  onClick={() => previewPlaying ? previewRef.current?.pause() : void previewRef.current?.play()}
                  className="w-9 h-9 rounded-full bg-[#f97316]/15 border border-[#f97316]/30 flex items-center justify-center text-[#f97316] flex-shrink-0"
                >
                  {previewPlaying ? <PauseIcon /> : <PlayIcon />}
                </button>
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-medium text-[#f2f2f2]">Preview recording</div>
                  <div className="text-xs text-[#525252] mt-0.5">{rec.seconds}s · WAV</div>
                </div>
              </div>

              <button
                onClick={() => void submit()}
                disabled={busy}
                className="w-full py-4 rounded-2xl bg-[#f97316] text-white font-bold text-base shadow-[0_4px_24px_-4px_rgba(249,115,22,0.5)] disabled:opacity-50 active:scale-[0.98] transition-transform"
              >
                {busy ? "Sending…" : "Send Report"}
              </button>
              <button
                onClick={rec.reset}
                className="w-full py-3 rounded-2xl border border-white/8 text-[#525252] text-sm flex items-center justify-center gap-2 hover:text-[#a3a3a3] transition-colors"
              >
                <RefreshIcon /> Record again
              </button>
            </div>
          )}

          {!rec.recording && !rec.wav && !rec.preparing && (
            <p className="text-[#525252] text-sm text-center max-w-[200px] leading-relaxed">
              Tap the mic and speak your emergency in {LANG_LABELS[lang]}
            </p>
          )}
        </div>

        {/* upload fallback + errors */}
        <div className="px-6 pb-10">
          <label className="block w-full py-3.5 rounded-2xl border border-white/8 text-[#525252] text-sm text-center cursor-pointer hover:border-white/15 hover:text-[#a3a3a3] transition-colors">
            Or upload an audio file
            <input type="file" accept="audio/*" className="hidden" onChange={(e) => e.target.files?.[0] && void submit(e.target.files[0])} />
          </label>
          {(err || rec.error) && (
            <div className="mt-3 bg-[#ef4444]/10 border border-[#ef4444]/20 rounded-xl px-4 py-3 text-[#ef4444] text-xs leading-relaxed">
              {err ?? rec.error}
            </div>
          )}
        </div>
      </div>
    );
  }

  /* ── PROCESSING ───────────────────────────────────────────────────────── */
  if (screen === "processing") {
    const jobs = (status as any)?.jobs ?? [];
    const doneStages = new Set(jobs.filter((j: any) => j.status === "succeeded").map((j: any) => j.stage));
    return (
      <div className="h-full flex flex-col items-center justify-center px-6 gap-8">
        <div className="text-center">
          {/* animated ring */}
          <div className="relative w-20 h-20 mx-auto mb-6">
            <div className="absolute inset-0 rounded-full border-2 border-[#f97316]/20" />
            <div className="absolute inset-0 rounded-full border-2 border-transparent border-t-[#f97316] spin" />
            <div className="absolute inset-3 rounded-full bg-[#f97316]/10 flex items-center justify-center">
              <MicIcon size={22} />
            </div>
          </div>
          <p className="text-base font-semibold text-[#f2f2f2]">Analysing your report</p>
          <p className="mt-1 text-xs text-[#525252]">Gnani AI pipeline running…</p>
        </div>

        <div className="w-full max-w-sm space-y-1">
          {STAGES.map((stage, i) => {
            const done = doneStages.has(stage.key);
            const active = !done && i === Array.from({ length: STAGES.length }, (_, j) => STAGES[j].key).findIndex(k => !doneStages.has(k));
            return (
              <div
                key={stage.key}
                className={`flex items-center gap-3 px-4 py-3 rounded-xl transition-all ${done ? "bg-[#22c55e]/8" : active ? "bg-[#f97316]/8" : "bg-transparent"}`}
              >
                <div className={`w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0 text-xs font-bold transition-all
                  ${done ? "bg-[#22c55e] text-white" : active ? "bg-[#f97316]/20 border border-[#f97316]/50" : "bg-white/6 border border-white/10"}`}>
                  {done ? "✓" : active ? <span className="w-2 h-2 rounded-full bg-[#f97316] animate-pulse block" /> : ""}
                </div>
                <div className="flex-1 min-w-0">
                  <div className={`text-sm ${done ? "text-[#525252]" : active ? "text-[#f2f2f2] font-medium" : "text-[#525252]"}`}>
                    {stage.label}
                  </div>
                  <div className="text-[10px] text-[#525252] mt-0.5">{stage.sub}</div>
                </div>
              </div>
            );
          })}
        </div>

        {reportId && (
          <p className="text-[#525252] text-[11px] font-mono tracking-wider">
            REF {reportId.slice(-12).toUpperCase()}
          </p>
        )}
      </div>
    );
  }

  /* ── shared done/followup state ─────────────────────────────────────── */
  const s = status;
  const failed = s?.status === "failed" || s?.status === "needs_transcript";
  const priority = s?.priority_label ?? "low";
  const pColor = PRIORITY_COLOR[priority] ?? "#22c55e";
  const pBg = PRIORITY_BG[priority] ?? "rgba(34,197,94,0.12)";
  const hasFollowUp = s?.follow_up_needed && (s?.follow_up_questions?.length ?? 0) > 0;

  /* ── FOLLOW-UP RECORDING OVERLAY ─────────────────────────────────────── */
  if (screen === "followup") {
    return (
      <div className="h-full flex flex-col items-center justify-center px-6 gap-6"
           style={{ background: "radial-gradient(ellipse at center, rgba(234,179,8,0.06) 0%, transparent 70%)" }}>
        <div className="text-center">
          <div className="text-[10px] font-bold tracking-[0.25em] uppercase text-[#eab308] mb-2">Answer the question</div>
          {s?.follow_up_questions?.[0] && (
            <p className="text-base text-[#f2f2f2] font-medium leading-snug max-w-[260px] mx-auto">
              "{s.follow_up_questions[0]}"
            </p>
          )}
        </div>

        {/* mic */}
        <div className="relative flex items-center justify-center">
          {rec.recording && (
            <>
              <span className="pulse-ring absolute w-36 h-36 rounded-full border border-[#eab308]/30" />
              <span className="pulse-ring absolute w-36 h-36 rounded-full border border-[#eab308]/15" style={{ animationDelay: "0.6s" }} />
            </>
          )}
          <button
            onClick={() => rec.recording ? rec.stop() : void rec.start()}
            disabled={rec.preparing}
            className={`relative w-28 h-28 rounded-full flex items-center justify-center transition-all duration-200 disabled:opacity-50
              ${rec.recording
                ? "bg-[#ef4444] shadow-[0_0_48px_-6px_#ef4444] scale-105"
                : "bg-[#eab308] shadow-[0_0_48px_-8px_rgba(234,179,8,0.7)] hover:scale-105 active:scale-95"
              }`}
          >
            {rec.recording ? <StopIcon /> : <MicIcon size={30} />}
          </button>
        </div>

        {rec.recording && (
          <div className="flex items-center gap-2 text-[#ef4444] text-sm font-mono">
            <span className="w-2 h-2 rounded-full bg-[#ef4444] animate-pulse" />
            {String(Math.floor(rec.seconds / 60)).padStart(2, "0")}:{String(rec.seconds % 60).padStart(2, "0")}
            <span className="text-[#525252]">/ 00:{MAX_SECONDS}</span>
          </div>
        )}

        {rec.preparing && (
          <div className="flex items-center gap-2 text-[#a3a3a3] text-sm">
            <span className="spin w-4 h-4 rounded-full border-2 border-[#eab308] border-t-transparent" />
            Encoding…
          </div>
        )}

        {rec.wav && !rec.recording && !rec.preparing && (
          <div className="w-full max-w-xs space-y-3">
            <div className="flex items-center gap-3 bg-[#111] border border-white/8 rounded-2xl px-4 py-3">
              <audio
                ref={previewRef}
                src={rec.wavUrl ?? undefined}
                onPlay={() => setPreviewPlaying(true)}
                onPause={() => setPreviewPlaying(false)}
                onEnded={() => setPreviewPlaying(false)}
              />
              <button
                onClick={() => previewPlaying ? previewRef.current?.pause() : void previewRef.current?.play()}
                className="w-9 h-9 rounded-full bg-[#eab308]/15 border border-[#eab308]/30 flex items-center justify-center text-[#eab308] flex-shrink-0"
              >
                {previewPlaying ? <PauseIcon /> : <PlayIcon />}
              </button>
              <div className="flex-1">
                <div className="text-xs font-medium text-[#f2f2f2]">Your answer</div>
                <div className="text-xs text-[#525252] mt-0.5">{rec.seconds}s</div>
              </div>
            </div>
            <button
              onClick={() => void submitFollowUp()}
              disabled={busy}
              className="w-full py-4 rounded-2xl bg-[#eab308] text-black font-bold text-base shadow-[0_4px_24px_-4px_rgba(234,179,8,0.5)] disabled:opacity-50 active:scale-[0.98] transition-transform"
            >
              {busy ? "Sending…" : "Send Answer"}
            </button>
            <button
              onClick={() => rec.reset()}
              className="w-full py-3 rounded-2xl border border-white/8 text-[#525252] text-sm flex items-center justify-center gap-2"
            >
              <RefreshIcon /> Record again
            </button>
          </div>
        )}

        {!rec.wav && !rec.recording && !rec.preparing && (
          <button
            onClick={() => { setScreen("done"); rec.reset(); }}
            className="text-[#525252] text-sm underline-offset-2 underline"
          >
            Cancel
          </button>
        )}
        {err && (
          <div className="bg-[#ef4444]/10 border border-[#ef4444]/20 rounded-xl px-4 py-3 text-[#ef4444] text-xs w-full max-w-xs">
            {err}
          </div>
        )}
      </div>
    );
  }

  /* ── DONE ─────────────────────────────────────────────────────────────── */

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* status header */}
      <div className="px-6 pt-10 pb-5 flex flex-col items-center gap-3 flex-shrink-0">
        <div className={failed ? "" : "drop-shadow-[0_0_24px_rgba(34,197,94,0.3)]"}>
          {failed ? <AlertCircle /> : <CheckCircle />}
        </div>
        <div className="text-center">
          <h2 className="text-lg font-bold text-[#f2f2f2]">
            {failed ? "Could not process" : "Report received"}
          </h2>
          {!failed && s?.priority_label && (
            <div
              className="inline-flex items-center gap-2 mt-2 px-3 py-1 rounded-full text-xs font-bold uppercase tracking-widest"
              style={{ background: pBg, color: pColor }}
            >
              <span className="w-1.5 h-1.5 rounded-full" style={{ background: pColor, boxShadow: `0 0 6px ${pColor}` }} />
              {priority} priority
            </div>
          )}
        </div>
      </div>

      {/* scrollable content */}
      <div className="flex-1 overflow-y-auto px-5 space-y-2.5 pb-4">
        {/* ack audio — always shown prominently if available */}
        {!failed && s?.acknowledgement && (
          <div className="rounded-2xl border border-[#f97316]/25 overflow-hidden"
               style={{ background: "linear-gradient(135deg, rgba(249,115,22,0.08), rgba(249,115,22,0.04))" }}>
            <div className="px-4 pt-4 pb-3">
              <div className="text-[10px] font-bold tracking-[0.18em] uppercase text-[#f97316] mb-2">
                Response from Aapda Awaaz
              </div>
              <p className="text-sm text-[#e5e5e5] leading-relaxed">{s.acknowledgement.text}</p>
            </div>
            {s.acknowledgement.audio_url && (
              <div className="px-4 pb-4">
                <audio
                  ref={ackRef}
                  src={ackUrl ?? s.acknowledgement.audio_url}
                  onPlay={() => setAckPlaying(true)}
                  onPause={() => setAckPlaying(false)}
                  onEnded={() => { setAckPlaying(false); setAckPlayedOnce(true); }}
                />
                <button
                  onClick={() => {
                    if (ackPlaying) {
                      ackRef.current?.pause();
                    } else {
                      ackRef.current?.play().then(() => setAckPlaying(true)).catch(() => {});
                    }
                  }}
                  className={`w-full flex items-center gap-3 py-3 px-4 rounded-xl border transition-all active:scale-[0.98]
                    ${ackPlaying
                      ? "bg-[#f97316]/20 border-[#f97316]/40 text-[#f97316]"
                      : "bg-[#f97316]/10 border-[#f97316]/20 text-[#f97316] hover:bg-[#f97316]/15"
                    }`}
                >
                  <div className={`w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0 ${ackPlaying ? "bg-[#f97316] text-white" : "bg-[#f97316]/20"}`}>
                    {ackPlaying ? <PauseIcon /> : <PlayIcon />}
                  </div>
                  <div className="text-left">
                    <div className="text-sm font-semibold">{ackPlaying ? "Playing…" : ackPlayedOnce ? "Play again" : "Hear the reply"}</div>
                    <div className="text-[10px] text-[#f97316]/60 mt-0.5">Gnani Timbre voice response</div>
                  </div>
                  {ackPlaying && (
                    <div className="ml-auto flex gap-1 items-end h-5">
                      {[0,1,2,3].map(i => (
                        <div key={i} className="w-1 bg-[#f97316] rounded-full audio-bar"
                             style={{ height: `${60 + i * 10}%`, animationDelay: `${i * 0.1}s` }} />
                      ))}
                    </div>
                  )}
                </button>
              </div>
            )}
          </div>
        )}

        {/* follow-up questions + record answer */}
        {!failed && hasFollowUp && (
          <div className="rounded-2xl border border-[#eab308]/25 overflow-hidden"
               style={{ background: "linear-gradient(135deg, rgba(234,179,8,0.08), rgba(234,179,8,0.04))" }}>
            <div className="px-4 pt-4 pb-3">
              <div className="flex items-center gap-2 mb-3">
                <QuestionIcon />
                <span className="text-[10px] font-bold tracking-[0.18em] uppercase text-[#eab308]">We need more information</span>
              </div>
              {s!.follow_up_questions.map((q, i) => (
                <div key={i} className="flex items-start gap-2 mb-2 last:mb-0">
                  <span className="text-[#eab308] font-bold text-sm flex-shrink-0 mt-0.5">{i + 1}.</span>
                  <p className="text-sm text-[#e5e5e5] leading-relaxed">{q}</p>
                </div>
              ))}
            </div>

            {/* inline follow-up recorder */}
            {screen === "done" && (
              <div className="px-4 pb-4 border-t border-[#eab308]/15 pt-3">
                {!rec.wav && !rec.recording && !rec.preparing && (
                  <button
                    onClick={() => { setScreen("followup"); void rec.start(); }}
                    className="w-full flex items-center justify-center gap-2 py-3 rounded-xl bg-[#eab308]/15 border border-[#eab308]/30 text-[#eab308] text-sm font-semibold active:scale-[0.98] transition-all"
                  >
                    <MicIcon size={16} /> Answer with voice
                  </button>
                )}
              </div>
            )}
          </div>
        )}

        {/* extracted facts */}
        {!failed && s && (
          <>
            {[
              { label: "Disaster type", value: s.disaster_type },
              { label: "Location", value: s.location_text },
              { label: "People affected", value: s.people_count != null ? String(s.people_count) : null },
            ].filter(({ value }) => value).map(({ label, value }) => (
              <div key={label} className="flex items-center justify-between gap-3 bg-[#111] rounded-xl border border-white/8 px-4 py-3">
                <span className="text-[10px] font-bold text-[#525252] uppercase tracking-wider">{label}</span>
                <span className="text-sm font-semibold text-[#f2f2f2]">{value}</span>
              </div>
            ))}
          </>
        )}

        {/* transcript */}
        {s?.transcript && (
          <div className="bg-[#111] rounded-xl border border-white/8 px-4 py-3">
            <div className="text-[10px] font-bold text-[#525252] uppercase tracking-wider mb-2">What you said</div>
            <p className="text-sm text-[#a3a3a3] leading-relaxed">{s.transcript}</p>
          </div>
        )}
      </div>

      {/* footer */}
      <div className="px-5 pb-8 pt-2 flex-shrink-0">
        <button
          onClick={reset}
          className="w-full py-4 rounded-2xl bg-[#111] border border-white/8 text-[#a3a3a3] text-sm font-semibold hover:border-white/15 transition-colors active:scale-[0.98]"
        >
          Report another emergency
        </button>
        {reportId && (
          <p className="text-center text-[#525252] text-[10px] mt-2 font-mono tracking-wider">
            REF {reportId.slice(-12).toUpperCase()}
          </p>
        )}
      </div>
    </div>
  );
}

/* ── follow-up recording overlay ────────────────────────────────────────────── */
// This screen is reached when user taps "Answer with voice" on the done screen.
// It reuses useRecorder state from the parent; we just need the submit logic.
// NOTE: The "followup" screen is handled inline via the screen state — when
// screen === "followup" the done screen shows a full-screen overlay instead.
// Actually screen is set to "followup" only temporarily while recording; once
// rec.wav is ready, we show the confirm UI overlaid on done. We handle this
// by checking screen === "followup" and showing an overlay on top of "done".
