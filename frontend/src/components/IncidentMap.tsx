import L from "leaflet";
import "leaflet.markercluster";
import "leaflet/dist/leaflet.css";
import "leaflet.markercluster/dist/MarkerCluster.css";
import { useEffect, useRef, useState } from "react";
import { PRIORITY_COLOR, PRIORITY_RANK, isMappable, label, locationText, peopleText } from "../lib/format";
import type { Incident, Place, Priority } from "../lib/types";

// Online tiles are the default. Set VITE_OFFLINE_ONLY=true to disable external requests.
// A local tile pack at backend/var/tiles (manifest.json) is preferred when present.
const LOCAL_TILES = "/tiles/{z}/{x}/{y}.png";
const OSM_URL = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";
const ALLOW_ONLINE = import.meta.env.VITE_OFFLINE_ONLY !== "true";

export function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);
}

type PMarker = L.Marker & { options: L.MarkerOptions & { priority?: Priority } };

function markerIcon(i: Incident, selected: boolean): L.DivIcon {
  const verified = i.location_status === "human_verified";
  const size = selected ? 30 : 24;
  return L.divIcon({
    className: "",
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    html: `<div class="aa-marker${verified ? " aa-verified" : " aa-unverified"}${selected ? " aa-selected" : ""}${i.priority_label === "critical" ? " aa-critical" : ""}"
      style="--c:${PRIORITY_COLOR[i.priority_label]};width:${size}px;height:${size}px">
      <span>${i.report_count}</span></div>`,
  });
}

function tooltipHtml(i: Incident): string {
  return `<div class="aa-tt"><b>${escapeHtml(i.id)}</b> · <span style="color:${PRIORITY_COLOR[i.priority_label]}">${i.priority_label.toUpperCase()}</span><br/>
    ${escapeHtml(locationText(i))}<br/>People: ${escapeHtml(peopleText(i))} · Reports: ${i.report_count}<br/>
    <i>${i.location_status === "human_verified" ? "Verified location" : "Reference location (unverified)"}</i></div>`;
}

