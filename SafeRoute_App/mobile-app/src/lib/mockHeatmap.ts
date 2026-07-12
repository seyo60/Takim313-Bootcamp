/**
 * Local mock for the backend `GET /api/v1/heatmap` endpoint (see end-to-end.md,
 * item 5 / §B). Shapes match src/lib/types.ts (`RiskPoint`), so swapping to the
 * real backend only means flipping USE_MOCK_HEATMAP in src/lib/api.ts.
 *
 * Generates deterministic clusters of risk points around Chicago downtown:
 * one high-risk, one medium, one low — enough to see the color ramp working.
 *
 * TODO(osman): delete this file's usage once Seymen's heatmap endpoint is live
 * and Merve/Mehmet Ali's batch predictions fill the real table.
 */

import type { LngLat, RiskPoint } from "./types";

/** Golden-angle spiral: deterministic, evenly spread points — no RNG needed. */
function cluster(
  center: LngLat,
  count: number,
  spreadDeg: number,
  baseRisk: number
): RiskPoint[] {
  const points: RiskPoint[] = [];
  for (let i = 0; i < count; i++) {
    const angle = i * 2.399963; // golden angle in radians
    const radius = spreadDeg * Math.sqrt((i + 1) / count);
    // Pseudo-variation without randomness so hot spots aren't perfectly flat.
    const riskJitter = ((i * 37) % 21) - 10;
    points.push({
      lng: center[0] + radius * Math.cos(angle),
      lat: center[1] + radius * Math.sin(angle),
      total_risk: Math.min(100, Math.max(0, baseRisk + riskJitter)),
    });
  }
  return points;
}

/** Mock risk points across the Chicago demo area. */
export const MOCK_RISK_POINTS: RiskPoint[] = [
  // High-risk cluster — west of the Loop.
  ...cluster([-87.6412, 41.8695], 18, 0.006, 85),
  // Medium-risk cluster — River North.
  ...cluster([-87.63, 41.892], 15, 0.005, 55),
  // Low-risk cluster — Millennium Park area.
  ...cluster([-87.6226, 41.8827], 12, 0.005, 20),
];

/**
 * Converts risk points into the GeoJSON FeatureCollection Mapbox's
 * ShapeSource expects. Works for both mock and (later) real backend points.
 */
export function riskPointsToFeatureCollection(
  points: RiskPoint[]
): GeoJSON.FeatureCollection<GeoJSON.Point> {
  return {
    type: "FeatureCollection",
    features: points.map((point) => ({
      type: "Feature",
      properties: { total_risk: point.total_risk },
      geometry: { type: "Point", coordinates: [point.lng, point.lat] },
    })),
  };
}
