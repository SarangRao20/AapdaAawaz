import { FileUp, Type } from "lucide-react";
import { useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { AudioRecorder } from "../components/AudioRecorder";
import { LiveFeed } from "../components/LiveFeed";
import { ReportDetailView } from "../components/ReportDetailView";
import { Button, Card, CardHeader, Empty, ErrorBanner, FieldLabel, Input, Select, Spinner, Textarea } from "../components/ui";
import { api } from "../lib/api";
import { usePoll } from "../lib/usePoll";

const ACCEPT = ".wav,.mp3,.m4a,.aac,.ogg,.flac,audio/*";

function LanguageSelect({ value, onChange, id }: { value: string; onChange: (v: string) => void; id?: string }) {
  return (
    <Select id={id} value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">Unknown / detect</option>
      <option value="mr">Marathi (mr-IN)</option>
      <option value="hi">Hindi (hi-IN)</option>
      <option value="mixed">Hinglish (sent to Prisma as hi-IN)</option>
      <option value="en">English (en-IN)</option>
    </Select>
  );
}

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

  const [lang, setLang] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const [text, setText] = useState("");
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

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold">Incoming Reports</h1>
        <p className="text-xs text-ink-3">Upload or record a voice note, or type a transcript. Processing runs in a background worker; this page polls for progress.</p>
      </div>
      <div className="grid gap-4 xl:grid-cols-[440px_1fr]">
        <div className="space-y-4">
          <Card>
            <CardHeader title="New report" subtitle="Use synthetic or test audio only — never real distress calls." />
            <div className="space-y-4 p-4">
              <div>
                <FieldLabel htmlFor="lang">Language hint (passed to speech-to-text)</FieldLabel>
                <LanguageSelect id="lang" value={lang} onChange={setLang} />
              </div>
              <div className="space-y-2">
                <FieldLabel htmlFor="file">Upload audio (WAV, MP3, M4A, AAC, OGG, FLAC · max 30 s for Prisma)</FieldLabel>
                <input id="file" ref={fileInput} type="file" accept={ACCEPT} onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="block w-full text-xs text-ink-2 file:mr-3 file:rounded-md file:border file:border-line file:bg-surface-2 file:px-3 file:py-1.5 file:text-ink" />
                <Button
                  variant="primary"
                  disabled={!file}
                  busy={busy === "upload"}
                  onClick={() =>
                    submit("upload", async () => {
                      const r = await api.uploadReport(file!, file!.name, lang || null, "upload");
                      setFile(null);
                      if (fileInput.current) fileInput.current.value = "";
                      return r;
                    }).catch(() => undefined)
                  }
                >
                  <FileUp className="h-4 w-4" /> Upload & process
                </Button>
              </div>
              <div className="space-y-2 border-t border-line pt-4">
                <FieldLabel>Record from microphone</FieldLabel>
                <AudioRecorder onRecorded={(wav) => submit("record", () => api.uploadReport(wav, "recording.wav", lang || null, "recording")).then(() => undefined)} />
              </div>
              <div className="space-y-2 border-t border-line pt-4">
                <FieldLabel htmlFor="manual">Or type / paste a transcript</FieldLabel>
                <Textarea id="manual" rows={3} value={text} onChange={(e) => setText(e.target.value)} placeholder="e.g. Kothale gaon, mandir ke paas…" />
                <Button
                  disabled={!text.trim()}
                  busy={busy === "text"}
                  onClick={() =>
                    submit("text", async () => {
                      const r = await api.createReport({ transcript: text, language_hint: lang || null, process: true });
                      setText("");
                      return r;
                    }).catch(() => undefined)
                  }
                >
                  <Type className="h-4 w-4" /> Submit transcript
                </Button>
              </div>
              {error && <ErrorBanner message={error} />}
            </div>
          </Card>
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
