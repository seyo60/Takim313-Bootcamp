/**
 * Shared types for the backend API contracts.
 *
 * The exact JSON shapes are agreed with Seymen in end-to-end.md
 * ("Zorunlu Dış Bağımlılıklar" §A/§B/§C). Fields marked TODO are still
 * pending a final decision on the backend side — the mocks follow these
 * same types, so when the contract is confirmed we only touch this file
 * and src/lib/api.ts, never the UI.
 */

/** Mapbox/GeoJSON coordinate order is [longitude, latitude]. */
export type LngLat = [number, number];

/**
 * Body of POST /api/v1/route.
 *
 * TODO(osman): field names/shape not final (§A) — Seymen may prefer
 * `start_lat`/`start_lng` etc. Update here + in getRoute() when decided.
 */
export interface RouteRequest {
  start: LngLat;
  end: LngLat;
  /** Local hour 0-23; risk depends on time of day. Optional until §A is settled. */
  hour?: number;
}

/**
 * The plain shortest route returned alongside the safe one, for the
 * "shortest vs safest" comparison + selection toggle (item 1 / item 8). It
 * carries its own stats so the detail panel can show the *selected* route's
 * numbers, not just the safe route's.
 *
 * TODO(osman): pending §A — confirm the backend returns these per-route stats
 * (distance/duration/risk) for `shortest`, not just its geometry.
 */
export interface ShortestRoute {
  /** The shortest route as a GeoJSON LineString ([lng, lat] pairs). */
  route: GeoJSON.LineString;
  distance_m: number;
  duration_s: number;
  /** Risk along this route, 0 (safe) – 100 (dangerous). */
  risk_score: number;
}

/**
 * Response of POST /api/v1/route.
 *
 * TODO(osman): pending §A decisions — is `risk_score` an average or a total?
 * Will `shortest` be included for comparison (item 1 / item 8)?
 */
export interface RouteResponse {
  /** The safe route as a GeoJSON LineString ([lng, lat] pairs). */
  route: GeoJSON.LineString;
  distance_m: number;
  duration_s: number;
  /** Risk along the route, 0 (safe) – 100 (dangerous). */
  risk_score: number;
  /** Optional: plain shortest route (geometry + its own stats), for comparison. */
  shortest?: ShortestRoute;
}

/**
 * One risk point from GET /api/v1/heatmap (and /heatmap/nearby).
 *
 * TODO(osman): pending §B — could also arrive as GeoJSON FeatureCollection<Point>;
 * field name `total_risk` and its 0-100 scale to be confirmed.
 */
export interface RiskPoint {
  lat: number;
  lng: number;
  total_risk: number;
}

/**
 * Body of POST /api/v1/report.
 *
 * TODO(osman): pending §C — field names to be confirmed.
 */
export interface ReportRequest {
  text: string;
  lat: number;
  lng: number;
}

/**
 * Response of POST /api/v1/report.
 *
 * Analysis runs in the background (LLM), so we expect an acknowledgement only —
 * no risk score in the response.
 *
 * TODO(osman): pending §C — if the backend ends up returning the analysis
 * synchronously, extend this type and show the result in the report screen.
 */
export interface ReportResponse {
  ok: boolean;
  id?: string;
}
