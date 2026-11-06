import { motion } from "framer-motion";
import { Check, Loader2, Mic, Phone, PhoneOff, Volume2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { PriorityBadge } from "../components/badges";
import { Button, Card, ErrorBanner } from "../components/ui";
import { cn } from "../lib/cn";
import { label } from "../lib/format";
import { LANGUAGE_LIST } from "../lib/languages";
import { LiveCallClient, type CallFacts, type CallLanguage, type CallMetrics, type CallState } from "../lib/liveCall";
import type { Priority } from "../lib/types";

const LANGUAGES: { code: CallLanguage; name: string; hint: string }[] = LANGUAGE_LIST.map((l) => ({ code: l.code, name: l.name, hint: l.english }));

const STATE_TEXT: Record<CallState, string> = {
  connecting: "Connecting to Gnani…",
  listening: "Listening",
  thinking: "Noting what you said",
  speaking: "Speaking",
  ended: "Call ended",
};

interface Line {
  speaker: "caller" | "assistant";
  text: string;
}

const NO_FACTS: CallFacts = { place: null, disaster: null, people: null, priority: null, score: null, report_id: null, needs_review: false };

function GnaniStep({ icon: Icon, name, role, active }: { icon: typeof Mic; name: string; role: string; active: boolean }) {
  return (
    <div className={cn("flex items-center gap-2.5 rounded-xl border px-3 py-2 transition-colors", active ? "border-accent/50 bg-accent/10" : "border-line bg-surface-2")}>
      <Icon className={cn("h-4 w-4 shrink-0", active ? "text-accent" : "text-ink-3")} aria-hidden />
      <div className="min-w-0">
        <div className={cn("text-xs font-semibold", active ? "text-ink" : "text-ink-2")}>{name}</div>
        <div className="truncate text-2xs text-ink-3">{role}</div>
      </div>
    </div>
  );
}

function Fact({ name, value, asking }: { name: string; value: string | null; asking: boolean }) {
  return (
    <div className={cn("rounded-xl border p-3 transition-colors", value ? "border-status-good/40 bg-status-good/10" : asking ? "border-accent/50 bg-accent/10" : "border-line bg-surface-2")}>
      <div className="flex items-center justify-between text-2xs text-ink-3">
        <span>{name}</span>
        {value && <Check className="h-3.5 w-3.5 text-status-good" aria-hidden />}
      </div>
      <div className={cn("mt-1 truncate text-base font-semibold", value ? "text-ink" : "text-ink-3")}>{value ?? (asking ? "Asking now…" : "Not yet")}</div>
    </div>
  );
}

export function LiveCall() {
  const [language, setLanguage] = useState<CallLanguage>("hi");
  const [state, setState] = useState<CallState | null>(null);
  const [lines, setLines] = useState<Line[]>([]);
  const [facts, setFacts] = useState<CallFacts>(NO_FACTS);
  const [askingFor, setAskingFor] = useState<string | null>(null);
  const [metrics, setMetrics] = useState<CallMetrics | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [reportId, setReportId] = useState<string | null>(null);
  const [level, setLevel] = useState(0);
  const client = useRef<LiveCallClient | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  // Leaving the page must release the microphone.
  useEffect(() => () => client.current?.dispose(), []);
  useEffect(() => {
    // In braces on purpose: newer browsers return a Promise here, and React would call it as a cleanup.
    bottom.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [lines]);

  const inCall = state !== null && state !== "ended";

  function startCall() {
    setLines([]);
    setFacts(NO_FACTS);
    setAskingFor(null);
    setMetrics(null);
    setError(null);
    setNotice(null);
    setReportId(null);
    setState("connecting");
    client.current = new LiveCallClient({
      onState: setState,
      onCaller: (text) => setLines((all) => [...all, { speaker: "caller", text }]),
      onAssistant: (text) => setLines((all) => [...all, { speaker: "assistant", text }]),
      onFacts: (next, asking) => {
        setFacts(next);
        setAskingFor(asking);
      },
      onMetrics: setMetrics,
      onLevel: setLevel,
      onNotice: setNotice,
      onDone: setReportId,
      onError: setError,
    });
    void client.current.start(language);
  }

  const listening = state === "listening";
  const orbScale = listening ? 1 + Math.min(level * 1.6, 0.45) : 1;

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold">Awaaz Live</h1>
        <p className="text-xs text-ink-3">A voice conversation that listens with Gnani Prisma and answers with Gnani Timbre, asking only for what's still missing.</p>
      </div>

      <div className="grid gap-4 lg:grid-cols-[360px_1fr]">
        <Card className="flex flex-col items-center p-5">
          <fieldset className="grid w-full grid-cols-2 gap-1.5" disabled={inCall}>
            <legend className="sr-only">Language of the call</legend>
            {LANGUAGES.map((option) => (
              <button
                key={option.code}
                type="button"
                onClick={() => setLanguage(option.code)}
                aria-pressed={language === option.code}
                className={cn(
                  "rounded-xl border px-3 py-2 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-60",
                  language === option.code ? "border-accent/60 bg-accent/10" : "border-line hover:bg-surface-2",
                )}
              >
                <div className="text-sm font-semibold text-ink">{option.name}</div>
                <div className="text-2xs text-ink-3">{option.hint}</div>
              </button>
            ))}
          </fieldset>

          <div className="my-8 grid h-44 w-44 place-items-center">
            <motion.div
              animate={{ scale: orbScale }}
              transition={{ type: "spring", stiffness: 300, damping: 20 }}
              className={cn(
                "grid h-32 w-32 place-items-center rounded-full border-2",
                state === "speaking" ? "border-accent bg-accent/15" : listening ? "border-status-good bg-status-good/15" : "border-line-strong bg-surface-2",
              )}
            >
              {state === "speaking" ? (
                <Volume2 className="h-9 w-9 text-accent" aria-hidden />
              ) : state === "thinking" || state === "connecting" ? (
                <Loader2 className="h-9 w-9 animate-spin text-ink-2" aria-hidden />
              ) : (
                <Mic className={cn("h-9 w-9", listening ? "text-status-good" : "text-ink-3")} aria-hidden />
              )}
            </motion.div>
          </div>
          <div className="min-h-5 text-sm font-medium text-ink" role="status" aria-live="polite">
            {state ? STATE_TEXT[state] : "Ready when you are"}
          </div>

          <div className="mt-5 flex w-full flex-col gap-2">
            {!inCall ? (
              <Button variant="primary" className="h-11 w-full justify-center text-base" onClick={startCall}>
                <Phone className="h-4 w-4" aria-hidden /> {state === "ended" ? "Start another call" : "Start call"}
              </Button>
            ) : (
              <>
                <Button className="h-10 w-full justify-center" disabled={!listening} onClick={() => client.current?.commit()}>
                  I've finished speaking
                </Button>
                <Button variant="danger" className="h-10 w-full justify-center" onClick={() => client.current?.hangUp()}>
                  <PhoneOff className="h-4 w-4" aria-hidden /> End call
                </Button>
              </>
            )}
          </div>

          <p className="mt-4 text-center text-2xs leading-relaxed text-ink-3">
            Prototype, not an emergency service. In an emergency, call 112. Use synthetic scenarios only.
          </p>
        </Card>

        <div className="space-y-4">
          <div className="grid gap-2 sm:grid-cols-2">
            <GnaniStep icon={Mic} name="Gnani Prisma" role="Streaming speech to text, with village-name hints" active={listening} />
            <GnaniStep icon={Volume2} name="Gnani Timbre" role="Streaming voice reply in the caller's language" active={state === "speaking"} />
          </div>

          <div className="grid gap-2 sm:grid-cols-3">
            <Fact name="Where" value={facts.place} asking={askingFor === "location_missing"} />
            <Fact name="What happened" value={facts.disaster ? label(facts.disaster) : null} asking={askingFor === "disaster_unknown"} />
            <Fact name="How many people" value={facts.people !== null ? String(facts.people) : null} asking={askingFor === "people_unknown"} />
          </div>

          {(facts.priority || metrics) && (
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-ink-2">
              {facts.priority && <PriorityBadge value={facts.priority as Priority} score={facts.score ?? undefined} />}
              {metrics && (
                <span title="From Prisma starting to transcribe to Timbre's first sound. It leaves out the moment of silence Prisma waits for to know you've stopped.">
                  Last reply in <strong className="text-ink">{(metrics.total_ms / 1000).toFixed(1)} s</strong> (Prisma {metrics.prisma_ms} ms)
                </span>
              )}
            </div>
          )}

          {error && <ErrorBanner message={error} />}
          {notice && <p className="text-xs text-status-warning">{notice}</p>}

          <Card className="min-h-64 p-4">
            {lines.length === 0 ? (
              <p className="py-16 text-center text-sm text-ink-3">The conversation will appear here.</p>
            ) : (
              <ol className="max-h-[420px] space-y-2.5 overflow-y-auto pr-1">
                {lines.map((line, i) => (
                  <li key={i} className={cn("flex", line.speaker === "caller" ? "justify-end" : "justify-start")}>
                    <div className={cn("max-w-[85%] rounded-2xl px-3.5 py-2 text-sm leading-relaxed", line.speaker === "caller" ? "bg-accent/15 text-ink" : "bg-surface-2 text-ink")}>
                      <div className="mb-0.5 text-2xs text-ink-3">{line.speaker === "caller" ? "Caller, heard by Prisma" : "Assistant, spoken by Timbre"}</div>
                      {line.text}
                    </div>
                  </li>
                ))}
                <div ref={bottom} />
              </ol>
            )}
          </Card>

          {state === "ended" && reportId && (
            <Link to={`/reports?id=${encodeURIComponent(reportId)}`} className="inline-block text-sm font-medium text-accent hover:underline">
              Open the saved report {reportId}
            </Link>
          )}
        </div>
      </div>
    </div>
  );
}
