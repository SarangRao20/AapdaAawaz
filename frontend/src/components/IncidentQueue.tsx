import { ChevronRight, HeartPulse, Users } from "lucide-react";
import { Link } from "react-router-dom";
import { cn } from "../lib/cn";
import { label, locationText, peopleText, timeAgo } from "../lib/format";
import type { Incident } from "../lib/types";
import { ConfidenceBadge, LocationBadge, PriorityBadge, ReviewBadge } from "./badges";
import { Empty } from "./ui";

export function IncidentQueue({
  items,
  selectedId,
  onSelect,
  emptyText = "No incidents match the current filters.",
}: {
  items: Incident[];
  selectedId?: string | null;
  onSelect?: (id: string) => void;
  emptyText?: string;
}) {
  if (!items.length) return <Empty title={emptyText} />;
  return (
    <ol className="divide-y divide-line">
      {items.map((i, idx) => {
        const top = i.priority_breakdown?.factors.slice(0, 2).map((f) => f.label).join(" · ");
        const vul = Object.keys(i.vulnerable ?? {});
        return (
          <li key={i.id}>
            <div
              role="button"
              tabIndex={0}
              onClick={() => onSelect?.(i.id)}
              onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onSelect?.(i.id)}
              className={cn(
                "grid cursor-pointer grid-cols-[2rem_1fr_auto] gap-3 px-4 py-3 outline-none transition-colors hover:bg-surface-2 focus-visible:bg-surface-2",
                selectedId === i.id && "bg-surface-2 shadow-[inset_3px_0_0_#3987e5]",
              )}
            >
              <div className="pt-0.5 font-mono text-xs text-ink-3">{idx + 1}</div>
              <div className="min-w-0 space-y-1.5">
                <div className="flex flex-wrap items-center gap-1.5">
                  <PriorityBadge value={i.priority_label} score={i.priority_score} />
                  <span className="font-mono text-xs text-ink-2">{i.id}</span>
                  <ReviewBadge value={i.review_status} />
                  <LocationBadge value={i.location_status} />
                  <ConfidenceBadge value={i.info_confidence?.overall} />
                </div>
                <div className="text-sm font-medium text-ink">{locationText(i)}</div>
                <p className="line-clamp-2 text-xs text-ink-2">{i.summary}</p>
                <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-2">
                  <span className="inline-flex items-center gap-1">
                    <Users className="h-3.5 w-3.5 text-ink-3" aria-hidden /> {peopleText(i)}
                  </span>
                  {vul.length > 0 && <span>Vulnerable: {vul.map(label).join(", ")}</span>}
                  {i.medical_emergency && (
                    <span className="inline-flex items-center gap-1 text-[#f08a8a]">
                      <HeartPulse className="h-3.5 w-3.5" aria-hidden /> Medical emergency
                    </span>
                  )}
                  {i.needs.length > 0 && <span>Needs: {i.needs.map(label).join(", ")}</span>}
                </div>
                {top && (
                  <div className="text-2xs text-ink-3">
                    Why: {top}
                    {i.priority_breakdown?.notes.length ? ` · ${i.priority_breakdown.notes[0]}` : ""}
                  </div>
                )}
                {i.recommended_action && <div className="text-2xs text-ink-2">Next (human): {i.recommended_action}</div>}
              </div>
              <div className="flex flex-col items-end justify-between gap-2 text-right">
                <span className="text-2xs text-ink-3">
                  {i.report_count} report{i.report_count === 1 ? "" : "s"}
                  <br />
                  {timeAgo(i.last_report_at)}
                </span>
                <Link
                  to={`/incidents/${i.id}`}
                  onClick={(e) => e.stopPropagation()}
                  className="inline-flex items-center text-xs text-accent hover:underline"
                >
                  Investigate <ChevronRight className="h-3.5 w-3.5" />
                </Link>
              </div>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
