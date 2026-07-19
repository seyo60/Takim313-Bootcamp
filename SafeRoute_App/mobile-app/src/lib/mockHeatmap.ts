/**
 * Local mock for the backend `GET /api/v1/heatmap` endpoint (item 3 / §B).
 * Shapes match src/lib/types.ts (`HexRisk`), so swapping to the real backend
 * only means flipping USE_MOCK_HEATMAP in src/lib/api.ts — the UI never changes.
 *
 * The real data is the XGBoost batch prediction over an H3 hexagon grid: each
 * cell has an `h3_index` + a 0-100 `risk_score`. Here we synthesize that grid
 * deterministically over Chicago downtown from a few risk hotspots, so the
 * heatmap looks alive without needing the h3 library on device.
 *
 * TODO(osman): delete this file's usage once Seymen's heatmap endpoint serves
 * Merve/Mehmet Ali's real batch predictions.
 */

import type { HexRisk, LngLat } from "./types";

/** Bounding box of the mock hexagon grid (Chicago downtown / the Loop). */
const GRID = {
  minLng: -87.665,
  maxLng: -87.605,
  minLat: 41.86,
  maxLat: 41.905,
  /** Cell spacing in degrees (~0.006° ≈ H3 res-9 edge near Chicago). */
  step: 0.006,
};

/**
 * Risk hotspots the grid is sampled from. Each cell's score is the strongest
 * nearby hotspot (Gaussian falloff), so risk varies smoothly across the map:
 * high west of the Loop, medium in River North, low near Millennium Park.
 */
const HOTSPOTS: { center: LngLat; weight: number; sigma: number }[] = [
  { center: [-87.6412, 41.8695], weight: 95, sigma: 0.011 }, // west of the Loop
  { center: [-87.63, 41.892], weight: 62, sigma: 0.009 }, // River North
  { center: [-87.6226, 41.8827], weight: 28, sigma: 0.008 }, // Millennium Park
];

/** Baseline risk everywhere, so no cell is a perfect zero. */
const BASE_RISK = 6;

/** Strongest hotspot influence at a point → a 0-100 risk score. */
function riskAt(lng: number, lat: number): number {
  let risk = BASE_RISK;
  for (const { center, weight, sigma } of HOTSPOTS) {
    const dLng = lng - center[0];
    const dLat = lat - center[1];
    const d2 = dLng * dLng + dLat * dLat;
    risk = Math.max(risk, weight * Math.exp(-d2 / (2 * sigma * sigma)));
  }
  return Math.round(Math.min(100, Math.max(0, risk)));
}

/**
 * Synthetic H3-ish index for a cell. Real H3 indices are 15-char hex strings;
 * this is a deterministic placeholder in the same shape so the field is
 * exercised. TODO(osman): the real backend supplies actual H3 indices.
 */
function mockH3Index(row: number, col: number): string {
  const suffix = (row * 1000 + col).toString(16).padStart(9, "0");
  return `8a2664${suffix}`;
}

/** Builds the static hexagon-risk grid once (deterministic, no RNG). */
function buildGrid(): HexRisk[] {
  const cells: HexRisk[] = [];
  let row = 0;
  for (let lat = GRID.minLat; lat <= GRID.maxLat; lat += GRID.step, row++) {
    let col = 0;
    // Offset every other row by half a step so cells sit in a hex-like layout.
    const rowOffset = row % 2 === 0 ? 0 : GRID.step / 2;
    for (
      let lng = GRID.minLng + rowOffset;
      lng <= GRID.maxLng;
      lng += GRID.step, col++
    ) {
      cells.push({
        h3_index: mockH3Index(row, col),
        lng,
        lat,
        risk_score: riskAt(lng, lat),
      });
    }
  }
  return cells;
}

/** The static batch-prediction grid across the Chicago demo area. */
export const MOCK_HEX_RISK: HexRisk[] = buildGrid();

/**
 * Danger reports submitted while in mock mode. The real backend does this
 * server-side (report → LLM analysis → risk table → next batch prediction);
 * locally we mimic the end result so the demo flow "report → heatmap shows a
 * new hot spot" works.
 */
const reportedCells: HexRisk[] = [];

/** Registers a mock high-risk hexagon at the reported location. */
export function addMockReportedHex(lng: number, lat: number): void {
  reportedCells.push({
    h3_index: `mock-report-${Date.now()}`,
    lng,
    lat,
    risk_score: 92,
  });
}

/** All mock hexagons: the static grid + anything reported this session. */
export function getMockHexRisk(): HexRisk[] {
  return [...MOCK_HEX_RISK, ...reportedCells];
}

/**
 * Converts hexagon-risk cells into the GeoJSON FeatureCollection Mapbox's
 * ShapeSource expects (one weighted point per cell centroid). Works for both
 * mock and (later) real backend data.
 */
export function hexRiskToFeatureCollection(
  cells: HexRisk[]
): GeoJSON.FeatureCollection<GeoJSON.Point> {
  return {
    type: "FeatureCollection",
    features: cells.map((cell) => ({
      type: "Feature",
      properties: { risk_score: cell.risk_score },
      geometry: { type: "Point", coordinates: [cell.lng, cell.lat] },
    })),
  };
}
