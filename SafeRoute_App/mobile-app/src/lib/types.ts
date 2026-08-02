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
export type RouteProfile = "shortest" | "balanced" | "safer";

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
  /** Distance-budget policy used by the multi-candidate routing engine. */
  profile?: RouteProfile;
  /** Rotanın tamamı için LLM destekli risk açıklaması iste. */
  include_risk_explanation?: boolean;
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
export interface RouteDetailStats {
  route_id: string;
  geometry: GeoJSON.LineString;
  distance_m: number;
  duration_s: number;
  route_risk: number;
  risk_score: number;
  safety_score: number;
  risk_coverage: number;
  edge_ids: string[];
  steps: NavigationStep[];
}

export type ManeuverType =
  | "depart"
  | "continue"
  | "turn_left"
  | "turn_right"
  | "sharp_left"
  | "sharp_right"
  | "arrive";

export interface NavigationStep {
  step_id: string;
  maneuver: ManeuverType;
  instruction: string;
  street_name: string | null;
  way_type?: string | null;
  distance_m: number;
  duration_s: number;
  bearing_before: number;
  bearing_after: number;
  location: LngLat;
  edge_ids: string[];
}

export interface RouteComparisonStats {
  risk_reduction_pct: number;
  extra_distance_m: number;
  extra_distance_pct: number;
  time_difference_s: number;
  selected_profile?: RouteProfile;
  max_detour_pct?: number;
  candidate_count?: number;
  eligible_candidate_count?: number;
  meaningful_safer_alternative?: boolean;
  decision_reason?: string;
  distinct_from_balanced?: boolean;
}

export interface RouteMetadata {
  schema_version: string;
  graph_version: string;
  risk_model_version: string;
  response_generated_at?: string;
  risk_snapshot_at: string;
  crime_data_updated_at?: string | null;
  lighting_data_updated_at?: string | null;
  routing_engine: string;
  algorithm: string;
  routing_profile?: RouteProfile;
  selection_method?: string;
  candidate_alphas?: number[];
  safety_disclaimer: string;
}

export interface RouteResponse {
  schema_version?: string;
  route_id?: string;
  safe_route?: RouteDetailStats;
  shortest_route?: RouteDetailStats;
  comparison?: RouteComparisonStats;
  metadata?: RouteMetadata;
  risk_explanation?: RouteRiskExplanation;

  /** The safe route as a GeoJSON LineString ([lng, lat] pairs). */
  route: GeoJSON.LineString;
  distance_m: number;
  duration_s: number;
  /** Risk along the route, 0 (safe) – 100 (dangerous). */
  risk_score: number;
  /** Safety score 100 (safe) – 0 (dangerous). */
  safety_score?: number;
  /** Normalized route risk 0.0 – 1.0. */
  route_risk?: number;
  /** Risk reduction percentage vs shortest route. */
  risk_reduction_pct?: number;
  /** Extra distance in meters vs shortest route. */
  extra_distance_m?: number;
  /** Extra distance percentage vs shortest route. */
  extra_distance_pct?: number;
  /** Optional: plain shortest route (geometry or full stats), for comparison. */
  shortest?: GeoJSON.LineString | ShortestRoute;
}

/**
  One H3 hexagon cell's risk from GET /api/v1/heatmap.
 */
export interface HexRisk {
  /** H3 cell index (resolution ~9). */
  h3_index: string;
  /** Cell centroid, [longitude, latitude] split into lat/lng. */
  lat: number;
  lng: number;
  /** Risk channel breakdowns */
  risk_crime?: number;
  risk_lighting?: number;
  risk_live?: number;
  /** Batch-predicted total risk for the cell, 0-1.0 or 0-100. */
  total_risk: number;
  risk_score?: number;
}

/** Report urgency. "urgent" is the one-tap emergency path. */
export type ReportPriority = "normal" | "urgent";

export type ReportStatus = "pending" | "processing" | "accepted" | "rejected" | "expired";

export const REPORT_STATUS_CONFIG: Record<ReportStatus, { label: string; bgColor: string; textColor: string }> = {
  pending: { label: "Topluluk Doğrulaması Bekleniyor", bgColor: "#FFF9C4", textColor: "#F57F17" },
  processing: { label: "Analiz Ediliyor", bgColor: "#E3F2FD", textColor: "#1976D2" },
  accepted: { label: "Doğrulandı", bgColor: "#E8F5E9", textColor: "#2E7D32" },
  rejected: { label: "Reddedildi", bgColor: "#FFEBEE", textColor: "#C62828" },
  expired: { label: "Zaman Aşımı", bgColor: "#F5F5F5", textColor: "#616161" },
};


export interface ReportRequest {
  text: string;
  lat: number;
  lng: number;

  category?: string;
  priority?: ReportPriority;
  reporter_installation_id?: string;
}


