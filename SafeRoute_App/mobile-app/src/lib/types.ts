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
 * Response of POST /api/v1/route — CONFIRMED against backend/main.py
 * (RouteResponse pydantic model). `risk_score` is 0 (safe) – 100 (dangerous);
 * the backend inverts its internal safety_score for us.
 *
 * `shortest` is a bare LineString: the backend does NOT return per-route stats
 * for it. The UI derives shortest distance/duration client-side from the
 * geometry (see getRouteOptions) and shows its risk as unknown.
 */
export interface RouteResponse {
  /** The safe route as a GeoJSON LineString ([lng, lat] pairs). */
  route: GeoJSON.LineString;
  distance_m: number;
  duration_s: number;
  /** Risk along the route, 0 (safe) – 100 (dangerous). */
  risk_score: number;
  /** Plain shortest route for comparison (geometry only, no stats). */
  shortest?: GeoJSON.LineString;
}

/**
 * One H3 hexagon cell's risk for the heatmap layer (item 3).
 *
 * CONFIRMED: the backend's GET /api/v1/heatmap returns a flat array of
 * `{ lat, lng, total_risk }` — the H3 index stays server-side and the field
 * is named `total_risk`. getHeatmap() maps that wire shape into this UI shape
 * (total_risk → risk_score); nothing outside api.ts needs to know.
 */
export interface HexRisk {
  /** H3 cell index — not exposed by the backend endpoint; mock-only. */
  h3_index?: string;
  /** Cell centroid, [longitude, latitude] split into lat/lng. */
  lat: number;
  lng: number;
  /** Risk for the cell, 0-100 (wire name: total_risk). */
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
 * A danger alert for users near a fresh report (item 5). Field names follow
 * the backend's llm_integration/schemas/types.py `AlertMessage` model — the
 * alert_dispatcher service builds these after the LLM analyzes a report.
 *
 * TODO(osman): the dispatcher is not exposed over HTTP yet — ask Seymen for
 * the route (suggested: GET /api/v1/alerts/nearby?lat=..&lng=..&radius=..).
 * Until then USE_MOCK_ALERTS stays true in api.ts.
 */
export interface NearbyAlert {
  alert_id: string;
  title: string;
  /** e.g. "300m yakınınızda şüpheli aktivite rapor edildi." */
  body: string;
  /** Where the reported danger is. */
  latitude: number;
  longitude: number;
  /** LLM-scored severity of the underlying report, 0-100. */
  risk_score: number;
  /** violent | theft | harassment | suspicious | environmental | other */
  category: string;
  /** ISO timestamp (wire) — kept as string on mobile. */
  created_at?: string;
  status?: "pending" | "sent" | "failed";
}

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
 * LLM street-risk explanation (item 2). Field names follow the backend's
 * llm_integration/schemas/types.py `StreetExplanation` model
 * (`summary` / `risk_level` / `factors`), so wiring the real endpoint later
 * is a parse-free swap.
 *
 * TODO(osman): the backend service (street_explainer.py) exists but is NOT
 * exposed as an HTTP endpoint yet — ask Seymen for the route (suggested:
 * POST /api/v1/street-risk-explanation). Until then USE_MOCK_STREET_RISK
 * stays true in api.ts.
 */
export interface StreetRiskExplanation {
  risk_level: RiskLevel;
  /** ≤2 sentence Turkish rationale (backend field name: summary). */
  summary: string;
  /** Up to 3 concrete risk factors (e.g. "Zayıf aydınlatma"). */
  factors: string[];
  /**
   * Per-channel breakdown (historical/live/social/total). The backend's
   * response schema does not include it — optional, mock/demo only.
   */
  channels?: RiskChannels;
}
