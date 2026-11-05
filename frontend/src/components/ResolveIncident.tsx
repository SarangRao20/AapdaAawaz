import { CheckCircle2, RotateCcw } from "lucide-react";
import { useState } from "react";
import { RESOLVE_REASONS, api, type ResolveReason } from "../lib/api";
import { getReviewer } from "../lib/reviewer";
import type { Incident } from "../lib/types";
import { Button, Select } from "./ui";

/** Close an incident once responders have dealt with it, or reopen a closed one. Nothing is deleted: it is audited. */
export function ResolveIncident({ incident, onChanged }: { incident: Pick<Incident, "id" | "status" | "human_overrides">; onChanged: () => void }) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState<ResolveReason>("rescued");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      setOpen(false);
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  if (incident.status === "closed") {
    const resolution = incident.human_overrides?.resolution as { reason?: string; by?: string } | undefined;
    return (
      <div className="space-y-1">
        <div className="text-xs text-ink-3">
          Closed{resolution?.reason ? ` · ${RESOLVE_REASONS.find((r) => r.value === resolution.reason)?.label ?? resolution.reason}` : ""}
          {resolution?.by ? ` · by ${resolution.by}` : ""}
        </div>
        <Button size="sm" busy={busy} onClick={() => void run(() => api.reopenIncident(incident.id, getReviewer()))}>
          <RotateCcw className="h-3.5 w-3.5" /> Reopen
        </Button>
        {error && <p className="text-xs text-[#f3b0b0]">{error}</p>}
      </div>
    );
  }
  if (incident.status !== "active") return null;

  if (!open)
    return (
      <Button size="sm" variant="success" onClick={() => setOpen(true)}>
        <CheckCircle2 className="h-3.5 w-3.5" /> Mark resolved
      </Button>
    );
  return (
    <div className="space-y-2 rounded-lg border border-white/10 bg-surface-2 p-2.5">
      <p className="text-xs text-ink-2">Remove {incident.id} from the live board? It stays in the record and can be reopened.</p>
      <Select value={reason} onChange={(e) => setReason(e.target.value as ResolveReason)} aria-label="Reason">
        {RESOLVE_REASONS.map((r) => (
          <option key={r.value} value={r.value}>{r.label}</option>
        ))}
      </Select>
      <div className="flex gap-2">
        <Button size="sm" variant="success" busy={busy} onClick={() => void run(() => api.resolveIncident(incident.id, reason, getReviewer()))}>
          Confirm
        </Button>
        <Button size="sm" variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
      </div>
      {error && <p className="text-xs text-[#f3b0b0]">{error}</p>}
    </div>
  );
}
