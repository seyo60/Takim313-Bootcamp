/**
 * Local mock for the backend `POST /api/v1/route` endpoint (see end-to-end.md,
 * item 2 / §A). Shapes exactly match src/lib/types.ts, so swapping to the real
 * backend only means flipping USE_MOCK_ROUTE in src/lib/api.ts — the UI never
 * changes.
 *
 * The line is a plausible walking path through Chicago downtown (roughly
 * Willis Tower → Millennium Park). It does NOT follow real streets; the real
 * street-following geometry comes from the backend's Dijkstra over the actual
 * street graph.
 *
 * Mapbox/GeoJSON coordinate order is [longitude, latitude].
 */

import type { LngLat, RouteResponse } from "./types";

/** Which of the two routes the user is currently looking at. */
export type RouteKind = "safe" | "shortest";

/**
 * A single route flattened for the UI: geometry + the stats needed by the
 * detail panel, plus a stable label/kind for the selection toggle. Both the
 * safe and shortest routes become one of these, so the map and panel iterate a
 * uniform list instead of special-casing each route (item 1, AC #3/#4).
 */
export interface RouteOption {
  kind: RouteKind;
  label: string;
  geometry: GeoJSON.LineString;
  distance_m: number;
  duration_s: number;
  /**
   * 0-100 risk, or null when unknown — the backend reports risk only for the
   * safe route; the shortest route's risk is not computed server-side.
   */
  risk_score: number | null;
}

/** Ordered points that make up the mock route line. */
export const MOCK_ROUTE_COORDINATES: LngLat[] = [
  [-87.6359, 41.8781], // near Willis Tower
  [-87.6359, 41.8806],
  [-87.632, 41.8806],
  [-87.632, 41.8827],
  [-87.6262, 41.8827],
  [-87.6226, 41.8827], // near Millennium Park
];

/** Default demo origin/destination inside the Chicago pilot area. */
export const MOCK_START: LngLat = MOCK_ROUTE_COORDINATES[0];
export const MOCK_END: LngLat =
  MOCK_ROUTE_COORDINATES[MOCK_ROUTE_COORDINATES.length - 1];

/**
 * The plain shortest route between the same endpoints — a more direct diagonal
 * that ignores risk. Drawn dashed gray for the "shortest vs safest" comparison
 * (item 8).
 */
export const MOCK_SHORTEST_COORDINATES: LngLat[] = [
  MOCK_ROUTE_COORDINATES[0],
  [-87.632, 41.8797],
  [-87.627, 41.8812],
  MOCK_ROUTE_COORDINATES[MOCK_ROUTE_COORDINATES.length - 1],
];

/**
 * Builds a fake RouteResponse the way the backend would.
 *
 * Note: the geometry is always the fixed Chicago line regardless of the
 * requested start/end — good enough to exercise the full fetch→draw flow.
 * TODO(osman): remove this file's usage once Seymen's POST /api/v1/route is
 * live (flip USE_MOCK_ROUTE in api.ts).
 */
export function buildMockRouteResponse(
  _start: LngLat,
  _end: LngLat
): RouteResponse {
  return {
    route: {
      type: "LineString",
      coordinates: MOCK_ROUTE_COORDINATES,
    },
    distance_m: 1350,
    duration_s: 1020, // ~17 min walk
    risk_score: 24, // fairly safe demo value
    // The direct-but-riskier alternative, for the comparison + toggle (item 1).
    // Matches the CONFIRMED backend shape: a bare LineString, no per-route
    // stats — the UI derives distance/duration from the geometry.
    shortest: {
      type: "LineString",
      coordinates: MOCK_SHORTEST_COORDINATES,
    },
  };
}

/** Average walking speed used by the backend for duration (m/s). */
const WALKING_SPEED_MPS = 1.2;

/** Haversine length of a coordinate path, in meters. */
function pathLengthMeters(coordinates: LngLat[]): number {
  const R = 6_371_000;
  let total = 0;
  for (let i = 1; i < coordinates.length; i++) {
    const [lng1, lat1] = coordinates[i - 1];
    const [lng2, lat2] = coordinates[i];
    const phi1 = (lat1 * Math.PI) / 180;
    const phi2 = (lat2 * Math.PI) / 180;
    const dPhi = ((lat2 - lat1) * Math.PI) / 180;
    const dLambda = ((lng2 - lng1) * Math.PI) / 180;
    const a =
      Math.sin(dPhi / 2) ** 2 +
      Math.cos(phi1) * Math.cos(phi2) * Math.sin(dLambda / 2) ** 2;
    total += R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  }
  return total;
}

/**
 * Flattens a RouteResponse into the list of routes the UI renders and toggles
 * between: always the safe route, plus the shortest one when present. Keeping
 * this in one place means the map layers, the camera fit and the detail panel
 * all read from the same normalized shape (item 1, AC #4) — swapping the mock
 * for the real backend never touches those components.
 */
export function getRouteOptions(response: RouteResponse): RouteOption[] {
  const options: RouteOption[] = [
    {
      kind: "safe",
      label: "Güvenli",
      geometry: response.route,
      distance_m: response.distance_m,
      duration_s: response.duration_s,
      risk_score: response.risk_score,
    },
  ];

  if (response.shortest) {
    // The backend sends only the geometry for the shortest route — derive
    // distance from it (haversine) and duration with the backend's own
    // walking-speed formula. Risk stays unknown (null → "—" in the panel).
    const distance = pathLengthMeters(
      response.shortest.coordinates as LngLat[]
    );
    options.push({
      kind: "shortest",
      label: "En kısa",
      geometry: response.shortest,
      distance_m: distance,
      duration_s: distance / WALKING_SPEED_MPS,
      risk_score: null,
    });
  }

  return options;
}

/** Camera bounds (with padding) that frame a set of coordinates on screen. */
export interface RouteBounds {
  ne: LngLat;
  sw: LngLat;
  paddingTop: number;
  paddingBottom: number;
  paddingLeft: number;
  paddingRight: number;
}

/**
 * Computes the bounding box of a list of coordinates so the camera can fit the
 * whole route in view. Returns null for an empty list.
 */
export function getRouteBounds(coordinates: LngLat[]): RouteBounds | null {
  if (coordinates.length === 0) return null;

  let minLng = coordinates[0][0];
  let maxLng = coordinates[0][0];
  let minLat = coordinates[0][1];
  let maxLat = coordinates[0][1];

  for (const [lng, lat] of coordinates) {
    if (lng < minLng) minLng = lng;
    if (lng > maxLng) maxLng = lng;
    if (lat < minLat) minLat = lat;
    if (lat > maxLat) maxLat = lat;
  }

  return {
    ne: [maxLng, maxLat],
    sw: [minLng, minLat],
    // Leave room for the top notice banner and the bottom detail card, which is
    // now tall (stats + route toggle + LLM risk explanation).
    paddingTop: 100,
    paddingBottom: 300,
    paddingLeft: 60,
    paddingRight: 60,
  };
}
