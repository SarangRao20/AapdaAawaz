import { AlertTriangle } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "../lib/cn";
import { useI18n } from "../lib/i18n";
import { label, langLabel } from "../lib/format";
import type { Evidence, Extraction, FieldAssessment, Job } from "../lib/types";
import { ModeBadge } from "./badges";
import { Badge } from "./ui";

function quotes(ev: Evidence[], prefix: string): ReactNode {
  const hits = ev.filter((e) => e.field === prefix || e.field.startsWith(`${prefix}.`));
  if (!hits.length) return <span className="text-ink-3">—</span>;
  return (
    <span className="flex flex-wrap gap-1">
      {hits.map((e, i) => (
        <span key={i} className={cn("rounded bg-surface-3 px-1 py-px text-2xs", e.negated && "line-through text-ink-3")} title={e.negated ? "negated in the transcript" : e.field}>
          “{e.text}”
        </span>
      ))}
    </span>
  );
}

function Assess({ a }: { a?: { status: string; evidence_level?: number } }) {
  if (!a) return null;
  const cls = a.status === "ok" ? "text-[#9fe0a8] border-[#1f4a2a]" : a.status === "review" ? "text-[#f6c75a] border-[#5b4413]" : "text-ink-3";
  const barColor = a.status === "ok" ? "#2fd06b" : a.status === "review" ? "#fab219" : "#8a909c";
  const level = typeof a.evidence_level === "number" ? Math.max(0, Math.min(1, a.evidence_level)) : null;
  return (
    <div className="space-y-1">
      <Badge className={cls}>
        {a.status}
        {level !== null && <span className="font-mono">· {level.toFixed(2)}</span>}
      </Badge>
      {level !== null && (
        <div className="w-16 overflow-hidden rounded-full bg-surface-3" style={{ height: 4 }} title={`Confidence: ${(level * 100).toFixed(0)}%`}>
          <div className="h-full rounded-full transition-all duration-500" style={{ width: `${level * 100}%`, background: barColor }} />
        </div>
      )}
    </div>
  );
}

/**
 * Side-by-side view of what the caller actually said (quoted evidence) and how the rule-based
 * system interpreted it. Unknown values are shown as unknown — never as zero or "none".
 */
