import { Database, PlayCircle, RotateCcw, ShieldQuestion } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { Button, ErrorBanner } from "./ui";

/**
 * Deterministic 60-second demo sequence. Every button calls the real API; nothing here
 * fakes progress — stage badges update from the backend's own job records.
 */
export function DemoControls({ onChanged, hasData }: { onChanged: () => void; hasData: boolean }) {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [confirmReset, setConfirmReset] = useState(false);
  const navigate = useNavigate();

  async function run(key: string, fn: () => Promise<string | void>) {
    setBusy(key);
    setError(null);
    try {
      const msg = await fn();
      setNote(msg || null);
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-2xs font-semibold uppercase tracking-wider text-ink-3">Demo</span>
        <Button
          size="sm"
          variant="danger"
          busy={busy === "reset"}
          title="Deletes all reports, incidents and review history in this local demo database"
          onClick={() => {
            if (hasData && !confirmReset) {
              setConfirmReset(true);
              return;
            }
            setConfirmReset(false);
            void run("reset", async () => {
              await api.reset();
              return "Demo data cleared.";
            });
          }}
          onBlur={() => setConfirmReset(false)}
        >
          <RotateCcw className="h-3.5 w-3.5" /> {confirmReset ? "Click again to delete all demo data" : "Reset"}
        </Button>
        <Button
          size="sm"
          variant="primary"
          busy={busy === "hero"}
          onClick={() =>
            run("hero", async () => {
              const r = await api.inject("SYN-001", true);
              return `Injected synthetic call ${r.id} (audio → mock STT). Watch its stages in the live feed.`;
            })
          }
        >
          <PlayCircle className="h-3.5 w-3.5" /> 1 · Incoming call
        </Button>
        <Button
          size="sm"
          busy={busy === "seed"}
          onClick={() =>
            run("seed", async () => {
              const r = await api.seed("remaining");
              return `Loaded ${r.created} synthetic reports → ${r.stats.unique_incidents} candidate incidents.`;
            })
          }
        >
          <Database className="h-3.5 w-3.5" /> 2 · Load all synthetic reports
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={async () => {
            const r = await api.report("R-SYN-025").catch(() => null);
            navigate(r?.incident_id ? `/incidents/${r.incident_id}` : "/review");
          }}
        >
          <ShieldQuestion className="h-3.5 w-3.5" /> 3 · Ambiguous-location case
        </Button>
      </div>
      {note && <p className="text-xs text-ink-2">{note}</p>}
      {error && <ErrorBanner message={error} />}
    </div>
  );
}
