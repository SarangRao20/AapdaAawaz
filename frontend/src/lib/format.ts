import type { Incident, Priority } from "./types";

export const PRIORITY_ORDER: Priority[] = ["critical", "high", "medium", "low"];
export const PRIORITY_RANK: Record<Priority, number> = { critical: 3, high: 2, medium: 1, low: 0 };

// Status palette (fixed): critical / serious / warning, plus a neutral for "low".
export const PRIORITY_COLOR: Record<Priority, string> = {
  critical: "#d03b3b",
  high: "#ec835a",
  medium: "#fab219",
  low: "#8e8d86",
};

export const LABELS: Record<string, string> = {
  rescue_evacuation: "Rescue / evacuation",
  medical: "Medical help",
  food: "Food",
  drinking_water: "Drinking water",
  shelter: "Shelter",
  fire_services: "Fire services",
  trapped: "Trapped",
  surrounded_by_water: "Surrounded by water",
  on_roof: "On a roof",
  water_rising: "Water rising",
  flooding_inside_home: "Water inside homes",
  swept_away: "Swept away",
  drowning: "Drowning",
  structure_collapse: "Structure collapse",
  under_debris: "Under debris",
  injured: "Injuries",
  unconscious: "Unconscious / drowsy",
  active_fire: "Active fire",
  missing_person: "Missing person",
  road_blocked: "Road blocked",
  elderly: "Elderly",
  children: "Children",
  infants: "Infants",
  pregnant_people: "Pregnant",
  people_with_disabilities: "Disability / bedridden",
  mr: "Marathi",
  hi: "Hindi",
  en: "English",
  mixed: "Hinglish / mixed",
  unknown: "Unknown",
  human_verified: "Verified by dispatcher",
  caller_gps: "GPS shared by caller (unverified)",
  simulated_reference: "Reference match (simulated, unverified)",
  caller_stated_unmapped: "Caller-stated, not in reference",
  ambiguous: "Ambiguous / conflicting",
  needs_review: "Needs review",
  reviewed: "Reviewed",
  rereview_needed: "Re-review needed",
  no_review_required: "No review flags",
  likely_duplicate: "Likely duplicate (auto-linked)",
  possible_duplicate: "Possible duplicate (review)",
  new_incident: "New incident",
  duplicate_confirmed: "Duplicate confirmed by reviewer",
  manual_merge: "Merged by reviewer",
  manual_split: "Split by reviewer",
  synthetic_fixture: "Synthetic text fixture",
  mock_fixture_lookup: "MOCK STT (fixture lookup)",
  prisma: "Gnani Prisma STT",
  manual_entry: "Entered by dispatcher",
  reported_safe: "Caller says safe",
  reported_evacuated: "Caller says evacuated",
};

export function label(key: string | null | undefined): string {
  if (!key) return "—";
  return LABELS[key] ?? key.replace(/_/g, " ");
}

export function langLabel(code: string | null | undefined): string {
  return code ? LABELS[code] ?? code : "—";
}

export function timeAgo(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return "—";
  const s = Math.round((now - new Date(iso).getTime()) / 1000);
  if (s < 0) return "just now";
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return `${Math.floor(s / 86400)} d ago`;
}

export function clock(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function pct(v: number | null | undefined, digits = 0): string {
  return v === null || v === undefined ? "n/a" : `${(v * 100).toFixed(digits)}%`;
}

export function num(v: number | null | undefined, digits = 0): string {
  return v === null || v === undefined ? "—" : v.toFixed(digits);
}

export function peopleText(i: Pick<Incident, "people_count" | "people_detail">): string {
  if (i.people_count !== null && i.people_count !== undefined) return `${i.people_count}`;
  if (i.people_detail?.families) return `${i.people_detail.families} families`;
  return "Unknown";
}

export function locationText(i: Incident): string {
  const loc = i.location;
  if (!loc) return "Unknown location";
  if (loc.place_name) return loc.landmark ? `${loc.place_name} · ${loc.landmark}` : loc.place_name;
  if (i.location_status === "caller_gps") return "GPS position shared by the caller";
  if (loc.landmark) return `Near “${loc.landmark}” (village unclear)`;
  if (loc.candidates?.length) return `Location unclear (${loc.candidates.length} possible places)`;
  return "Unknown location";
}

/** Grounded = has coordinates from the simulated reference or a dispatcher; only these are mapped. */
export function isMappable(i: Incident): boolean {
  return i.latitude !== null && i.longitude !== null &&
    (i.location_status === "simulated_reference" || i.location_status === "human_verified" || i.location_status === "caller_gps");
}

export function sortIncidents(items: Incident[]): Incident[] {
  return [...items].sort(
    (a, b) =>
      PRIORITY_RANK[b.priority_label] - PRIORITY_RANK[a.priority_label] ||
      b.priority_score - a.priority_score ||
      b.report_count - a.report_count ||
      a.id.localeCompare(b.id),
  );
}

export function needsReview(i: Incident): boolean {
  return i.review_status === "needs_review" || i.review_status === "rereview_needed";
}
