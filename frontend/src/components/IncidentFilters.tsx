import { PRIORITY_COLOR, PRIORITY_ORDER, langLabel } from "../lib/format";
import { cn } from "../lib/cn";
import type { Incident, Priority } from "../lib/types";
import { Select } from "./ui";

export interface Filters {
  priorities: Priority[];
  review: "" | "open" | "reviewed" | "clear";
  disaster: string;
  language: string;
  verification: "" | "verified" | "reference" | "ungrounded";
}

export const EMPTY_FILTERS: Filters = { priorities: [], review: "", disaster: "", language: "", verification: "" };

export function applyFilters(items: Incident[], f: Filters): Incident[] {
  return items.filter((i) => {
    if (f.priorities.length && !f.priorities.includes(i.priority_label)) return false;
    if (f.review === "open" && !["needs_review", "rereview_needed"].includes(i.review_status)) return false;
    if (f.review === "reviewed" && i.review_status !== "reviewed") return false;
    if (f.review === "clear" && i.review_status !== "no_review_required") return false;
    if (f.disaster && i.disaster_type !== f.disaster) return false;
    if (f.language && !i.languages.includes(f.language)) return false;
    if (f.verification === "verified" && i.location_status !== "human_verified") return false;
    if (f.verification === "reference" && !["simulated_reference", "caller_gps"].includes(i.location_status)) return false;
    if (f.verification === "ungrounded" && ["human_verified", "simulated_reference", "caller_gps"].includes(i.location_status)) return false;
    return true;
  });
}

export function IncidentFilters({ value, onChange, counts }: { value: Filters; onChange: (f: Filters) => void; counts: Record<string, number> }) {
  const toggle = (p: Priority) =>
    onChange({ ...value, priorities: value.priorities.includes(p) ? value.priorities.filter((x) => x !== p) : [...value.priorities, p] });
  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="flex items-center gap-1" role="group" aria-label="Priority filter">
        {PRIORITY_ORDER.map((p) => {
          const on = value.priorities.includes(p);
          return (
            <button
              key={p}
              onClick={() => toggle(p)}
              aria-pressed={on}
              className={cn(
                "inline-flex h-7 items-center gap-1.5 rounded-md border px-2 text-xs capitalize",
                on ? "border-ink-2 bg-surface-3 text-ink" : "border-line bg-surface-2 text-ink-2 hover:text-ink",
              )}
            >
              <span className="h-2 w-2 rounded-full" style={{ background: PRIORITY_COLOR[p] }} />
              {p}
              <span className="font-mono text-ink-3">{counts[p] ?? 0}</span>
            </button>
          );
        })}
      </div>
      <Select aria-label="Review status" className="h-7 w-auto text-xs" value={value.review} onChange={(e) => onChange({ ...value, review: e.target.value as Filters["review"] })}>
        <option value="">Any review status</option>
        <option value="open">Needs review</option>
        <option value="reviewed">Reviewed</option>
        <option value="clear">No review flags</option>
      </Select>
      <Select aria-label="Disaster type" className="h-7 w-auto text-xs" value={value.disaster} onChange={(e) => onChange({ ...value, disaster: e.target.value })}>
        <option value="">Any hazard</option>
        {["flood", "landslide", "earthquake", "fire", "other", "unknown"].map((d) => (
          <option key={d} value={d}>
            {d}
          </option>
        ))}
      </Select>
      <Select aria-label="Language" className="h-7 w-auto text-xs" value={value.language} onChange={(e) => onChange({ ...value, language: e.target.value })}>
        <option value="">Any language</option>
        {["mr", "hi", "en", "mixed"].map((l) => (
          <option key={l} value={l}>
            {langLabel(l)}
          </option>
        ))}
      </Select>
      <Select aria-label="Verification" className="h-7 w-auto text-xs" value={value.verification} onChange={(e) => onChange({ ...value, verification: e.target.value as Filters["verification"] })}>
        <option value="">Any location state</option>
        <option value="verified">Verified by dispatcher</option>
        <option value="reference">Reference match (unverified)</option>
        <option value="ungrounded">Not grounded (not on map)</option>
      </Select>
      {(value.priorities.length > 0 || value.review || value.disaster || value.language || value.verification) && (
        <button className="text-xs text-accent hover:underline" onClick={() => onChange(EMPTY_FILTERS)}>
          Clear filters
        </button>
      )}
    </div>
  );
}
