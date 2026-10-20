import { useCallback, useEffect, useRef, useState } from "react";
import { PRIORITY_RANK } from "./format";
import type { Incident } from "./types";

export interface Alert {
  key: string;
  incidentId: string;
  kind: "new" | "escalated";
  incident: Incident;
  at: number;
}

const FLASH_MS = 9000;

/**
 * Diffs each poll against the previous one and raises an alert when a high/critical incident appears
 * or an existing incident is upgraded. The first successful load only seeds state: nothing is announced
 * for data that was already there.
 */
export function useIncidentAlerts(incidents: Incident[] | undefined) {
  const seen = useRef<Map<string, number> | null>(null);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [fresh, setFresh] = useState<Record<string, number>>({});

  useEffect(() => {
    if (!incidents) return;
    const next = new Map(incidents.map((i) => [i.id, PRIORITY_RANK[i.priority_label]]));
    if (seen.current === null) {
      seen.current = next;
      return;
    }
    const raised: Alert[] = [];
    const flashed: Record<string, number> = {};
    const now = Date.now();
    for (const i of incidents) {
      const before = seen.current.get(i.id);
      const rank = PRIORITY_RANK[i.priority_label];
      const isNew = before === undefined;
      const up = !isNew && rank > before;
      if (isNew || up) flashed[i.id] = now;
      if ((isNew || up) && rank >= PRIORITY_RANK.high)
        raised.push({ key: `${i.id}-${i.priority_label}-${now}`, incidentId: i.id, kind: isNew ? "new" : "escalated", incident: i, at: now });
    }
    seen.current = next;
    if (raised.length) setAlerts((a) => [...raised, ...a].slice(0, 4));
    if (Object.keys(flashed).length) setFresh((f) => ({ ...f, ...flashed }));
  }, [incidents]);

  useEffect(() => {
    if (!alerts.length) return;
    const t = window.setTimeout(() => setAlerts((a) => a.slice(0, -1)), 9000);
    return () => window.clearTimeout(t);
  }, [alerts]);

  useEffect(() => {
    if (!Object.keys(fresh).length) return;
    const t = window.setTimeout(() => {
      const cut = Date.now() - FLASH_MS;
      setFresh((f) => Object.fromEntries(Object.entries(f).filter(([, at]) => at > cut)));
    }, FLASH_MS);
    return () => window.clearTimeout(t);
  }, [fresh]);

  const dismiss = useCallback((key: string) => setAlerts((a) => a.filter((x) => x.key !== key)), []);
  return { alerts, dismiss, fresh };
}
