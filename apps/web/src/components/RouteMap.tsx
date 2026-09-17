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
  vehicle_plate?: string | null;
}

interface MapRoute {
  origin_address?: string | null;
  origin_name?: string | null;
  id: number;
  codigo_ut: string;
  status: string;
  stops: MapStop[];
  routing_geometry_json?: string | null;
  suggested_geometry_json?: string | null;
}

// Cor por status da PARADA (mesma paleta usada em Routes.tsx/RouteDetail.tsx),
// para o pino refletir o progresso real da entrega e não o status geral da rota.
const STOP_STATUS_COLOR: Record<string, string> = {
  carregamento: "#f9a61a",
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
  "itapecerica da serra": [-23.7161, -46.8492],
  "santana de parnaiba": [-23.4448, -46.9178],
  "santana de parnaíba": [-23.4448, -46.9178],
  "sao bernardo do campo": [-23.6914, -46.5646],
  "são bernardo do campo": [-23.6914, -46.5646],
  "sao caetano do sul": [-23.6229, -46.5548],
  "são caetano do sul": [-23.6229, -46.5548],
};

export default function RouteMap({ routes, selectedRouteId, onSelectRoute, variant = "delivery" }: {
  routes: MapRoute[];
  selectedRouteId: number | null;
  onSelectRoute: (id: number) => void;
  variant?: "delivery" | "vehicle";
}) {
  const elementRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const layerRef = useRef<L.LayerGroup | null>(null);

  const points = useMemo(() => {
    return routes.flatMap((route, routeIndex) => {
      const stops: MapStop[] = [...route.stops];
      const originPosition = parseGeometry(route.routing_geometry_json || route.suggested_geometry_json)?.[0];
      if (route.origin_address && originPosition) {
        stops.unshift({ id: -route.id, sequence: 0, customer_name: `Carregamento no CD — ${route.origin_address}`, status: "carregamento", latitude: originPosition[0], longitude: originPosition[1] });
      }
      return [...stops].sort((a, b) => (a.sequence ?? 0) - (b.sequence ?? 0) || a.id - b.id).flatMap((stop, stopIndex) => {
        const position = pointPosition(stop, routeIndex, stopIndex);
        return position ? [{ route, stop, label: String(stop.sequence ?? stopIndex + 1), position, real: hasRealPosition(stop) }] : [];
      });
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

    const observer = new ResizeObserver(() => {
      map.invalidateSize();
      const selected = points.filter((point) => point.route.id === selectedRouteId).map((point) => point.position);
      focusMap(map, selected);
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, [points, selectedRouteId]);

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
      const roadPositions = parseGeometry(route.routing_geometry_json || route.suggested_geometry_json) ?? [];
      if (roadPositions.length >= 2) {
        const line = L.polyline(roadPositions, {
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
      roadPositions.forEach((position) => {
        bounds.extend(position);
        if (selected) selectedBounds.extend(position);
      });
    });

    const orderedPoints = [...points].sort((a, b) => Number(a.route.id === selectedRouteId) - Number(b.route.id === selectedRouteId));
    const labelsByPosition = new Map<string, string[]>();
    orderedPoints.forEach((point) => {
      const key = `${point.route.id}:${point.position[0].toFixed(6)}:${point.position[1].toFixed(6)}`;
      labelsByPosition.set(key, [...(labelsByPosition.get(key) ?? []), point.label]);
    });
    const indexByPosition = new Map<string, number>();
    orderedPoints.forEach(({ route, stop, label, position }) => {
      const positionKey = `${route.id}:${position[0].toFixed(6)}:${position[1].toFixed(6)}`;
      const duplicateIndex = indexByPosition.get(positionKey) ?? 0;
      indexByPosition.set(positionKey, duplicateIndex + 1);
      if (duplicateIndex > 0) return;
      const markerPosition = position;
      const selected = route.id === selectedRouteId;
      const dimmed = selectedRouteId !== null && !selected;
      let marker: L.Marker | L.CircleMarker;
      if (variant === "vehicle") {
        marker = L.marker(markerPosition, { icon: vehicleIcon(selected, dimmed) });
        marker.bindTooltip(escapeHtml(stop.vehicle_plate || "Sem placa"), {
          permanent: true, direction: "top", offset: [0, -30], className: "vehicle-plate-label",
        });
        marker.bindPopup(`<strong>${escapeHtml(route.codigo_ut)}</strong><br>${escapeHtml(stop.customer_name)}`);
      } else {
        marker = L.circleMarker(markerPosition, {
          radius: selected ? 14 : 11,
          color: "#fff",
          weight: selected ? 3 : 2,
          fillColor: STOP_STATUS_COLOR[stop.status] ?? "#12a386",
          fillOpacity: dimmed ? .45 : 1,
        });
        marker.bindTooltip((labelsByPosition.get(positionKey) ?? [label]).join(" / "), { permanent: true, direction: "center", className: "route-sequence-label" });
        marker.bindPopup(`<strong>${escapeHtml(route.codigo_ut)}${stop.sequence === 0 ? " · 0 — Partida / Carregamento no CD" : ""}</strong><br>${escapeHtml(stop.customer_name)}${stop.city ? `<br>${escapeHtml(stop.city)}` : ""}`);
      }
      marker.on("click", () => onSelectRoute(route.id));
      marker.addTo(layer);
    });

    if (selectedBounds.isValid()) {
      const stopPositions = points.filter((point) => point.route.id === selectedRouteId).map((point) => point.position);
      const selectedRoute = routes.find((route) => route.id === selectedRouteId);
      const selectedPositions = stopPositions.length ? stopPositions
        : parseGeometry(selectedRoute?.suggested_geometry_json || selectedRoute?.routing_geometry_json) ?? [];
      map.invalidateSize();
      focusMap(map, selectedPositions, true);
      window.setTimeout(() => { map.invalidateSize(); focusMap(map, selectedPositions); }, 180);
    } else if (selectedRouteId !== null) {
      // Não enquadra pontos de outras cargas quando a selecionada ainda não foi geocodificada.
      map.setView(DEFAULT_CENTER, 5, { animate: true });
    } else if (bounds.isValid() && points.some((point) => point.real)) {
      map.fitBounds(bounds.pad(0.35), { maxZoom: 10 });
    } else if (bounds.isValid() && routes.length > 0) {
      map.fitBounds(bounds.pad(0.35), { maxZoom: 11 });
    } else {
      map.fitBounds(BRAZIL_BOUNDS, { padding: [18, 18] });
    }
  }, [onSelectRoute, points, routes, selectedRouteId]);

  return <div ref={elementRef} className="route-map" />;
}

function parseGeometry(value?: string | null): [number, number][] | null {
  if (!value) return null;
  try {
    const coordinates = JSON.parse(value);
    if (!Array.isArray(coordinates)) return null;
    const points = coordinates.flatMap((point: unknown) => {
      if (!Array.isArray(point) || point.length < 2 || typeof point[0] !== "number" || typeof point[1] !== "number") return [];
      return [[point[1], point[0]] as [number, number]];
    });
    return points.length >= 2 ? points : null;
  } catch { return null; }
}

function pointPosition(stop: Partial<MapStop>, _routeIndex: number, stopIndex: number): [number, number] | null {
  if (hasRealPosition(stop)) {
    const expectedCity = CITY_POINTS[normalizeCity(stop.city)];
    // Descarta resultados claramente incompatíveis com a cidade informada.
    // O Photon pode encontrar uma rua homônima em outro município.
    if (!expectedCity || distanceKm([stop.latitude, stop.longitude], expectedCity) <= 60) {
      return [stop.latitude, stop.longitude];
    }
  }
  return null;
}

function distanceKm(a: [number, number], b: [number, number]) {
  const rad = Math.PI / 180;
  const dLat = (b[0] - a[0]) * rad;
  const dLng = (b[1] - a[1]) * rad;
  const value = Math.sin(dLat / 2) ** 2 + Math.cos(a[0] * rad) * Math.cos(b[0] * rad) * Math.sin(dLng / 2) ** 2;
  return 6371 * 2 * Math.atan2(Math.sqrt(value), Math.sqrt(1 - value));
}

function focusMap(map: L.Map, positions: [number, number][], animate = false) {
  if (!positions.length) return;
  const bounds = L.latLngBounds(positions);
  if (positions.length === 1 || (bounds.getNorthEast().equals(bounds.getSouthWest()))) {
    map.setView(positions[0], 13, { animate });
  } else {
    map.fitBounds(bounds.pad(0.28), { maxZoom: 13, animate, padding: [36, 36] });
  }
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

function vehicleIcon(selected: boolean, dimmed: boolean) {
  return L.divIcon({
    className: "",
    html: `<div class="leaflet-vehicle-pin${selected ? " is-selected" : ""}" style="${dimmed ? "opacity:0.45;filter:grayscale(40%);" : ""}">🚚</div>`,
    iconSize: [34, 34],
    iconAnchor: [17, 17],
    popupAnchor: [0, -20],
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
