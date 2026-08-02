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

import type {
  LngLat,
  NavigationStep,
  RouteDetailStats,
  RouteProfile,
  RouteResponse,
  ShortestRoute,
} from "./types";

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
  detail: RouteDetailStats;
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

/** A longer route used by the "Daha Güvenli" mock profile. */
export const MOCK_SAFER_COORDINATES: LngLat[] = [
  MOCK_ROUTE_COORDINATES[0],
  [-87.6372, 41.8808],
  [-87.6332, 41.8841],
  [-87.6274, 41.8841],
  MOCK_ROUTE_COORDINATES[MOCK_ROUTE_COORDINATES.length - 1],
];

const PROFILE_LABELS: Record<RouteProfile, string> = {
  shortest: "En kısa",
  balanced: "Dengeli",
  safer: "Daha güvenli",
};

function buildRouteDetail(
  geometry: GeoJSON.LineString,
  distance_m: number,
  duration_s: number,
  risk_score: number
): RouteDetailStats {
  const routeId = `mock-${Math.round(distance_m)}-${Math.round(risk_score)}`;
  const coordinates = geometry.coordinates as LngLat[];
  const edgeIds = coordinates.slice(1).map((_, index) => `${routeId}-edge-${index}`);
  const steps: NavigationStep[] = coordinates.slice(0, -1).map((coordinate, index) => ({
    step_id: `${routeId}-step-${index}`,
    maneuver: index === 0 ? "depart" : "continue",
    instruction:
      index === 0
        ? "Rotaya başlayın"
        : "Güzergâh üzerinde ilerlemeye devam edin",
    street_name: null,
    distance_m: distance_m / Math.max(1, coordinates.length - 1),
    duration_s: duration_s / Math.max(1, coordinates.length - 1),
    bearing_before: 0,
    bearing_after: 0,
    location: coordinate,
    edge_ids: [edgeIds[index]],
  }));
  steps.push({
    step_id: `${routeId}-arrive`,
    maneuver: "arrive",
    instruction: "Hedefinize ulaştınız",
    street_name: null,
    distance_m: 0,
    duration_s: 0,
    bearing_before: 0,
    bearing_after: 0,
    location: coordinates[coordinates.length - 1],
    edge_ids: [],
  });
  return {
    route_id: routeId,
    geometry,
    distance_m,
    duration_s,
    route_risk: risk_score / 100,
    risk_score,
    safety_score: 100 - risk_score,
    risk_coverage: 100,
    edge_ids: edgeIds,
    steps,
  };
}

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
  _end: LngLat,
  profile: RouteProfile = "balanced"
): RouteResponse {
  const shortestGeometry: GeoJSON.LineString = {
    type: "LineString",
    coordinates: MOCK_SHORTEST_COORDINATES,
  };
  const balancedGeometry: GeoJSON.LineString = {
    type: "LineString",
    coordinates: MOCK_ROUTE_COORDINATES,
  };
  const saferGeometry: GeoJSON.LineString = {
    type: "LineString",
    coordinates: MOCK_SAFER_COORDINATES,
  };

  const shortestRoute = buildRouteDetail(
    shortestGeometry,
    1120,
    840,
    58
  );
  const selectedRoute =
    profile === "shortest"
      ? shortestRoute
      : profile === "safer"
        ? buildRouteDetail(saferGeometry, 1450, 1090, 16)
        : buildRouteDetail(balancedGeometry, 1275, 960, 25);

  const extraDistanceM = Math.max(
    0,
    selectedRoute.distance_m - shortestRoute.distance_m
  );
  const extraDistancePct =
    shortestRoute.distance_m > 0
      ? Number(
          ((extraDistanceM / shortestRoute.distance_m) * 100).toFixed(1)
        )
      : 0;
  const riskReductionPct =
    selectedRoute.risk_score < shortestRoute.risk_score
      ? Number(
          (
            ((shortestRoute.risk_score - selectedRoute.risk_score) /
              shortestRoute.risk_score) *
            100
          ).toFixed(1)
        )
      : 0;
  const meaningfulSaferAlternative =
    profile !== "shortest" && riskReductionPct >= 5;

  return {
    schema_version: "1.0",
    route_id: selectedRoute.route_id,
    safe_route: selectedRoute,
    shortest_route: shortestRoute,
    comparison: {
      risk_reduction_pct: riskReductionPct,
      extra_distance_m: extraDistanceM,
      extra_distance_pct: extraDistancePct,
      time_difference_s: Math.max(
        0,
        selectedRoute.duration_s - shortestRoute.duration_s
      ),
      selected_profile: profile,
      max_detour_pct:
        profile === "shortest" ? 0 : profile === "balanced" ? 15 : 25,
      candidate_count: profile === "shortest" ? 1 : 4,
      eligible_candidate_count: profile === "shortest" ? 1 : 3,
      meaningful_safer_alternative: meaningfulSaferAlternative,
      decision_reason:
        profile === "shortest"
          ? "shortest_profile_requested"
          : meaningfulSaferAlternative
            ? "lower_risk_within_detour_budget"
            : "no_meaningful_safer_alternative",
    },
    metadata: {
      schema_version: "1.0",
      graph_version: "mock-graph-v1",
      risk_model_version: "mock-risk-v1",
      response_generated_at: new Date().toISOString(),
      risk_snapshot_at: new Date().toISOString(),
      routing_engine: "mock",
      algorithm: "mock_multi_candidate",
      routing_profile: profile,
      selection_method: "detour_budget_multi_candidate",
      candidate_alphas: [1, 2, 4, 8],
      safety_disclaimer: "Güvenlik skoru kesin güvenlik garantisi değildir.",
    },
    route: selectedRoute.geometry,
    distance_m: selectedRoute.distance_m,
    duration_s: selectedRoute.duration_s,
    risk_score: selectedRoute.risk_score,
    safety_score: selectedRoute.safety_score,
    route_risk: selectedRoute.route_risk,
    risk_reduction_pct: riskReductionPct,
    extra_distance_m: extraDistanceM,
    extra_distance_pct: extraDistancePct,
    shortest: shortestGeometry,
    risk_explanation: {
      risk_level:
        selectedRoute.risk_score <= 33
          ? "low"
          : selectedRoute.risk_score <= 66
            ? "medium"
            : "high",
      explanation:
        "Bu mock rota genelinde risk orta seviyede; aydınlatma ve suç sinyalleri örneklenmiş hücrelerden birleştirildi.",
      factors: ["örnek suç sinyali", "örnek aydınlatma", "canlı ihbar yok"],
      channels: {
        crime: Math.round(selectedRoute.risk_score * 0.65) / 100,
        lighting: Math.round(selectedRoute.risk_score * 0.2) / 100,
        live: 0,
        total: selectedRoute.risk_score / 100,
      },
      data_available: true,
      disclaimer: "Güvenlik skoru kesin güvenlik garantisi değildir.",
      route_risk: selectedRoute.route_risk,
      high_risk_share_pct: Math.round(selectedRoute.risk_score * 0.4),
      data_coverage_pct: 92,
      sampled_cell_count: 24,
      explanation_method: "mock",
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
  const profile =
    response.comparison?.selected_profile ??
    response.metadata?.routing_profile ??
    "balanced";
  const selectedRoute = response.safe_route;

  const options: RouteOption[] = [
    {
      kind: "safe",
      label: PROFILE_LABELS[profile],
      geometry: selectedRoute?.geometry ?? response.route,
      distance_m: selectedRoute?.distance_m ?? response.distance_m,
      duration_s: selectedRoute?.duration_s ?? response.duration_s,
      risk_score: selectedRoute?.risk_score ?? response.risk_score,
      detail: selectedRoute ?? {
        route_id: response.route_id ?? "legacy-route",
        geometry: response.route,
        distance_m: response.distance_m,
        duration_s: response.duration_s,
        route_risk: response.route_risk ?? response.risk_score / 100,
        risk_score: response.risk_score,
        safety_score: response.safety_score ?? 100 - response.risk_score,
        risk_coverage: 0,
        edge_ids: [],
        steps: [],
      },
    },
  ];

  const shortestDetail = response.shortest_route;
  const selectedDistance = selectedRoute?.distance_m ?? response.distance_m;
  const selectedIsShortest =
    shortestDetail !== undefined &&
    Math.abs(selectedDistance - shortestDetail.distance_m) < 1;

  if (!selectedIsShortest && (shortestDetail || response.shortest)) {
    const isShortestObj =
      typeof response.shortest === "object" && "route" in response.shortest;
    const shortestObj = response.shortest as ShortestRoute;
    const shortestLine = response.shortest as GeoJSON.LineString;

    options.push({
      kind: "shortest",
      label: "En kısa",
      geometry:
        shortestDetail?.geometry ??
        (isShortestObj ? shortestObj.route : shortestLine),
      distance_m:
        shortestDetail?.distance_m ??
        (isShortestObj
          ? shortestObj.distance_m
          : Math.round(response.distance_m * 0.85)),
      duration_s:
        shortestDetail?.duration_s ??
        (isShortestObj
          ? shortestObj.duration_s
          : Math.round(response.duration_s * 0.85)),
      risk_score:
        shortestDetail?.risk_score ??
        (isShortestObj
          ? shortestObj.risk_score
          : Math.min(100, Math.round(response.risk_score * 1.3))),
      detail: shortestDetail ?? {
        route_id: `${response.route_id ?? "legacy-route"}-shortest`,
        geometry: isShortestObj ? shortestObj.route : shortestLine,
        distance_m:
          isShortestObj
            ? shortestObj.distance_m
            : Math.round(response.distance_m * 0.85),
        duration_s:
          isShortestObj
            ? shortestObj.duration_s
            : Math.round(response.duration_s * 0.85),
        route_risk: (isShortestObj
          ? shortestObj.risk_score
          : Math.min(100, Math.round(response.risk_score * 1.3))) / 100,
        risk_score: isShortestObj
          ? shortestObj.risk_score
          : Math.min(100, Math.round(response.risk_score * 1.3)),
        safety_score: 100 - (isShortestObj
          ? shortestObj.risk_score
          : Math.min(100, Math.round(response.risk_score * 1.3))),
        risk_coverage: 0,
        edge_ids: [],
        steps: [],
      },
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
