import { Download, FlaskConical, Play } from "lucide-react";
import { useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Badge, Button, Card, CardHeader, ErrorBanner, Spinner, Stat } from "../components/ui";
import { api } from "../lib/api";
import { cn } from "../lib/cn";
import { num, pct } from "../lib/format";
import type { Breakdown, EvaluationResult, PRF } from "../lib/types";
import { usePoll } from "../lib/usePoll";

const SERIES = "#3987e5"; // categorical slot 1 (dark) — single-series charts
const GRID = "#2a2d33";
const AXIS = "#8e8d86";
// Sequential blue ramp (light -> dark) for the confusion-matrix heatmap.
const SEQ = ["#1d1f23", "#104281", "#184f95", "#1c5cab", "#256abf", "#2a78d6", "#3987e5"];
const LANG_COLORS: Record<string, string> = { hi: "#4d9dff", mr: "#fab219", en: "#2fd06b", mixed: "#ff8a5c" };

function TooltipBox({ active, payload }: { active?: boolean; payload?: { payload: { name: string; value: number; detail?: string } }[] }) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="rounded-md border border-line-strong bg-surface-2 px-2.5 py-1.5 text-xs text-ink shadow-lg">
      <div className="font-medium">{d.name}</div>
      <div className="font-mono text-ink-2">{d.detail ?? d.value}</div>
    </div>
  );
}

function HBar({ data, unit = "", domain }: { data: { name: string; value: number; detail?: string }[]; unit?: string; domain?: [number, number] }) {
  return (
    <ResponsiveContainer width="100%" height={Math.max(120, data.length * 34 + 30)}>
      <BarChart data={data} layout="vertical" margin={{ left: 8, right: 40, top: 4, bottom: 4 }}>
        <CartesianGrid horizontal={false} stroke={GRID} />
        <XAxis type="number" domain={domain} tick={{ fill: AXIS, fontSize: 11 }} axisLine={{ stroke: GRID }} tickLine={false} unit={unit} />
        <YAxis type="category" dataKey="name" width={150} tick={{ fill: "#c3c2b7", fontSize: 11 }} axisLine={false} tickLine={false} />
        <Tooltip content={<TooltipBox />} cursor={{ fill: "#ffffff0d" }} />
        <Bar dataKey="value" fill={SERIES} barSize={16} radius={[0, 4, 4, 0]} isAnimationActive={false} label={{ position: "right", fill: "#c3c2b7", fontSize: 11, formatter: (v: number) => `${v}${unit}` }} />
      </BarChart>
    </ResponsiveContainer>
  );
}

function BreakdownRow({ name, b }: { name: string; b: Breakdown }) {
  return (
    <tr className="border-t border-line">
      <td className="py-1.5 pr-2 text-ink">{name}</td>
      <td className="py-1.5 pr-2 text-right font-mono">{b.n}</td>
      <td className="py-1.5 pr-2 text-right font-mono">{b.correct}</td>
      <td className="py-1.5 pr-2 text-right font-mono">{b.correct_unknown}</td>
      <td className={cn("py-1.5 pr-2 text-right font-mono", b.wrong && "text-[#f3b0b0]")}>{b.wrong}</td>
      <td className={cn("py-1.5 pr-2 text-right font-mono", b.missed && "text-[#f6c75a]")}>{b.missed}</td>
      <td className={cn("py-1.5 pr-2 text-right font-mono", b.false_value && "text-[#f3b0b0]")}>{b.false_value}</td>
      <td className="py-1.5 text-right font-mono text-ink">{pct(b.accuracy, 1)}</td>
    </tr>
  );
}

