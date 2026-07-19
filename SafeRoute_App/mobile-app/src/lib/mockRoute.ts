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
  risk_score: number;
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
    // It's shorter/faster than the safe route but carries a higher risk score —
    // that trade-off is the whole point the user weighs.
    // TODO(osman): §A — if the backend ends up not returning `shortest`,
    // the UI already handles its absence (comparison simply not shown).
    shortest: {
      route: {
        type: "LineString",
        coordinates: MOCK_SHORTEST_COORDINATES,
      },
      distance_m: 1120, // shorter than the safe route (1350 m)
      duration_s: 840, // ~14 min walk (vs ~17 min)
      risk_score: 58, // riskier than the safe route (24)
    },
  };
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
    options.push({
      kind: "shortest",
      label: "En kısa",
      geometry: response.shortest.route,
      distance_m: response.shortest.distance_m,
      duration_s: response.shortest.duration_s,
      risk_score: response.shortest.risk_score,
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
