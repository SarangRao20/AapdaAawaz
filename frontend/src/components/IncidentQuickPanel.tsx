import { ArrowRight, Check, Copy, MapPinOff, Printer, X } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { label, langLabel, locationText, peopleText, timeAgo } from "../lib/format";
import type { Incident } from "../lib/types";
import { ConfidenceBadge, LocationBadge, PriorityBadge, ReviewBadge } from "./badges";
import { PriorityExplain } from "./PriorityExplain";
import { Card, Empty, KV } from "./ui";

type DetailTab = "overview" | "score";

export function IncidentQuickPanel({ incident, onClose }: { incident: Incident | null; onClose?: () => void }) {
  const [tab, setTab] = useState<DetailTab>("overview");
  const [copied, setCopied] = useState(false);
  const copyLink = () => {
    const url = `${window.location.origin}/incidents/${incident?.id}`;
    navigator.clipboard.writeText(url).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }).catch(() => {/* noop */});
  };
  const printIncident = () => window.print();

  if (!incident)
    return (
      <Card className="h-full">
        <Empty title="Select an incident">Click a marker or a queue entry to see its details here.</Empty>
      </Card>
    );
  const i = incident;
  return (
    <Card className="flex h-full flex-col overflow-hidden">
      <div className="flex items-start justify-between gap-2 border-b border-line px-4 py-3">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="font-mono text-sm text-ink">{i.id}</span>
            <PriorityBadge value={i.priority_label} score={i.priority_score} />
          </div>
          <div className="flex flex-wrap gap-1.5">
            <ReviewBadge value={i.review_status} />
            <LocationBadge value={i.location_status} />
            <ConfidenceBadge value={i.info_confidence?.overall} />
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button onClick={copyLink} className="rounded p-1.5 text-ink-3 hover:bg-surface-2 hover:text-ink" aria-label="Copy incident link" title="Copy link">
            {copied ? <Check className="h-3.5 w-3.5 text-status-good" /> : <Copy className="h-3.5 w-3.5" />}
          </button>
          <button onClick={printIncident} className="rounded p-1.5 text-ink-3 hover:bg-surface-2 hover:text-ink" aria-label="Print incident" title="Print / Export">
            <Printer className="h-3.5 w-3.5" />
          </button>
          {onClose && (
            <button onClick={onClose} className="rounded p-1 text-ink-3 hover:bg-surface-2 hover:text-ink" aria-label="Close details">
              <X className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>
      {/* Tabs */}
      <div className="flex gap-2 border-b border-line px-4">
        {(["overview", "score"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`flex items-center gap-2 px-3 py-2 text-sm font-medium transition-colors border-b-2 -mb-px whitespace-nowrap ${
              tab === t ? "border-accent text-ink" : "border-transparent text-ink-3 hover:text-ink"
            }`}
          >
            {t === "overview" ? "Overview" : "Score & Audit"}
          </button>
        ))}
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto px-4 py-3">
        {tab === "overview" && (
          <dl>
            <KV k="Location">
              {locationText(i)}
              {i.coordinates_are_simulated && <div className="text-2xs text-ink-3">Map point = reference location, not the exact spot.</div>}
              {!i.latitude && (
                <div className="inline-flex items-center gap-1 text-2xs text-[#f6c75a]">
                  <MapPinOff className="h-3 w-3" /> Not on the map until a dispatcher verifies the location.
                </div>
              )}
            </KV>
            <KV k="People reported">{peopleText(i)}</KV>
            <KV k="Vulnerable">{Object.keys(i.vulnerable).length ? Object.keys(i.vulnerable).map(label).join(", ") : "None mentioned (unknown)"}</KV>
            <KV k="Dangers">{i.dangers.length ? i.dangers.map(label).join(", ") : "—"}</KV>
            <KV k="Needs">{i.needs.length ? i.needs.map(label).join(", ") : "—"}</KV>
            <KV k="Caller urgency">{i.urgency}</KV>
            <KV k="Hazard">{i.disaster_type}</KV>
            <KV k="Languages">{i.languages.map(langLabel).join(", ") || "—"}</KV>
            <KV k="Latest update">{timeAgo(i.last_report_at)} · {i.report_count} report(s)</KV>
          </dl>
        )}

        {tab === "score" && (
          <div className="space-y-3">
            {i.priority_breakdown && <PriorityExplain b={i.priority_breakdown} compact />}
            {i.review_reasons.length > 0 && (
              <div className="rounded-md border border-[#5b4413] bg-[#221c0e] px-3 py-2 text-xs text-[#f6c75a]">
                <div className="mb-1 font-semibold">Why human review is needed</div>
                <ul className="list-disc space-y-0.5 pl-4">
                  {i.review_reasons.map((r, idx) => (
                    <li key={idx}>{r.message}</li>
                  ))}
                </ul>
              </div>
            )}
            {i.recommended_action && (
              <div className="text-xs text-ink-2">
                <span className="text-ink-3">Suggested next human action: </span>
                {i.recommended_action}
              </div>
            )}
          </div>
        )}
      </div>
      <Link to={`/incidents/${i.id}`} className="flex items-center justify-center gap-1 border-t border-line py-2.5 text-sm text-accent hover:bg-surface-2">
        Open investigation <ArrowRight className="h-4 w-4" />
      </Link>
    </Card>
  );
}
