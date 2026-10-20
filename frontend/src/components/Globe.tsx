import createGlobe, { type Globe as CobeGlobe, type Marker } from "cobe";
import { LocateFixed, Map as MapIcon, Minus, Pause, Play, Plus } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { PRIORITY_COLOR, PRIORITY_RANK, isMappable, locationText } from "../lib/format";
import type { Incident, Priority } from "../lib/types";

const SIZE: Record<Priority, number> = { critical: 0.085, high: 0.07, medium: 0.055, low: 0.045 };

function rgb(hex: string): [number, number, number] {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255];
}

export const pinId = (incidentId: string) => "p" + incidentId.toLowerCase().replace(/[^a-z0-9]/g, "-");

/** cobe maps lat/lon to 3D then rotates by phi (around Y) and theta (around X); this inverts that to face a point. */
function facing(lat: number, lon: number) {
  const la = (lat * Math.PI) / 180;
  const lo = (lon * Math.PI) / 180 - Math.PI;
  const px = -Math.cos(la) * Math.cos(lo);
  const pz = Math.cos(la) * Math.sin(lo);
  return { phi: Math.atan2(pz, px) - Math.PI / 2, theta: la };
}

const wrap = (a: number) => Math.atan2(Math.sin(a), Math.cos(a));
const supportsAnchors = typeof CSS !== "undefined" && CSS.supports?.("anchor-name", "--x");

/**
 * Offline 3D globe (WebGL, no textures or network). Pins are real incident coordinates, the selected
 * incident is flown to, and critical pins pulse. Coordinates are the simulated reference points.
 */
