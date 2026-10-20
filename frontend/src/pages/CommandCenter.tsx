import { motion } from "framer-motion";
import { ArrowLeft, ChevronDown, Clock, Globe2, Map as MapIcon } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { AttentionList } from "../components/AttentionList";
import { DemoControls } from "../components/DemoControls";
import { Globe } from "../components/Globe";
import { IncidentMap } from "../components/IncidentMap";
import { IncidentQueue } from "../components/IncidentQueue";
import { IncidentQuickPanel } from "../components/IncidentQuickPanel";
import { Card, CardHeader, CountUpStat, ErrorBanner, Spinner } from "../components/ui";
import { useIncidentAlerts } from "../lib/alerts";
import { api } from "../lib/api";
import { cn } from "../lib/cn";
import { useI18n } from "../lib/i18n";
import { PRIORITY_COLOR, sortIncidents, timeAgo } from "../lib/format";
import { Reveal, Stagger } from "../lib/motion";
import { usePoll } from "../lib/usePoll";
import type { Incident } from "../lib/types";

const POLL_MS = 2500;
type View = "globe" | "map" | "timeline";

const PRIORITY_FILTERS = ["critical", "high", "medium", "low"] as const;

function TimelineFeed({ incidents, onSelect }: { incidents: Incident[]; onSelect: (id: string) => void }) {
  const sorted = [...incidents].sort((a, b) => new Date(b.last_report_at ?? 0).getTime() - new Date(a.last_report_at ?? 0).getTime());
  if (!sorted.length) return <p className="p-6 text-center text-sm text-ink-3">No incidents yet.</p>;
  return (
    <ol className="relative space-y-0 border-l border-line ml-4">
      {sorted.map((i) => (
        <li key={i.id} className="relative pl-6 pb-4 last:pb-0">
          <span className="absolute -left-1.5 top-1.5 h-3 w-3 rounded-full border-2" style={{ borderColor: PRIORITY_COLOR[i.priority_label], background: `${PRIORITY_COLOR[i.priority_label]}33` }} />
          <button onClick={() => onSelect(i.id)} className="group text-left">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="font-mono text-xs text-ink">{i.id}</span>
              <span className="rounded-md px-1.5 py-0.5 text-2xs font-medium" style={{ color: PRIORITY_COLOR[i.priority_label], background: `${PRIORITY_COLOR[i.priority_label]}22` }}>
                {i.priority_label}
              </span>
            </div>
            <p className="mt-0.5 text-xs text-ink-2 group-hover:text-ink">{i.disaster_type} · {i.report_count} report{i.report_count !== 1 ? "s" : ""}</p>
            <p className="mt-0.5 text-2xs text-ink-3">{timeAgo(i.last_report_at)}</p>
          </button>
        </li>
      ))}
    </ol>
  );
}