function Confusion({ m, labels, title }: { m: Record<string, Record<string, number>>; labels: string[]; title: string }) {
  const cols = Array.from(new Set([...labels, ...Object.values(m).flatMap((r) => Object.keys(r))]));
  const rows = labels.filter((l) => m[l]);
  const max = Math.max(1, ...rows.flatMap((r) => cols.map((c) => m[r]?.[c] ?? 0)));
  return (
    <div className="overflow-x-auto">
      <table className="text-xs">
        <caption className="mb-1 text-left text-2xs text-ink-3">{title} — rows: ground truth, columns: predicted</caption>
        <thead>
          <tr>
            <th />
            {cols.map((c) => (
              <th key={c} className="px-2 py-1 text-center font-medium text-ink-3">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r}>
              <th className="pr-2 text-right font-medium text-ink-3">{r}</th>
              {cols.map((c) => {
                const v = m[r]?.[c] ?? 0;
                const step = v ? Math.min(SEQ.length - 1, 1 + Math.floor((v / max) * (SEQ.length - 2))) : 0;
                return (
                  <td
                    key={c}
                    title={`ground truth ${r}, predicted ${c}: ${v}`}
                    className={cn("h-9 w-14 border-2 border-surface-1 text-center font-mono", r === c ? "font-semibold" : "", v ? "text-white" : "text-ink-3")}
                    style={{ background: SEQ[step] }}
                  >
                    {v}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function prfCells(x: PRF) {
  return (
    <>
      <td className="py-1 pr-2 text-right font-mono">{x.support ?? x.tp + x.fn}</td>
      <td className="py-1 pr-2 text-right font-mono">{x.tp}</td>
      <td className="py-1 pr-2 text-right font-mono">{x.fp}</td>
      <td className="py-1 pr-2 text-right font-mono">{x.fn}</td>
      <td className="py-1 pr-2 text-right font-mono">{pct(x.precision)}</td>
      <td className="py-1 pr-2 text-right font-mono">{pct(x.recall)}</td>
      <td className="py-1 text-right font-mono">{pct(x.f1)}</td>
    </>
  );
}

export function Evaluation() {
  const ev = usePoll(api.evaluation, 0);
  const settings = usePoll(api.settings, 0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [onlyErrors, setOnlyErrors] = useState(false);
  const [split, setSplit] = useState<"development" | "holdout">("holdout");

  async function run(includeStt: boolean) {
    setBusy(true);
    setError(null);
    try {
      ev.setData(await api.runEvaluation(includeStt));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const data = ev.data as EvaluationResult | null;
  const rows = useMemo(() => {
    if (!data?.splits) return [];
    return data.splits[split].rows.filter((r) =>
      !onlyErrors ||
      r.gt_place !== r.pred_place || r.gt_people !== r.pred_people || r.gt_priority !== r.pred_priority || r.gt_language !== r.pred_language,
    );
  }, [data, onlyErrors, split]);

  if (ev.loading && !data) return <Spinner label="Running evaluation on the synthetic dataset…" />;
  if (!data?.splits) return <ErrorBanner offline message={ev.error ?? "No evaluation available"} />;
  const sp = data.splits[split];
  const m = sp.metrics;
  const keyConfigured = settings.data?.providers.gnani_api_key_configured;

  const accuracy = [
    { name: "Location (reference place)", value: Math.round((m.location.accuracy ?? 0) * 100), detail: `${pct(m.location.accuracy, 1)} of n=${m.location.n}` },
    { name: "People count", value: Math.round((m.people_count.accuracy ?? 0) * 100), detail: `${pct(m.people_count.accuracy, 1)} of n=${m.people_count.n}` },
    { name: "Priority label", value: Math.round((m.priority.accuracy ?? 0) * 100), detail: `${pct(m.priority.accuracy, 1)} of n=${m.n_reports}` },
    { name: "Language", value: Math.round((m.language.accuracy ?? 0) * 100), detail: `${pct(m.language.accuracy, 1)} of n=${m.n_reports}` },
    { name: "Hazard type", value: Math.round((m.disaster_type.accuracy ?? 0) * 100), detail: `${pct(m.disaster_type.accuracy, 1)} of n=${m.disaster_type.n}` },
  ];
  const reasons = Object.entries(m.human_review.reasons)
    .sort((a, b) => b[1] - a[1])
    .map(([name, value]) => ({ name: name.replace(/_/g, " "), value }));

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold">Evaluation Lab</h1>
          <p className="text-xs text-ink-3">
            Run {data.run_id} · {new Date(data.generated_at).toLocaleString()} · {data.dataset.label} · v{data.dataset.version}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="primary" busy={busy} onClick={() => run(false)}>
            <Play className="h-4 w-4" /> Re-run with current settings
          </Button>
          <Button busy={busy} disabled={!keyConfigured} title={keyConfigured ? "" : "Requires GNANI_API_KEY"} onClick={() => run(true)}>
            Include real Prisma STT
          </Button>
          <a href="/api/evaluation/export.csv" className="inline-flex h-9 items-center gap-1.5 rounded-md border border-line bg-surface-2 px-3.5 text-sm text-ink hover:bg-surface-3">
            <Download className="h-4 w-4" /> CSV
          </a>
        </div>
      </div>
      {error && <ErrorBanner message={error} />}

      <Card className="border-[#3d2f5c] bg-[#17142a] px-4 py-3 text-xs text-[#d8cff8]">
        <div className="mb-1 flex items-center gap-1.5 font-semibold">
          <FlaskConical className="h-3.5 w-3.5" /> Read before quoting any number
        </div>
        <ul className="list-disc space-y-0.5 pl-4">
          {data.caveats.map((c) => (
            <li key={c}>{c}</li>
          ))}
          <li>Extraction: {data.providers.extraction}. Transcripts: {data.providers.transcripts}.</li>
        </ul>
      </Card>

      <Card className="flex flex-wrap items-center gap-3 px-4 py-2.5">
        <div className="flex gap-1" role="tablist" aria-label="Dataset split">
          {(["holdout", "development"] as const).map((k) => (
            <button
              key={k}
              role="tab"
              aria-selected={split === k}
              onClick={() => setSplit(k)}
              className={cn("h-8 rounded-md border px-3 text-sm", split === k ? "border-ink-2 bg-surface-3 text-ink" : "border-line bg-surface-2 text-ink-3 hover:text-ink")}
            >
              {k === "holdout" ? "Hold-out" : "Development"} <span className="font-mono text-xs text-ink-3">n={data.splits[k].n_reports}</span>
            </button>
          ))}
        </div>
        <p className="text-xs text-ink-2">{sp.description}</p>
      </Card>

      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-white/[0.06] bg-surface-2 px-4 py-3 text-xs">
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-status-good" />
          <span className="font-medium text-ink">Evaluation extractor:</span>
          <span className="rounded-md bg-surface-3 px-2 py-0.5 font-mono text-2xs text-ink-2">
            rule-based-v1
          </span>
          <span className="text-ink-3">
            Live calls: {data.providers.evon_available ? "Gnani Evon v3.3" : "rule-based-v1"}
          </span>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-8">
        <Stat label="Test reports" value={m.n_reports} hint="labelled synthetic fixtures" />
        <Stat label="STT success rate" value={data.stt.measured ? pct(data.stt.success_rate) : "not measured"} hint={data.stt.measured ? `n=${data.stt.samples.length}` : "mock STT is not ASR"} />
        <Stat label="Location accuracy" value={pct(m.location.accuracy)} hint={`n=${m.location.n}`} />
        <Stat label="People-count accuracy" value={pct(m.people_count.accuracy)} hint={`n=${m.people_count.n}`} />
        <Stat label="Vulnerable F1 (micro)" value={pct(m.vulnerable.micro.f1)} hint={`${m.vulnerable.micro.tp + m.vulnerable.micro.fn} labelled mentions`} />
        <Stat label="Priority accuracy" value={pct(m.priority.accuracy)} hint={`${m.priority.under_triaged.length} under-triaged · n=${m.n_reports}`} />
        <Stat label="Duplicate P / R" value={`${pct(m.deduplication.pairwise.precision)} / ${pct(m.deduplication.pairwise.recall)}`} hint={`${m.deduplication.pairwise.tp + m.deduplication.pairwise.fn} labelled pairs`} />
        <Stat label="Human-review rate" value={pct(m.human_review.rate)} hint={`${m.human_review.count} of ${m.n_reports} · ${num(m.latency_ms.mean, 1)} ms avg`} />
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader title="Accuracy by field" subtitle="% of labelled reports where the prediction matched (including correctly-unknown)" />
          <div className="p-3">
            <HBar data={accuracy} unit="%" domain={[0, 100]} />
          </div>
        </Card>
        <Card>
          <CardHeader title="Error breakdown" subtitle="Unknown is a valid answer: 'missed' = labelled value not extracted; 'invented' = value where the label is unknown" />
          <div className="overflow-x-auto p-4">
            <table className="w-full text-xs">
              <thead className="text-2xs uppercase tracking-wider text-ink-3">
                <tr>
                  <th className="text-left font-medium">Field</th>
                  <th className="text-right font-medium">n</th>
                  <th className="text-right font-medium">Correct</th>
                  <th className="text-right font-medium">Correctly unknown</th>
                  <th className="text-right font-medium">Wrong</th>
                  <th className="text-right font-medium">Missed</th>
                  <th className="text-right font-medium">Invented</th>
                  <th className="text-right font-medium">Accuracy</th>
                </tr>
              </thead>
              <tbody>
                <BreakdownRow name="Location" b={m.location} />
                <BreakdownRow name="People count" b={m.people_count} />
                <BreakdownRow name="Hazard type" b={m.disaster_type} />
              </tbody>
            </table>
            <p className="mt-2 text-2xs text-ink-3">{m.disaster_type.definition}</p>
          </div>
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Card>
          <CardHeader title="Priority classification" subtitle={`Under-triaged: ${m.priority.under_triaged.join(", ") || "none"} · Over-triaged: ${m.priority.over_triaged.join(", ") || "none"}`} />
          <div className="space-y-3 p-4">
            <Confusion m={m.priority.confusion} labels={m.priority.labels} title="Priority" />
            <table className="w-full text-xs">
              <thead className="text-2xs uppercase tracking-wider text-ink-3">
                <tr>
                  <th className="text-left font-medium">Label</th>
                  <th className="text-right font-medium">n</th>
                  <th className="text-right font-medium">TP</th>
                  <th className="text-right font-medium">FP</th>
                  <th className="text-right font-medium">FN</th>
                  <th className="text-right font-medium">P</th>
                  <th className="text-right font-medium">R</th>
                  <th className="text-right font-medium">F1</th>
                </tr>
              </thead>
              <tbody>
                {m.priority.labels.map((l) => (
                  <tr key={l} className="border-t border-line">
                    <td className="py-1 text-ink">{l}</td>
                    {prfCells(m.priority.per_class[l])}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
        <Card>
          <CardHeader title="Vulnerable-person detection" subtitle="Mention-level, per group" />
          <div className="overflow-x-auto p-4">
            <table className="w-full text-xs">
              <thead className="text-2xs uppercase tracking-wider text-ink-3">
                <tr>
                  <th className="text-left font-medium">Group</th>
                  <th className="text-right font-medium">n</th>
                  <th className="text-right font-medium">TP</th>
                  <th className="text-right font-medium">FP</th>
                  <th className="text-right font-medium">FN</th>
                  <th className="text-right font-medium">P</th>
                  <th className="text-right font-medium">R</th>
                  <th className="text-right font-medium">F1</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(m.vulnerable.per_group).map(([g, x]) => (
                  <tr key={g} className="border-t border-line">
                    <td className="py-1 text-ink">{g.replace(/_/g, " ")}</td>
                    {prfCells(x)}
                  </tr>
                ))}
                <tr className="border-t border-line-strong">
                  <td className="py-1 font-semibold text-ink">medical emergency</td>
                  {prfCells(m.medical_emergency)}
                </tr>
              </tbody>
            </table>
            <p className="mt-2 text-2xs text-ink-3">Small supports (n &lt; 5) make these numbers fragile.</p>
          </div>
        </Card>
        <Card>
          <CardHeader title="Duplicate detection" subtitle={m.deduplication.definition} />
          <div className="space-y-3 p-4 text-xs">
            <table className="w-full">
              <tbody>
                <tr><td className="text-ink-3">Labelled incidents</td><td className="text-right font-mono">{m.deduplication.gt_incidents}</td></tr>
                <tr><td className="text-ink-3">Predicted incidents</td><td className="text-right font-mono">{m.deduplication.predicted_incidents}</td></tr>
                <tr><td className="text-ink-3">Same-incident pairs (labelled)</td><td className="text-right font-mono">{m.deduplication.pairwise.tp + m.deduplication.pairwise.fn}</td></tr>
                <tr><td className="text-ink-3">Auto-linked pairs correct / wrong</td><td className="text-right font-mono">{m.deduplication.pairwise.tp} / {m.deduplication.pairwise.fp}</td></tr>
                <tr><td className="text-ink-3">Pairwise precision</td><td className="text-right font-mono">{pct(m.deduplication.pairwise.precision, 1)}</td></tr>
                <tr><td className="text-ink-3">Pairwise recall</td><td className="text-right font-mono">{pct(m.deduplication.pairwise.recall, 1)}</td></tr>
                <tr><td className="text-ink-3">Possible-duplicate suggestions</td><td className="text-right font-mono">{m.deduplication.possible_duplicate_suggestions.total}</td></tr>
                <tr><td className="text-ink-3">… that were true duplicates</td><td className="text-right font-mono">{m.deduplication.possible_duplicate_suggestions.true_duplicate}</td></tr>
              </tbody>
            </table>
            <p className="text-2xs text-ink-3">Recall is limited on purpose: contradictory, noisy or ungrounded reports are sent to a human as suggestions instead of being merged automatically.</p>
          </div>
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Card>
          <CardHeader title="Why reports were sent to human review" subtitle={`${m.human_review.count} of ${m.n_reports} reports (a report can have several reasons)`} />
          <div className="p-3">{reasons.length ? <HBar data={reasons} /> : <p className="p-3 text-xs text-ink-3">No review flags.</p>}</div>
        </Card>
        <Card>
          <CardHeader title="Language detection" subtitle="Distribution in this split" />
          <div className="p-4 space-y-4">
            {(() => {
              const langs = ["hi", "mr", "en", "mixed"];
              const totals = langs.map((l) => ({
                name: l === "hi" ? "Hindi" : l === "mr" ? "Marathi" : l === "en" ? "English" : "Mixed",
                code: l,
                value: Object.values(m.language.confusion[l] ?? {}).reduce((a, b) => a + b, 0),
              })).filter((d) => d.value > 0);
              return (
                <div className="flex items-center gap-6">
                  <PieChart width={120} height={120}>
                    <Pie data={totals} dataKey="value" cx="50%" cy="50%" innerRadius={32} outerRadius={52} paddingAngle={3} isAnimationActive={false}>
                      {totals.map((d) => <Cell key={d.code} fill={LANG_COLORS[d.code] ?? SERIES} />)}
                    </Pie>
                    <Tooltip formatter={(v, _n, p) => [`${v} reports`, p.payload.name]} contentStyle={{ background: "#14171d", border: "1px solid #343b47", borderRadius: 8 }} />
                  </PieChart>
                  <ul className="space-y-1.5">
                    {totals.map((d) => (
                      <li key={d.code} className="flex items-center gap-2 text-xs">
                        <span className="h-2.5 w-2.5 rounded-full flex-shrink-0" style={{ background: LANG_COLORS[d.code] ?? SERIES }} />
                        <span className="text-ink-2">{d.name}</span>
                        <span className="ml-auto font-mono text-ink">{d.value}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              );
            })()}
            <Confusion m={m.language.confusion} labels={["mr", "hi", "en", "mixed"]} title="Language confusion matrix" />
          </div>
        </Card>
        <Card>
          <CardHeader title="Speech-to-text" subtitle={data.stt.provider ?? "no real provider run"} />
          <div className="space-y-2 p-4 text-xs text-ink-2">
            <p>{data.stt.note}</p>
            <p>Synthetic audio fixtures available: {data.stt.audio_fixtures}</p>
            {data.stt.measured && (
              <p>
                Success {pct(data.stt.success_rate)} · mean character error rate {num(data.stt.mean_cer, 3)}
              </p>
            )}
            <p className="text-2xs text-ink-3">Latency: {m.latency_ms.note} — mean {num(m.latency_ms.mean, 2)} ms, p95 {num(m.latency_ms.p95, 2)} ms.</p>
          </div>
        </Card>
      </div>

      <Card>
        <CardHeader
          title="Per-report comparison"
          subtitle="Ground truth vs prediction for every synthetic report"
          right={
            <label className="flex items-center gap-1.5 text-xs text-ink-2">
              <input type="checkbox" checked={onlyErrors} onChange={(e) => setOnlyErrors(e.target.checked)} /> Only mismatches
            </label>
          }
        />
        <div className="max-h-[560px] overflow-auto">
          <table className="w-full min-w-[960px] text-xs">
            <thead className="sticky top-0 bg-surface-1 text-2xs uppercase tracking-wider text-ink-3">
              <tr>
                {["Report", "Group → incident", "Dedup", "Place gt/pred", "People gt/pred", "Priority gt/pred", "Language gt/pred", "Review reasons"].map((h) => (
                  <th key={h} className="px-3 py-2 text-left font-medium">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {rows.map((r) => {
                const bad = (a: unknown, b: unknown) => (a !== b ? "text-[#f3b0b0]" : "text-ink-2");
                return (
                  <tr key={String(r.fixture_id)}>
                    <td className="px-3 py-1.5 font-mono text-ink">{r.fixture_id}</td>
                    <td className="px-3 py-1.5 font-mono text-ink-2">{r.gt_group} → {r.pred_incident}</td>
                    <td className="px-3 py-1.5">
                      <Badge>{String(r.dedup_outcome).replace(/_/g, " ")}</Badge>
                    </td>
                    <td className={cn("px-3 py-1.5 font-mono", bad(r.gt_place, r.pred_place))}>{String(r.gt_place ?? "∅")} / {String(r.pred_place ?? "∅")}</td>
                    <td className={cn("px-3 py-1.5 font-mono", bad(r.gt_people, r.pred_people))}>{String(r.gt_people ?? "∅")} / {String(r.pred_people ?? "∅")}</td>
                    <td className={cn("px-3 py-1.5 font-mono", bad(r.gt_priority, r.pred_priority))}>{String(r.gt_priority)} / {String(r.pred_priority)}</td>
                    <td className={cn("px-3 py-1.5 font-mono", bad(r.gt_language, r.pred_language))}>{String(r.gt_language)} / {String(r.pred_language)}</td>
                    <td className="px-3 py-1.5 text-2xs text-ink-3">{String(r.review_reasons || "—").replace(/\|/g, ", ")}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="border-t border-line px-4 py-2 text-2xs text-ink-3">∅ = unknown / not stated. Red = mismatch with the synthetic label.</p>
      </Card>
    </div>
  );
}
