/** The browser side of a live call: microphone up to Prisma, Timbre's voice back to the speaker. */

export type CallState = "connecting" | "listening" | "thinking" | "speaking" | "ended";
export type CallLanguage = "hi" | "mr" | "en" | "mixed";

export interface CallFacts {
  place: string | null;
  disaster: string | null;
  people: number | null;
  priority: string | null;
  score: number | null;
  report_id: string | null;
  needs_review: boolean;
}

export interface CallMetrics {
  prisma_ms: number;
  reply_ms: number;
  total_ms: number;
}

export interface CallHandlers {
  onState: (state: CallState) => void;
  onCaller: (text: string) => void;
  onAssistant: (text: string) => void;
  onFacts: (facts: CallFacts, askingFor: string | null) => void;
  onMetrics: (metrics: CallMetrics) => void;
  onLevel: (level: number) => void;
  onNotice: (message: string) => void;
  onDone: (reportId: string | null) => void;
  onError: (message: string) => void;
}

const RATE = 16000;
const FRAME_SAMPLES = 512;

// Runs on the audio thread: averages the microphone down to 16 kHz and posts 16-bit frames.
const CAPTURE_WORKLET = `
class Capture extends AudioWorkletProcessor {
  constructor() {
    super();
    this.ratio = sampleRate / ${RATE};
    this.position = 0;
    this.sum = 0;
    this.count = 0;
    this.frame = new Int16Array(${FRAME_SAMPLES});
    this.filled = 0;
  }
  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (!channel) return true;
    for (let i = 0; i < channel.length; i++) {
      this.sum += channel[i];
      this.count++;
      this.position++;
      if (this.position >= this.ratio) {
        this.position -= this.ratio;
        const sample = Math.max(-1, Math.min(1, this.sum / this.count));
        this.sum = 0;
        this.count = 0;
        this.frame[this.filled++] = sample * 32767;
        if (this.filled === ${FRAME_SAMPLES}) {
          const copy = this.frame.slice();
          this.port.postMessage(copy.buffer, [copy.buffer]);
          this.filled = 0;
        }
      }
    }
    return true;
  }
}
registerProcessor("capture", Capture);
`;

function micError(error: unknown): string {
  const name = error instanceof DOMException ? error.name : "";
  if (name === "NotAllowedError") return "Microphone access was blocked. Allow it in the browser's address bar, then try again.";
  if (name === "NotFoundError") return "No microphone was found on this device.";
  return "The microphone couldn't start. This page needs localhost or HTTPS to use it.";
}

/**
 * Where the call socket goes. By default the page's own host (Vite proxies it in development; a reverse proxy
 * that passes WebSockets does in production). Hosts like Vercel rewrite plain HTTP but not WebSockets, so there
 * VITE_WS_ORIGIN (for example wss://api.example.com) points the socket straight at the API. That host cannot see
 * the dashboard's login cookie, so a one-minute ticket is fetched first over the normal logged-in API.
 */
async function callUrl(): Promise<string> {
  const configured = (import.meta.env.VITE_WS_ORIGIN as string | undefined)?.trim().replace(/\/+$/, "");
  if (!configured) {
    const scheme = location.protocol === "https:" ? "wss" : "ws";
    return `${scheme}://${location.host}/api/live/call`;
  }
  let res: Response;
  try {
    res = await fetch("/api/live/ticket", { method: "POST", headers: { "ngrok-skip-browser-warning": "1" }, credentials: "same-origin" });
  } catch {
    throw new Error("Could not reach the server to start the call.");
  }
  if (res.status === 401) throw new Error("Your session has ended. Please log in again.");
  if (!res.ok) throw new Error(`The server refused to start a call (${res.status}).`);
  const { ticket } = (await res.json()) as { ticket: string };
  return `${configured.replace(/^http/, "ws")}/api/live/call?ticket=${encodeURIComponent(ticket)}`;
}

export class LiveCallClient {
  private ws: WebSocket | null = null;
  private context: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private worklet: AudioWorkletNode | null = null;
  private nextPlayAt = 0;
  private playing = 0;
  private serverFinishedAudio = false;
  private finished = false;

  constructor(private handlers: CallHandlers) {}

