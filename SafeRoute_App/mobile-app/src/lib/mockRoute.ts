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
    // The direct-but-riskier alternative, for the comparison view (item 8).
    // TODO(osman): §A — if the backend ends up not returning `shortest`,
    // the UI already handles its absence (comparison simply not shown).
    shortest: {
      type: "LineString",
      coordinates: MOCK_SHORTEST_COORDINATES,
    },
  };
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
    // Leave room for the top notice banner and any bottom UI (route info card).
    paddingTop: 100,
    paddingBottom: 160,
    paddingLeft: 60,
    paddingRight: 60,
  };
}
