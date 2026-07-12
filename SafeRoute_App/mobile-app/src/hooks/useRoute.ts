import { useCallback, useEffect, useState } from "react";
import { getRoute } from "@/lib/api";
import type { LngLat, RouteResponse } from "@/lib/types";

export type RouteStatus =
  | "idle" // no start/end yet (e.g. destination not chosen)
  | "loading" // request in flight
  | "ready" // route fetched and available
  | "error"; // request failed (backend down, tunnel dead, …)

export interface UseRouteResult {
  route: RouteResponse | null;
  status: RouteStatus;
  /** Re-runs the failed request (item 7 "Tekrar dene"). */
  retry: () => void;
}

/**
 * Fetches the safest route whenever both endpoints are known. Pass null while
 * the destination hasn't been chosen yet — the hook stays "idle" and does not
 * hit the backend.
 *
 * Re-fetches when start/end coordinates change; a stale response from a
 * superseded request is ignored.
 */
export function useRoute(
  start: LngLat | null,
  end: LngLat | null
): UseRouteResult {
  const [result, setResult] = useState<Omit<UseRouteResult, "retry">>({
    route: null,
    status: "idle",
  });
  // Bumping this re-runs the fetch effect with the same coordinates.
  const [nonce, setNonce] = useState(0);

  // Depend on the coordinate values (not array identity) so a re-render with
  // an equal-but-new array doesn't refetch.
  const startLng = start?.[0];
  const startLat = start?.[1];
  const endLng = end?.[0];
  const endLat = end?.[1];

  useEffect(() => {
    if (
      startLng === undefined ||
      startLat === undefined ||
      endLng === undefined ||
      endLat === undefined
    ) {
      setResult({ route: null, status: "idle" });
      return;
    }

    let cancelled = false;
    setResult({ route: null, status: "loading" });

    (async () => {
      const route = await getRoute([startLng, startLat], [endLng, endLat]);
      if (cancelled) return;
      setResult(
        route
          ? { route, status: "ready" }
          : { route: null, status: "error" }
      );
    })();

    return () => {
      cancelled = true;
    };
  }, [startLng, startLat, endLng, endLat, nonce]);

  const retry = useCallback(() => setNonce((n) => n + 1), []);

  return { ...result, retry };
}
