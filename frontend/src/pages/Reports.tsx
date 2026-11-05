import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { LiveFeed } from "../components/LiveFeed";
import { ReportDetailView } from "../components/ReportDetailView";
import { UnifiedIntakeForm } from "../components/UnifiedIntakeForm";
import { Button, Card, CardHeader, Empty, ErrorBanner, Input, Select, Spinner } from "../components/ui";
import { api } from "../lib/api";
import { usePoll } from "../lib/usePoll";

export function Reports() {
  const [params, setParams] = useSearchParams();
  const selected = params.get("id");
  const [status, setStatus] = useState("");
  const [source, setSource] = useState("");
  const [q, setQ] = useState("");
  const list = usePoll(
    () => api.reports({ limit: 100, status: status || undefined, source: source || undefined, q: q || undefined }),
    2500,
    [status, source, q],
  );
  const detail = usePoll(() => (selected ? api.report(selected) : Promise.resolve(null)), selected ? 2000 : 0, [selected]);

  const [showForm, setShowForm] = useState(false);
  const [lang, setLang] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const select = (id: string) => setParams({ id });

  async function submit(key: string, fn: () => Promise<{ id: string }>) {
    setBusy(key);
    setError(null);
    try {
      const r = await fn();
      select(r.id);
      void list.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      throw e;
    } finally {
      setBusy(null);
    }
  }

  const handleUpload = (file: File, name: string, fileLang: string | null) => {
    void submit("upload", async () => {
      const r = await api.uploadReport(file, name, fileLang, "upload");
      return r;
    }).catch(() => undefined);
  };

  const handleRecorded = async (wav: Blob) => {
    return submit("record", () => api.uploadReport(wav, "recording.wav", lang || null, "recording")).catch(() => undefined);
  };

  const handleTypeSubmit = (text: string) => {
    void submit("text", async () => {
      const r = await api.createReport({ transcript: text, language_hint: lang || null, process: true });
      return r;
    }).catch(() => undefined);
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold">Incoming Reports</h1>
          <p className="text-xs text-ink-3">
            Everything that came in. Live calls, Telegram chats and caller-app recordings appear here on their own, with their audio;
            you do not need to upload anything. Processing runs in a background worker and this page polls for progress.
          </p>
        </div>
        <Button size="sm" variant={showForm ? "ghost" : "secondary"} onClick={() => setShowForm((v) => !v)}>
          {showForm ? "Hide manual entry" : "Add a report by hand"}
        </Button>
      </div>
      <div className="grid gap-4 xl:grid-cols-[440px_1fr]">
        <div className="space-y-4">
          {showForm && (
            <UnifiedIntakeForm
              lang={lang}
              onLangChange={setLang}
              onUpload={handleUpload}
              onRecorded={handleRecorded}
              onTypeSubmit={handleTypeSubmit}
              error={error}
              busy={busy}
            />
          )}
          <Card>
            <CardHeader
              title="Reports"
              right={<span className="font-mono text-xs text-ink-3">{list.data?.total ?? 0}</span>}
            />
            <div className="flex gap-2 border-b border-line px-4 py-2">
              <Input className="h-8 text-xs" placeholder="Search transcript or ID" value={q} onChange={(e) => setQ(e.target.value)} />
              <Select className="h-8 w-40 text-xs" value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status filter">
                <option value="">All statuses</option>
                <option value="queued,transcribing,extracting">In progress</option>
                <option value="processed">Processed</option>
                <option value="needs_transcript">Needs transcript</option>
                <option value="failed">Failed</option>
              </Select>
              <Select className="h-8 w-32 text-xs" value={source} onChange={(e) => setSource(e.target.value)} aria-label="Source filter">
                <option value="">All sources</option>
                <option value="live_call">Live call</option>
                <option value="telegram">Telegram</option>
                <option value="recording">Recording</option>
                <option value="upload">Upload</option>
                <option value="manual_text">Typed</option>
                <option value="synthetic_fixture">Synthetic</option>
              </Select>
            </div>
            {list.error && <div className="p-3"><ErrorBanner offline message={list.error} /></div>}
            <div className="max-h-[720px] overflow-y-auto">
              {list.loading && !list.data ? (
                <Spinner />
              ) : (
                // Each report ID links to /reports?id=…, which selects it here.
                <LiveFeed items={list.data?.items ?? []} compact />
              )}
            </div>
          </Card>
        </div>
        <Card className="self-start p-4">
          {!selected ? (
            <Empty title="Select a report">Choose a report from the list to see its audio, transcript provenance, processing stages and extraction.</Empty>
          ) : detail.loading && !detail.data ? (
            <Spinner />
          ) : detail.error ? (
            <ErrorBanner message={detail.error} />
          ) : detail.data ? (
            <ReportDetailView key={detail.data.id} report={detail.data} onChanged={() => { void detail.refresh(); void list.refresh(); }} />
          ) : null}
        </Card>
      </div>
    </div>
  );
}
