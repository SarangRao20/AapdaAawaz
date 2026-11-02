/** The caller app's side of Awaaz Live: microphone up to Prisma, Timbre's voice back to the speaker. */

import { BASE } from "./api";

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

/** The APK is served from http://localhost, so the socket must point at the API, not at the page. */
function socketUrl(): string {
  const base = BASE.replace(/\/+$/, "").replace(/^http/i, "ws");
  return `${base}/api/live/call`;
}

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
  switch ((error as { name?: string } | null)?.name) {
    case "NotAllowedError":
    case "SecurityError":
      return "Microphone blocked. Settings → Apps → Aapda Awaaz → Permissions → allow Microphone.";
    case "NotFoundError":
    case "OverconstrainedError":
      return "No microphone was found on this device.";
    case "NotReadableError":
      return "The microphone is busy in another app. Close it and try again.";
    default:
      return error instanceof Error ? error.message : "The microphone couldn't start.";
  }
}

function closeMessage(code: number): string {
  if (code === 4401) return "This call needs a login. Please update the app.";
  if (code === 4429) return "Awaaz Live is busy right now. Please try again in a minute.";
  return "The call was disconnected. Check your connection and try again.";
}

export class LiveCallClient {
  private ws: WebSocket | null = null;
  private context: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private worklet: AudioWorkletNode | null = null;
  private processor: ScriptProcessorNode | null = null;
  private workletReady = false;
  private nextPlayAt = 0;
  private playing = 0;
  private serverFinishedAudio = false;
  private finished = false;
  private errored = false;
  private handlers: CallHandlers;

  constructor(handlers: CallHandlers) {
    this.handlers = handlers;
  }

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

    try {
      // "interactive" asks Android for the smallest output buffer, which shortens every reply.
      this.context = new AudioContext({ latencyHint: "interactive" });
      await this.context.resume();
      this.workletReady = await this.loadWorklet();
    } catch {
      this.handlers.onError("Audio couldn't start on this device. Close other audio apps and try again.");
      this.handlers.onState("ended");
      this.releaseAudio();
      return;
    }

    let ws: WebSocket;
    try {
      ws = new WebSocket(socketUrl());
    } catch {
      this.handlers.onError("The call address is not valid. Check the app's API URL.");
      this.handlers.onState("ended");
      this.releaseAudio();
      return;
    }
    ws.binaryType = "arraybuffer";
    this.ws = ws;
    ws.onopen = () => {
      ws.send(JSON.stringify({ type: "start", language }));
      this.startMicrophone();
    };
    ws.onmessage = (event) => this.onMessage(event);
    ws.onclose = (event) => {
      if (this.finished) return;
      if (!this.errored) this.handlers.onError(closeMessage(event.code));
      this.finish(null);
    };
    ws.onerror = () => {
      // onclose always follows and carries the useful message.
    };
  }

  /** The caller finished talking, so don't wait for Prisma to notice the silence. */
  commit(): void {
    this.sendJson({ type: "commit" });
  }

  hangUp(): void {
    this.sendJson({ type: "end" });
  }

  /** Always release the microphone, even if the screen is left mid-call. */
  dispose(): void {
    this.finished = true;
    this.ws?.close();
    this.releaseAudio();
  }

  private async loadWorklet(): Promise<boolean> {
    if (!this.context?.audioWorklet) return false;
    const url = URL.createObjectURL(new Blob([CAPTURE_WORKLET], { type: "application/javascript" }));
    try {
      await this.context.audioWorklet.addModule(url);
      return true;
    } catch {
      // Older WebViews have audioWorklet but refuse blob modules; ScriptProcessor still works.
      return false;
    } finally {
      URL.revokeObjectURL(url);
    }
  }

  private sendJson(payload: object): void {
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(payload));
  }

  private startMicrophone(): void {
    if (!this.context || !this.stream) return;
    const source = this.context.createMediaStreamSource(this.stream);
    // A silent output keeps the audio graph running without playing the caller back to themselves.
    const silent = this.context.createGain();
    silent.gain.value = 0;

    if (this.workletReady) {
      this.worklet = new AudioWorkletNode(this.context, "capture");
      this.worklet.port.onmessage = ({ data }: MessageEvent<ArrayBuffer>) => this.emit(data);
      source.connect(this.worklet);
      this.worklet.connect(silent);
    } else {
      const processor = this.context.createScriptProcessor(2048, 1, 1);
      const ratio = this.context.sampleRate / RATE;
      const frame = new Int16Array(FRAME_SAMPLES);
      let position = 0;
      let sum = 0;
      let count = 0;
      let filled = 0;
      processor.onaudioprocess = (event) => {
        const channel = event.inputBuffer.getChannelData(0);
        for (let i = 0; i < channel.length; i++) {
          sum += channel[i];
          count++;
          position++;
          if (position >= ratio) {
            position -= ratio;
            const sample = Math.max(-1, Math.min(1, sum / count));
            sum = 0;
            count = 0;
            frame[filled++] = sample * 32767;
            if (filled === FRAME_SAMPLES) {
              this.emit(frame.slice().buffer);
              filled = 0;
            }
          }
        }
      };
      this.processor = processor;
      source.connect(processor);
      processor.connect(silent);
    }
    silent.connect(this.context.destination);
  }

  private emit(data: ArrayBuffer): void {
    const samples = new Int16Array(data);
    let peak = 0;
    for (let i = 0; i < samples.length; i += 8) peak = Math.max(peak, Math.abs(samples[i]));
    this.handlers.onLevel(peak / 32767);
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(data);
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
        this.errored = true;
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
    // A small lead keeps chunks seamless; 20 ms is enough on Android and keeps the reply snappy.
    const startAt = Math.max(this.nextPlayAt, this.context.currentTime + 0.02);
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
    this.processor?.disconnect();
    this.stream?.getTracks().forEach((track) => track.stop());
    void this.context?.close().catch(() => undefined);
    this.worklet = null;
    this.processor = null;
    this.stream = null;
    this.context = null;
  }
}
