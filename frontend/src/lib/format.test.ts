import { describe, expect, it } from "vitest";
import { isMappable, locationText, peopleText, pct, sortIncidents, timeAgo } from "./format";
import type { Incident } from "./types";

const base = {
  id: "INC-0001",
  priority_label: "high",
  priority_score: 30,
  report_count: 1,
  latitude: 18.6,
  longitude: 73.5,
  location_status: "simulated_reference",
  people_count: null,
  people_detail: null,
} as unknown as Incident;

describe("sortIncidents", () => {
  it("orders by label, then score, then report count", () => {
    const items = [
      { ...base, id: "A", priority_label: "medium", priority_score: 90 },
      { ...base, id: "B", priority_label: "critical", priority_score: 60 },
      { ...base, id: "C", priority_label: "critical", priority_score: 99 },
      { ...base, id: "D", priority_label: "high", priority_score: 30, report_count: 3 },
      { ...base, id: "E", priority_label: "high", priority_score: 30, report_count: 1 },
    ] as Incident[];
    expect(sortIncidents(items).map((i) => i.id)).toEqual(["C", "B", "D", "E", "A"]);
  });
});

describe("isMappable", () => {
  it("never maps ungrounded incidents even if coordinates are present", () => {
    expect(isMappable(base)).toBe(true);
    expect(isMappable({ ...base, location_status: "ambiguous" })).toBe(false);
    expect(isMappable({ ...base, location_status: "caller_gps" })).toBe(true);
    expect(locationText({ ...base, location_status: "caller_gps", location: { place_name: null } as never })).toBe("GPS position shared by the caller");
    expect(isMappable({ ...base, latitude: null })).toBe(false);
  });
});

describe("peopleText", () => {
  it("keeps unknown as unknown and never shows zero", () => {
    expect(peopleText(base)).toBe("Unknown");
    expect(peopleText({ ...base, people_detail: { per_report: [], families: 50, basis: "" } })).toBe("50 families");
    expect(peopleText({ ...base, people_count: 25 })).toBe("25");
  });
});

describe("formatters", () => {
  it("formats percentages and relative time", () => {
    expect(pct(null)).toBe("n/a");
    expect(pct(0.875, 1)).toBe("87.5%");
    const now = Date.parse("2026-01-01T00:10:00Z");
    expect(timeAgo("2026-01-01T00:09:30Z", now)).toBe("30s ago");
    expect(timeAgo("2026-01-01T00:00:00Z", now)).toBe("10 min ago");
  });
});
