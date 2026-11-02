import { Mic, Radio, Volume2 } from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { cn } from "../lib/cn";
import { label } from "../lib/format";
import type { LiveCallSummary, Priority } from "../lib/types";
import { usePoll } from "../lib/usePoll";
import { PriorityBadge } from "./badges";
import { Card } from "./ui";

const STATE_TEXT: Record<string, string> = {
  connecting: "Connecting",
  listening: "Caller speaking",
  thinking: "Noting details",
  speaking: "Assistant speaking",
  ended: "Call ended",
};

function CallCard({ call }: { call: LiveCallSummary }) {
  const live = call.state !== "ended";
  const recent = call.turns.slice(-3);
  const { place, disaster, people, priority, report_id: reportId } = call.facts;
  return (
    <div className="space-y-2.5 rounded-xl border border-line bg-surface-2 p-3.5">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className={cn("inline-flex items-center gap-1.5 font-semibold", live ? "text-status-critical" : "text-ink-3")}>
          {live && <span className="h-2 w-2 animate-pulse rounded-full bg-status-critical" aria-hidden />}
          {live ? "LIVE" : "ENDED"}
        </span>
        <span className="text-ink-2">{STATE_TEXT[call.state] ?? call.state}</span>
        <span className="text-ink-3">{label(call.language)}</span>
        {priority && <PriorityBadge value={priority as Priority} />}
        {reportId && (
          <Link to={`/reports?id=${encodeURIComponent(reportId)}`} className="ml-auto font-mono text-2xs text-accent hover:underline">
            {reportId}
          </Link>
        )}
      </div>
      <dl className="grid grid-cols-3 gap-2 text-xs">
        {[
          ["Where", place, "location_missing"],
          ["What", disaster ? label(disaster) : null, "disaster_unknown"],
          ["People", people !== null ? String(people) : null, "people_unknown"],
        ].map(([name, value, field]) => (
          <div key={name}>
            <dt className="text-2xs text-ink-3">{name}</dt>
            <dd className={cn("truncate font-semibold", value ? "text-ink" : call.asking_for === field ? "text-accent" : "text-ink-3")}>
              {value ?? (call.asking_for === field ? "Asking…" : "—")}
            </dd>
          </div>
        ))}
      </dl>
      <ul className="space-y-1 text-xs">
        {recent.map((turn) => (
          <li key={turn.at} className="flex gap-1.5">
            {turn.speaker === "caller" ? (
              <Mic className="mt-0.5 h-3 w-3 shrink-0 text-accent" aria-label="Caller" />
            ) : (
              <Volume2 className="mt-0.5 h-3 w-3 shrink-0 text-ink-3" aria-label="Assistant" />
            )}
            <span className={cn("line-clamp-2", turn.speaker === "caller" ? "text-ink" : "text-ink-3")}>{turn.text}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Conversations as they happen. Shows nothing at all when there are none, so it doesn't crowd the room. */
export function LiveCallsPanel() {
  const calls = usePoll(api.liveCalls, 1000);
  const items = calls.data?.items ?? [];
  if (!items.length) return null;
  return (
    <Card className="p-4">
      <div className="mb-3 flex items-center gap-2 text-sm font-semibold">
        <Radio className="h-4 w-4 text-status-critical" aria-hidden /> Calls on Awaaz Live
        <span className="text-2xs font-normal text-ink-3">Gnani Prisma + Timbre, streaming</span>
      </div>
      <div className="grid gap-3 lg:grid-cols-2">
        {items.slice(0, 4).map((call) => (
          <CallCard key={call.id} call={call} />
        ))}
      </div>
    </Card>
  );
}
