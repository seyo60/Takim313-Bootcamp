/**
 * Nearby-danger alerts (item 5), derived from LIVE backend risk data.
 *
 * Why derived rather than fetched: the LLM `alert_dispatcher` service exists in
 * backend/llm_integration/ but is not exposed over HTTP yet. What IS live is
 * GET /api/v1/heatmap/nearby — and the backend's report pipeline (BE-03) runs
 * every submitted report through the LLM in a background task and writes the
 * resulting risk back onto the map. So a freshly reported danger near the user
 * *becomes* a high-risk point in that endpoint's response. Reading it back is
 * the same signal the dispatcher would push, just pulled instead of pushed.
 *
 * When Seymen exposes the dispatcher (GET /api/v1/alerts/nearby), swap the
 * source in api.ts — `NearbyAlert` already mirrors the dispatcher's
 * `AlertMessage` schema, so nothing in the UI changes.
 */

import type { HexRisk, LngLat, NearbyAlert } from "./types";

/** Same radius the backend dispatcher uses (config: ALERT_RADIUS_METERS). */
export const ALERT_RADIUS_METERS = 500;

/**
 * Only high/critical risk becomes an alert (AC #1). Below this a point is
 * ordinary background risk — it belongs on the heatmap, not in a popup that
 * interrupts the user.
 */
const ALERT_RISK_THRESHOLD = 60;

/** At or above this the danger is "critical" — red, and never auto-dismissed. */
export const CRITICAL_RISK_SCORE = 80;

/** Haversine distance in meters. */
export function distanceMeters(
  lat1: number,
  lng1: number,
  lat2: number,
  lng2: number
): number {
  const R = 6_371_000;
  const phi1 = (lat1 * Math.PI) / 180;
  const phi2 = (lat2 * Math.PI) / 180;
  const dPhi = ((lat2 - lat1) * Math.PI) / 180;
  const dLambda = ((lng2 - lng1) * Math.PI) / 180;
  const a =
    Math.sin(dPhi / 2) ** 2 +
    Math.cos(phi1) * Math.cos(phi2) * Math.sin(dLambda / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

/** "120m uzakta" / "1.4km uzakta" — the distance line on the alert card (AC #2). */
export function formatDistance(meters: number): string {
  return meters < 1000
    ? `${Math.round(meters)}m uzakta`
    : `${(meters / 1000).toFixed(1)}km uzakta`;
}

/**
 * Stable id for a derived alert.
 *
 * Must not change between polls: the id is what "dismissed for this session"
 * is keyed on, so a coordinate-derived id keeps a dismissed alert dismissed
 * instead of having it pop straight back on the next poll. Rounded to ~1m so
 * float jitter in the backend response can't mint a new id for the same cell.
 */
function alertIdFor(lat: number, lng: number): string {
  return `risk_${lat.toFixed(5)}_${lng.toFixed(5)}`;
}

/** One-sentence Turkish summary — the `body` line of the card (AC #2). */
function summaryFor(riskScore: number, meters: number): string {
  const where = formatDistance(meters);
  return riskScore >= CRITICAL_RISK_SCORE
    ? `${where} kritik risk seviyesinde bir bölge var. Rotanızı değiştirmeniz önerilir.`
    : `${where} yüksek riskli bir bölge bildirildi. Dikkatli olun.`;
}

/**
 * Turns the live risk points around the user into alert cards, nearest first.
 *
 * Heatmap points carry no LLM category (that only exists on the dispatcher's
 * AlertMessage), so these get the synthetic category "risk_zone". Real
 * categories (violent/theft/harassment/…) will arrive unchanged the day the
 * dispatcher endpoint lands.
 */
export function riskPointsToAlerts(
  points: HexRisk[],
  location: LngLat
): NearbyAlert[] {
  const [lng, lat] = location;

  return points
    .map((point) => ({
      point,
      meters: distanceMeters(lat, lng, point.lat, point.lng),
    }))
    .filter(
      ({ point, meters }) =>
        point.risk_score >= ALERT_RISK_THRESHOLD &&
        meters <= ALERT_RADIUS_METERS
    )
    .sort((a, b) => a.meters - b.meters)
    .map(({ point, meters }) => ({
      alert_id: alertIdFor(point.lat, point.lng),
      title:
        point.risk_score >= CRITICAL_RISK_SCORE
          ? "ACİL: Yakınınızda kritik risk"
          : "Dikkat: Yakınınızda yüksek risk",
      body: summaryFor(point.risk_score, meters),
      latitude: point.lat,
      longitude: point.lng,
      risk_score: point.risk_score,
      category: "risk_zone",
      distance_m: meters,
    }));
}
