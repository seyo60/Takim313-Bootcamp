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
 * One H3 hexagon cell's risk from GET /api/v1/heatmap. The backend's XGBoost
 * batch prediction scores each H3 cell; `lat`/`lng` are the cell centroid and
 * `risk_score` is 0 (safe) – 100 (dangerous). Rendered as the risk heatmap
 * (item 3).
 *
 * TODO(osman): pending §B — confirm exact field names (`h3_index` vs `cell`,
 * `risk_score` vs `total_risk`) and whether the payload is a flat array or a
 * GeoJSON FeatureCollection; if so, adjust the parsing in getHeatmap() only.
 */
export interface HexRisk {
  /** H3 cell index (resolution ~9). */
  h3_index: string;
  /** Cell centroid, [longitude, latitude] split into lat/lng. */
  lat: number;
  lng: number;
  /** Batch-predicted risk for the cell, 0-100. */
  risk_score: number;
}

/** Report urgency. "urgent" is the one-tap emergency path (item 4). */
export type ReportPriority = "normal" | "urgent";

/**
 * Body of POST /api/v1/report.
 *
 * TODO(osman): pending §C — field names to be confirmed. `priority` may not be
 * supported by the backend yet; it's sent regardless and simulated in mock mode
 * (item 4, AC #3). Drop/rename here + in submitReport() once Seda Nur/Seymen
 * confirm the field.
 */
export interface ReportRequest {
  text: string;
  lat: number;
  lng: number;
  /** Defaults to "normal" when omitted. */
  priority?: ReportPriority;
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

/**
 * Risk severity bucket for a street/route, driving the colored badge
 * (item 2, AC #1): low=green, medium=yellow, high=orange, critical=red.
 */
export type RiskLevel = "low" | "medium" | "high" | "critical";

/**
 * The risk score broken down by source channel, each 0-100. These feed the
 * LLM explanation and are shown as a small breakdown under the summary.
 *
 * TODO(osman): pending backend §D — confirm channel names/scale for
 * GET|POST /api/v1/street-risk-explanation.
 */
export interface RiskChannels {
  /** Crime history / static risk (OSMnx + crime ETL). */
  historical: number;
  /** Live signals (recent reports, time-of-day). */
  live: number;
  /** Social/NLP-derived risk (reports, social webhook). */
  social: number;
  /** Combined score the badge/level is derived from. */
  total: number;
}

/**
 * Response of the LLM street-risk explanation endpoint
 * (POST /api/v1/street-risk-explanation). The backend runs the LLM over the
 * risk channels and returns a short, human-readable rationale.
 *
 * TODO(osman): pending §D — confirm field names + that the text is
 * pre-truncated (≤2 sentences) server-side or if the UI must clamp it.
 */
export interface StreetRiskExplanation {
  risk_level: RiskLevel;
  /** ≤2 sentence Turkish rationale for why the street/route is risky. */
  explanation: string;
  /** Up to 3 concrete risk factors (e.g. "Zayıf aydınlatma"). */
  factors: string[];
  /** Per-channel breakdown (historical/live/social/total). */
  channels: RiskChannels;
}