  async start(language: CallLanguage): Promise<void> {
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 },
      });
    } catch (error) {
      this.handlers.onError(micError(error));
      this.handlers.onState("ended");
      return;
    }
    this.handlers.onState("connecting");
    this.context = new AudioContext();
    await this.context.resume();
    const moduleUrl = URL.createObjectURL(new Blob([CAPTURE_WORKLET], { type: "application/javascript" }));
    await this.context.audioWorklet.addModule(moduleUrl);
    URL.revokeObjectURL(moduleUrl);

    let url: string;
    try {
      url = await callUrl();
    } catch (error) {
      this.handlers.onError(error instanceof Error ? error.message : "Could not prepare the call.");
      this.finish(null);
      return;
    }
    const ws = new WebSocket(url);
    ws.binaryType = "arraybuffer";
    this.ws = ws;
    let opened = false;
    ws.onopen = () => {
      opened = true;
      ws.send(JSON.stringify({ type: "start", language }));
      this.startMicrophone();
    };
    ws.onmessage = (event) => this.onMessage(event);
    ws.onclose = (event) => {
      if (this.finished) return;
      if (event.code === 4401) this.handlers.onError("Your session has ended. Please log in again.");
      else if (!opened)
        // Never connected: the server is down, or something in between (a proxy or a host such as Vercel
        // rewrites) does not pass WebSockets. This is a connection problem, not a problem with the caller.
        this.handlers.onError("Could not open the call connection. The server may be unreachable, or a proxy in front of it is blocking WebSockets.");
      else this.handlers.onError("The call was disconnected.");
      this.finish(null);
    };
  }

  /** The caller finished talking, so don't wait for Prisma to notice the silence. */
  commit(): void {
    this.sendJson({ type: "commit" });
  }

  hangUp(): void {
    this.sendJson({ type: "end" });
  }

  /** Always release the microphone, even if the page is left mid-call. */
  dispose(): void {
    this.finished = true;
    this.ws?.close();
    this.releaseAudio();
  }

  private sendJson(payload: object): void {
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(payload));
  }

  private startMicrophone(): void {
    if (!this.context || !this.stream) return;
    const source = this.context.createMediaStreamSource(this.stream);
    this.worklet = new AudioWorkletNode(this.context, "capture");
    this.worklet.port.onmessage = ({ data }: MessageEvent<ArrayBuffer>) => {
      const samples = new Int16Array(data);
      let peak = 0;
      for (let i = 0; i < samples.length; i += 8) peak = Math.max(peak, Math.abs(samples[i]));
      this.handlers.onLevel(peak / 32767);
      if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(data);
    };
    // A silent output keeps the audio graph running without playing the caller back to themselves.
    const silent = this.context.createGain();
    silent.gain.value = 0;
    source.connect(this.worklet);
    this.worklet.connect(silent);
    silent.connect(this.context.destination);
  }

  private onMessage(event: MessageEvent): void {
    if (event.data instanceof ArrayBuffer) {
      this.play(event.data);
      return;
    }
    const message = JSON.parse(event.data as string);
    switch (message.type) {
      case "state":
        this.handlers.onState(message.state);
        break;
      case "caller":
        this.handlers.onCaller(message.text);
        break;
      case "assistant":
        this.handlers.onAssistant(message.text);
        break;
      case "facts":
        this.handlers.onFacts(message.facts, message.asking_for);
        break;
      case "metrics":
        this.handlers.onMetrics(message);
        break;
      case "audio_start":
        this.serverFinishedAudio = false;
        break;
      case "audio_end":
        this.serverFinishedAudio = true;
        this.reportPlaybackIfDone();
        break;
      case "notice":
        this.handlers.onNotice(message.message);
        break;
      case "error":
        this.handlers.onError(message.message);
        break;
      case "done":
        this.finish(message.report_id ?? null);
        break;
    }
  }

  private play(buffer: ArrayBuffer): void {
    if (!this.context) return;
    const samples = new Int16Array(buffer);
    const audio = this.context.createBuffer(1, samples.length, RATE);
    const channel = audio.getChannelData(0);
    for (let i = 0; i < samples.length; i++) channel[i] = samples[i] / 32768;
    const source = this.context.createBufferSource();
    source.buffer = audio;
    source.connect(this.context.destination);
    const startAt = Math.max(this.nextPlayAt, this.context.currentTime + 0.05);
    source.start(startAt);
    this.nextPlayAt = startAt + audio.duration;
    this.playing++;
    source.onended = () => {
      this.playing--;
      this.reportPlaybackIfDone();
    };
  }

  /** The server waits for this before listening again, so it can't hear its own voice from the speaker. */
  private reportPlaybackIfDone(): void {
    if (this.serverFinishedAudio && this.playing === 0) {
      this.serverFinishedAudio = false;
      this.sendJson({ type: "playback_done" });
    }
  }

  private finish(reportId: string | null): void {
    if (this.finished) return;
    this.finished = true;
    this.handlers.onState("ended");
    this.handlers.onDone(reportId);
    this.ws?.close();
    this.releaseAudio();
  }

  private releaseAudio(): void {
    this.worklet?.disconnect();
    this.stream?.getTracks().forEach((track) => track.stop());
    void this.context?.close().catch(() => undefined);
    this.worklet = null;
    this.stream = null;
    this.context = null;
  }
}
