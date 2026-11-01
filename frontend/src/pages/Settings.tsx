import { RefreshCw } from "lucide-react";
import { useState } from "react";
import { DemoControls } from "../components/DemoControls";
import { Button, ErrorBanner, Spinner } from "../components/ui";
import { api } from "../lib/api";
import { cn } from "../lib/cn";
import { usePoll } from "../lib/usePoll";

function StatusRow({ label, mode, note }: { label: string; mode: string; note?: string | null }) {
  const ok = mode === "real";
  return (
    <div className="flex items-center justify-between py-3 border-b border-line last:border-0">
      <div className="flex items-center gap-3">
        <span className="relative flex h-2 w-2 shrink-0">
          {ok && <span className="absolute inline-flex h-full w-full animate-pulse-ring rounded-full bg-status-good" />}
          <span className={cn("relative inline-flex h-2 w-2 rounded-full", ok ? "bg-status-good" : "bg-status-warning")} />
        </span>
        <span className="text-sm text-ink">{label}</span>
      </div>
      <span className={cn("text-xs font-mono", ok ? "text-status-good" : "text-ink-3")}>
        {ok ? "operational" : note ?? mode}
      </span>
    </div>
  );
}

export function Settings() {
  const health = usePoll(api.health, 8000);
  const stats = usePoll(api.stats, 0);
  const [latency, setLatency] = useState<number | null>(null);
  const [pinging, setPinging] = useState(false);

  const ping = async () => {
    setPinging(true);
    const t0 = Date.now();
    try { await api.health(); setLatency(Date.now() - t0); }
    catch { setLatency(null); }
    finally { setPinging(false); }
  };

  if (health.loading && !health.data) return <Spinner />;
  if (health.error && !health.data) return <ErrorBanner offline message={health.error} />;

  const p = health.data?.providers;

  return (
    <div className="mx-auto max-w-xl space-y-6 py-2">
      <div>
        <h1 className="text-xl font-semibold text-ink">Settings</h1>
        <p className="mt-1 text-sm text-ink-3">Pipeline status and demo data.</p>
      </div>

      {/* Pipeline status */}
      <div className="rounded-2xl border border-line bg-surface-1">
        <div className="flex items-center justify-between px-5 py-4 border-b border-line">
          <div>
            <div className="text-sm font-medium text-ink">Pipeline status</div>
            {latency !== null && (
              <div className="mt-0.5 text-xs text-ink-3">
                Backend <span className={cn("font-mono", latency < 200 ? "text-status-good" : "text-status-warning")}>{latency} ms</span>
              </div>
            )}
          </div>
          <Button size="sm" variant="ghost" busy={pinging} onClick={ping}>
            <RefreshCw className="h-3.5 w-3.5" />
            Ping
          </Button>
        </div>
        <div className="px-5">
          {p ? (
            <>
              <StatusRow label="Gnani Prisma · Speech-to-text" mode={p.speech_to_text.mode} note={p.speech_to_text.note} />
              <StatusRow label="Gnani Evon · Extraction" mode={p.extraction.mode} note={p.extraction.note} />
              <StatusRow label="Gnani Timbre · Text-to-speech" mode={p.text_to_speech.mode} note={p.text_to_speech.note} />
            </>
          ) : (
            <div className="py-4 text-sm text-ink-3">Connecting…</div>
          )}
        </div>
      </div>

      {/* Demo data */}
      <div className="rounded-2xl border border-line bg-surface-1">
        <div className="px-5 py-4 border-b border-line">
          <div className="text-sm font-medium text-ink">Demo data</div>
          <div className="mt-0.5 text-xs text-ink-3">
            {stats.data?.total_reports ?? 0} synthetic reports loaded · fictional locations
          </div>
        </div>
        <div className="px-5 py-4">
          <DemoControls hasData={(stats.data?.total_reports ?? 0) > 0} onChanged={() => void stats.refresh()} />
        </div>
      </div>
    </div>
  );
}
