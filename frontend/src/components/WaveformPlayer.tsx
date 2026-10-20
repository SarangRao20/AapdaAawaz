import { Pause, Play } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

interface WaveformPlayerProps {
  src: string;
}

export function WaveformPlayer({ src }: WaveformPlayerProps) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animRef = useRef<number>(0);
  const [playing, setPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [loading, setLoading] = useState(true);
  const [waveform, setWaveform] = useState<Float32Array | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Decode audio data and build waveform once
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setWaveform(null);

    fetch(src)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.arrayBuffer();
      })
      .then((buf) => {
        const ctx = new AudioContext();
        return ctx.decodeAudioData(buf);
      })
      .then((audioBuffer) => {
        if (cancelled) return;
        setWaveform(audioBuffer.getChannelData(0));
        setLoading(false);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : "Failed to load audio");
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [src]);

  // Draw waveform
  const draw = useCallback(
    (progress: number) => {
      const canvas = canvasRef.current;
      if (!canvas || !waveform) return;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      const { width, height } = canvas;
      ctx.clearRect(0, 0, width, height);
      const step = Math.ceil(waveform.length / width);
      const progressX = Math.floor(progress * width);
      for (let i = 0; i < width; i++) {
        let max = 0;
        for (let j = i * step; j < (i + 1) * step && j < waveform.length; j++) {
          const abs = Math.abs(waveform[j]);
          if (abs > max) max = abs;
        }
        const h = Math.max(2, max * height);
        const y = (height - h) / 2;
        ctx.fillStyle = i < progressX ? "#4d9dff" : "#2d3748";
        ctx.fillRect(i, y, 1, h);
      }
    },
    [waveform],
  );

  // Redraw when waveform loads
  useEffect(() => {
    draw(0);
  }, [draw]);

  // Animation loop
  useEffect(() => {
    if (!playing) {
      cancelAnimationFrame(animRef.current);
      return;
    }
    const tick = () => {
      const audio = audioRef.current;
      if (!audio) return;
      const t = audio.currentTime;
      const d = audio.duration || 1;
      setCurrentTime(t);
      draw(t / d);
      animRef.current = requestAnimationFrame(tick);
    };
    animRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(animRef.current);
  }, [playing, draw]);

  const toggle = () => {
    const audio = audioRef.current;
    if (!audio) return;
    if (playing) {
      audio.pause();
    } else {
      void audio.play();
    }
  };

  // Canvas click to seek
  const handleCanvasClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const audio = audioRef.current;
    const canvas = canvasRef.current;
    if (!audio || !canvas || !audio.duration) return;
    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const ratio = x / rect.width;
    audio.currentTime = ratio * audio.duration;
    setCurrentTime(audio.currentTime);
    draw(ratio);
  };

  const fmt = (s: number) => {
    if (!isFinite(s)) return "0:00";
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return `${m}:${sec.toString().padStart(2, "0")}`;
  };

  return (
    <div className="rounded-xl border border-white/10 bg-surface-2 p-3 space-y-2">
      <audio
        ref={audioRef}
        src={src}
        preload="metadata"
        onLoadedMetadata={(e) => setDuration((e.target as HTMLAudioElement).duration)}
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onEnded={() => {
          setPlaying(false);
          setCurrentTime(0);
          draw(0);
        }}
        onTimeUpdate={(e) => setCurrentTime((e.target as HTMLAudioElement).currentTime)}
      />

      {loading && (
        <div className="flex h-12 items-center justify-center">
          <span className="h-4 w-4 animate-spin rounded-full border-2 border-accent border-t-transparent" />
          <span className="ml-2 text-xs text-ink-3">Loading waveform…</span>
        </div>
      )}

      {error && (
        <div className="flex h-12 items-center justify-center">
          <span className="text-xs text-status-warning">{error}</span>
        </div>
      )}

      {!loading && !error && (
        <canvas
          ref={canvasRef}
          width={600}
          height={48}
          onClick={handleCanvasClick}
          className="w-full cursor-pointer rounded"
          style={{ height: 48 }}
          aria-label="Audio waveform — click to seek"
        />
      )}

      <div className="flex items-center gap-3">
        <button
          onClick={toggle}
          disabled={loading || !!error}
          aria-label={playing ? "Pause" : "Play"}
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent text-white transition-opacity disabled:opacity-40 hover:opacity-90"
        >
          {playing ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
        </button>
        <span className="font-mono text-xs text-ink-3 tabular-nums">
          {fmt(currentTime)} / {fmt(duration)}
        </span>
      </div>
    </div>
  );
}
