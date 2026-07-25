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

import type { HexRisk, LngLat, RouteResponse } from "./types";
import { distanceMeters } from "./nearbyAlerts";

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
   * safe route; the shortest route's risk is not computed server-side, so we
   * estimate it from the live heatmap cells instead (see scorePathRisk).
   */
  risk_score: number | null;
  /**
   * True when `risk_score` was derived on the client from heatmap cells rather
   * than returned by the routing engine. The panel marks these as "tahmini" so
   * an estimate is never presented as the backend's own number.
   */
  risk_estimated?: boolean;
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

/** A path vertex counts as "inside" a heatmap cell within this many meters. */
const RISK_MATCH_RADIUS_M = 200;

/**
 * Cap on how many vertices we sample along a path. A city route can carry
 * hundreds of vertices and the heatmap thousands of cells; sampling keeps this
 * O(40 × candidates) instead of O(n × m) without changing the answer much,
 * since consecutive vertices sit in the same cell anyway.
 */
const MAX_RISK_SAMPLES = 40;

/**
 * Estimates a 0-100 risk for a path from the live heatmap cells around it.
 *
 * Why this exists: the backend computes a risk score for the safe route only —
 * `shortest` comes back as bare geometry (backend/main.py RouteResponse). That
 * left the comparison panel showing "—" for the very route the user is being
 * asked to compare against, which defeats the point of the toggle. The cells
 * behind GET /api/v1/heatmap are the same risk data the routing engine weights
 * its edges with, so sampling them along the path is a fair approximation.
 *
 * It is an approximation, not the engine's number — callers mark it
 * `risk_estimated` so the UI can label it. Returns null when no cell is close
 * enough to say anything, which keeps the honest "—" for that case.
 */
export function scorePathRisk(
  coordinates: LngLat[],
  hexes: HexRisk[]
): number | null {
  if (coordinates.length === 0 || hexes.length === 0) return null;

  // Prefilter to the path's bounding box (+ the match radius) so the per-vertex
  // scan only looks at cells that could possibly match. ~0.0018° ≈ 200m.
  const pad = RISK_MATCH_RADIUS_M / 111_000;
  const lngs = coordinates.map(([lng]) => lng);
  const lats = coordinates.map(([, lat]) => lat);
  const minLng = Math.min(...lngs) - pad;
  const maxLng = Math.max(...lngs) + pad;
  const minLat = Math.min(...lats) - pad;
  const maxLat = Math.max(...lats) + pad;

  const candidates = hexes.filter(
    (hex) =>
      hex.lng >= minLng &&
      hex.lng <= maxLng &&
      hex.lat >= minLat &&
      hex.lat <= maxLat
  );
  if (candidates.length === 0) return null;

  const step = Math.max(1, Math.ceil(coordinates.length / MAX_RISK_SAMPLES));
  const scores: number[] = [];

  for (let i = 0; i < coordinates.length; i += step) {
    const [lng, lat] = coordinates[i];
    let nearestRisk: number | null = null;
    let nearestDistance = RISK_MATCH_RADIUS_M;

    for (const hex of candidates) {
      const distance = distanceMeters(lat, lng, hex.lat, hex.lng);
      if (distance <= nearestDistance) {
        nearestDistance = distance;
        nearestRisk = hex.risk_score;
      }
    }

    if (nearestRisk !== null) scores.push(nearestRisk);
  }

  if (scores.length === 0) return null;
  const mean = scores.reduce((sum, score) => sum + score, 0) / scores.length;
  return Math.round(mean * 10) / 10;
}

/**
 * Flattens a RouteResponse into the list of routes the UI renders and toggles
 * between: always the safe route, plus the shortest one when present. Keeping
 * this in one place means the map layers, the camera fit and the detail panel
 * all read from the same normalized shape (item 1, AC #4) — swapping the mock
 * for the real backend never touches those components.
 *
 * @param hexes live heatmap cells, used to estimate the shortest route's risk
 *   (the backend doesn't report one). Omit to keep that risk unknown.
 */
export function getRouteOptions(
  response: RouteResponse,
  hexes: HexRisk[] = []
): RouteOption[] {
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
    // distance from it (haversine), duration with the backend's own
    // walking-speed formula, and risk from the heatmap cells along it.
    const coordinates = response.shortest.coordinates as LngLat[];
    const distance = pathLengthMeters(coordinates);
    const estimatedRisk = scorePathRisk(coordinates, hexes);
    options.push({
      kind: "shortest",
      label: "En kısa",
      geometry: response.shortest,
      distance_m: distance,
      duration_s: distance / WALKING_SPEED_MPS,
      risk_score: estimatedRisk,
      risk_estimated: estimatedRisk !== null,
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
