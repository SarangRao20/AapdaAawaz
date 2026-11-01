import * as d3 from "d3";
import * as topojson from "topojson-client";
import type { Topology, GeometryCollection } from "topojson-specification";
import { LocateFixed, Map as MapIcon, Minus, Plus } from "lucide-react";
import { useEffect, useRef, useState, useMemo } from "react";
import { PRIORITY_COLOR, PRIORITY_RANK, isMappable, locationText } from "../lib/format";
import type { Incident, Priority } from "../lib/types";

// Orange accent matching the app palette
const ACCENT = "#f97316";
const BG = "#05070B";
const OCEAN = "#070E19";
const LAND = "#1a2e40";

const PIN_SIZE: Record<Priority, number> = { critical: 7, high: 6, medium: 5, low: 4 };

type WorldTopo = Topology<{ land: GeometryCollection; countries: GeometryCollection }>;

function norm180(x: number) {
  return (((x + 180) % 360) + 360) % 360 - 180;
}
function eio(u: number) {
  u = Math.max(0, Math.min(1, u));
  return u < 0.5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2;
}
function eoc(u: number) {
  u = Math.max(0, Math.min(1, u));
  return 1 - Math.pow(1 - u, 3);
}

// Build easing LUT (same as globe-locator)
const LUT_N = 512;
const lut = new Float32Array(LUT_N + 1);
(function () {
  let sum = 0;
  for (let i = 0; i < LUT_N; i++) {
    const u = (i + 0.5) / LUT_N;
    const r = Math.min(1, u / 0.08);
    const ramp = r * r * (3 - 2 * r);
    sum += ramp * Math.pow(1 - u, 2.2);
    lut[i + 1] = sum;
  }
  for (let i = 1; i <= LUT_N; i++) lut[i] /= sum;
})();
function ease(u: number) {
  const x = Math.max(0, Math.min(1, u)) * LUT_N;
  const i = Math.min(LUT_N - 1, Math.floor(x));
  return lut[i] + (lut[i + 1] - lut[i]) * (x - i);
}

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
  const canvasEl = useRef<HTMLCanvasElement>(null);
  const mappable = useMemo(() => incidents.filter(isMappable), [incidents]);
  const selected = mappable.find((i) => i.id === selectedId) ?? null;

  // Mutable render state (not React state — avoids re-renders in the RAF loop)
  const state = useRef({
    rot: [-60, -18, 0] as [number, number, number],
    k: 1,
    kGoal: 1,
    drag: null as { x: number; y: number; l: number; p: number } | null,
    anim: null as {
      t0: number; dur: number; spin: boolean;
      lam0: number; dLam: number; phi0: number; phiT: number;
      k0: number; kT: number;
      onDone?: () => void;
    } | null,
    animU: 0,
    speed: 0,
    idleHold: 0,
    last: 0,
    lockAt: 0,
    phase: "loading" as "loading" | "idle" | "spinning" | "locked",
    lo: null as { land: d3.GeoPermissibleObjects; borders: d3.GeoPermissibleObjects } | null,
    hi: null as { land: d3.GeoPermissibleObjects; borders: d3.GeoPermissibleObjects } | null,
    stars: [] as { x: number; y: number; r: number; a: number }[],
    W: 0, H: 0, dpr: 1, R: 0, Rcss: 0, cx: 0, cy: 0,
    target: null as Incident | null,
    selectedId: null as string | null,
    incidents: [] as Incident[],
  });

  const [, forceUpdate] = useState(0);
  const phase = useRef<"loading" | "idle" | "spinning" | "locked">("loading");

  function resize() {
    const wrap = wrapEl.current;
    const canvas = canvasEl.current;
    if (!wrap || !canvas) return;
    const s = state.current;
    s.W = Math.max(1, wrap.clientWidth);
    s.H = Math.max(1, wrap.clientHeight);
    s.dpr = Math.min(2, window.devicePixelRatio || 1);
    canvas.width = Math.round(s.W * s.dpr);
    canvas.height = Math.round(s.H * s.dpr);
    s.Rcss = Math.min(s.W, s.H) * 0.44;
    s.R = s.Rcss * s.dpr;
    s.cx = canvas.width / 2;
    s.cy = canvas.height / 2;
    let seed = 7;
    const rnd = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
    s.stars = [];
    for (let i = 0; i < 220; i++) s.stars.push({ x: rnd(), y: rnd(), r: 0.5 + rnd() * 1.1, a: 0.15 + rnd() * 0.55 });
  }

  // Main render + RAF loop
  useEffect(() => {
    // eslint-disable-next-line @typescript-eslint/no-non-null-assertion
    const canvas = canvasEl.current!;
    // eslint-disable-next-line @typescript-eslint/no-non-null-assertion
    const wrap = wrapEl.current!;
    if (!canvas || !wrap) return;

    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(wrap);

    const s = state.current;
    const proj = d3.geoOrthographic().clipAngle(90).precision(0.6);
    const path = d3.geoPath(proj);
    const grat = d3.geoGraticule10();

    function prepTopo(t: WorldTopo) {
      return {
        land: topojson.feature(t, t.objects.land) as unknown as d3.GeoPermissibleObjects,
        borders: topojson.mesh(t, t.objects.countries, (a, b) => a !== b) as unknown as d3.GeoPermissibleObjects,
      };
    }

    fetch("https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json")
      .then((r) => r.json())
      .then((t: WorldTopo) => {
        s.lo = prepTopo(t);
        if (s.phase === "loading") {
          s.phase = "idle";
          phase.current = "idle";
          // Center on India (where demo incidents are)
          s.rot = [-80, -20, 0];
        }
      })
      .catch(() => {});

    fetch("https://cdn.jsdelivr.net/npm/world-atlas@2/countries-50m.json")
      .then((r) => r.json())
      .then((t: WorldTopo) => { s.hi = prepTopo(t); })
      .catch(() => {});

    function drawStars(ctx: CanvasRenderingContext2D) {
      const off = s.rot[0] * 0.12 * s.dpr;
      ctx.fillStyle = "#C8D4E6";
      for (const star of s.stars) {
        let x = (star.x * canvas.width + off) % canvas.width;
        if (x < 0) x += canvas.width;
        ctx.globalAlpha = star.a;
        ctx.fillRect(x, star.y * canvas.height, star.r * s.dpr, star.r * s.dpr);
      }
      ctx.globalAlpha = 1;
    }

    function reticle(ctx: CanvasRenderingContext2D, x: number, y: number, sz: number, ang: number, alpha: number) {
      ctx.save();
      ctx.translate(x, y);
      ctx.rotate(ang);
      ctx.globalAlpha = alpha;
      ctx.lineWidth = 1.6 * s.dpr;
      ctx.lineCap = "square";
      const l = sz * 0.42;
      ctx.beginPath();
      for (const [qx, qy] of [[-1, -1], [1, -1], [1, 1], [-1, 1]] as [number, number][]) {
        ctx.moveTo(qx * sz, qy * (sz - l));
        ctx.lineTo(qx * sz, qy * sz);
        ctx.lineTo(qx * (sz - l), qy * sz);
      }
      ctx.stroke();
      ctx.restore();
    }

    function crosshair(ctx: CanvasRenderingContext2D, x: number, y: number, alpha: number, gap: number) {
      ctx.save();
      ctx.globalAlpha = alpha;
      ctx.lineWidth = s.dpr;
      ctx.setLineDash([2 * s.dpr, 6 * s.dpr]);
      ctx.beginPath();
      ctx.moveTo(0, y); ctx.lineTo(x - gap, y);
      ctx.moveTo(x + gap, y); ctx.lineTo(canvas.width, y);
      ctx.moveTo(x, 0); ctx.lineTo(x, y - gap);
      ctx.moveTo(x, y + gap); ctx.lineTo(x, canvas.height);
      ctx.stroke();
      ctx.restore();
    }

    function drawIncidents(ctx: CanvasRenderingContext2D, pr: d3.GeoProjection, Rv: number) {
      const inc = s.incidents;
      if (!inc.length) return;
      const D = Math.PI / 180;
      const lam = -s.rot[0] * D, phi2 = -s.rot[1] * D;
      const ux = Math.cos(phi2) * Math.cos(lam);
      const uy = Math.cos(phi2) * Math.sin(lam);
      const uz = Math.sin(phi2);
      const ratio = Math.hypot(canvas.width, canvas.height) / 2 / Rv;
      const lim = ratio >= 1 ? 0.03 : Math.cos(Math.asin(ratio));

      for (const i of inc) {
        if (!isMappable(i)) continue;
        const lat = i.latitude!;
        const lng = i.longitude!;
        const la = lat * D, lo = lng * D;
        const vx = Math.cos(la) * Math.cos(lo);
        const vy = Math.cos(la) * Math.sin(lo);
        const vz = Math.sin(la);
        if (vx * ux + vy * uy + vz * uz < lim) continue;
        const p = pr([lng, lat]);
        if (!p) continue;
        const isSel = i.id === s.selectedId;
        const color = PRIORITY_COLOR[i.priority_label as Priority];
        const r = (PIN_SIZE[i.priority_label as Priority] + (isSel ? 2 : 0)) * s.dpr;
        ctx.save();
        if (isSel) {
          ctx.strokeStyle = color;
          ctx.lineWidth = 1.5 * s.dpr;
          ctx.globalAlpha = 0.5;
          ctx.beginPath();
          ctx.arc(p[0], p[1], r * 2.5, 0, Math.PI * 2);
          ctx.stroke();
        }
        ctx.globalAlpha = 1;
        ctx.beginPath();
        ctx.arc(p[0], p[1], r, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.fill();
        ctx.lineWidth = 1.5 * s.dpr;
        ctx.strokeStyle = BG;
        ctx.stroke();
        // label for selected
        if (isSel) {
          const txt = locationText(i).toUpperCase();
          ctx.font = `500 ${10 * s.dpr}px "IBM Plex Mono", ui-monospace, monospace`;
          try { (ctx as unknown as { letterSpacing: string }).letterSpacing = (1.2 * s.dpr) + "px"; } catch (_) {}
          const tx = p[0] + 20 * s.dpr, ty = p[1] - 18 * s.dpr;
          const w = ctx.measureText(txt).width;
          ctx.strokeStyle = color;
          ctx.globalAlpha = 0.7;
          ctx.lineWidth = s.dpr;
          ctx.beginPath();
          ctx.moveTo(p[0] + 10 * s.dpr, p[1] - 10 * s.dpr);
          ctx.lineTo(tx - 4 * s.dpr, ty - 2 * s.dpr);
          ctx.stroke();
          ctx.globalAlpha = 1;
          ctx.fillStyle = "rgba(5,7,11,0.88)";
          ctx.fillRect(tx - 4 * s.dpr, ty - 12 * s.dpr, w + 10 * s.dpr, 16 * s.dpr);
          ctx.fillStyle = "#E8EDF3";
          ctx.textBaseline = "alphabetic";
          ctx.fillText(txt, tx, ty);
        }
        ctx.restore();
      }
    }

    function drawTarget(ctx: CanvasRenderingContext2D, pr: d3.GeoProjection, now: number) {
      const t = s.target;
      if (!t) return;
      const vis = d3.geoDistance([t.longitude!, t.latitude!], [-s.rot[0], -s.rot[1]]) < Math.PI / 2 - 0.03;
      const p = vis ? pr([t.longitude!, t.latitude!]) : null;
      ctx.save();
      ctx.strokeStyle = ACCENT;
      ctx.fillStyle = ACCENT;
      if (s.phase === "spinning" && s.anim) {
        const e = ease(s.animU);
        crosshair(ctx, s.cx, s.cy, 0.1 + 0.14 * e, (40 + 40 * (1 - e)) * s.dpr);
        reticle(ctx, s.cx, s.cy, (18 + 96 * (1 - e)) * s.dpr, (1 - e) * Math.PI * 0.75, 0.35 + 0.65 * e);
      } else if (s.phase === "locked" && p) {
        const elapsed = now - s.lockAt;
        crosshair(ctx, p[0], p[1], 0.24, 40 * s.dpr);
        ctx.lineWidth = 1.5 * s.dpr;
        for (let j = 0; j < 2; j++) {
          const f = ((elapsed / 1800) + j * 0.5) % 1;
          ctx.globalAlpha = (1 - f) * 0.55;
          ctx.beginPath();
          ctx.arc(p[0], p[1], (6 + 42 * f) * s.dpr, 0, Math.PI * 2);
          ctx.stroke();
        }
        if (elapsed < 700) {
          const f = elapsed / 700;
          ctx.globalAlpha = (1 - f) * 0.9;
          ctx.lineWidth = 2 * s.dpr;
          ctx.beginPath();
          ctx.arc(p[0], p[1], (18 + 110 * eoc(f)) * s.dpr, 0, Math.PI * 2);
          ctx.stroke();
        }
        ctx.globalAlpha = 1;
        reticle(ctx, p[0], p[1], (18 + Math.sin(elapsed / 420) * 1.5) * s.dpr, 0, 1);
      }
      ctx.restore();
    }

    function draw(ctx: CanvasRenderingContext2D, now: number) {
      const { W, H, dpr, R, k, cx, cy } = s;
      const Rv = R * k;
      const TAU = Math.PI * 2;
      // Background outside globe
      ctx.save();
      ctx.beginPath();
      ctx.rect(0, 0, canvas.width, canvas.height);
      ctx.arc(cx, cy, Rv, 0, TAU);
      ctx.clip("evenodd");
      ctx.fillStyle = BG;
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      drawStars(ctx);
      // Subtle blue glow ring
      const glow = ctx.createRadialGradient(cx, cy, Rv * 0.98, cx, cy, Rv * 1.28);
      glow.addColorStop(0, "rgba(84,150,255,0.25)");
      glow.addColorStop(0.3, "rgba(84,150,255,0.07)");
      glow.addColorStop(1, "rgba(84,150,255,0)");
      ctx.fillStyle = glow;
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.restore();

      if (!s.lo) return;
      proj.translate([cx, cy]).scale(Rv).rotate(s.rot as [number, number, number]);
      const pg = path.context(ctx);
      const geo = s.hi && s.speed < 90 ? s.hi : s.lo;

      ctx.save();
      ctx.beginPath();
      ctx.arc(cx, cy, Rv, 0, TAU);
      ctx.clip();
      // Ocean gradient
      const oc = ctx.createRadialGradient(cx - Rv * 0.35, cy - Rv * 0.4, Rv * 0.05, cx, cy, Rv);
      oc.addColorStop(0, "#0f1e2f");
      oc.addColorStop(1, OCEAN);
      ctx.fillStyle = oc;
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.lineJoin = "round";
      // Graticule
      ctx.beginPath();
      (pg as unknown as (d: d3.GeoPermissibleObjects) => void)(grat as unknown as d3.GeoPermissibleObjects);
      ctx.strokeStyle = "rgba(140,172,205,0.08)";
      ctx.lineWidth = dpr;
      ctx.stroke();
      // Land
      ctx.beginPath();
      (pg as unknown as (d: d3.GeoPermissibleObjects) => void)(geo.land);
      ctx.fillStyle = LAND;
      ctx.fill();
      ctx.strokeStyle = "rgba(132,166,200,0.7)";
      ctx.lineWidth = 0.8 * dpr;
      ctx.stroke();
      // Borders
      ctx.beginPath();
      (pg as unknown as (d: d3.GeoPermissibleObjects) => void)(geo.borders);
      ctx.strokeStyle = "rgba(150,180,210,0.25)";
      ctx.lineWidth = 0.6 * dpr;
      ctx.stroke();
      // Incidents
      drawIncidents(ctx, proj, Rv);
      // Shadow vignette
      const sh = ctx.createRadialGradient(cx, cy, Rv * 0.55, cx, cy, Rv);
      sh.addColorStop(0, "rgba(3,6,12,0)");
      sh.addColorStop(1, "rgba(3,6,12,0.5)");
      ctx.fillStyle = sh;
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      // Highlight
      const hx = cx - Rv * 0.4, hy = cy - Rv * 0.45;
      const hl = ctx.createRadialGradient(hx, hy, 0, hx, hy, Rv * 0.9);
      hl.addColorStop(0, "rgba(150,190,255,0.08)");
      hl.addColorStop(1, "rgba(150,190,255,0)");
      ctx.fillStyle = hl;
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.restore();
      // Globe rim
      ctx.beginPath();
      ctx.arc(cx, cy, Rv, 0, TAU);
      ctx.strokeStyle = "rgba(150,195,255,0.28)";
      ctx.lineWidth = dpr;
      ctx.stroke();
      // Target reticle
      drawTarget(ctx, proj, now);
      void W; void H;
    }

    let rafId = 0;
    function tick(now: number) {
      rafId = requestAnimationFrame(tick);
      const s2 = state.current;
      const dt = s2.last ? Math.min(0.05, (now - s2.last) / 1000) : 0.016;
      s2.last = now;
      const l0 = s2.rot[0];
      const a = s2.anim;
      if (a) {
        const u = Math.min(1, (now - a.t0) / a.dur);
        s2.animU = u;
        s2.rot[0] = a.lam0 + a.dLam * ease(u);
        s2.rot[1] = a.phi0 + (a.phiT - a.phi0) * eio(u);
        // zoom
        if (!a.spin) {
          s2.k = a.k0 + (a.kT - a.k0) * eio(u);
        } else {
          const kMid = Math.min(a.k0, 1) * 0.9;
          if (u < 0.3) s2.k = a.k0 + (kMid - a.k0) * eoc(u / 0.3);
          else if (u < 0.5) s2.k = kMid;
          else s2.k = kMid + (a.kT - kMid) * eio((u - 0.5) / 0.5);
        }
        if (u >= 1) {
          s2.anim = null;
          s2.kGoal = s2.k;
          if (a.onDone) a.onDone();
        }
      } else {
        if (s2.phase === "idle" && !s2.drag && now > s2.idleHold) s2.rot[0] += 5 * dt;
        if (Math.abs(s2.kGoal - s2.k) > 1e-4) s2.k += (s2.kGoal - s2.k) * Math.min(1, dt * 9);
      }
      const inst = dt > 0 ? Math.abs(s2.rot[0] - l0) / dt : 0;
      s2.speed += (inst - s2.speed) * 0.3;
      const ctx = canvas.getContext("2d");
      if (ctx) draw(ctx, now);
    }
    rafId = requestAnimationFrame(tick);

    return () => {
      cancelAnimationFrame(rafId);
      ro.disconnect();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Sync incidents to render state
  useEffect(() => {
    state.current.incidents = mappable;
  }, [mappable]);

  // Fly to selected incident
  useEffect(() => {
    const s = state.current;
    s.selectedId = selectedId;
    if (!selected) {
      s.target = null;
      if (s.phase === "locked" || s.phase === "spinning") {
        s.phase = "idle";
        phase.current = "idle";
        s.anim = null;
        s.kGoal = 1;
      }
      return;
    }
    const lat = selected.latitude!;
    const lng = selected.longitude!;
    const lam0 = norm180(s.rot[0]);
    s.rot[0] = lam0;
    let d = (((-lng - lam0) % 360) + 360) % 360;
    if (d > 180) d -= 360;
    d += 360; // one extra revolution
    s.anim = {
      t0: performance.now(),
      dur: 4000,
      spin: true,
      lam0,
      dLam: d,
      phi0: s.rot[1],
      phiT: -lat,
      k0: s.k,
      kT: 3.5,
      onDone: () => {
        s.lockAt = performance.now();
        s.phase = "locked";
        phase.current = "locked";
        forceUpdate((n) => n + 1);
      },
    };
    s.target = selected;
    s.phase = "spinning";
    phase.current = "spinning";
    forceUpdate((n) => n + 1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  // Pointer events
  const onDown = (e: React.PointerEvent) => {
    const s = state.current;
    if (s.anim?.spin) return;
    if (s.anim) { s.anim = null; s.kGoal = s.k; }
    s.drag = { x: e.clientX, y: e.clientY, l: s.rot[0], p: s.rot[1] };
    try { (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId); } catch (_) {}
  };
  const onMove = (e: React.PointerEvent) => {
    const s = state.current;
    const d = s.drag;
    if (!d || !s.Rcss) return;
    const sc = (180 / Math.PI) / (s.Rcss * s.k);
    s.rot[0] = d.l + (e.clientX - d.x) * sc;
    s.rot[1] = Math.max(-90, Math.min(90, d.p - (e.clientY - d.y) * sc));
  };
  const onUp = () => {
    const s = state.current;
    s.drag = null;
    s.idleHold = performance.now() + 2500;
  };
  const onWheel = (e: React.WheelEvent) => {
    const s = state.current;
    if (s.anim?.spin) return;
    s.kGoal = Math.max(0.7, Math.min(8, s.kGoal * Math.exp(-e.deltaY * 0.0015)));
  };

  const ordered = [...mappable].sort((a, b) => PRIORITY_RANK[a.priority_label] - PRIORITY_RANK[b.priority_label]);

  return (
    <div
      ref={wrapEl}
      className={`relative overflow-hidden ${className ?? ""}`}
      style={{ background: BG }}
    >
      <canvas
        ref={canvasEl}
        className="h-full w-full cursor-grab touch-none select-none active:cursor-grabbing"
        aria-label="3D globe of active incidents"
        onPointerDown={onDown}
        onPointerMove={onMove}
        onPointerUp={onUp}
        onPointerCancel={onUp}
        onWheel={onWheel}
      />

      {/* Clickable incident hit areas (invisible, positioned at centre) */}
      {mappable.map((i) => {
        const isSel = i.id === selectedId;
        return (
          <button
            key={i.id}
            onPointerDown={(e) => e.stopPropagation()}
            onClick={() => onSelect(i.id)}
            aria-label={`${i.id} ${i.priority_label} ${locationText(i)}`}
            className={`absolute rounded-full opacity-0 pointer-events-auto ${isSel ? "z-30" : ""}`}
            style={{ width: 28, height: 28, left: "50%", top: "50%", transform: "translate(-50%,-50%)" }}
          />
        );
      })}

      {/* Controls */}
      <div className="absolute bottom-3 right-3 flex gap-1.5">
        <button
          onClick={() => { state.current.kGoal = Math.max(0.7, state.current.kGoal / 1.6); }}
          className="grid h-9 w-9 place-items-center rounded-xl border border-white/10 bg-[#05070B]/80 text-[#C9D3DE] backdrop-blur transition-colors hover:text-white hover:border-white/25"
          aria-label="Zoom out"
        >
          <Minus className="h-4 w-4" />
        </button>
        <button
          onClick={() => { state.current.kGoal = Math.min(8, state.current.kGoal * 1.6); }}
          className="grid h-9 w-9 place-items-center rounded-xl border border-white/10 bg-[#05070B]/80 text-[#C9D3DE] backdrop-blur transition-colors hover:text-white hover:border-white/25"
          aria-label="Zoom in"
        >
          <Plus className="h-4 w-4" />
        </button>
        <button
          onClick={() => {
            const top = ordered[ordered.length - 1];
            if (top) onSelect(top.id);
          }}
          className="grid h-9 w-9 place-items-center rounded-xl border border-white/10 bg-[#05070B]/80 text-[#C9D3DE] backdrop-blur transition-colors hover:text-white hover:border-white/25"
          aria-label="Fly to highest priority incident"
          title="Fly to highest priority incident"
        >
          <LocateFixed className="h-4 w-4" />
        </button>
      </div>

      {selected && onOpenMap && (
        <button
          onClick={onOpenMap}
          className="absolute bottom-3 left-3 inline-flex h-9 items-center gap-1.5 rounded-xl border border-white/10 bg-[#05070B]/80 px-3 text-xs font-medium text-[#C9D3DE] backdrop-blur transition-colors hover:text-white hover:border-white/25"
        >
          <MapIcon className="h-4 w-4" aria-hidden /> See on street map
        </button>
      )}
    </div>
  );
}
