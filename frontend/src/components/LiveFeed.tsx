import { CheckCircle2, Copy, FileAudio, GitMerge, Loader2, Mic, XCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { cn } from "../lib/cn";
import { clock, label, langLabel } from "../lib/format";
import type { ReportSummary } from "../lib/types";
import { ModeBadge, PriorityBadge, SyntheticTag } from "./badges";
import { Badge, Empty } from "./ui";

const PROCESSING = new Set(["queued", "transcribing", "extracting"]);

export function StatusPill({ status }: { status: string }) {
  if (PROCESSING.has(status))
    return (
      <Badge className="border-[#1c3f6b] text-[#8fc0f5]">
        <Loader2 className="h-3 w-3 animate-spin" aria-hidden /> {status}
      </Badge>
    );
  if (status === "processed")
    return (
      <Badge className="text-ink-2">
        <CheckCircle2 className="h-3 w-3 text-status-good" aria-hidden /> processed
      </Badge>
    );
  if (status === "needs_transcript")
    return (
      <Badge className="border-[#5b4413] text-[#f6c75a]">
        <Mic className="h-3 w-3" aria-hidden /> needs transcript
      </Badge>
    );
  if (status === "failed")
    return (
      <Badge className="border-[#5a2323] text-[#f3b0b0]">
        <XCircle className="h-3 w-3" aria-hidden /> failed
      </Badge>
    );
  return <Badge>{status}</Badge>;
}

export function DedupPill({ r }: { r: ReportSummary }) {
  if (!r.dedup_outcome) return null;
  if (r.dedup_outcome === "likely_duplicate")
    return (
      <Badge title="Auto-linked to an existing incident by the matching rules">
        <GitMerge className="h-3 w-3" aria-hidden /> duplicate → {r.incident_id}
      </Badge>
    );
  if (r.pending_suggestions > 0)
    return (
      <Badge className="border-[#5b4413] text-[#f6c75a]" title="Possible duplicate: waiting for human decision">
        <Copy className="h-3 w-3" aria-hidden /> possible duplicate
      </Badge>
    );
  return <Badge className="text-ink-2">new incident {r.incident_id}</Badge>;
}

export function LiveFeed({ items, compact }: { items: ReportSummary[]; compact?: boolean }) {
  // Highlight reports that appeared since the previous poll (real arrivals, not an animation loop).
  const seen = useRef<Set<string> | null>(null);
  const [fresh, setFresh] = useState<Set<string>>(new Set());
  useEffect(() => {
    const ids = new Set(items.map((r) => r.id));
    if (seen.current) {
      const n = new Set([...ids].filter((id) => !seen.current!.has(id)));
      if (n.size) setFresh(n);
    }
    seen.current = ids;
  }, [items]);
  useEffect(() => {
    if (!fresh.size) return;
    const t = window.setTimeout(() => setFresh(new Set()), 6000);
    return () => window.clearTimeout(t);
  }, [fresh]);

  if (!items.length)
    return (
      <Empty icon={<FileAudio className="h-6 w-6" />} title="No reports yet">
        Upload or record audio on the Incoming Reports page to begin.
      </Empty>
    );
  return (
    <ul className="divide-y divide-line">
      {items.map((r) => (
        <li key={r.id} className={cn("space-y-1.5 px-4 py-3 transition-colors", fresh.has(r.id) && "bg-[#13233a]")}>
          <div className="flex flex-wrap items-center gap-1.5">
            <Link to={`/reports?id=${encodeURIComponent(r.id)}`} className="font-mono text-xs text-accent hover:underline">
              {r.id}
            </Link>
            <span className="text-2xs text-ink-3">{clock(r.received_at)}</span>
            <Badge>{langLabel(r.language)}</Badge>
            <StatusPill status={r.status} />
            {r.priority_label && <PriorityBadge value={r.priority_label} />}
            {r.source === "telegram" && <Badge className="border-[#1d4f6e] text-[#7cc7f0]">{label(r.source)}</Badge>}
            {r.caller_location && <Badge className="border-[#1d4f6e] text-[#7cc7f0]">GPS shared</Badge>}
            {r.is_synthetic && <SyntheticTag />}
          </div>
          {!compact && r.audio[0] && <audio controls preload="none" src={r.audio[0].url} className="h-8 w-full" />}
          <div className="flex flex-wrap items-center gap-1.5">
            <ModeBadge mode={r.transcript_provider_mode} provider={r.transcript_provider} />
            <DedupPill r={r} />
          </div>
          {r.transcript ? (
            <p className={cn("text-xs text-ink-2", compact ? "line-clamp-2" : "line-clamp-3")} lang={r.language ?? undefined}>
              “{r.transcript}”
            </p>
          ) : (
            <p className="text-xs italic text-ink-3">{r.error ?? "No transcript yet"}</p>
          )}
          {r.status === "processed" && (
            <div className="text-2xs text-ink-3">
              Location: {r.location_text ?? "not stated"} ({r.location_status}, evidence level {r.location_confidence?.toFixed(2) ?? "—"}) · People:{" "}
              {r.people_count ?? "unknown"}
              {r.review_reasons.length > 0 && !r.review_resolved && (
                <span className="text-[#f6c75a]"> · {r.review_reasons.length} review flag(s)</span>
              )}
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}
