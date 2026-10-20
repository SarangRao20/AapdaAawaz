import { Mic, Square, Upload } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { blobToWav } from "../lib/wav";
import { Button, ErrorBanner } from "./ui";

const MAX_SECONDS = 30; // Gnani Prisma's documented per-request limit

export function AudioRecorder({ onRecorded, disabled }: { onRecorded: (wav: Blob) => Promise<void>; disabled?: boolean }) {
  const [state, setState] = useState<"idle" | "recording" | "converting" | "ready" | "uploading">("idle");
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [wav, setWav] = useState<Blob | null>(null);
  const [url, setUrl] = useState<string | null>(null);
  const rec = useRef<MediaRecorder | null>(null);
  const timer = useRef<number | null>(null);
  const supported = typeof navigator !== "undefined" && !!navigator.mediaDevices?.getUserMedia && typeof MediaRecorder !== "undefined";

  useEffect(() => () => {
    if (timer.current) window.clearInterval(timer.current);
    if (url) URL.revokeObjectURL(url);
  }, [url]);

  async function start() {
    setError(null);
    setWav(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const chunks: Blob[] = [];
      const mr = new MediaRecorder(stream);
      mr.ondataavailable = (e) => e.data.size && chunks.push(e.data);
      mr.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        if (timer.current) window.clearInterval(timer.current);
        setState("converting");
        try {
          const out = await blobToWav(new Blob(chunks, { type: mr.mimeType }));
          setWav(out);
          setUrl(URL.createObjectURL(out));
          setState("ready");
        } catch (e) {
          setError(`Could not convert the recording to WAV: ${e instanceof Error ? e.message : e}`);
          setState("idle");
        }
      };
      rec.current = mr;
      mr.start();
      setSeconds(0);
      setState("recording");
      const t0 = Date.now();
      timer.current = window.setInterval(() => {
        const s = Math.floor((Date.now() - t0) / 1000);
        setSeconds(s);
        if (s >= MAX_SECONDS - 1) mr.state === "recording" && mr.stop();
      }, 250);
    } catch (e) {
      setError(e instanceof DOMException && e.name === "NotAllowedError" ? "Microphone permission was denied." : `Microphone unavailable: ${e instanceof Error ? e.message : e}`);
      setState("idle");
    }
  }

  if (!supported)
    return <p className="text-xs text-ink-3">This browser does not support microphone recording. Upload a file or use the synthetic demo data instead.</p>;

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        {state !== "recording" ? (
          <Button onClick={start} disabled={disabled || state === "converting" || state === "uploading"}>
            <Mic className="h-4 w-4" /> Record voice note
          </Button>
        ) : (
          <Button variant="danger" onClick={() => rec.current?.stop()}>
            <Square className="h-4 w-4" /> Stop ({seconds}s / {MAX_SECONDS}s)
          </Button>
        )}
        {state === "converting" && <span className="text-xs text-ink-3">Converting to 16 kHz WAV…</span>}
        {wav && state !== "recording" && (
          <Button
            variant="primary"
            busy={state === "uploading"}
            onClick={async () => {
              setState("uploading");
              try {
                await onRecorded(wav);
                setWav(null);
                setState("idle");
              } catch (e) {
                setError(e instanceof Error ? e.message : String(e));
                setState("ready");
              }
            }}
          >
            <Upload className="h-4 w-4" /> Submit recording
          </Button>
        )}
      </div>
      {url && wav && <audio controls src={url} className="h-8 w-full" />}
      {error && <ErrorBanner message={error} />}
    </div>
  );
}
