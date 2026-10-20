import { AnimatePresence, motion } from "framer-motion";
import { Siren, X } from "lucide-react";
import type { Alert } from "../lib/alerts";
import { PRIORITY_COLOR, locationText, peopleText } from "../lib/format";
import { EASE } from "../lib/motion";

export function AlertToasts({ alerts, onOpen, onDismiss }: { alerts: Alert[]; onOpen: (a: Alert) => void; onDismiss: (key: string) => void }) {
  return (
    <div className="pointer-events-none fixed right-4 top-4 z-[2500] flex w-[22rem] max-w-[calc(100vw-2rem)] flex-col gap-2" aria-live="assertive">
      <AnimatePresence initial={false}>
        {alerts.map((a) => {
          const color = PRIORITY_COLOR[a.incident.priority_label];
          return (
            <motion.div
              key={a.key}
              layout
              initial={{ opacity: 0, x: 60, scale: 0.95 }}
              animate={{ opacity: 1, x: 0, scale: 1 }}
              exit={{ opacity: 0, x: 60, transition: { duration: 0.2 } }}
              transition={{ duration: 0.35, ease: EASE }}
              className="glass pointer-events-auto relative overflow-hidden rounded-2xl"
              style={{ boxShadow: `0 0 0 1px ${color}66, 0 16px 40px -12px ${color}66` }}
            >
              <button onClick={() => onOpen(a)} className="flex w-full items-start gap-3 p-3.5 pr-9 text-left">
                <span className="relative mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-xl" style={{ background: `${color}26`, color }}>
                  <Siren className="h-[18px] w-[18px]" aria-hidden />
                </span>
                <span className="min-w-0">
                  <span className="block text-2xs font-semibold uppercase tracking-wider" style={{ color }}>
                    {a.kind === "new" ? "New" : "Escalated to"} {a.incident.priority_label}
                  </span>
                  <span className="block truncate text-sm font-medium text-ink">{locationText(a.incident)}</span>
                  <span className="block truncate text-xs text-ink-3">
                    {peopleText(a.incident)} · {a.incident.report_count} report{a.incident.report_count === 1 ? "" : "s"} · tap to locate
                  </span>
                </span>
              </button>
              <button
                onClick={() => onDismiss(a.key)}
                aria-label="Dismiss alert"
                className="absolute right-2 top-2 rounded-lg p-1 text-ink-3 hover:bg-white/10 hover:text-ink"
              >
                <X className="h-4 w-4" />
              </button>
              <div className="h-0.5 origin-left animate-shrink" style={{ background: color }} />
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}
