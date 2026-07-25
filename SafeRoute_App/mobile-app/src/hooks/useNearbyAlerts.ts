import { useCallback, useEffect, useState } from "react";
import { getNearbyAlerts } from "@/lib/api";
import { CRITICAL_RISK_SCORE } from "@/lib/nearbyAlerts";
import type { LngLat, NearbyAlert } from "@/lib/types";

/**
 * Never show more than this many cards at once (item 5, AC #5). Alerts arrive
 * nearest-first, so the cap keeps the closest — and the most actionable — ones.
 */
const MAX_VISIBLE_ALERTS = 3;

/**
 * How long a non-critical alert stays before it fades itself out. Long enough
 * to read two lines, short enough that a walk through a busy area doesn't leave
 * a wall of cards over the map.
 */
const AUTO_DISMISS_MS = 15_000;

/**
 * Poll interval. The backend analyzes each report in a background task, so a
 * danger reported near the user appears in the risk data a little after the
 * report succeeds — polling is what turns that into a proactive alert without a
 * WebSocket. 30s is well under the "walk 500m" timescale this feature cares
 * about and costs one small request.
 */
const POLL_INTERVAL_MS = 30_000;

export interface UseNearbyAlertsResult {
  /** Alerts to render: nearest first, dismissed removed, capped at 3. */
  alerts: NearbyAlert[];
  /** Hides an alert for the rest of the session. */
  dismiss: (alertId: string) => void;
  /** Reloads alerts (e.g. after returning from the report screen). */
  refetch: () => void;
}

/**
 * Loads danger alerts near the given location (item 5), polls for new ones,
 * caps the visible stack and auto-dismisses the non-critical ones.
 *
 * Failures are silent by design: a broken alert feed must never block the map,
 * so on error we simply keep the last list.
 *
 * Re-fetches when the location changes meaningfully, every POLL_INTERVAL_MS,
 * and on demand via `refetch()` (the map screen calls it when returning from
 * the report modal, mirroring the heatmap refresh).
 */
export function useNearbyAlerts(location: LngLat | null): UseNearbyAlertsResult {
  const [alerts, setAlerts] = useState<NearbyAlert[]>([]);
  const [dismissedIds, setDismissedIds] = useState<Set<string>>(new Set());
  const [nonce, setNonce] = useState(0);

  // Depend on values, not array identity, to avoid refetch loops.
  const lng = location?.[0];
  const lat = location?.[1];

  useEffect(() => {
    if (lng === undefined || lat === undefined) {
      setAlerts([]);
      return;
    }

    let cancelled = false;
    (async () => {
      const fresh = await getNearbyAlerts([lng, lat]);
      if (cancelled || !fresh) return; // error → keep whatever we had
      setAlerts(fresh);
    })();

    return () => {
      cancelled = true;
    };
  }, [lng, lat, nonce]);

  // Background polling — the "trigger" for proactive alerts (AC #4), now that
  // the data behind it is live instead of a mock timer.
  useEffect(() => {
    if (lng === undefined || lat === undefined) return;
    const timer = setInterval(() => setNonce((n) => n + 1), POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [lng, lat]);

  const dismiss = useCallback((alertId: string) => {
    setDismissedIds((prev) => {
      if (prev.has(alertId)) return prev; // no-op keeps the effect below stable
      const next = new Set(prev);
      next.add(alertId);
      return next;
    });
  }, []);

  const refetch = useCallback(() => setNonce((n) => n + 1), []);

  const visible = alerts
    .filter((alert) => !dismissedIds.has(alert.alert_id))
    .slice(0, MAX_VISIBLE_ALERTS);

  // Auto-dismiss (AC #5). Critical alerts are exempt: a card warning about an
  // 80+ risk zone should wait for the user to acknowledge it, not disappear on
  // its own.
  //
  // The ids are carried into the effect as a joined string so the dependency is
  // a primitive: re-renders that don't change *which* alerts are showing then
  // leave the running timers alone instead of restarting them.
  const expiringKey = visible
    .filter((alert) => alert.risk_score < CRITICAL_RISK_SCORE)
    .map((alert) => alert.alert_id)
    .join("|");

  useEffect(() => {
    if (!expiringKey) return;
    const timers = expiringKey
      .split("|")
      .map((alertId) => setTimeout(() => dismiss(alertId), AUTO_DISMISS_MS));
    return () => timers.forEach(clearTimeout);
  }, [expiringKey, dismiss]);

  return { alerts: visible, dismiss, refetch };
}
