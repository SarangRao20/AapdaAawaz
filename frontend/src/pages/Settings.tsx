import { Activity, Bot, Cpu, RefreshCw, Volume2 } from "lucide-react";
import { useEffect, useState } from "react";
import { DemoControls } from "../components/DemoControls";
import { ModeBadge } from "../components/badges";
import { Badge, Button, Card, CardHeader, ErrorBanner, FieldLabel, Input, Select, Spinner } from "../components/ui";
import { api } from "../lib/api";
import { cn } from "../lib/cn";
import type { RuntimeConfig } from "../lib/types";
import { usePoll } from "../lib/usePoll";

function HealthDot({ ok, pulse }: { ok: boolean | null; pulse?: boolean }) {
  return (
    <span className="relative flex h-2.5 w-2.5 shrink-0">
      {ok && pulse && <span className="absolute inline-flex h-full w-full animate-pulse-ring rounded-full bg-status-good" />}
      <span className={cn("relative inline-flex h-2.5 w-2.5 rounded-full", ok === true ? "bg-status-good" : ok === false ? "bg-status-critical" : "bg-status-warning")} />
    </span>
  );
}

function HealthDashboard() {
  const health = usePoll(api.health, 8000);
  const [latency, setLatency] = useState<number | null>(null);
  const [pinging, setPinging] = useState(false);

  const ping = async () => {
    setPinging(true);
    const t0 = Date.now();
    try {
      await api.health();
      setLatency(Date.now() - t0);
    } catch { setLatency(null); }
    finally { setPinging(false); }
  };

  const p = health.data?.providers;
  const rows = p ? [
    { label: "Speech-to-text (Gnani Prisma)", ok: p.speech_to_text.mode === "real", mode: p.speech_to_text.mode, note: p.speech_to_text.note },
    { label: "Extraction (LLM)", ok: p.extraction.mode !== "mock", mode: p.extraction.mode, note: p.extraction.note },
    { label: "Text-to-speech (Gnani Timbre)", ok: p.text_to_speech.mode === "real", mode: p.text_to_speech.mode, note: p.text_to_speech.note },
  ] : [];

  return (
    <Card>
      <CardHeader
        title={<span className="flex items-center gap-1.5"><Activity className="h-4 w-4 text-accent-glow" /> API Health</span>}
        subtitle="Live provider status — polled every 8 s"
        right={
          <Button size="sm" variant="ghost" busy={pinging} onClick={ping}>
            <RefreshCw className="h-3.5 w-3.5" /> Ping
          </Button>
        }
      />
      <div className="space-y-0 divide-y divide-line">
        {health.loading && !health.data && <div className="px-4 py-3 text-xs text-ink-3">Checking…</div>}
        {rows.map((r) => (
          <div key={r.label} className="flex items-center justify-between gap-3 px-4 py-2.5">
            <div className="flex items-center gap-2.5 min-w-0">
              <HealthDot ok={r.ok} pulse={r.ok} />
              <span className="text-sm text-ink truncate">{r.label}</span>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <span className={cn("rounded-md px-2 py-0.5 font-mono text-2xs", r.ok ? "bg-status-good/10 text-status-good" : "bg-surface-3 text-ink-3")}>{r.mode}</span>
              {r.note && <span className="text-2xs text-ink-3 max-w-xs truncate">{r.note}</span>}
            </div>
          </div>
        ))}
        {latency !== null && (
          <div className="flex items-center gap-2 px-4 py-2.5 text-xs text-ink-3">
            <span>Backend latency:</span>
            <span className={cn("font-mono", latency < 200 ? "text-status-good" : latency < 600 ? "text-status-warning" : "text-status-critical")}>{latency} ms</span>
          </div>
        )}
        {health.error && (
          <div className="flex items-center gap-2 px-4 py-2.5 text-xs text-status-critical">
            <HealthDot ok={false} /> Backend unreachable
          </div>
        )}
      </div>
    </Card>
  );
}

function NumberField({ label, value, step = 0.05, onChange }: { label: string; value: number; step?: number; onChange: (v: number) => void }) {
  return (
    <div>
      <FieldLabel>{label}</FieldLabel>
      <Input type="number" step={step} value={value} onChange={(e) => onChange(Number(e.target.value))} />
    </div>
  );
}

