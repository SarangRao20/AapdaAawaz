import { Download } from "lucide-react";
import { useAudioUrl } from "../lib/useAudioUrl";

/** A plain audio player for a recording on the server, with a download link. */
export function AudioClip({ url, filename, className, download = true }: { url: string; filename?: string; className?: string; download?: boolean }) {
  const audio = useAudioUrl(url);
  if (audio.error) return <p className="text-xs text-status-warning">{audio.error}</p>;
  if (!audio.src) return <p className="text-xs text-ink-3">Loading audio…</p>;
  return (
    <div className="flex items-center gap-2">
      <audio controls src={audio.src} className={className ?? "h-8 w-full"} />
      {download && (
        <a href={audio.src} download={filename ?? "recording"} className="inline-flex shrink-0 items-center gap-1 rounded-md border border-white/10 px-2 py-1 text-2xs text-ink-2 hover:bg-white/5 hover:text-ink">
          <Download className="h-3 w-3" aria-hidden /> Download
        </a>
      )}
    </div>
  );
}
