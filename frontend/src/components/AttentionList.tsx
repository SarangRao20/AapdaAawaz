import { AnimatePresence, motion } from "framer-motion";
import { MapPinOff, Users } from "lucide-react";
import { cn } from "../lib/cn";
import { useI18n } from "../lib/i18n";
import { PRIORITY_COLOR, locationText, isMappable, peopleText, timeAgo } from "../lib/format";
import { EASE } from "../lib/motion";
import type { Incident } from "../lib/types";
import { Empty } from "./ui";

/** Deliberately plain: what, where, how many, how urgent. Everything else is one click away. */
export function AttentionList({
  items,
  selectedId,
  fresh,
  onSelect,
}: {
  items: Incident[];
  selectedId: string | null;
  fresh: Record<string, number>;
  onSelect: (id: string) => void;
}) {
  const { t } = useI18n();
  if (!items.length) return <Empty title="Nothing here right now">New incidents appear here the moment a report is processed.</Empty>;
  return (
    <ul className="space-y-2 p-3">
      <AnimatePresence initial={false}>
        {items.map((i) => {
          const color = PRIORITY_COLOR[i.priority_label];
          const isFresh = !!fresh[i.id];
          return (
            <motion.li
              key={i.id}
              layout="position"
              initial={{ opacity: 0, y: -12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.3, ease: EASE }}
            >
              <button
                onClick={() => onSelect(i.id)}
                className={cn(
                  "relative flex w-full items-stretch gap-3 overflow-hidden rounded-xl border bg-white/[0.03] p-3 text-left transition-colors hover:bg-white/[0.07]",
                  selectedId === i.id ? "border-accent/60 bg-accent/10" : "border-white/[0.06]",
                )}
              >
                <span className="w-1 shrink-0 rounded-full" style={{ background: color, boxShadow: `0 0 12px ${color}` }} />
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-2">
                    <span className="text-2xs font-semibold uppercase tracking-wider" style={{ color }}>
                      {i.priority_label === 'critical' ? t.critical : i.priority_label === 'high' ? t.high : i.priority_label === 'medium' ? t.medium : i.priority_label === 'low' ? t.low : i.priority_label}
                    </span>
                    {isFresh && <span className="rounded-full bg-accent px-1.5 py-px text-2xs font-semibold text-white">NEW</span>}
                    <span className="ml-auto text-2xs text-ink-3">{timeAgo(i.last_report_at)}</span>
                  </span>
                  <span className="mt-0.5 block truncate text-sm font-medium text-ink">{locationText(i)}</span>
                  <span className="mt-1 flex items-center gap-3 text-xs text-ink-3">
                    <span className="inline-flex items-center gap-1">
                      <Users className="h-3.5 w-3.5" aria-hidden /> {peopleText(i)}
                    </span>
                    {!isMappable(i) && (
                      <span className="inline-flex items-center gap-1 text-[#f6c75a]">
                        <MapPinOff className="h-3.5 w-3.5" aria-hidden /> not on map
                      </span>
                    )}
                  </span>
                </span>
                {isFresh && (
                  <motion.span
                    className="pointer-events-none absolute inset-0 rounded-xl"
                    initial={{ boxShadow: `inset 0 0 0 2px ${color}` }}
                    animate={{ boxShadow: `inset 0 0 0 2px ${color}00` }}
                    transition={{ duration: 4 }}
                  />
                )}
              </button>
            </motion.li>
          );
        })}
      </AnimatePresence>
    </ul>
  );
}
