import { motion, useReducedMotion } from "framer-motion";
import { AlertTriangle, ArrowRight, AudioLines, ClipboardCheck, Languages, MessageCircleQuestion, Mic, ShieldCheck, Waypoints } from "lucide-react";
import { Link } from "react-router-dom";
import { useAuth } from "../lib/auth";

const STEPS = [
  { icon: AudioLines, title: "Someone speaks", text: "In a live call, a Telegram voice note or the caller app, in Hindi, Marathi, English or Hinglish." },
  { icon: Waypoints, title: "Gnani Prisma listens", text: "Streaming speech-to-text, primed with local village names so places are heard correctly." },
  { icon: MessageCircleQuestion, title: "Gnani Timbre asks what's missing", text: "A calm voice asks one question at a time, then reads the facts back to confirm them." },
  { icon: ClipboardCheck, title: "A dispatcher decides", text: "The report fills in live, is ranked and mapped, and a person can send voice alerts back." },
];

const POINTS = [
  { icon: Languages, title: "Works in the caller's language", text: "Hindi, Marathi, English and Hinglish, in both directions." },
  { icon: ShieldCheck, title: "Evidence you can check", text: "The original audio, the transcript and the reason for each ranking stay with every report." },
  { icon: AlertTriangle, title: "Clear about uncertainty", text: "Doubtful details are flagged for review, and unverified locations are marked as unverified." },
];

const BARS = [28, 52, 36, 70, 44, 88, 60, 34, 76, 48, 92, 56, 30, 66, 42, 80, 50, 26, 62, 38];

const EXAMPLE_CALL = [
  { speaker: "Caller", text: "Yahan baadh aa gayi hai, log phanse hain." },
  { speaker: "Assistant", text: "Theek hai. Aap kahan se bol rahe hain?" },
  { speaker: "Caller", text: "Nandwadi gaon se." },
  { speaker: "Assistant", text: "Kitne log phanse hain?" },
];

function Logo() {
  return (
    <span className="flex items-center gap-2.5">
      <span className="grid h-9 w-9 place-items-center rounded-xl border border-accent/25 bg-accent/10">
        <Mic className="h-4 w-4 text-accent" aria-hidden />
      </span>
      <span className="text-sm font-semibold tracking-tight text-ink">Aapda Awaaz</span>
    </span>
  );
}

