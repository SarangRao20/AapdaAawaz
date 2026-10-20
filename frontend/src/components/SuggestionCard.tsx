import { Check, X } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { getReviewer, setReviewer } from "../lib/reviewer";
import type { Suggestion, SuggestionItem } from "../lib/types";
import { Badge, Button, ErrorBanner, Input } from "./ui";

export function MatchEvidenceTable({ evidence }: { evidence: { feature: string; points: number; detail: string }[] }) {
  return (
    <table className="w-full text-2xs">
      <tbody>
        {evidence.map((e, i) => (
          <tr key={i} className="align-top">
            <td className="w-16 py-0.5 pr-2 text-right font-mono" style={{ color: e.points >= 0 ? "#9fe0a8" : "#f3b0b0" }}>
              {e.points >= 0 ? "+" : ""}
              {e.points.toFixed(2)}
            </td>
            <td className="py-0.5 pr-2 text-ink-2">{e.feature.replace(/_/g, " ")}</td>
            <td className="py-0.5 text-ink-3">{e.detail}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** Possible-duplicate decision: a human confirms (moves the report) or rejects it. */
export function SuggestionCard({ s, onDone, showReport }: { s: Suggestion | SuggestionItem; onDone: () => void; showReport?: boolean }) {
  const [reviewer, setReviewerName] = useState(getReviewer);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const item = s as SuggestionItem;

  async function decide(confirm: boolean) {
    setBusy(confirm ? "c" : "r");
    setError(null);
    try {
      setReviewer(reviewer);
      await api.decideSuggestion(s.id, confirm, reviewer);
      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-2 rounded-md border border-line bg-surface-2 p-3">
      <div className="flex flex-wrap items-center gap-1.5 text-xs">
        <Badge className="border-[#5b4413] text-[#f6c75a]">possible duplicate · score {s.score.toFixed(2)}</Badge>
        <span className="text-ink-2">
          Report{" "}
          <Link to={`/reports?id=${s.report_id}`} className="font-mono text-accent hover:underline">
            {s.report_id}
          </Link>{" "}
          (in{" "}
          <Link to={`/incidents/${s.source_incident_id}`} className="font-mono text-accent hover:underline">
            {s.source_incident_id}
          </Link>
          ) may belong to{" "}
          <Link to={`/incidents/${s.candidate_incident_id}`} className="font-mono text-accent hover:underline">
            {s.candidate_incident_id}
          </Link>
        </span>
        {s.status !== "pending" && <Badge>{s.status}{s.resolved_by ? ` by ${s.resolved_by}` : ""}</Badge>}
      </div>
      {showReport && item.report && (
        <div className="grid gap-2 md:grid-cols-2">
          <div className="rounded border border-line bg-surface-1 p-2 text-xs">
            <div className="mb-1 text-2xs uppercase tracking-wider text-ink-3">New report</div>
            <p className="text-ink" lang={item.report.language ?? undefined}>“{item.report.transcript}”</p>
          </div>
          <div className="rounded border border-line bg-surface-1 p-2 text-xs">
            <div className="mb-1 text-2xs uppercase tracking-wider text-ink-3">Candidate incident {s.candidate_incident_id}</div>
            <p className="text-ink-2">{item.candidate_incident?.summary}</p>
          </div>
        </div>
      )}
      {s.contradictions.length > 0 && (
        <ul className="list-disc pl-4 text-xs text-[#f3b0b0]">
          {s.contradictions.map((c) => (
            <li key={c}>Contradiction: {c}</li>
          ))}
        </ul>
      )}
      {s.evidence?.caps?.length ? <p className="text-2xs text-[#f6c75a]">Not auto-linked because: {s.evidence.caps.join("; ")}</p> : null}
      {s.evidence?.evidence && <MatchEvidenceTable evidence={s.evidence.evidence} />}
      {s.status === "pending" && (
        <div className="flex flex-wrap items-center gap-2 pt-1">
          <Input className="h-7 w-36 text-xs" value={reviewer} onChange={(e) => setReviewerName(e.target.value)} aria-label="Reviewer" />
          <Button size="sm" variant="success" busy={busy === "c"} disabled={!reviewer.trim()} onClick={() => decide(true)}>
            <Check className="h-3.5 w-3.5" /> Same incident — link
          </Button>
          <Button size="sm" variant="danger" busy={busy === "r"} disabled={!reviewer.trim()} onClick={() => decide(false)}>
            <X className="h-3.5 w-3.5" /> Different incident — reject
          </Button>
        </div>
      )}
      {error && <ErrorBanner message={error} />}
    </div>
  );
}
