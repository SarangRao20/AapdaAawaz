import { Database, PlayCircle, RotateCcw, ShieldQuestion, ChevronDown } from "lucide-react";
import { useState, useRef, useEffect } from "react";
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

  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    if (open) document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [open]);

  return (
    <div className="space-y-2">
      <div className="relative" ref={menuRef}>
        <Button
          size="sm"
          variant="secondary"
          onClick={() => setOpen(!open)}
          className="flex items-center gap-1"
        >
          Demo Actions <ChevronDown className="h-3.5 w-3.5" />
        </Button>

        {open && (
          <div className="absolute right-0 z-50 mt-2 w-56 rounded-lg border border-neutral-800 bg-surface-1 shadow-lg">
            <div className="p-2 space-y-1">
              <button
                className="w-full text-left px-3 py-2 rounded-md text-sm hover:bg-surface-2 transition-colors flex items-center gap-2 text-ink"
                onClick={() => {
                  if (hasData && !confirmReset) {
                    setConfirmReset(true);
                    return;
                  }
                  setConfirmReset(false);
                  void run("reset", async () => {
                    await api.reset();
                    return "Data cleared.";
                  });
                  setOpen(false);
                }}
                onBlur={() => setConfirmReset(false)}
                disabled={busy === "reset"}
              >
                <RotateCcw className="h-3.5 w-3.5" />
                <span>{confirmReset ? "Confirm reset" : "Reset all data"}</span>
              </button>

              <button
                className="w-full text-left px-3 py-2 rounded-md text-sm hover:bg-surface-2 transition-colors flex items-center gap-2 text-ink"
                onClick={() => {
                  void run("hero", async () => {
                    const r = await api.inject("SYN-001", true);
                    return `Call ${r.id} queued — watch its stages in the live feed.`;
                  });
                  setOpen(false);
                }}
                disabled={busy === "hero"}
              >
                <PlayCircle className="h-3.5 w-3.5" />
                <span>1 · Incoming call</span>
              </button>

              <button
                className="w-full text-left px-3 py-2 rounded-md text-sm hover:bg-surface-2 transition-colors flex items-center gap-2 text-ink"
                onClick={() => {
                  void run("seed", async () => {
                    const r = await api.seed("remaining");
                    return `Loaded ${r.created} reports → ${r.stats.unique_incidents} candidate incidents.`;
                  });
                  setOpen(false);
                }}
                disabled={busy === "seed"}
              >
                <Database className="h-3.5 w-3.5" />
                <span>2 · Load sample reports</span>
              </button>

              <button
                className="w-full text-left px-3 py-2 rounded-md text-sm hover:bg-surface-2 transition-colors flex items-center gap-2 text-ink"
                onClick={async () => {
                  const r = await api.report("R-SYN-025").catch(() => null);
                  navigate(r?.incident_id ? `/incidents/${r.incident_id}` : "/review");
                  setOpen(false);
                }}
              >
                <ShieldQuestion className="h-3.5 w-3.5" />
                <span>3 · Ambiguous-location case</span>
              </button>
            </div>
          </div>
        )}
      </div>
      {note && <p className="text-xs text-ink-2">{note}</p>}
      {error && <ErrorBanner message={error} />}
    </div>
  );
}
