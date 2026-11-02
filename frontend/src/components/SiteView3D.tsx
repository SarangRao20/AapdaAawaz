import { AlertTriangle, Crosshair, Pause, Play, Satellite } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { PRIORITY_COLOR, isMappable, label, locationText, peopleText } from "../lib/format";
import type { Incident } from "../lib/types";

// Optional. With a key this uses Google's photorealistic 3D tiles; without one, or if Google fails to
// load, it uses free satellite imagery with terrain. The key reaches the browser, so restrict it by
// HTTP referrer in the Google Cloud console.
const GOOGLE_KEY = (import.meta.env.VITE_GOOGLE_MAPS_API_KEY as string | undefined)?.trim() || "";

type Engine = "google" | "open";
type Camera = { zoom: number; range: number; radiusM: number };

/** A caller's GPS supports a close-up; a simulated village point must not look like an exact spot. */
function cameraFor(i: Incident): Camera {
  if (i.location_status === "caller_gps") {
    return { zoom: 17.2, range: 550, radiusM: Math.max(i.location?.gps_accuracy_m ?? 30, 15) };
  }
  if (i.location_status === "human_verified") return { zoom: 16.5, range: 800, radiusM: 60 };
  return { zoom: 14.2, range: 3500, radiusM: 500 };
}

function sourceText(i: Incident): string {
  if (i.location_status === "caller_gps") {
    const accuracy = i.location?.gps_accuracy_m;
    return `GPS shared by the caller${accuracy ? ` (±${Math.round(accuracy)} m)` : ""}; confirm it is the incident site`;
  }
  if (i.location_status === "human_verified") return "Location verified by a dispatcher";
  return "Simulated village reference point, not the exact site";
}

function circle(lat: number, lon: number, radiusM: number): GeoJSON.Feature<GeoJSON.Polygon> {
  const dLat = radiusM / 111_320;
  const dLon = radiusM / (111_320 * Math.cos((lat * Math.PI) / 180));
  const ring = Array.from({ length: 65 }, (_, k) => {
    const a = (k / 64) * 2 * Math.PI;
    return [lon + dLon * Math.cos(a), lat + dLat * Math.sin(a)];
  });
  return { type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [ring] } };
}

function alertMarker(color: string): HTMLDivElement {
  const el = document.createElement("div");
  el.className = "site3d-marker";
  el.setAttribute("aria-hidden", "true");
  el.style.setProperty("--alert", color);
  el.innerHTML = `<span class="site3d-ring"></span><span class="site3d-ring site3d-ring-2"></span>
    <svg viewBox="0 0 48 44" width="44" height="40"><path d="M24 3 45 40H3Z" fill="${color}33" stroke="${color}"
    stroke-width="3" stroke-linejoin="round"/><path d="M24 15v13M24 33v2" stroke="#fff" stroke-width="4"
    stroke-linecap="round"/></svg>`;
  return el;
}

const STYLE = `
.site3d-marker{position:relative;display:grid;place-items:center;width:44px;height:40px;filter:drop-shadow(0 0 10px var(--alert))}
.site3d-ring{position:absolute;left:50%;top:50%;width:26px;height:26px;margin:-13px;border:2px solid var(--alert);border-radius:50%;animation:site3d-pulse 2.2s ease-out infinite}
.site3d-ring-2{animation-delay:1.1s}
@keyframes site3d-pulse{from{transform:scale(.6);opacity:.9}to{transform:scale(4);opacity:0}}
@media (prefers-reduced-motion:reduce){.site3d-ring{animation:none;opacity:.5}}
.site3d-canvas .maplibregl-canvas{filter:saturate(.72) brightness(.82) contrast(1.06)}
.site3d-canvas .maplibregl-ctrl-attrib{background:rgba(9,13,17,.72)!important;color:#8b949e;font-size:10px;max-width:58%}
.site3d-canvas .maplibregl-ctrl-attrib a{color:#8b949e}
.site3d-canvas .maplibregl-ctrl-attrib-button{filter:invert(1);background-color:transparent!important}
`;

let googleLoader: Promise<any> | null = null; // eslint-disable-line @typescript-eslint/no-explicit-any