export function Globe({
  incidents,
  selectedId,
  onSelect,
  onOpenMap,
  className,
}: {
  incidents: Incident[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onOpenMap?: () => void;
  className?: string;
}) {
  const wrapEl = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const globe = useRef<CobeGlobe | null>(null);
  const view = useRef({ phi: 0.6, theta: 0.35, tPhi: null as number | null, tTheta: 0.35, drag: false, lastX: 0, lastY: 0, spin: false, scale: 1, tScale: 1 });
  const [spin, setSpin] = useState(false);
  const placed = useRef(false);
  const [failed, setFailed] = useState(false);
  const [size, setSize] = useState(0);
  const mappable = useMemo(() => incidents.filter(isMappable), [incidents]);
  const selected = mappable.find((i) => i.id === selectedId) ?? null;

  const markers: Marker[] = useMemo(
    () =>
      mappable.map((i) => ({
        location: [i.latitude!, i.longitude!],
        size: SIZE[i.priority_label] * (i.id === selectedId ? 1.5 : 1),
        color: rgb(PRIORITY_COLOR[i.priority_label]),
        id: pinId(i.id),
      })),
    [mappable, selectedId],
  );
  const markersRef = useRef(markers);
  markersRef.current = markers;

  useEffect(() => {
    const box = wrapEl.current;
    if (!box) return;
    const measure = () => setSize(Math.floor(Math.min(box.clientWidth, box.clientHeight)));
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(box);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    const c = canvas.current;
    const box = wrapEl.current;
    if (!c || !box || size <= 0) return;
    let raf = 0;
    let g: CobeGlobe;
    try {
      const px = Math.max(300, size);
      g = createGlobe(c, {
        devicePixelRatio: Math.min(window.devicePixelRatio || 1, 2),
        width: px * 2,
        height: px * 2,
        phi: view.current.phi,
        theta: view.current.theta,
        dark: 1,
        diffuse: 1.4,
        mapSamples: 22000,
        mapBrightness: 5,
        baseColor: [0.16, 0.2, 0.3],
        markerColor: [1, 0.3, 0.3],
        glowColor: [0.12, 0.22, 0.45],
        markers: markersRef.current,
        markerElevation: 0.01,
      });
    } catch {
      setFailed(true);
      return;
    }
    globe.current = g;
    const tick = () => {
      const v = view.current;
      if (v.tPhi !== null && !v.drag) {
        const dp = wrap(v.tPhi - v.phi);
        const dt = v.tTheta - v.theta;
        v.phi += dp * 0.08;
        v.theta += dt * 0.08;
      } else if (v.spin && !v.drag) {
        v.phi += 0.0035;
      }
      v.scale += (v.tScale - v.scale) * 0.08;
      g.update({ phi: v.phi, theta: v.theta, scale: v.scale });
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(raf);
      g.destroy();
      globe.current = null;
    };
  }, [size > 0]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    globe.current?.update({ markers });
  }, [markers]);

  useEffect(() => {
    const v = view.current;
    if (selected) {
      const f = facing(selected.latitude!, selected.longitude!);
      v.tPhi = f.phi;
      v.tTheta = Math.max(-0.9, Math.min(0.9, f.theta));
      v.tScale = Math.max(v.tScale, 2.4);
      if (!placed.current) {
        v.scale = v.tScale;
        v.phi = f.phi;
        v.theta = v.tTheta;
        placed.current = true;
      }
    } else {
      v.tPhi = null;
      v.tScale = 1;
    }
  }, [selected?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // First load: open on the incident cluster instead of an arbitrary continent.
  useEffect(() => {
    if (placed.current || !mappable.length) return;
    const lat = mappable.reduce((a, i) => a + i.latitude!, 0) / mappable.length;
    const lon = mappable.reduce((a, i) => a + i.longitude!, 0) / mappable.length;
    const f = facing(lat, lon);
    view.current.phi = f.phi;
    view.current.theta = f.theta;
    placed.current = true;
  }, [mappable]);

  useEffect(() => {
    view.current.spin = spin;
  }, [spin]);

  const down = (e: React.PointerEvent) => {
    const v = view.current;
    v.drag = true;
    v.tPhi = null;
    v.lastX = e.clientX;
    v.lastY = e.clientY;
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  };
  const move = (e: React.PointerEvent) => {
    const v = view.current;
    if (!v.drag) return;
    v.phi += (e.clientX - v.lastX) * 0.006;
    v.theta = Math.max(-1.1, Math.min(1.1, v.theta + (e.clientY - v.lastY) * 0.006));
    v.lastX = e.clientX;
    v.lastY = e.clientY;
  };
  const up = () => {
    view.current.drag = false;
  };

  const ordered = [...mappable].sort((a, b) => PRIORITY_RANK[a.priority_label] - PRIORITY_RANK[b.priority_label]);

  if (failed)
    return (
      <div className={`grid place-items-center text-sm text-ink-3 ${className ?? ""}`}>
        3D globe needs WebGL, which this browser or device doesn't provide. Switch to the Map view.
      </div>
    );

  return (
    <div ref={wrapEl} className={`relative grid min-h-0 min-w-0 place-items-center overflow-hidden ${className ?? ""}`}>
      <div
        style={{ width: size, height: size }}
        className="relative cursor-grab touch-none select-none active:cursor-grabbing"
        onPointerDown={down}
        onPointerMove={move}
        onPointerUp={up}
        onPointerCancel={up}
      >
        <canvas ref={canvas} className="h-full w-full" aria-label="3D globe of active incidents" />
        {supportsAnchors &&
          ordered.map((i) => {
            const id = pinId(i.id);
            const isSel = i.id === selectedId;
            const crit = i.priority_label === "critical";
            const style = {
              position: "absolute",
              positionAnchor: `--cobe-${id}`,
              left: "anchor(center)",
              top: "anchor(center)",
              transform: `scale(var(--cobe-visible-${id}, 0))`,
              opacity: `var(--cobe-visible-${id}, 0)`,
              transition: "opacity .3s, transform .3s",
              zIndex: isSel ? 30 : PRIORITY_RANK[i.priority_label],
            } as React.CSSProperties;
            const color = PRIORITY_COLOR[i.priority_label];
            return (
              <div key={i.id} style={style}>
                <button
                  onPointerDown={(e) => e.stopPropagation()}
                  onClick={() => onSelect(i.id)}
                  aria-label={`${i.id} ${i.priority_label} ${locationText(i)}`}
                  className="group absolute -left-4 -top-4 grid h-8 w-8 place-items-center rounded-full outline-none"
                >
                  {(crit || isSel) && (
                    <span className="absolute inset-0 animate-pulse-ring rounded-full" style={{ background: color, opacity: 0.55 }} />
                  )}
                  {isSel && <span className="absolute inset-[-6px] rounded-full border-2" style={{ borderColor: color }} />}
                  <span className="pointer-events-none absolute bottom-full left-1/2 mb-2 -translate-x-1/2 whitespace-nowrap rounded-lg border border-white/10 bg-bg/90 px-2.5 py-1 text-xs text-ink opacity-0 backdrop-blur transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100">
                    <b style={{ color }}>{i.priority_label.toUpperCase()}</b> · {locationText(i)}
                  </span>
                </button>
                {isSel && (
                  <div
                    className="pointer-events-none absolute bottom-6 left-1/2 w-52 -translate-x-1/2 rounded-xl border bg-bg/90 p-2.5 text-xs shadow-glass backdrop-blur"
                    style={{ borderColor: color }}
                  >
                    <div className="font-semibold" style={{ color }}>
                      {i.priority_label.toUpperCase()} · {i.id}
                    </div>
                    <div className="mt-0.5 text-ink">{locationText(i)}</div>
                  </div>
                )}
              </div>
            );
          })}
      </div>

      <div className="absolute bottom-3 right-3 flex gap-1.5">
        <button onClick={() => (view.current.tScale = Math.max(1, view.current.tScale - 0.8))} className="grid h-9 w-9 place-items-center rounded-xl border border-white/10 bg-bg/70 text-ink-2 backdrop-blur transition-colors hover:text-ink" aria-label="Zoom out" title="Zoom out">
          <Minus className="h-4 w-4" />
        </button>
        <button onClick={() => (view.current.tScale = Math.min(6, view.current.tScale + 0.8))} className="grid h-9 w-9 place-items-center rounded-xl border border-white/10 bg-bg/70 text-ink-2 backdrop-blur transition-colors hover:text-ink" aria-label="Zoom in" title="Zoom in">
          <Plus className="h-4 w-4" />
        </button>
        <button
          onClick={() => setSpin((s) => !s)}
          className="grid h-9 w-9 place-items-center rounded-xl border border-white/10 bg-bg/70 text-ink-2 backdrop-blur transition-colors hover:text-ink"
          aria-label={spin ? "Pause rotation" : "Resume rotation"}
          title={spin ? "Pause rotation" : "Resume rotation"}
        >
          {spin ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
        </button>
        <button
          onClick={() => {
            const top = ordered[ordered.length - 1];
            if (top) onSelect(top.id);
          }}
          className="grid h-9 w-9 place-items-center rounded-xl border border-white/10 bg-bg/70 text-ink-2 backdrop-blur transition-colors hover:text-ink"
          aria-label="Fly to the highest priority incident"
          title="Fly to the highest priority incident"
        >
          <LocateFixed className="h-4 w-4" />
        </button>
      </div>
      {selected && onOpenMap && (
        <button
          onClick={onOpenMap}
          className="absolute bottom-3 left-3 inline-flex h-9 items-center gap-1.5 rounded-xl border border-white/10 bg-bg/70 px-3 text-xs font-medium text-ink backdrop-blur transition-colors hover:bg-white/10"
        >
          <MapIcon className="h-4 w-4" aria-hidden /> See on street map
        </button>
      )}
      {!supportsAnchors && mappable.length > 0 && (
        <div className="absolute left-3 top-16 rounded-lg border border-white/10 bg-bg/70 px-2.5 py-1 text-2xs text-ink-3 backdrop-blur">
          Coloured dots are incidents. Pin labels need a Chromium-based browser.
        </div>
      )}
    </div>
  );
}