export function CommandCenter() {
  const stats = usePoll(api.stats, POLL_MS);
  const incidents = usePoll(() => api.incidents({ limit: 500 }), POLL_MS);
  const gaz = usePoll(api.gazetteer, 0);
  const [params, setParams] = useSearchParams();
  const [selected, setSelected] = useState<string | null>(params.get("focus"));
  const [view, setView] = useState<View>("globe");
  const [scope, setScope] = useState<"urgent" | "all">("urgent");
  const [showAll, setShowAll] = useState(false);
  const [priorityFilter, setPriorityFilter] = useState<Set<string>>(new Set());
  const [typeFilter, setTypeFilter] = useState<string>("all");
  const { fresh } = useIncidentAlerts(incidents.data?.items);
  const { t } = useI18n();

  useEffect(() => {
    const f = params.get("focus");
    if (f) {
      setSelected(f);
      setView("globe");
      params.delete("focus");
      setParams(params, { replace: true });
    }
  }, [params, setParams]);

  const all = useMemo(() => sortIncidents(incidents.data?.items ?? []), [incidents.data]);
  const disasterTypes = useMemo(() => {
    const types = new Set(all.map((i) => i.disaster_type).filter(Boolean));
    return Array.from(types).sort();
  }, [all]);
  const filtered = useMemo(() => all.filter((i) => {
    if (priorityFilter.size > 0 && !priorityFilter.has(i.priority_label)) return false;
    if (typeFilter !== "all" && i.disaster_type !== typeFilter) return false;
    return true;
  }), [all, priorityFilter, typeFilter]);
  const urgent = useMemo(() => filtered.filter((i) => i.priority_label === "critical" || i.priority_label === "high"), [filtered]);
  const list = scope === "urgent" && urgent.length ? urgent : filtered;
  const selectedIncident = all.find((i) => i.id === selected) ?? null;
  const s = stats.data;
  const critical = all.filter((i) => i.priority_label === "critical").length;
  const refreshAll = () => {
    void stats.refresh();
    void incidents.refresh();
  };
  const offline = stats.error && !stats.data;

  return (
    <Stagger className="space-y-5">
      <Reveal className="accent-line-top relative overflow-hidden rounded-2xl glass px-6 py-5">
        {/* Background gradient */}
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-r from-accent/[0.06] via-transparent to-status-critical/[0.04]" aria-hidden />
        <div className="relative flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="mb-2 flex items-center gap-2.5">
              <span className="relative flex h-3 w-3">
                <span className="absolute inline-flex h-full w-full animate-pulse-ring rounded-full bg-status-good" />
                <span className="relative inline-flex h-3 w-3 rounded-full bg-status-good shadow-[0_0_8px_2px_rgba(47,208,107,0.7)]" />
              </span>
              <span className="text-xs font-semibold uppercase tracking-[0.22em] text-ink-3">Situation Room · Live</span>
            </div>
            <h1 className="text-gradient text-4xl font-bold tracking-tight md:text-5xl">Aapda Awaaz</h1>
            <p className="mt-2 max-w-xl text-sm text-ink-2">
              {critical > 0
                ? `${critical} ${t.critical} incident${critical === 1 ? "" : "s"} active — start with the red pins.`
                : all.length
                  ? `${t.allClear} — no critical incidents right now.`
                  : "Waiting for reports. Use “Demo” to load sample calls."}
            </p>
          </div>
          <DemoControls onChanged={refreshAll} hasData={(s?.total_reports ?? 0) > 0} />
        </div>
      </Reveal>

      {stats.error && <ErrorBanner offline message={offline ? stats.error : `Showing last known data — ${stats.error}`} />}

      <Reveal className="grid grid-cols-3 gap-3">
        <CountUpStat label="Critical" value={critical} tone="critical" />
        <CountUpStat label="Needs review" value={s?.incidents_needing_review ?? 0} tone="warning" />
        <CountUpStat label="Reports in" value={s?.total_reports ?? 0} />
      </Reveal>

      <Reveal className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_400px]">
        <Card className="relative overflow-hidden">
          <div className="absolute left-3 top-3 z-20 flex rounded-xl border border-white/10 bg-bg/70 p-1 backdrop-blur" role="tablist" aria-label="Map style">
            {(
              [
                ["globe", "Globe", Globe2],
                ["map", "Map", MapIcon],
                ["timeline", "Timeline", Clock],
              ] as const
            ).map(([key, text, Icon]) => (
              <button
                key={key}
                role="tab"
                aria-selected={view === key}
                onClick={() => setView(key)}
                className={cn("relative flex h-8 items-center gap-1.5 rounded-lg px-3 text-xs font-medium transition-colors", view === key ? "text-ink" : "text-ink-3 hover:text-ink")}
              >
                {view === key && <motion.span layoutId="view-pill" className="absolute inset-0 rounded-lg bg-white/10" transition={{ type: "spring", stiffness: 400, damping: 32 }} />}
                <Icon className="relative h-3.5 w-3.5" aria-hidden />
                <span className="relative">{text}</span>
              </button>
            ))}
          </div>
          {view !== "timeline" && (
            <div className="absolute right-3 top-3 z-20 flex flex-wrap gap-1.5">
              {PRIORITY_FILTERS.map((p) => (
                <button
                  key={p}
                  onClick={() => setPriorityFilter((prev) => {
                    const next = new Set(prev);
                    if (next.has(p)) next.delete(p); else next.add(p);
                    return next;
                  })}
                  className={cn("rounded-full border px-2.5 py-0.5 text-2xs font-medium transition-all", priorityFilter.has(p) ? "border-transparent" : "border-white/10 bg-bg/70 text-ink-3 backdrop-blur hover:text-ink")}
                  style={priorityFilter.has(p) ? { background: `${PRIORITY_COLOR[p]}22`, borderColor: PRIORITY_COLOR[p], color: PRIORITY_COLOR[p] } : {}}
                >
                  {p}
                </button>
              ))}
              {disasterTypes.length > 0 && (
                <select
                  value={typeFilter}
                  onChange={(e) => setTypeFilter(e.target.value)}
                  className="rounded-full border border-white/10 bg-bg/70 px-2.5 py-0.5 text-2xs text-ink-3 backdrop-blur focus:outline-none"
                >
                  <option value="all">All types</option>
                  {disasterTypes.map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
              )}
            </div>
          )}
          <div className="relative h-[560px] md:h-[640px]">
            {/* Inner ambient glow */}
            <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_50%_55%,rgba(37,99,184,0.22),transparent_58%)]" aria-hidden />
            {/* Corner vignette to frame the map */}
            <div className="pointer-events-none absolute inset-0 z-10 bg-[radial-gradient(ellipse_120%_100%_at_50%_50%,transparent_60%,rgba(7,8,11,0.55)_100%)]" aria-hidden />
            {view === "globe" ? (
              <Globe className="h-full w-full" incidents={filtered} selectedId={selected} onSelect={setSelected} onOpenMap={() => setView("map")} />
            ) : view === "map" ? (
              <IncidentMap className="!rounded-none !border-0 h-full" incidents={filtered} places={gaz.data?.places ?? []} selectedId={selected} onSelect={setSelected} compactLegend />
            ) : (
              <div className="h-full overflow-y-auto px-5 py-14">
                <TimelineFeed incidents={filtered} onSelect={(id) => { setSelected(id); setView("globe"); }} />
              </div>
            )}
          </div>
        </Card>

        <div className="flex min-h-[420px] flex-col lg:h-[640px]">
          {selectedIncident ? (
            <div className="flex min-h-0 flex-1 flex-col gap-2">
              <button onClick={() => setSelected(null)} className="inline-flex w-fit items-center gap-1.5 text-xs text-ink-3 transition-colors hover:text-ink">
                <ArrowLeft className="h-3.5 w-3.5" /> Back to list
              </button>
              <div className="min-h-0 flex-1">
                <IncidentQuickPanel incident={selectedIncident} onClose={() => setSelected(null)} />
              </div>
            </div>
          ) : (
            <Card className="flex min-h-0 flex-1 flex-col">
              <CardHeader
                title={scope === "urgent" && urgent.length ? "Needs attention" : "All incidents"}
                subtitle="Tap one to find it on the globe"
                right={
                  <div className="flex rounded-lg bg-white/5 p-0.5 text-2xs">
                    {(["urgent", "all"] as const).map((k) => (
                      <button key={k} onClick={() => setScope(k)} className={cn("rounded-md px-2 py-1 transition-colors", scope === k ? "bg-white/10 text-ink" : "text-ink-3 hover:text-ink")}>
                        {k === "urgent" ? "Urgent" : "All"}
                      </button>
                    ))}
                  </div>
                }
              />
              <div className="min-h-0 flex-1 overflow-y-auto">
                {incidents.loading && !incidents.data ? <Spinner /> : <AttentionList items={list} selectedId={selected} fresh={fresh} onSelect={setSelected} />}
              </div>
            </Card>
          )}
        </div>
      </Reveal>

      <Reveal>
        <Card>
          <button onClick={() => setShowAll((v) => !v)} className="flex w-full items-center justify-between px-5 py-3.5 text-left" aria-expanded={showAll}>
            <span>
              <span className="block text-sm font-semibold">Detailed incident table</span>
              <span className="block text-xs text-ink-3">Scores, confidence and review flags for every incident ({filtered.length}{filtered.length !== all.length ? ` of ${all.length}` : ""})</span>
            </span>
            <ChevronDown className={cn("h-4 w-4 text-ink-3 transition-transform", showAll && "rotate-180")} />
          </button>
          {showAll && <IncidentQueue items={filtered} selectedId={selected} onSelect={setSelected} />}
        </Card>
      </Reveal>
    </Stagger>
  );
}
