import { describe, expect, it } from "vitest";
import { encodeWav } from "./wav";

describe("encodeWav", () => {
  it("writes a valid 16 kHz mono PCM header and clamps samples", () => {
    const bytes = encodeWav(new Float32Array([0, 1, -1, 2]), 16000);
    const view = new DataView(bytes.buffer);
    const text = (o: number) => String.fromCharCode(...bytes.slice(o, o + 4));
    expect(text(0)).toBe("RIFF");
    expect(text(8)).toBe("WAVE");
    expect(view.getUint16(22, true)).toBe(1);
    expect(view.getUint32(24, true)).toBe(16000);
    expect(view.getUint32(40, true)).toBe(8);
    expect(view.getInt16(46, true)).toBe(0x7fff);
    expect(view.getInt16(48, true)).toBe(-0x8000);
    expect(view.getInt16(50, true)).toBe(0x7fff); // 2 is clamped to 1
    expect(bytes.length).toBe(44 + 8);
  });
});