export interface ReportResponse {
  ok: boolean;
  id?: string;
  tracking_token?: string;
  status?: ReportStatus;
  message?: string;
  event_id?: string;
  event_status?: string;
  validation_score?: number;
  cluster_report_count?: number;
  live_risk_applied?: boolean;
}

export interface ReportDetailResponse {
  id: string;
  status: ReportStatus;
  category?: string;
  created_at: string;
  message?: string;
  /** Kullanıcının gönderdiği ihbar metni (İhbarlarım listesi). */
  description?: string | null;
}


export interface MapReport {
  public_id: string;
  category: string;
  lat: number;
  lng: number;
  reported_at: string;
  status: string;
  verification_label: string;
  minutes_ago: number;
}

export interface MapReportsResponse {
  generated_at: string;
  window_minutes: number;
  count: number;
  reports: MapReport[];
}

export interface GetRecentMapReportsOptions {
  minutes?: number;
  bbox?: string;
  category?: string;
  signal?: AbortSignal;
}

/**
 * Risk severity bucket for a street/route, driving the colored badge
 * (item 2, AC #1): low=green, medium=yellow, high=orange, critical=red.
 */
export type RiskLevel = "low" | "low_medium" | "medium" | "high" | "very_high" | "no_data";

export interface RiskChannels {
  crime: number;
  lighting: number;
  live: number;
  total: number;
}

export interface StreetRiskExplanation {
  risk_level: RiskLevel;
  /** ≤2 sentence Turkish rationale for why the street/route is risky. */
  explanation: string;
  /** Up to 3 concrete risk factors (e.g. "Zayıf aydınlatma"). */
  factors: string[];
  /** Per-channel breakdown (crime/lighting/live/total). */
  channels: RiskChannels;
  h3_index?: string;
  data_available?: boolean;
  observed_risk_level?: string;
  disclaimer?: string;
  risk_snapshot_at?: string | null;
  crime_risk?: number;
  lighting_risk?: number;
  live_risk?: number;
  total_risk?: number | null;
}

/**
 * Rotanın tamamı için birleştirilmiş risk açıklaması. Tek noktalık
 * `StreetRiskExplanation`'dan farkı, değerlerin rota geometrisi boyunca uzunluk
 * ağırlıklı toplanmasıdır; bu yüzden gösterilen `route_risk` ile tutarlıdır.
 */
export interface RouteRiskExplanation
  extends Omit<StreetRiskExplanation, "h3_index"> {
  /** Motorun bildirdiği rota riski (0.0 – 1.0). */
  route_risk?: number;
  /** Rota uzunluğunun yüzde kaçı daha riskli hücrelerden geçiyor. */
  high_risk_share_pct?: number;
  /** Örneklenen hücrelerin yüzde kaçında risk verisi bulundu. */
  data_coverage_pct?: number;
  /** Açıklama için örneklenen H3 hücre sayısı. */
  sampled_cell_count?: number;
  /** "deepseek_structured_output" veya deterministik fallback nedeni. */
  explanation_method?: string;
}

export interface GetStreetRiskExplanationOptions {
  riskScore?: number;
  signal?: AbortSignal;
}

/** Risk channel selection for regional risk heatmap layer. */
export type HeatmapChannel = "total" | "crime" | "lighting" | "live";

export interface HeatmapGeoJSONProperties {
  h3_index: string;
  lat: number;
  lng: number;
  risk: number | null;
  risk_crime: number;
  risk_lighting: number;
  risk_live: number;
  total_risk: number;
  data_available: boolean;
}

export interface HeatmapGeoJSONFeature extends GeoJSON.Feature<GeoJSON.Polygon, HeatmapGeoJSONProperties> {
  id: string;
}

export interface HeatmapGeoJSONMetadata {
  generated_at: string;
  risk_snapshot_at?: string | null;
  crime_data_updated_at?: string | null;
  lighting_data_updated_at?: string | null;
  h3_resolution: number;
  channel: HeatmapChannel;
  feature_count: number;
  data_coverage_pct: number;
}

export interface HeatmapGeoJSONResponse {
  type: "FeatureCollection";
  metadata: HeatmapGeoJSONMetadata;
  features: HeatmapGeoJSONFeature[];
}

export interface GetRiskHeatmapMapOptions {
  bbox?: string;
  channel?: HeatmapChannel;
  include_no_data?: boolean;
  signal?: AbortSignal;
}

export interface UserProfile {
  user_id: string;
  display_name?: string | null;
  role: "user" | "moderator" | "admin";
  deletion_requested_at?: string | null;
}

export interface MyReportsResponse {
  reports: ReportDetailResponse[];
}

export interface AccountDeletionResponse {
  status: "scheduled" | "cancelled";
  requested_at?: string | null;
  message: string;
}
