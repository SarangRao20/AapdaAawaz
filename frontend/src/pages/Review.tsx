import { ShieldCheck } from "lucide-react";
import { useMemo } from "react";
import { Link } from "react-router-dom";
import { LocationBadge, PriorityBadge, ReviewBadge } from "../components/badges";
import { SuggestionCard } from "../components/SuggestionCard";
import { Badge, Card, CardHeader, Empty, ErrorBanner, Spinner } from "../components/ui";
import { api } from "../lib/api";
import { locationText, needsReview, peopleText, sortIncidents } from "../lib/format";
import { usePoll } from "../lib/usePoll";

export function Review() {
  const incidents = usePoll(() => api.incidents({ limit: 500 }), 3000);
  const suggestions = usePoll(() => api.suggestions("pending"), 3000);
  const transcripts = usePoll(() => api.reports({ status: "needs_transcript,failed", limit: 50 }), 3000);
  const queue = useMemo(() => sortIncidents((incidents.data?.items ?? []).filter(needsReview)), [incidents.data]);
  const refresh = () => {
    void incidents.refresh();
    void suggestions.refresh();
  };
  const err = incidents.error || suggestions.error;

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold">Human Review</h1>
        <p className="text-xs text-ink-3">
          Resolve uncertain locations, validate extracted information and decide duplicate suggestions. Nothing here is automated: every decision is
          recorded with the reviewer’s name, and the original AI output is preserved.
        </p>
      </div>
      {err && <ErrorBanner offline message={err} />}

      <div className="grid gap-4 xl:grid-cols-2">
        <Card className="self-start">
          <CardHeader title="Incidents awaiting review" subtitle="Highest priority first" right={<span className="font-mono text-xs text-ink-3">{queue.length}</span>} />
          {incidents.loading && !incidents.data ? (
            <Spinner />
          ) : queue.length ? (
            <ul className="divide-y divide-line">
              {queue.map((i) => (
                <li key={i.id} className="space-y-1.5 px-4 py-3">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <PriorityBadge value={i.priority_label} score={i.priority_score} />
                    <Link to={`/incidents/${i.id}`} className="font-mono text-xs text-accent hover:underline">
                      {i.id}
                    </Link>
                    <ReviewBadge value={i.review_status} />
                    <LocationBadge value={i.location_status} />
                  </div>
                  <div className="text-sm">{locationText(i)} · people: {peopleText(i)}</div>
                  <ul className="space-y-0.5 text-xs">
                    {i.review_reasons.map((r, idx) => (
                      <li key={idx} className="flex gap-2">
                        <Badge className="border-[#5b4413] text-[#f6c75a]">{r.code}</Badge>
                        <span className="text-ink-2">{r.message}</span>
                      </li>
                    ))}
                  </ul>
                  <Link to={`/incidents/${i.id}`} className="inline-block text-xs text-accent hover:underline">
                    Open evidence & verification controls →
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <Empty icon={<ShieldCheck className="h-6 w-6" />} title="No incidents need review" />
          )}
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader title="Duplicate suggestions" subtitle="Possible duplicates the rules would not merge on their own" right={<span className="font-mono text-xs text-ink-3">{suggestions.data?.pending ?? 0}</span>} />
            <div className="space-y-3 p-4">
              {suggestions.loading && !suggestions.data ? (
                <Spinner />
              ) : suggestions.data?.items.length ? (
                suggestions.data.items.map((s) => <SuggestionCard key={s.id} s={s} showReport onDone={refresh} />)
              ) : (
                <Empty title="No pending duplicate suggestions" />
              )}
            </div>
          </Card>
          <Card>
            <CardHeader title="Reports needing a transcript or retry" subtitle="Speech-to-text could not produce text (mock STT only knows the bundled fixtures)" />
            {transcripts.data?.items.length ? (
              <ul className="divide-y divide-line">
                {transcripts.data.items.map((r) => (
                  <li key={r.id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-2 text-xs">
                    <Link to={`/reports?id=${r.id}`} className="font-mono text-accent hover:underline">
                      {r.id}
                    </Link>
                    <span className="text-ink-3">{r.status} · {r.error ?? ""}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <Empty title="None" />
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