export function ExtractionView({ ext, assessment }: { ext: Extraction; assessment?: FieldAssessment | null }) {
  const { t } = useI18n();
  const loc = ext.location;
  const pa = ext.people_affected;
  const vul = Object.entries(ext.vulnerable_people).filter(([, v]) => v);
  const rows: { field: string; said: ReactNode; system: ReactNode; assess?: ReactNode }[] = [
    {
      field: t.location,
      said: loc.stated_text.length ? quotes(ext.evidence, "location") : <span className="text-ink-3">not stated</span>,
      system: (
        <div className="space-y-0.5">
          <div>
            {loc.status === "grounded" ? (
              <>
                Matched reference <b>{loc.place_name}</b>
                {loc.landmark && <> · {loc.landmark}</>} <span className="text-ink-3">({loc.place_id}{loc.landmark_id ? `/${loc.landmark_id}` : ""})</span>
              </>
            ) : loc.status === "missing" ? (
              "No location"
            ) : (
              <>
                {label(loc.status)}
                {loc.place_name && <> · “{loc.place_name}”</>}
                {loc.landmark && <> · near “{loc.landmark}”</>}
                {loc.candidates.length > 0 && <> · candidates {loc.candidates.join(", ")}</>}
              </>
            )}
          </div>
          <div className="text-2xs text-ink-3">{loc.confidence_basis}</div>
          {loc.latitude !== null && <div className="text-2xs text-ink-3">Coordinates: SIMULATED reference point ({loc.latitude}, {loc.longitude})</div>}
        </div>
      ),
      assess: <Assess a={assessment?.location} />,
    },
    {
      field: t.people,
      said: quotes(ext.evidence, "people_affected"),
      system: (
        <div>
          {pa.count !== null ? (
            <>
              {pa.approximate ? "≈ " : ""}
              {pa.count}
              {pa.range && <span className="text-ink-3"> (range {pa.range.join("–")})</span>}
            </>
          ) : (
            <span className="text-[#f6c75a]">Unknown</span>
          )}
          {pa.families !== null && <span className="text-ink-2"> · {pa.families} families</span>}
          <div className="text-2xs text-ink-3">{pa.confidence_basis}</div>
        </div>
      ),
      assess: <Assess a={assessment?.people_count} />,
    },
    {
      field: "Vulnerable people",
      said: quotes(ext.evidence, "vulnerable"),
      system: vul.length ? (
        vul.map(([k, v]) => `${label(k)}${v?.count ? ` (${v.count})` : ""}`).join(", ")
      ) : (
        <span className="text-ink-3">None mentioned — unknown, not “none present”</span>
      ),
    },
    { field: "Reported danger", said: quotes(ext.evidence, "danger"), system: ext.reported_danger.map(label).join(", ") || "—" },
    { field: "Immediate needs", said: quotes(ext.evidence, "need"), system: ext.immediate_needs.map(label).join(", ") || "—" },
    {
      field: "Medical emergency",
      said: quotes(ext.evidence, "medical_emergency"),
      system: ext.medical_emergency ? "Yes" : <span className="text-ink-3">Not mentioned (unknown)</span>,
    },
    { field: "Hazard", said: quotes(ext.evidence, "disaster_type"), system: <>{ext.disaster_type} <div className="text-2xs text-ink-3">{ext.disaster_basis}</div></> },
    {
      field: t.urgency,
      said: quotes(ext.evidence, "urgency"),
      system: <>{ext.urgency} <div className="text-2xs text-ink-3">{ext.urgency_basis}</div></>,
      assess: <Assess a={assessment?.urgency} />,
    },
    { field: "Status claims", said: quotes(ext.evidence, "status"), system: ext.status_claims.map(label).join(", ") || "—" },
    {
      field: "Language / quality",
      said: <span className="text-ink-3">—</span>,
      system: (
        <>
          {langLabel(ext.language)} · transcript {ext.transcript_quality}
          <div className="text-2xs text-ink-3">{ext.transcript_quality_basis}</div>
        </>
      ),
      assess: <Assess a={assessment?.transcript} />,
    },
  ];
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-1.5 text-2xs text-ink-3">
        Extracted by <ModeBadge mode={ext.provider_mode} provider={ext.provider} /> <span className="font-mono">{ext.provider}</span>
        <span>· evidence levels are documented rule scores, not probabilities</span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-xs">
          <thead>
            <tr className="border-b border-line text-left text-2xs uppercase tracking-wider text-ink-3">
              <th className="py-1.5 pr-2 font-medium">Field</th>
              <th className="py-1.5 pr-2 font-medium">Caller’s words (quoted)</th>
              <th className="py-1.5 pr-2 font-medium">System interpretation</th>
              <th className="py-1.5 font-medium">Gate</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {rows.map((r) => (
              <tr key={r.field} className="align-top">
                <td className="py-1.5 pr-2 text-ink-2">{r.field}</td>
                <td className="py-1.5 pr-2">{r.said}</td>
                <td className="py-1.5 pr-2 text-ink">{r.system}</td>
                <td className="py-1.5">{r.assess}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {ext.uncertainties.length > 0 && (
        <div className="rounded-md border border-[#5b4413] bg-[#221c0e] px-3 py-2 text-xs text-[#f6c75a]">
          <div className="mb-1 inline-flex items-center gap-1 font-semibold">
            <AlertTriangle className="h-3.5 w-3.5" /> Extraction warnings
          </div>
          <ul className="list-disc space-y-0.5 pl-4">
            {ext.uncertainties.map((u) => (
              <li key={u}>{u}</li>
            ))}
          </ul>
        </div>
      )}
      <p className="text-2xs text-ink-3">
        Rule-generated summary (not the caller’s words): <span className="text-ink-2">{ext.summary}</span>
      </p>
    </div>
  );
}

export function JobTimeline({ jobs }: { jobs: Job[] }) {
  if (!jobs.length) return <p className="text-xs text-ink-3">No processing has run yet.</p>;
  return (
    <ol className="space-y-1">
      {jobs.map((j) => (
        <li key={j.id} className="grid grid-cols-[7.5rem_1fr_auto] items-start gap-2 text-xs">
          <span className="text-ink-2">{label(j.stage)}</span>
          <span className="min-w-0 space-x-1">
            <Badge className={cn(j.status === "failed" && "border-[#5a2323] text-[#f3b0b0]", j.status === "succeeded" && "text-[#9fe0a8]")}>{j.status}</Badge>
            <ModeBadge mode={j.provider_mode} provider={j.provider} />
            <span className="font-mono text-2xs text-ink-3">{j.provider}</span>
            {j.error && <div className="text-2xs text-[#f3b0b0]">{j.error}</div>}
            {typeof j.detail?.note === "string" && <div className="text-2xs text-[#f6c75a]">{j.detail.note}</div>}
          </span>
          <span className="font-mono text-2xs text-ink-3">{j.duration_ms != null ? `${j.duration_ms.toFixed(1)} ms` : ""}</span>
        </li>
      ))}
    </ol>
  );
}
