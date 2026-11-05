import { useEffect, useState } from "react";
import { fetchAudio } from "./api";

export interface AudioSource {
  /** A blob: URL that plays and downloads without further requests, or null while loading / on error. */
  src: string | null;
  blob: Blob | null;
  loading: boolean;
  error: string | null;
}

/** Loads a recording from the API (with credentials and tunnel headers) and exposes it as a local blob URL. */
export function useAudioUrl(url: string | null | undefined): AudioSource {
  const [state, setState] = useState<AudioSource>({ src: null, blob: null, loading: !!url, error: null });

  useEffect(() => {
    if (!url) {
      setState({ src: null, blob: null, loading: false, error: null });
      return;
    }
    let cancelled = false;
    let objectUrl: string | null = null;
    setState({ src: null, blob: null, loading: true, error: null });
    fetchAudio(url)
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setState({ src: objectUrl, blob, loading: false, error: null });
      })
      .catch((e: unknown) => {
        if (!cancelled) setState({ src: null, blob: null, loading: false, error: e instanceof Error ? e.message : "Failed to load audio" });
      });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [url]);

  return state;
}
