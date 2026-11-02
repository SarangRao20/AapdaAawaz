import { Megaphone, Play, Send, Square } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import { cn } from "../lib/cn";
import { label } from "../lib/format";
import { getReviewer } from "../lib/reviewer";
import type { VoiceAlertOptions } from "../lib/types";
import { Button, Card, CardHeader, ErrorBanner } from "./ui";

const LANGUAGES = [
  { code: "hi", name: "हिंदी" },
  { code: "mr", name: "मराठी" },
  { code: "mixed", name: "Hinglish" },
  { code: "en", name: "English" },
];

/** A dispatcher hears a fixed safety message in each language, then sends it to the people who reported this. */
export function VoiceAlerts({ incidentId }: { incidentId: string }) {
  const [options, setOptions] = useState<VoiceAlertOptions | null>(null);
  const [template, setTemplate] = useState("");
  const [language, setLanguage] = useState("hi");
  const [playing, setPlaying] = useState(false);
  const [loadingAudio, setLoadingAudio] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const audio = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    setOptions(null);
    api.alertOptions(incidentId)
      .then((loaded) => {
        if (cancelled) return;
        setOptions(loaded);
        setTemplate(loaded.templates[0]?.id ?? "");
      })
      .catch((e: Error) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
      audio.current?.pause();
    };
  }, [incidentId]);

  const chosen = options?.templates.find((t) => t.id === template);

  function stop() {
    audio.current?.pause();
    setPlaying(false);
  }

  function preview() {
    if (playing) {
      stop();
      return;
    }
    setError(null);
    setLoadingAudio(true);
    const player = new Audio(api.alertPreviewUrl(incidentId, template, language));
    audio.current = player;
    player.onplaying = () => {
      setLoadingAudio(false);
      setPlaying(true);
    };
    player.onended = () => setPlaying(false);
    player.onerror = () => {
      setLoadingAudio(false);
      setPlaying(false);
      setError("Timbre couldn't speak this just now. Check the provider status in Settings.");
    };
    void player.play().catch(() => undefined);
  }

  async function send() {
    setBusy(true);
    setError(null);
    try {
      const r = await api.sendAlert(incidentId, template, getReviewer() || "dispatcher");
      const spoken = r.voice === r.sent ? "with a voice note" : `${r.voice} with a voice note`;
      setResult(
        r.sent === 0
          ? "Nobody received this."
          : `Sent to ${r.sent} ${r.sent === 1 ? "person" : "people"} ${spoken}${r.failed ? `. ${r.failed} couldn't be reached.` : "."}`,
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
      setConfirming(false);
    }
  }

  if (!options) return error ? <ErrorBanner message={error} /> : null;
  const { total, languages } = options.recipients;
  const breakdown = Object.entries(languages).map(([code, n]) => `${n} ${label(code)}`).join(", ");

  return (
    <Card>
      <CardHeader
        title={
          <span className="flex items-center gap-2">
            <Megaphone className="h-4 w-4 text-accent" aria-hidden /> Voice alert
          </span>
        }
        subtitle="Fixed safety wording, spoken by Gnani Timbre in each person's language"
      />
      <div className="space-y-3 p-4">
        <div className="flex flex-wrap gap-1.5">
          {options.templates.map((t) => (
            <button
              key={t.id}
              type="button"
              aria-pressed={template === t.id}
              onClick={() => {
                stop();
                setResult(null);
                setConfirming(false);
                setTemplate(t.id);
              }}
              className={cn("rounded-lg border px-2.5 py-1.5 text-xs transition-colors", template === t.id ? "border-accent/60 bg-accent/10 text-ink" : "border-line text-ink-2 hover:bg-surface-2")}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div className="flex gap-1" role="group" aria-label="Language to preview">
          {LANGUAGES.map((l) => (
            <button
              key={l.code}
              type="button"
              aria-pressed={language === l.code}
              onClick={() => {
                stop();
                setLanguage(l.code);
              }}
              className={cn("flex-1 rounded-md px-2 py-1 text-xs transition-colors", language === l.code ? "bg-surface-3 font-medium text-ink" : "text-ink-3 hover:text-ink")}
            >
              {l.name}
            </button>
          ))}
        </div>

        {chosen && (
          <p className="rounded-md border border-line bg-surface-2 px-3 py-2 text-sm leading-relaxed text-ink" lang={language === "mixed" ? "hi" : language}>
            {chosen.text[language]}
          </p>
        )}

        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={preview} busy={loadingAudio}>
            {playing ? <Square className="h-3.5 w-3.5" aria-hidden /> : <Play className="h-3.5 w-3.5" aria-hidden />}
            {playing ? "Stop" : "Hear it"}
          </Button>
          {total > 0 && !confirming && (
            <Button variant="primary" onClick={() => { setResult(null); setConfirming(true); }}>
              <Send className="h-3.5 w-3.5" aria-hidden /> Send to {total} on Telegram
            </Button>
          )}
          {confirming && (
            <>
              <Button variant="danger" busy={busy} onClick={() => void send()}>
                Confirm: send to {total} now
              </Button>
              <Button disabled={busy} onClick={() => setConfirming(false)}>
                Cancel
              </Button>
            </>
          )}
        </div>

        <p className="text-2xs text-ink-3">
          {total > 0
            ? `Goes only to people who reported this incident on Telegram: ${breakdown}.`
            : "Nobody reported this incident on Telegram, so there's no one to send it to. You can still hear each language."}
        </p>
        {result && <p className="text-xs text-status-good" role="status">{result}</p>}
        {error && <ErrorBanner message={error} />}
      </div>
    </Card>
  );
}
