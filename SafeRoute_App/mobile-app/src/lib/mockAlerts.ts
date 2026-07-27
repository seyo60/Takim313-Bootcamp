/**
 * Local mock for the backend's nearby-alert flow (item 5). Shapes match
 * src/lib/types.ts `NearbyAlert`, which mirrors the backend's AlertMessage
 * schema (llm_integration/schemas/types.py) — swapping to the real endpoint
 * only means flipping USE_MOCK_ALERTS in src/lib/api.ts.
 *
 * The real pipeline: report → LLM analysis → alert_dispatcher finds users
 * within ALERT_RADIUS_METERS (500m) and pushes an AlertMessage. Here we mimic
 * the receiving end: a static demo alert near the Chicago hotspot, plus any
 * alerts "dispatched" locally after this session's own urgent reports.
 *
 * TODO(osman): delete this file's usage once Seymen exposes the dispatcher
 * over HTTP (suggested: GET /api/v1/alerts/nearby).
 */

import type { LngLat, NearbyAlert } from "./types";
import { ALERT_RADIUS_METERS, distanceMeters } from "./nearbyAlerts";

/**
 * Static demo alert pinned near the Chicago demo center, modeled after the
 * backend's mocks/sample_alerts.json — so the alert UI is visible on first
 * launch without having to submit a report.
 */
const STATIC_ALERTS: NearbyAlert[] = [
  {
    alert_id: "alert_demo_001",
    title: "Dikkat: Yakınınızda tehlike bildirimi",
    body: "400m yakınınızda şüpheli aktivite rapor edildi.",
    latitude: 41.8815,
    longitude: -87.632,
    risk_score: 60,
    category: "suspicious",
    created_at: new Date().toISOString(),
    status: "sent",
  },
];

/** Alerts "dispatched" for reports submitted this session (mock-only). */
const sessionAlerts: NearbyAlert[] = [];

/**
 * Mimics the backend dispatcher for a just-submitted report: creates an alert
 * at the report location so the map screen shows it on return — the same
 * end result alert_dispatcher.dispatch_alerts() will produce server-side.
 */
export function addMockDispatchedAlert(
  lng: number,
  lat: number,
  urgent: boolean
): void {
  sessionAlerts.push({
    alert_id: `alert_local_${Date.now()}`,
    title: urgent
      ? "ACİL: Yakınınızda tehlike bildirimi"
      : "Dikkat: Yakınınızda tehlike bildirimi",
    body: urgent
      ? "Hemen yakınınızda acil durum bildirildi. Alternatif rota önerilir."
      : "Yakınınızda yeni bir tehlike bildirimi alındı.",
    latitude: lat,
    longitude: lng,
    risk_score: urgent ? 90 : 55,
    category: urgent ? "violent" : "suspicious",
    created_at: new Date().toISOString(),
    status: "sent",
  });
}

/**
 * Returns alerts within the dispatch radius of the given location, nearest
 * first — the same filtering find_nearby_users() applies server-side, from
 * the receiving user's perspective.
 */
export function getMockNearbyAlerts(location: LngLat): NearbyAlert[] {
  const [lng, lat] = location;
  return [...STATIC_ALERTS, ...sessionAlerts]
    .map((alert) => ({
      alert,
      dist: distanceMeters(lat, lng, alert.latitude, alert.longitude),
    }))
    .filter(({ dist }) => dist <= ALERT_RADIUS_METERS)
    .sort((a, b) => a.dist - b.dist)
    // Carry the measured distance like the live path does, so the card's
    // "120m uzakta" line renders identically in mock mode.
    .map(({ alert, dist }) => ({ ...alert, distance_m: dist }));
}