/** An illustration of the idea, not live data, and labelled as an example. */
function ExampleReport() {
  const reduced = useReducedMotion();
  return (
    <div className="rounded-2xl border border-line bg-surface-1 p-5 shadow-glass">
      <div className="text-2xs font-medium uppercase tracking-[0.14em] text-ink-3">Example conversation</div>

      <div className="mt-4 flex h-14 items-center gap-1" aria-hidden>
        {BARS.map((height, i) => (
          <motion.span
            key={i}
            className="w-full flex-1 origin-center rounded-full bg-accent/70"
            style={{ height: `${height}%` }}
            animate={reduced ? undefined : { scaleY: [1, 0.45, 1] }}
            transition={reduced ? undefined : { duration: 1.6, repeat: Infinity, ease: "easeInOut", delay: i * 0.07 }}
          />
        ))}
      </div>

      <ol className="mt-4 space-y-2">
        {EXAMPLE_CALL.map((line, i) => (
          <li key={i} className={line.speaker === "Caller" ? "flex justify-end" : "flex justify-start"}>
            <div className={line.speaker === "Caller" ? "max-w-[85%] rounded-2xl bg-accent/15 px-3 py-1.5 text-sm text-ink" : "max-w-[85%] rounded-2xl bg-surface-2 px-3 py-1.5 text-sm text-ink"}>
              <div className="text-2xs text-ink-3">{line.speaker === "Caller" ? "Caller, heard by Prisma" : "Assistant, spoken by Timbre"}</div>
              {line.text}
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}

export function Landing() {
  const { status } = useAuth();
  const loggedIn = status === "in";
  const destination = loggedIn ? "/awaaz" : "/login";
  const action = loggedIn ? "Open Awaaz Live" : "Log in to try a live call";

  return (
    <div className="min-h-full">
      <div className="ambient" aria-hidden>
        <div className="ambient-grid" />
      </div>

      <div className="relative">
        <header className="mx-auto flex max-w-6xl items-center justify-between px-4 py-5 md:px-8">
          <Logo />
          <Link
            to={destination}
            className="rounded-lg border border-line-strong px-3.5 py-2 text-sm font-medium text-ink transition-colors hover:bg-surface-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
          >
            {loggedIn ? "Awaaz Live" : "Log in"}
          </Link>
        </header>

        <main>
          <section className="mx-auto grid max-w-6xl items-center gap-10 px-4 pb-16 pt-8 md:px-8 md:pt-16 lg:grid-cols-[1.15fr_1fr] lg:gap-16">
            <div>
              <p className="text-sm font-medium text-accent-glow [html.light_&]:text-accent-dim">A voice assistant for disaster response, built on Gnani AI</p>
              <h1 className="mt-3 text-4xl font-semibold leading-[1.1] tracking-tight text-ink md:text-5xl">
                When the phone lines are full, a voice still answers
              </h1>
              <p className="mt-5 max-w-xl text-base leading-relaxed text-ink-2 md:text-lg">
                Aapda Awaaz holds a live conversation in the caller's own language: Gnani Prisma listens, Gnani Timbre speaks, and it asks only for what's still missing. A dispatcher watches the report fill in as the person talks.
              </p>
              <div className="mt-8 flex flex-wrap items-center gap-3">
                <Link
                  to={destination}
                  className="inline-flex items-center gap-2 rounded-lg bg-accent px-5 py-2.5 text-sm font-semibold text-black transition-colors hover:bg-accent-glow focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50 focus-visible:ring-offset-2 focus-visible:ring-offset-bg"
                >
                  {action} <ArrowRight className="h-4 w-4" aria-hidden />
                </Link>
                <a href="#how-it-works" className="rounded-lg px-3 py-2.5 text-sm font-medium text-ink-2 transition-colors hover:text-ink">
                  See how it works
                </a>
              </div>
            </div>
            <ExampleReport />
          </section>

          <section id="how-it-works" className="scroll-mt-6 border-t border-line">
            <div className="mx-auto max-w-6xl px-4 py-16 md:px-8">
              <h2 className="text-2xl font-semibold tracking-tight text-ink">How it works</h2>
              <ol className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                {STEPS.map(({ icon: Icon, title, text }, i) => (
                  <li key={title} className="rounded-xl border border-line bg-surface-1 p-5">
                    <div className="flex items-center justify-between">
                      <Icon className="h-5 w-5 text-accent" aria-hidden />
                      <span className="font-mono text-xs text-ink-3">{i + 1}</span>
                    </div>
                    <h3 className="mt-4 text-sm font-semibold text-ink">{title}</h3>
                    <p className="mt-1.5 text-sm leading-relaxed text-ink-2">{text}</p>
                  </li>
                ))}
              </ol>
            </div>
          </section>

          <section className="border-t border-line">
            <div className="mx-auto grid max-w-6xl gap-8 px-4 py-16 md:grid-cols-3 md:px-8">
              {POINTS.map(({ icon: Icon, title, text }) => (
                <div key={title}>
                  <Icon className="h-5 w-5 text-accent" aria-hidden />
                  <h3 className="mt-3 text-sm font-semibold text-ink">{title}</h3>
                  <p className="mt-1.5 text-sm leading-relaxed text-ink-2">{text}</p>
                </div>
              ))}
            </div>
          </section>

          <section className="mx-auto max-w-6xl px-4 pb-16 md:px-8">
            <div className="flex gap-3 rounded-xl border border-status-warning/30 bg-status-warning/10 p-5">
              <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-status-warning" aria-hidden />
              <div className="text-sm leading-relaxed text-ink">
                <p className="font-semibold">This is not an emergency service. In an emergency, call 112.</p>
                <p className="mt-1 text-ink-2">
                  Aapda Awaaz is a decision-support prototype. It does not dispatch responders or contact emergency services.
                </p>
              </div>
            </div>
          </section>
        </main>

        <footer className="border-t border-line">
          <div className="mx-auto max-w-6xl px-4 py-6 text-xs text-ink-3 md:px-8">Voice by Gnani AI: Prisma streaming speech-to-text and Timbre streaming text-to-speech</div>
        </footer>
      </div>
    </div>
  );
}
