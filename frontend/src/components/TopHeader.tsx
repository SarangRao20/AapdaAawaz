import { useEffect, useState } from "react";
import { WifiOff } from "lucide-react";
import { cn } from "../lib/cn";
import type { ProviderStatus } from "../lib/types";
import { usePoll } from "../lib/usePoll";
import { api } from "../lib/api";

type PipelineTone = "good" | "warning" | "unknown";

function pipelineRows(p: ProviderStatus | null): { label: string; tone: PipelineTone }[] {
  if (!p) {
    return ["STT", "TTS", "Extraction"].map((label) => ({ label, tone: "unknown" }));
  }
  const stt = p.speech_to_text.mode;
  return [
    stt === "real"
      ? { label: "Prisma · STT", tone: "good" }
      : { label: `${stt === "mock" ? "Mock" : "Unavailable"} · STT`, tone: "warning" },
    p.text_to_speech.mode === "real"
      ? { label: "Timbre · TTS", tone: "good" }
      : { label: "Text only · TTS", tone: "warning" },
    { label: `${p.extraction.mode === "real" ? "Evon" : "Rule-based"} · Extraction`, tone: "good" },
  ];
}

function useOnline() {
  const [online, setOnline] = useState(typeof navigator === "undefined" ? true : navigator.onLine);
  useEffect(() => {
    const up = () => setOnline(true);
    const down = () => setOnline(false);
    window.addEventListener("online", up);
    window.addEventListener("offline", down);
    return () => {
      window.removeEventListener("online", up);
      window.removeEventListener("offline", down);
    };
  }, []);
  return online;
}

export function TopHeader() {
  const health = usePoll(api.health, 10000);
  const online = useOnline();
  const stt = health.data?.providers.speech_to_text;
  const apiDown = !!health.error;
  const tone = apiDown ? "bad" : !online ? "offline" : "good";
  const text = apiDown
    ? "Backend unreachable"
    : !online
      ? "Offline mode · local data"
      : `STT ${stt?.mode === "real" ? "Gnani Prisma" : stt?.mode === "mock" ? "mock" : (stt?.mode ?? "…")}`;

  const rows = pipelineRows(health.error ? null : (health.data?.providers ?? null));

  return (
    <div className="sticky top-0 z-50 border-b border-neutral-800 bg-bg/60 px-4 py-2.5 backdrop-blur-xl">
      <div className="flex items-center justify-between gap-3">
        <div className="text-2xs text-ink-3">
          <span className="inline-flex items-center gap-2">
            <span className="relative flex h-2 w-2">
              <span
                className={cn(
                  "absolute inline-flex h-full w-full rounded-full",
                  tone === "good" && "animate-pulse-ring bg-status-good",
                )}
              />
              <span
                className={cn(
                  "relative inline-flex h-2 w-2 rounded-full",
                  tone === "good" && "bg-status-good",
                  tone === "offline" && "bg-status-warning",
                  tone === "bad" && "bg-status-critical",
                )}
              />
            </span>
            <span className="font-medium">{text}</span>
          </span>
        </div>
        <div className="flex items-center gap-3">
          {rows.map(({ label, tone: t }) => (
            <div key={label} className="flex items-center gap-1.5 text-2xs text-ink-2">
              <span
                className={cn(
                  "h-1.5 w-1.5 rounded-full shrink-0",
                  t === "good" && "bg-status-good",
                  t === "warning" && "bg-status-warning",
                  t === "unknown" && "bg-ink-3/40",
                )}
              />
              <span className="hidden sm:inline">{label}</span>
            </div>
          ))}
          {!online && <WifiOff className="h-3.5 w-3.5 text-status-warning" aria-hidden />}
        </div>
      </div>
    </div>
  );
}
