import { FileUp, Mic, Type as TypeIcon } from "lucide-react";
import { useRef, useState } from "react";
import { AudioRecorder } from "./AudioRecorder";
import { Button, Card, CardHeader, ErrorBanner, FieldLabel, Select, Textarea } from "./ui";

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

type IntakeTab = "upload" | "record" | "type";

interface UnifiedIntakeFormProps {
  lang: string;
  onLangChange: (v: string) => void;
  onUpload: (file: File, name: string, lang: string | null) => void;
  onRecorded: (wav: Blob) => Promise<void>;
  onTypeSubmit: (text: string) => void;
  error: string | null;
  busy: string | null;
}

export function UnifiedIntakeForm({
  lang,
  onLangChange,
  onUpload,
  onRecorded,
  onTypeSubmit,
  error,
  busy,
}: UnifiedIntakeFormProps) {
  const [tab, setTab] = useState<IntakeTab>("upload");
  const [file, setFile] = useState<File | null>(null);
  const [text, setText] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);

  const handleUpload = () => {
    if (file) {
      onUpload(file, file.name, lang || null);
      setFile(null);
      if (fileInput.current) fileInput.current.value = "";
    }
  };

  const handleTypeSubmit = () => {
    if (text.trim()) {
      onTypeSubmit(text);
      setText("");
    }
  };

  return (
    <Card>
      <CardHeader
        title="New report"
        subtitle="Use synthetic or test audio only — never real distress calls."
      />
      <div className="space-y-4 p-4">
        {/* Language selector - always visible */}
        <div>
          <FieldLabel htmlFor="lang">Language hint (passed to speech-to-text)</FieldLabel>
          <LanguageSelect id="lang" value={lang} onChange={onLangChange} />
        </div>

        {/* Tab buttons */}
        <div className="flex gap-2 border-b border-white/5 -mx-4 px-4">
          {(
            [
              ["upload", "📁 Upload file", FileUp],
              ["record", "🎙️ Record voice", Mic],
              ["type", "📝 Type text", TypeIcon],
            ] as const
          ).map(([key, label, Icon]) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={`flex items-center gap-2 px-3 py-2 text-sm font-medium transition-colors border-b-2 -mb-px whitespace-nowrap ${
                tab === key
                  ? "border-accent text-ink"
                  : "border-transparent text-ink-3 hover:text-ink"
              }`}
            >
              <Icon className="h-4 w-4" aria-hidden />
              {label}
            </button>
          ))}
        </div>

        {/* Tab content */}
        <div className="space-y-3">
          {tab === "upload" && (
            <>
              <FieldLabel htmlFor="file">Upload audio (WAV, MP3, M4A, AAC, OGG, FLAC · max 30 s for Prisma)</FieldLabel>
              <input
                id="file"
                ref={fileInput}
                type="file"
                accept={ACCEPT}
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                className="block w-full text-xs text-ink-2 file:mr-3 file:rounded-md file:border file:border-line file:bg-surface-2 file:px-3 file:py-1.5 file:text-ink"
              />
              <Button
                variant="primary"
                disabled={!file}
                busy={busy === "upload"}
                onClick={handleUpload}
                className="w-full"
              >
                <FileUp className="h-4 w-4" /> Upload & process
              </Button>
            </>
          )}

          {tab === "record" && (
            <>
              <FieldLabel>Record from microphone</FieldLabel>
              <AudioRecorder onRecorded={onRecorded} />
            </>
          )}

          {tab === "type" && (
            <>
              <FieldLabel htmlFor="manual">Type or paste a transcript</FieldLabel>
              <Textarea
                id="manual"
                rows={4}
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="e.g. Kothale gaon, mandir ke paas…"
              />
              <Button
                disabled={!text.trim()}
                busy={busy === "text"}
                onClick={handleTypeSubmit}
                className="w-full"
              >
                <TypeIcon className="h-4 w-4" /> Submit transcript
              </Button>
            </>
          )}
        </div>

        {error && <ErrorBanner message={error} />}
      </div>
    </Card>
  );
}