export function IncidentMap({
  incidents,
  places,
  selectedId,
  onSelect,
  className,
  compactLegend,
}: {
  incidents: Incident[];
  places: Place[];
  selectedId?: string | null;
  onSelect?: (id: string) => void;
  className?: string;
  compactLegend?: boolean;
}) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const cluster = useRef<L.MarkerClusterGroup | null>(null);
  const placeLayer = useRef<L.LayerGroup | null>(null);
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;
  const fitted = useRef(false);
  const [basemap, setBasemap] = useState<"offline" | "local" | "online">("offline");

  useEffect(() => {
    if (!el.current || map.current) return;
    const m = L.map(el.current, { minZoom: 5, maxZoom: 18, zoomControl: true, attributionControl: true, scrollWheelZoom: false }).setView([18.61, 73.54], 11);
    // Wheel-zoom only after the user clicks the map, so scrolling the page never gets trapped.
    m.on("click focus", () => m.scrollWheelZoom.enable());
    m.on("mouseout blur", () => m.scrollWheelZoom.disable());
    let cancelled = false;
    const addTiles = (url: string, mode: "local" | "online", attribution: string) => {
      if (cancelled) return;
      L.tileLayer(url, { maxZoom: 18, attribution }).addTo(m);
      setBasemap(mode);
    };
    fetch("/tiles/manifest.json", { cache: "no-store" })
      .then((r) => {
        if (r.ok) addTiles(LOCAL_TILES, "local", "Offline tile pack");
        else if (ALLOW_ONLINE) addTiles(OSM_URL, "online", '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors');
      })
      .catch(() => {
        if (ALLOW_ONLINE && navigator.onLine) addTiles(OSM_URL, "online", '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors');
      });

    placeLayer.current = L.layerGroup().addTo(m);
    cluster.current = L.markerClusterGroup({
      showCoverageOnHover: false,
      spiderfyOnMaxZoom: true,
      maxClusterRadius: 36,
      iconCreateFunction: (c) => {
        const children = c.getAllChildMarkers() as PMarker[];
        const top = children.reduce<Priority>((acc, mk) => {
          const p = mk.options.priority ?? "low";
          return PRIORITY_RANK[p] > PRIORITY_RANK[acc] ? p : acc;
        }, "low");
        return L.divIcon({
          className: "",
          iconSize: [34, 34],
          html: `<div class="aa-cluster" style="--c:${PRIORITY_COLOR[top]}"><span>${children.length}</span></div>`,
        });
      },
    });
    m.addLayer(cluster.current);
    map.current = m;
    return () => {
      cancelled = true;
      m.remove();
      map.current = null;
    };
  }, []);

  // Simulated reference villages: faint labelled points so the map is readable offline too.
  useEffect(() => {
    const layer = placeLayer.current;
    const m = map.current;
    if (!layer || !m) return;
    layer.clearLayers();
    for (const p of places) {
      L.circleMarker([p.latitude, p.longitude], { radius: 3, color: "#737373", weight: 1, fillOpacity: 0.4, interactive: false })
        .bindTooltip(escapeHtml(p.name), { permanent: true, direction: "right", className: "aa-place-label", offset: [4, 0] })
        .addTo(layer);
    }
    if (places.length && !fitted.current) {
      m.fitBounds(L.latLngBounds(places.map((p) => [p.latitude, p.longitude] as [number, number])).pad(0.25));
      fitted.current = true;
    }
  }, [places]);

  useEffect(() => {
    const c = cluster.current;
    if (!c) return;
    c.clearLayers();
    const markers = incidents.filter(isMappable).map((i) => {
      const mk = L.marker([i.latitude!, i.longitude!], {
        icon: markerIcon(i, i.id === selectedId),
        keyboard: true,
        title: `${i.id} ${i.priority_label} ${label(i.location_status)}`,
        zIndexOffset: PRIORITY_RANK[i.priority_label] * 100 + (i.id === selectedId ? 1000 : 0),
      }) as PMarker;
      mk.options.priority = i.priority_label;
      mk.bindTooltip(tooltipHtml(i), { direction: "top", offset: [0, -10] });
      mk.on("click", () => onSelectRef.current?.(i.id));
      return mk;
    });
    c.addLayers(markers);
  }, [incidents, selectedId]);

  return (
    <div className={`glass relative overflow-hidden rounded-2xl ${className ?? ""}`}>
      <div ref={el} className="offline-basemap h-full w-full" aria-label="Incident map" />
      <div className="pointer-events-none absolute right-3 top-3 z-[500] rounded-full border border-white/10 bg-bg/70 px-2.5 py-1 text-2xs text-ink-3 backdrop-blur">
        {basemap === "offline" ? "Offline basemap · works with no network" : basemap === "local" ? "Local tile pack" : "Online tiles"}
      </div>
      {compactLegend ? (
        <div className="absolute bottom-2 left-2 z-[500] rounded-lg border border-white/10 bg-bg/80 px-2 py-1 backdrop-blur text-2xs text-ink-2">
          Dashed ring = reference location (unverified) · solid green = verified
        </div>
      ) : (
      <div className="absolute bottom-2 left-2 z-[500] rounded-xl border border-white/10 bg-bg/80 px-3 py-2.5 backdrop-blur text-2xs text-ink-2">
        <div className="mb-1 font-semibold text-ink">Priority</div>
        <div className="flex flex-wrap gap-x-3 gap-y-1">
          {(["critical", "high", "medium", "low"] as Priority[]).map((p) => (
            <span key={p} className="inline-flex items-center gap-1">
              <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: PRIORITY_COLOR[p] }} />
              {p}
            </span>
          ))}
        </div>
        <div className="mt-1.5 flex gap-3">
          <span className="inline-flex items-center gap-1">
            <span className="inline-block h-3 w-3 rounded-full border-2 border-dashed border-ink-2" /> reference · unverified
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="inline-block h-3 w-3 rounded-full border-2 border-[#9fe0a8]" /> verified
          </span>
        </div>
        <div className="mt-1 text-ink-3">Filled marker: number = linked reports. Dark ring: incidents grouped at one point (click to expand).</div>
        <div className="text-ink-3">Click the map to enable wheel zoom.</div>
      </div>
      )}
    </div>
  );
}
