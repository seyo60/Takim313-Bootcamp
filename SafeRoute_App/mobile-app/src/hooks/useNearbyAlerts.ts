import { useCallback, useEffect, useState } from "react";
import { getNearbyAlerts } from "@/lib/api";
import type { LngLat, NearbyAlert } from "@/lib/types";

export interface UseNearbyAlertsResult {
  /** Active alerts near the user, dismissed ones filtered out. */
  alerts: NearbyAlert[];
  /** Hides an alert for the rest of the session. */
  dismiss: (alertId: string) => void;
  /** Reloads alerts (e.g. after returning from the report screen). */
  refetch: () => void;
}

/**
 * Loads danger alerts near the given location (item 5) and keeps track of the
 * ones the user dismissed. Failures are silent by design: a broken alert feed
 * must never block the map, so on error we simply keep the last list.
 *
 * Re-fetches when the location changes meaningfully and on demand via
 * `refetch()` (the map screen calls it when returning from the report modal,
 * mirroring the heatmap refresh).
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

  const dismiss = useCallback((alertId: string) => {
    setDismissedIds((prev) => {
      const next = new Set(prev);
      next.add(alertId);
      return next;
    });
  }, []);

  const refetch = useCallback(() => setNonce((n) => n + 1), []);

  const visible = alerts.filter((alert) => !dismissedIds.has(alert.alert_id));

  return { alerts: visible, dismiss, refetch };
}
