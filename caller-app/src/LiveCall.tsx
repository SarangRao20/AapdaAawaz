import { useEffect, useRef, useState } from "react";
import { LiveCallClient } from "./liveCall";
import type { CallFacts, CallLanguage, CallMetrics, CallState } from "./liveCall";

interface Line {
  speaker: "caller" | "assistant";
  text: string;
}

const NO_FACTS: CallFacts = {
  place: null, disaster: null, people: null, priority: null, score: null, report_id: null, needs_review: false,
};

const STATE_TEXT: Record<CallState, { title: string; hint: string }> = {
  connecting: { title: "जुड़ रहे हैं…", hint: "Connecting to Awaaz Live" },
  listening: { title: "सुन रहे हैं…", hint: "Speak now — I'm listening" },
  thinking: { title: "समझ रहे हैं…", hint: "Noting what you said" },
  speaking: { title: "बोल रहे हैं…", hint: "Listen to the reply" },
  ended: { title: "कॉल समाप्त", hint: "Call ended" },
};

const DISASTER: Record<string, string> = {
  flood: "बाढ़ · Flood",
  landslide: "भूस्खलन · Landslide",
  earthquake: "भूकंप · Earthquake",
  fire: "आग · Fire",
};

const PRIORITY_COLOR: Record<string, string> = {
  critical: "#ef4444", high: "#f97316", medium: "#eab308", low: "#22c55e",
};

