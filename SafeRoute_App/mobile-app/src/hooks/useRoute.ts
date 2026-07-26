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
  /**
   * Backend's explanatory message for a 4xx failure (e.g. destination outside
   * Chicago's service area). Null for network/server failures.
   */
  errorDetail: string | null;
  /** Re-runs the failed request (item 7 "Tekrar dene"). */
  retry: () => void;
}

/** A settled response, tagged with the request that produced it. */
interface FetchedRoute {
  /** The requestKey this result answers — stale results are ignored. */
  key: string;
  route: RouteResponse | null;
  errorDetail: string | null;
}

/**
 * Fetches the safest route whenever both endpoints are known. Pass null while
 * the destination hasn't been chosen yet — the hook stays "idle" and does not
 * hit the backend.
 *
 * Re-fetches when start/end coordinates change; a stale response from a
 * superseded request is ignored.
 *
 * "idle" and "loading" are DERIVED during render from the current inputs rather
 * than written into state by the effect. Writing them in the effect meant every
 * change rendered once with the old status and then immediately again with the
 * new one — two passes per change, on a screen that also redraws map layers.
 * Deriving also removes the one-frame window where a new destination still
 * showed the previous route's result.
 */
export function useRoute(
  start: LngLat | null,
  end: LngLat | null
): UseRouteResult {
  const [fetched, setFetched] = useState<FetchedRoute | null>(null);
  // Bumping this re-runs the fetch effect with the same coordinates.
  const [nonce, setNonce] = useState(0);

  // Depend on the coordinate values (not array identity) so a re-render with
  // an equal-but-new array doesn't refetch.
  const startLng = start?.[0];
  const startLat = start?.[1];
  const endLng = end?.[0];
  const endLat = end?.[1];

  const enabled =
    startLng !== undefined &&
    startLat !== undefined &&
    endLng !== undefined &&
    endLat !== undefined;

  // Identifies the request the current inputs call for. Null means "nothing to
  // request"; a change means whatever we already fetched is stale.
  const requestKey = enabled
    ? `${startLng},${startLat},${endLng},${endLat},${nonce}`
    : null;

  useEffect(() => {
    if (requestKey === null) return;

    let cancelled = false;
    (async () => {
      const { route, errorDetail } = await getRoute(
        [startLng as number, startLat as number],
        [endLng as number, endLat as number]
      );
      if (cancelled) return;
      setFetched({ key: requestKey, route, errorDetail });
    })();

    return () => {
      cancelled = true;
    };
  }, [requestKey, startLng, startLat, endLng, endLat]);

  const retry = useCallback(() => setNonce((n) => n + 1), []);

  // Derived: no endpoints → idle; result doesn't match the current request →
  // still loading; otherwise the settled outcome.
  const settled = fetched?.key === requestKey ? fetched : null;

  if (requestKey === null) {
    return { route: null, status: "idle", errorDetail: null, retry };
  }
  if (settled === null) {
    return { route: null, status: "loading", errorDetail: null, retry };
  }
  return settled.route
    ? { route: settled.route, status: "ready", errorDetail: null, retry }
    : {
        route: null,
        status: "error",
        errorDetail: settled.errorDetail,
        retry,
      };
}
