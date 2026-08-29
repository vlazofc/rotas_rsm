import { useEffect, useMemo, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

interface MapStop {
  id: number;
  sequence?: number;
  customer_name: string;
  city?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  status: string;
}

interface MapRoute {
  id: number;
  codigo_ut: string;
  status: string;
  stops: MapStop[];
}

// Cor por status da PARADA (mesma paleta usada em Routes.tsx/RouteDetail.tsx),
// para o pino refletir o progresso real da entrega e não o status geral da rota.
const STOP_STATUS_COLOR: Record<string, string> = {
  pendente: "#64748b",
  em_rota: "#0ea5e9",
  entregue: "#16a34a",
  falha: "#ef4444",
  devolvido: "#f59e0b",
};

const DEFAULT_CENTER: [number, number] = [-23.5505, -46.6333]; // São Paulo
const BRAZIL_BOUNDS = L.latLngBounds(
  [-33.75, -73.99],
  [5.27, -28.84],
);
const WORLD_TILE_URL = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";
// Pontos de fallback (sem lat/lng real) — região operacional (Grande São Paulo).
const BRAZIL_POINTS: [number, number][] = [
  [-23.5505, -46.6333],  // São Paulo
  [-23.6639, -46.5383],  // Santo André (filial)
  [-23.4538, -46.5333],  // Guarulhos
  [-23.5106, -46.8761],  // Barueri
  [-23.0297, -46.9763],  // Vinhedo
  [-23.2136, -46.8133],  // Várzea Paulista
  [-22.9099, -47.0626],  // Campinas
  [-23.9608, -46.3331],  // Santos
];
const CITY_POINTS: Record<string, [number, number]> = {
  "sao paulo": [-23.5505, -46.6333],
  "são paulo": [-23.5505, -46.6333],
  "santo andre": [-23.6639, -46.5383],
  "santo andré": [-23.6639, -46.5383],
  guarulhos: [-23.4538, -46.5333],
  barueri: [-23.5106, -46.8761],
  vinhedo: [-23.0297, -46.9763],
  "varzea paulista": [-23.2136, -46.8133],
  "várzea paulista": [-23.2136, -46.8133],
  campinas: [-22.9099, -47.0626],
  santos: [-23.9608, -46.3331],
  osasco: [-23.5329, -46.7918],
  sorocaba: [-23.5015, -47.4526],
  "ribeirao preto": [-21.1775, -47.8103],
  "ribeirão preto": [-21.1775, -47.8103],
  "rio de janeiro": [-22.9068, -43.1729],
  "belo horizonte": [-19.9167, -43.9345],
  curitiba: [-25.4284, -49.2733],
  brasilia: [-15.7939, -47.8828],
  "brasília": [-15.7939, -47.8828],
};

export default function RouteMap({ routes, selectedRouteId, onSelectRoute }: {
  routes: MapRoute[];
  selectedRouteId: number | null;
  onSelectRoute: (id: number) => void;
}) {
  const elementRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const layerRef = useRef<L.LayerGroup | null>(null);

  const points = useMemo(() => {
    return routes.flatMap((route, routeIndex) => {
      const stops = route.stops.length ? route.stops : [{ id: route.id, customer_name: route.codigo_ut, status: route.status }];
      return stops.map((stop, stopIndex) => ({
        route,
        stop,
        label: String(stop.sequence ?? stopIndex + 1),
        position: pointPosition(stop, routeIndex, stopIndex),
        real: hasRealPosition(stop),
      }));
    });
  }, [routes]);

  useEffect(() => {
    if (!elementRef.current || mapRef.current) return;

    const map = L.map(elementRef.current, {
      zoomControl: true,
      attributionControl: false,
      minZoom: 2,
      maxZoom: 18,
    }).fitBounds(BRAZIL_BOUNDS);

    // Camada base mundial (OpenStreetMap)
    L.tileLayer(WORLD_TILE_URL, {
      maxZoom: 19,
    }).addTo(map);

    layerRef.current = L.layerGroup().addTo(map);
    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
      layerRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    const el = elementRef.current;
    if (!map || !el) return;

    const observer = new ResizeObserver(() => map.invalidateSize());
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    const layer = layerRef.current;
    if (!map || !layer) return;

    layer.clearLayers();
    const bounds = L.latLngBounds([]);
    const selectedBounds = L.latLngBounds([]);

    const orderedRoutes = [...routes].sort((a, b) => Number(a.id === selectedRouteId) - Number(b.id === selectedRouteId));
    orderedRoutes.forEach((route) => {
      const routePoints = points.filter((point) => point.route.id === route.id);
      const positions = routePoints.map((point) => point.position);
      const selected = route.id === selectedRouteId;
      if (positions.length >= 2) {
        const line = L.polyline(positions, {
          color: selected ? "#087f6d" : "#64748b",
          weight: selected ? 6 : 3,
          opacity: selectedRouteId === null || selected ? 0.9 : 0.18,
          dashArray: selected ? undefined : "7 8",
          lineCap: "round",
          lineJoin: "round",
        }).on("click", () => onSelectRoute(route.id)).addTo(layer);
        if (selected) line.bringToFront();
      }
      positions.forEach((position) => {
        bounds.extend(position);
        if (selected) selectedBounds.extend(position);
      });
    });

    const orderedPoints = [...points].sort((a, b) => Number(a.route.id === selectedRouteId) - Number(b.route.id === selectedRouteId));
    orderedPoints.forEach(({ route, stop, label, position }) => {
      const selected = route.id === selectedRouteId;
      const dimmed = selectedRouteId !== null && !selected;
      const marker = L.marker(position, {
        icon: markerIcon(STOP_STATUS_COLOR[stop.status] ?? "#12a386", label, selected, stop.status, dimmed),
        title: `${route.codigo_ut} - ${stop.customer_name}`,
        zIndexOffset: selected ? 1000 : dimmed ? -500 : 0,
      });
      marker.bindPopup(`<strong>${route.codigo_ut}</strong><br>${escapeHtml(stop.customer_name)}${stop.city ? `<br>${escapeHtml(stop.city)}` : ""}`);
      marker.on("click", () => onSelectRoute(route.id));
      marker.addTo(layer);
    });

    if (selectedBounds.isValid()) {
      map.fitBounds(selectedBounds.pad(0.35), { maxZoom: 11, animate: true });
    } else if (bounds.isValid() && points.some((point) => point.real)) {
      map.fitBounds(bounds.pad(0.35), { maxZoom: 10 });
    } else if (bounds.isValid() && routes.length > 0) {
      map.fitBounds(bounds.pad(0.35), { maxZoom: 11 });
    } else {
      map.fitBounds(BRAZIL_BOUNDS, { padding: [18, 18] });
    }
  }, [onSelectRoute, points, routes.length, selectedRouteId]);

  return <div ref={elementRef} className="route-map" />;
}

function pointPosition(stop: Partial<MapStop>, routeIndex: number, stopIndex: number): [number, number] {
  if (hasRealPosition(stop)) {
    return [stop.latitude, stop.longitude];
  }
  const city = normalizeCity(stop.city);
  if (city && CITY_POINTS[city]) return CITY_POINTS[city];
  return BRAZIL_POINTS[(routeIndex * 3 + stopIndex) % BRAZIL_POINTS.length];
}

function hasRealPosition(stop: Partial<MapStop>): stop is Partial<MapStop> & { latitude: number; longitude: number } {
  return typeof stop.latitude === "number" && typeof stop.longitude === "number";
}

function normalizeCity(value?: string | null) {
  return value?.trim().toLowerCase() ?? "";
}

function markerIcon(color: string, label: string, selected: boolean, status: string, dimmed = false) {
  return L.divIcon({
    className: "",
    html: `<div class="leaflet-route-pin status-${escapeHtml(status)}${selected ? " is-selected" : ""}" style="background:${color};${dimmed ? "opacity:0.45;filter:grayscale(40%);" : "filter:drop-shadow(0 0 4px rgba(0,0,0,.35));"}"><span>${escapeHtml(label)}</span></div>`,
    iconSize: [32, 38],
    iconAnchor: [16, 34],
    popupAnchor: [0, -30],
  });
}

function escapeHtml(value: string) {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