function loadGoogle3D(): Promise<any> { // eslint-disable-line @typescript-eslint/no-explicit-any
  googleLoader ??= new Promise((resolve, reject) => {
    const w = window as any; // eslint-disable-line @typescript-eslint/no-explicit-any
    w.__aapdaGoogleReady = () => w.google.maps.importLibrary("maps3d").then(resolve, reject);
    const script = document.createElement("script");
    script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(GOOGLE_KEY)}&v=beta&loading=async&callback=__aapdaGoogleReady`;
    script.async = true;
    script.onerror = () => reject(new Error("Google Maps script failed to load"));
    document.head.appendChild(script);
  });
  return googleLoader;
}

export default function SiteView3D({ incident, className, compact = false }: { incident: Incident | null; className?: string; compact?: boolean }) {
  const host = useRef<HTMLDivElement>(null);
  const handle = useRef<{ flyTo: (i: Incident) => void; setOrbit: (on: boolean) => void; destroy: () => void } | null>(null);
  const [engine, setEngine] = useState<Engine>(GOOGLE_KEY ? "google" : "open");
  const [problem, setProblem] = useState<string | null>(null);
  const [orbit, setOrbit] = useState(() => !window.matchMedia?.("(prefers-reduced-motion: reduce)").matches);
  const [ready, setReady] = useState(false);
  const mappable = incident && isMappable(incident) ? incident : null;
  const latest = useRef(mappable);
  latest.current = mappable;
  const orbitRef = useRef(orbit);
  orbitRef.current = orbit;
  const hasTarget = mappable !== null;

  useEffect(() => {
    if (!hasTarget || !host.current) return;
    let cancelled = false;
    const el = host.current;
    setReady(false);
    const fallback = (why: string) => {
      if (cancelled) return;
      console.warn(`3D view: ${why}; using free satellite imagery`);
      setEngine("open");
    };

    if (engine === "google") {
      const w = window as any; // eslint-disable-line @typescript-eslint/no-explicit-any
      w.gm_authFailure = () => fallback("Google rejected the API key");
      // A bad key neither calls gm_authFailure nor stops this element from reporting itself as settled.
      // Google's console error is the only signal, so watch for it while this view is showing.
      const consoleError = console.error;
      console.error = (...args: unknown[]) => {
        consoleError(...args);
        const message = String(args[0]);
        if (message.startsWith("Google Maps JavaScript API error")) fallback(message.split("\n")[0]);
      };
      loadGoogle3D().then(({ Map3DElement, Marker3DElement }) => {
        const first = latest.current;
        if (cancelled || !first) return;
        const cam = (i: Incident) => ({
          center: { lat: i.latitude as number, lng: i.longitude as number, altitude: 0 },
          range: cameraFor(i).range, tilt: 68, heading: 20,
        });
        const map = new Map3DElement({ ...cam(first), mode: "HYBRID" });
        const marker = new Marker3DElement({ position: { lat: first.latitude, lng: first.longitude } });
        map.append(marker);
        el.replaceChildren(map);
        const spin = () => {
          if (orbitRef.current && latest.current) {
            map.flyCameraAround?.({ camera: cam(latest.current), durationMillis: 60000, repeatCount: 100 });
          }
        };
        // A view that hasn't settled in time, or reports an error, falls back instead of staying blank.
        let settled = false;
        const watchdog = window.setTimeout(() => { if (!settled) fallback("Google 3D did not render in time"); }, 15000);
        map.addEventListener("gmp-error", () => fallback("Google 3D reported an error"));
        map.addEventListener("gmp-steadychange", (e: { isSteady?: boolean }) => {
          if (e.isSteady && !settled) {
            settled = true;
            window.clearTimeout(watchdog);
            spin(); // only now: orbiting straight away would stop the view from ever settling
          }
        });
        handle.current = {
          flyTo: (i) => {
            marker.position = { lat: i.latitude, lng: i.longitude };
            map.flyCameraTo?.({ endCamera: cam(i), durationMillis: 3000 });
          },
          setOrbit: (on) => { if (on) spin(); else map.stopCameraAnimation?.(); },
          destroy: () => { window.clearTimeout(watchdog); map.stopCameraAnimation?.(); el.replaceChildren(); },
        };
        setReady(true);
      }).catch((e: unknown) => fallback(e instanceof Error ? e.message : "Google failed to load"));
      return () => { cancelled = true; console.error = consoleError; handle.current?.destroy(); handle.current = null; };
    }

    (async () => {
      const [{ default: maplibre }] = await Promise.all([import("maplibre-gl"), import("maplibre-gl/dist/maplibre-gl.css")]);
      const first = latest.current;
      if (cancelled || !first) return;
      const map = new maplibre.Map({
        container: el,
        center: [first.longitude as number, first.latitude as number],
        zoom: 9.5,
        attributionControl: { compact: true },
        maxPitch: 75,
        style: {
          version: 8,
          sources: {
            imagery: {
              type: "raster", tileSize: 256, maxzoom: 19,
              tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"],
              attribution: "Imagery © Esri, Maxar, Earthstar Geographics",
            },
            elevation: {
              type: "raster-dem", tileSize: 256, maxzoom: 14, encoding: "terrarium",
              tiles: ["https://elevation-tiles-prod.s3.amazonaws.com/terrarium/{z}/{x}/{y}.png"],
              attribution: "Elevation © Mapzen, AWS Open Data",
            },
          },
          layers: [{ id: "imagery", type: "raster", source: "imagery" }],
        },
      });
      const marker = new maplibre.Marker({ element: alertMarker(PRIORITY_COLOR[first.priority_label]) })
        .setLngLat([first.longitude as number, first.latitude as number]).addTo(map);
      let frame = 0;
      let interacting = false;
      const area = (i: Incident) => circle(i.latitude as number, i.longitude as number, cameraFor(i).radiusM);
      const fly = (i: Incident) => {
        map.flyTo({ center: [i.longitude as number, i.latitude as number], zoom: cameraFor(i).zoom, pitch: 68,
                    bearing: -25, duration: orbitRef.current ? 3800 : 0, essential: false });
      };
      const turn = () => {
        if (orbitRef.current && !interacting && !map.isMoving()) map.setBearing(map.getBearing() + 0.035);
        frame = requestAnimationFrame(turn);
      };
      map.on("dragstart", () => { interacting = true; });
      map.on("dragend", () => { interacting = false; });
      map.on("error", (e) => {
        // Missing tiles at the edges are normal; only report a problem when imagery itself is unreachable.
        const source = (e as unknown as { sourceId?: string }).sourceId;
        if (source === "imagery") setProblem("Satellite imagery could not load. The position is still correct.");
        else if (!source) console.warn("3D view:", e.error?.message);
      });
      // "style.load" fires as soon as sources can be added; "load" would hold the camera until every
      // tile of the distant starting view had arrived.
      map.once("style.load", () => {
        map.addSource("alert-area", { type: "geojson", data: area(first) });
        map.addLayer({ id: "alert-fill", type: "fill", source: "alert-area",
                       paint: { "fill-color": PRIORITY_COLOR[first.priority_label], "fill-opacity": 0.28 } });
        map.addLayer({ id: "alert-line", type: "line", source: "alert-area",
                       paint: { "line-color": PRIORITY_COLOR[first.priority_label], "line-width": 2 } });
        map.setTerrain({ source: "elevation", exaggeration: 1.4 });
        setReady(true);
        fly(first);
        turn();
      });
      handle.current = {
        flyTo: (i) => {
          marker.setLngLat([i.longitude as number, i.latitude as number]);
          marker.getElement().style.setProperty("--alert", PRIORITY_COLOR[i.priority_label]);
          const color = PRIORITY_COLOR[i.priority_label];
          if (map.getLayer("alert-fill")) {
            (map.getSource("alert-area") as import("maplibre-gl").GeoJSONSource).setData(area(i));
            map.setPaintProperty("alert-fill", "fill-color", color);
            map.setPaintProperty("alert-line", "line-color", color);
          }
          fly(i);
        },
        setOrbit: () => undefined, // read from orbitRef on every frame
        destroy: () => { cancelAnimationFrame(frame); map.remove(); },
      };
    })().catch((e: unknown) => {
      if (!cancelled) setProblem(e instanceof Error ? `3D view unavailable: ${e.message}` : "3D view unavailable on this device.");
    });
    return () => { cancelled = true; handle.current?.destroy(); handle.current = null; };
  }, [engine, hasTarget]);

  // Polling re-renders with new objects, so only fly when the target really changes.
  const targetKey = mappable ? `${mappable.id}:${mappable.latitude}:${mappable.longitude}` : "";
  const flownKey = useRef("");
  useEffect(() => {
    if (!ready || !latest.current) return;
    if (flownKey.current && flownKey.current !== targetKey) handle.current?.flyTo(latest.current);
    flownKey.current = targetKey;
  }, [ready, targetKey]);

  useEffect(() => { handle.current?.setOrbit(orbit); }, [orbit]);
  const recenter = useCallback(() => { if (latest.current) handle.current?.flyTo(latest.current); }, []);

  if (!mappable) {
    return (
      <div className={`grid place-items-center bg-[#07090c] p-6 text-center text-sm text-ink-3 ${className ?? ""}`}>
        <div>
          <Satellite className="mx-auto mb-2 h-6 w-6" aria-hidden />
          {incident ? "This incident has no confirmed position yet, so there is nothing to show in 3D." : "Select an incident with a known position."}
        </div>
      </div>
    );
  }
  const color = PRIORITY_COLOR[mappable.priority_label];
  return (
    <div className={`relative overflow-hidden bg-[#07090c] ${className ?? ""}`} data-testid="site-view-3d" data-engine={engine}>
      <style>{STYLE}</style>
      {/* Inline: MapLibre's CSS sets position: relative on this element, which would collapse it. */}
      <div ref={host} className="site3d-canvas" style={{ position: "absolute", inset: 0 }} />
      <div className="pointer-events-none absolute inset-0 shadow-[inset_0_0_120px_40px_rgba(4,7,10,0.85)]" />

      {compact ? (
        <p className="absolute left-3 right-14 top-3 z-10 rounded-lg border border-white/10 bg-[#090d11]/85 px-2.5 py-1.5 text-2xs text-ink-2 backdrop-blur">{sourceText(mappable)}</p>
      ) : (
      <section className="absolute bottom-3 left-3 z-10 w-[min(300px,calc(100%-24px))] rounded-xl border border-white/10 bg-[#090d11]/85 p-3 text-xs text-ink-2 backdrop-blur">
        <div className="flex items-center justify-between gap-2">
          <span className="flex items-center gap-1.5 font-medium text-ink"><AlertTriangle className="h-3.5 w-3.5" style={{ color }} aria-hidden /> {mappable.id}</span>
          <span className="rounded-md border px-1.5 py-0.5 text-2xs font-medium" style={{ color, borderColor: `${color}66` }}>{label(mappable.priority_label)}</span>
        </div>
        <dl className="mt-2 grid grid-cols-[64px_1fr] gap-x-2 gap-y-1">
          <dt className="text-ink-3">Where</dt><dd className="text-ink">{locationText(mappable)}</dd>
          <dt className="text-ink-3">What</dt><dd>{label(mappable.disaster_type ?? "unknown")}</dd>
          <dt className="text-ink-3">People</dt><dd>{peopleText(mappable)}</dd>
          <dt className="text-ink-3">Position</dt><dd className="font-mono">{mappable.latitude?.toFixed(5)}, {mappable.longitude?.toFixed(5)}</dd>
        </dl>
        <p className="mt-2 border-t border-white/10 pt-2 text-2xs text-ink-3">{sourceText(mappable)}</p>
      </section>
      )}

      <div className={`absolute right-3 z-10 flex flex-col gap-1.5 ${compact ? "top-3" : "top-14"}`}>
        <button type="button" onClick={() => setOrbit((v) => !v)} aria-label={orbit ? "Stop rotating" : "Rotate view"} title={orbit ? "Stop rotating" : "Rotate view"}
          className="grid h-8 w-8 place-items-center rounded-lg border border-white/10 bg-[#090d11]/85 text-ink-2 hover:text-ink">
          {orbit ? <Pause className="h-3.5 w-3.5" aria-hidden /> : <Play className="h-3.5 w-3.5" aria-hidden />}
        </button>
        <button type="button" onClick={recenter} aria-label="Return to the incident" title="Return to the incident"
          className="grid h-8 w-8 place-items-center rounded-lg border border-white/10 bg-[#090d11]/85 text-ink-2 hover:text-ink">
          <Crosshair className="h-3.5 w-3.5" aria-hidden />
        </button>
      </div>
      {problem && (
        <div role="status" className="absolute left-1/2 top-3 z-10 -translate-x-1/2 rounded-lg border border-[#5b4413] bg-[#090d11]/90 px-3 py-1.5 text-xs text-[#f6c75a]">{problem}</div>
      )}
    </div>
  );
}