export function Settings() {
  const s = usePoll(api.settings, 0);
  const stats = usePoll(api.stats, 0);
  const [cfg, setCfg] = useState<RuntimeConfig | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (s.data) setCfg(s.data.config);
  }, [s.data]);

  if (s.loading && !s.data) return <Spinner />;
  if (s.error && !s.data) return <ErrorBanner offline message={s.error} />;
  const p = s.data!.providers;

  async function save(section: keyof RuntimeConfig) {
    if (!cfg) return;
    setBusy(true);
    setError(null);
    setMsg(null);
    try {
      const res = await api.saveSettings({ [section]: cfg[section] } as Partial<RuntimeConfig>);
      setCfg(res.config);
      setMsg(res.note);
      void s.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }
  const set = <K extends keyof RuntimeConfig>(section: K, patch: Partial<RuntimeConfig[K]>) => cfg && setCfg({ ...cfg, [section]: { ...cfg[section], ...patch } });

  const providers = [
    { icon: Bot, name: "Speech-to-text", active: p.speech_to_text.active, mode: p.speech_to_text.mode, note: p.speech_to_text.note, avail: p.speech_to_text.prisma_available ? "Gnani Prisma available" : "Gnani Prisma unavailable (no API key)" },
    { icon: Cpu, name: "Structured extraction", active: p.extraction.active, mode: p.extraction.mode, note: p.extraction.note, avail: "Gnani Evon: not publicly documented" },
    { icon: Volume2, name: "Text-to-speech", active: p.text_to_speech.active, mode: p.text_to_speech.mode, note: p.text_to_speech.note, avail: p.text_to_speech.timbre_available ? "Gnani Timbre available" : "Gnani Timbre unavailable (no API key)" },
  ];

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold">System Settings</h1>
        <p className="text-xs text-ink-3">Provider availability, provider mode, confidence thresholds and demo data. API keys are read from environment variables and never shown here.</p>
      </div>
      {error && <ErrorBanner message={error} />}
      {msg && <p className="text-xs text-[#9fe0a8]">{msg}</p>}

      <HealthDashboard />

      <Card>
        <CardHeader title="AI providers" subtitle={`Gnani API key configured: ${p.gnani_api_key_configured ? "yes" : "no"} · ${p.gnani_base_url}`} />
        <div className="grid gap-3 p-4 md:grid-cols-3">
          {providers.map((x) => (
            <div key={x.name} className="space-y-1.5 rounded-md border border-line bg-surface-2 p-3">
              <div className="flex items-center gap-2 text-sm font-medium">
                <x.icon className="h-4 w-4 text-ink-3" /> {x.name}
              </div>
              <div className="flex flex-wrap gap-1.5">
                <ModeBadge mode={x.mode} provider={x.active} />
                <Badge>{x.active ?? "none"}</Badge>
              </div>
              <div className="text-2xs text-ink-2">{x.avail}</div>
              {x.note && <div className="text-2xs text-ink-3">{x.note}</div>}
            </div>
          ))}
        </div>
        {cfg && (
          <div className="flex flex-wrap items-end gap-3 border-t border-line px-4 py-3">
            <div className="w-56">
              <FieldLabel>Speech-to-text mode</FieldLabel>
              <Select value={cfg.providers.stt} onChange={(e) => set("providers", { stt: e.target.value })}>
                <option value="auto">auto (Prisma if key, else mock)</option>
                <option value="mock">mock (fixture lookup only)</option>
                <option value="prisma">prisma (fail if unavailable)</option>
              </Select>
            </div>
            <div className="w-56">
              <FieldLabel>Text-to-speech mode</FieldLabel>
              <Select value={cfg.providers.tts} onChange={(e) => set("providers", { tts: e.target.value })}>
                <option value="auto">auto (Timbre if key)</option>
                <option value="none">none (text acknowledgements only)</option>
              </Select>
            </div>
            <Button variant="primary" busy={busy} onClick={() => save("providers")}>
              Save provider mode
            </Button>
          </div>
        )}
      </Card>

      {cfg && (
        <div className="grid gap-4 lg:grid-cols-3">
          <Card>
            <CardHeader title="Confidence gate" subtitle="Field-level thresholds (rule evidence levels 0–1)" />
            <div className="space-y-3 p-4">
              <NumberField label="Min location evidence" value={cfg.gate.min_location_confidence} onChange={(v) => set("gate", { min_location_confidence: v })} />
              <NumberField label="Min people-count evidence" value={cfg.gate.min_people_confidence} onChange={(v) => set("gate", { min_people_confidence: v })} />
              <div>
                <FieldLabel>Flag unknown people count at priority ≥</FieldLabel>
                <Select value={cfg.gate.unknown_people_review_at} onChange={(e) => set("gate", { unknown_people_review_at: e.target.value })}>
                  {["critical", "high", "medium", "low", "never"].map((l) => (
                    <option key={l}>{l}</option>
                  ))}
                </Select>
              </div>
              <label className="flex items-center gap-2 text-xs text-ink-2">
                <input type="checkbox" checked={cfg.gate.flag_low_quality_transcript} onChange={(e) => set("gate", { flag_low_quality_transcript: e.target.checked })} /> Flag low-quality transcripts
              </label>
              <label className="flex items-center gap-2 text-xs text-ink-2">
                <input type="checkbox" checked={cfg.gate.flag_unclear_urgency} onChange={(e) => set("gate", { flag_unclear_urgency: e.target.checked })} /> Flag unclear situations
              </label>
              <Button variant="primary" busy={busy} onClick={() => save("gate")}>
                Save gate
              </Button>
            </div>
          </Card>
          <Card>
            <CardHeader title="Deduplication" subtitle="Score thresholds for linking reports" />
            <div className="space-y-3 p-4">
              <NumberField label="Likely duplicate (auto-link) ≥" value={cfg.dedup.likely_threshold} onChange={(v) => set("dedup", { likely_threshold: v })} />
              <NumberField label="Possible duplicate (review) ≥" value={cfg.dedup.possible_threshold} onChange={(v) => set("dedup", { possible_threshold: v })} />
              <NumberField label="Time window (minutes)" step={10} value={cfg.dedup.time_window_minutes} onChange={(v) => set("dedup", { time_window_minutes: v })} />
              <details className="text-2xs text-ink-3">
                <summary className="cursor-pointer">Feature weights (read-only here; see docs/ARCHITECTURE.md)</summary>
                <pre className="mt-1">{JSON.stringify(cfg.dedup.weights, null, 1)}</pre>
              </details>
              <Button variant="primary" busy={busy} onClick={() => save("dedup")}>
                Save deduplication
              </Button>
            </div>
          </Card>
          <Card>
            <CardHeader title="Priority labels" subtitle="Score thresholds; weights documented in docs/ARCHITECTURE.md" />
            <div className="space-y-3 p-4">
              {(["critical", "high", "medium"] as const).map((k) => (
                <NumberField key={k} label={`${k} ≥`} step={1} value={cfg.priority.thresholds[k]} onChange={(v) => set("priority", { thresholds: { ...cfg.priority.thresholds, [k]: v } })} />
              ))}
              <div>
                <FieldLabel>Cap when callers report everyone safe</FieldLabel>
                <Select value={cfg.priority.safe_status_cap} onChange={(e) => set("priority", { safe_status_cap: e.target.value })}>
                  {["critical", "high", "medium", "low"].map((l) => (
                    <option key={l}>{l}</option>
                  ))}
                </Select>
              </div>
              <Button variant="primary" busy={busy} onClick={() => save("priority")}>
                Save priority
              </Button>
              <p className="text-2xs text-ink-3">Prototype weights — not an operationally or clinically validated triage algorithm.</p>
            </div>
          </Card>
        </div>
      )}

      <Card>
        <CardHeader title="Demo data" subtitle={`${stats.data?.total_reports ?? 0} reports in the local database · all demo records are synthetic`} />
        <div className="p-4">
          <DemoControls hasData={(stats.data?.total_reports ?? 0) > 0} onChanged={() => void stats.refresh()} />
        </div>
      </Card>
    </div>
  );
}