/* ── icons ─────────────────────────────────────────────────────────────────── */
const MicIcon = ({ size = 40 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
    <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
    <line x1="12" y1="19" x2="12" y2="23" />
  </svg>
);

const SpeakerIcon = ({ size = 40 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
    <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
    <path d="M15.54 8.46a5 5 0 0 1 0 7.07" />
    <path d="M19.07 4.93a10 10 0 0 1 0 14.14" />
  </svg>
);

const SpinnerIcon = ({ size = 40 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" className="spin">
    <path d="M21 12a9 9 0 1 1-6.22-8.56" />
  </svg>
);

const PhoneOffIcon = () => (
  <svg width={18} height={18} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M10.68 13.31a16 16 0 0 0 3.41 2.6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-3.33-2.67m-2.67-3.34a19.79 19.79 0 0 1-3.07-8.63A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91" />
    <line x1="23" y1="1" x2="1" y2="23" />
  </svg>
);

const CheckIcon = () => (
  <svg width={22} height={22} viewBox="0 0 24 24" fill="none" stroke="#22c55e" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="10" />
    <polyline points="8 12 11 15 16 9" />
  </svg>
);

function FactChip({ label, value }: { label: string; value: string | null }) {
  return (
    <div className={`rounded-xl border px-2.5 py-2 min-w-0 ${value ? "border-[#22c55e]/35 bg-[#22c55e]/8" : "border-white/8 bg-[#111]"}`}>
      <div className="text-[9px] uppercase tracking-wider text-[#525252]">{label}</div>
      <div className={`mt-0.5 truncate text-[11px] font-semibold ${value ? "text-[#f2f2f2]" : "text-[#3f3f46]"}`}>
        {value ?? "…"}
      </div>
    </div>
  );
}

export default function LiveCallScreen({ lang, onHome }: { lang: CallLanguage; onHome: () => void }) {
  const [state, setState] = useState<CallState | null>(null);
  const [lines, setLines] = useState<Line[]>([]);
  const [facts, setFacts] = useState<CallFacts>(NO_FACTS);
  const [metrics, setMetrics] = useState<CallMetrics | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [reportId, setReportId] = useState<string | null>(null);
  const [level, setLevel] = useState(0);
  const client = useRef<LiveCallClient | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  // Leaving the screen must release the microphone.
  useEffect(() => () => client.current?.dispose(), []);
  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [lines]);
  // A hidden app cannot use the microphone, and a forgotten call keeps spending credits.
  useEffect(() => {
    const onHide = () => {
      if (document.visibilityState === "hidden") client.current?.hangUp();
    };
    const onLeave = () => client.current?.hangUp();
    document.addEventListener("visibilitychange", onHide);
    window.addEventListener("pagehide", onLeave);
    return () => {
      document.removeEventListener("visibilitychange", onHide);
      window.removeEventListener("pagehide", onLeave);
    };
  }, []);

  const inCall = state !== null && state !== "ended";
  const listening = state === "listening";
  const ended = state === "ended";
  const ref = reportId ?? facts.report_id;
  const orbScale = listening ? 1 + Math.min(level * 0.55, 0.3) : 1;

  function startCall() {
    setLines([]);
    setFacts(NO_FACTS);
    setMetrics(null);
    setError(null);
    setNotice(null);
    setReportId(null);
    setLevel(0);
    setState("connecting");
    client.current?.dispose();
    client.current = new LiveCallClient({
      onState: setState,
      onCaller: (text) => setLines((all) => [...all, { speaker: "caller", text }]),
      onAssistant: (text) => setLines((all) => [...all, { speaker: "assistant", text }]),
      onFacts: setFacts,
      onMetrics: setMetrics,
      onLevel: setLevel,
      onNotice: setNotice,
      onDone: setReportId,
      onError: setError,
    });
    void client.current.start(lang);
  }

  function leave() {
    client.current?.dispose();
    client.current = null;
    onHome();
  }

  function hangUp() {
    // The server answers with `done` and then closes, so the summary waits for the real report id.
    client.current?.hangUp();
  }

  const text = state ? STATE_TEXT[state] : null;
  const priorityColor = facts.priority ? PRIORITY_COLOR[facts.priority] ?? "#22c55e" : "#22c55e";

  return (
    <div className="h-full flex flex-col overflow-hidden">
      <header className="px-5 pt-10 pb-2 flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-[#f97316] shadow-[0_0_8px_#f97316]" />
          <span className="text-[10px] font-bold tracking-[0.25em] uppercase text-[#f97316]">Awaaz Live</span>
        </div>
        <button
          onClick={leave}
          className="text-[11px] font-semibold text-[#a3a3a3] px-3 py-1.5 rounded-full border border-white/8 active:scale-95 transition-transform"
        >
          {inCall ? "Close" : "Home"}
        </button>
      </header>

      <div className="flex-1 overflow-y-auto px-5 pb-4">
        <div className="flex flex-col items-center pt-4 pb-5">
          <div className="relative grid place-items-center h-40 w-40">
            {listening && (
              <>
                <span className="pulse-ring absolute w-32 h-32 rounded-full border border-[#22c55e]/30" />
                <span className="pulse-ring absolute w-32 h-32 rounded-full border border-[#22c55e]/15" style={{ animationDelay: "0.7s" }} />
              </>
            )}
            <div
              className={`grid h-28 w-28 place-items-center rounded-full border-2 transition-colors duration-300 ${
                state === "speaking"
                  ? "border-[#f97316] bg-[#f97316]/15 text-[#f97316]"
                  : listening
                    ? "border-[#22c55e] bg-[#22c55e]/15 text-[#22c55e]"
                    : "border-white/12 bg-[#141414] text-[#a3a3a3]"
              }`}
              style={{ transform: `scale(${orbScale})` }}
            >
              {state === "speaking" ? (
                <SpeakerIcon />
              ) : state === "thinking" || state === "connecting" ? (
                <SpinnerIcon />
              ) : (
                <MicIcon />
              )}
            </div>
          </div>

          <div className="mt-2 text-base font-bold text-[#f2f2f2] text-center" role="status" aria-live="polite">
            {text ? text.title : "बात करने के लिए तैयार"}
          </div>
          <div className="mt-0.5 text-[11px] text-[#525252] text-center">
            {text ? text.hint : "A live voice conversation with Aapda Awaaz"}
          </div>
        </div>

        {(facts.place || facts.disaster || facts.people !== null) && (
          <div className="grid grid-cols-3 gap-2 mb-3">
            <FactChip label="Where" value={facts.place} />
            <FactChip label="What" value={facts.disaster ? DISASTER[facts.disaster] ?? facts.disaster : null} />
            <FactChip label="People" value={facts.people !== null ? String(facts.people) : null} />
          </div>
        )}

        {error && (
          <div className="mb-3 rounded-xl border border-[#ef4444]/25 bg-[#ef4444]/10 px-3.5 py-2.5 text-[11px] leading-relaxed text-[#ef4444]">
            {error}
          </div>
        )}
        {notice && <p className="mb-3 text-[11px] text-[#eab308]">{notice}</p>}

        {lines.length > 0 && (
          <ol className="space-y-2">
            {lines.map((line, i) => (
              <li key={i} className={`flex ${line.speaker === "caller" ? "justify-end" : "justify-start"}`}>
                <div
                  className={`max-w-[86%] rounded-2xl px-3.5 py-2 text-[13px] leading-relaxed ${
                    line.speaker === "caller" ? "bg-[#f97316]/15 text-[#f2f2f2]" : "bg-[#161616] text-[#e5e5e5]"
                  }`}
                >
                  <div className="mb-0.5 text-[9px] uppercase tracking-wider text-[#525252]">
                    {line.speaker === "caller" ? "You" : "Aapda Awaaz"}
                  </div>
                  {line.text}
                </div>
              </li>
            ))}
          </ol>
        )}
        <div ref={bottom} />

        {ended && (
          <div className="mt-4 rounded-2xl border border-white/8 bg-[#111] p-4">
            <div className="flex items-center gap-2.5">
              {ref ? <CheckIcon /> : null}
              <div>
                <div className="text-sm font-bold text-[#f2f2f2]">
                  {ref ? "रिपोर्ट दर्ज हो गई" : "कोई रिपोर्ट दर्ज नहीं हुई"}
                </div>
                <div className="text-[11px] text-[#525252]">
                  {ref ? "Your report was saved for the response team." : "No report was created in that call."}
                </div>
              </div>
            </div>

            {ref && (
              <>
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  {facts.priority && (
                    <span
                      className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[10px] font-bold uppercase tracking-widest"
                      style={{ background: `${priorityColor}1f`, color: priorityColor }}
                    >
                      <span className="w-1.5 h-1.5 rounded-full" style={{ background: priorityColor }} />
                      {facts.priority} priority
                    </span>
                  )}
                  {facts.needs_review && (
                    <span className="rounded-full bg-[#eab308]/15 px-2.5 py-1 text-[10px] font-bold uppercase tracking-widest text-[#eab308]">
                      Needs review
                    </span>
                  )}
                </div>
                <div className="mt-3 text-[10px] font-mono tracking-wider text-[#525252]">
                  REF {ref.slice(-12).toUpperCase()}
                </div>
                {metrics && (
                  <div className="mt-1 text-[10px] text-[#525252]">
                    Last reply in {(metrics.total_ms / 1000).toFixed(1)} s
                  </div>
                )}
              </>
            )}
          </div>
        )}

        <p className="mt-4 text-center text-[10px] leading-relaxed text-[#3f3f46]">
          Prototype, not an emergency service. If life is in danger, call 112.
        </p>
      </div>

      <footer className="px-5 pb-8 pt-2 space-y-2 flex-shrink-0">
        {!inCall ? (
          <>
            <button
              onClick={startCall}
              className="w-full py-4 rounded-2xl bg-[#f97316] text-white font-bold text-base shadow-[0_4px_24px_-4px_rgba(249,115,22,0.5)] active:scale-[0.98] transition-transform"
            >
              {ended ? "फिर से कॉल करें · Start another call" : "कॉल शुरू करें · Start call"}
            </button>
            {ended && (
              <button
                onClick={leave}
                className="w-full py-3 rounded-2xl border border-white/8 text-[#a3a3a3] text-sm font-semibold active:scale-[0.98] transition-transform"
              >
                होम पर जाएँ · Home
              </button>
            )}
          </>
        ) : (
          <>
            <button
              onClick={() => client.current?.commit()}
              disabled={!listening}
              className="w-full py-3.5 rounded-2xl bg-[#161616] border border-white/10 text-[#f2f2f2] text-sm font-semibold disabled:opacity-35 active:scale-[0.98] transition-transform"
            >
              मैंने कह दिया · I've finished speaking
            </button>
            <button
              onClick={hangUp}
              className="w-full py-3.5 rounded-2xl border border-[#ef4444]/30 bg-[#ef4444]/10 text-[#ef4444] text-sm font-semibold flex items-center justify-center gap-2 active:scale-[0.98] transition-transform"
            >
              <PhoneOffIcon /> कॉल बंद करें · End call
            </button>
          </>
        )}
      </footer>
    </div>
  );
}
