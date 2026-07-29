import { useCallback, useEffect, useState } from "react";
import { getHeatmap } from "@/lib/api";
import type { HexRisk, LngLat } from "@/lib/types";

export type HeatmapStatus = "loading" | "ready" | "error";

export interface UseHeatmapResult {
  points: HexRisk[];
  status: HeatmapStatus;
  /** Reloads the risk cells (e.g. after a danger report is submitted). */
  refetch: () => void;
}

/**
 * Grid the location is snapped to before it becomes part of the request key,
 * in degrees. ~0.02° is roughly 2 km, comfortably inside the 5 km radius we
 * fetch — so the user can walk a couple of blocks (or GPS can jitter) without
 * triggering a refetch, and by the time the key does change they are still well
 * inside the data we already hold.
 */
const LOCATION_GRID_DEG = 0.02;

function snap(value: number): number {
  return Math.round(value / LOCATION_GRID_DEG) * LOCATION_GRID_DEG;
}

/**
 * Loads the hexagon-risk cells around `location`; `refetch()` reloads them on
 * demand. While a refetch is in flight the previous cells stay on screen so the
 * layer doesn't flicker.
 *
 * `status` is derived during render by comparing the settled result against the
 * request the current inputs call for, instead of being written into state by
 * the effect — that used to cost a second render pass on every load.
 */
export function useHeatmap(location: LngLat | null): UseHeatmapResult {
  // Last successful cells. Kept across refetches on purpose: the layer keeps
  // rendering these while the next request is in flight, so it never blinks.
  const [points, setPoints] = useState<HexRisk[]>([]);
  // The settled outcome of a request, tagged with which request it answers.
  const [fetched, setFetched] = useState<{ key: string; ok: boolean } | null>(
    null
  );
  // Bumping this re-runs the fetch effect.
  const [nonce, setNonce] = useState(0);

  const lng = location?.[0];
  const lat = location?.[1];
  const enabled = lng !== undefined && lat !== undefined;

  // Snapped so that ordinary movement doesn't re-request the same neighbourhood.
  const requestKey = enabled
    ? `${snap(lng)},${snap(lat)},${nonce}`
    : null;

  useEffect(() => {
    if (requestKey === null) return;

    let cancelled = false;
    (async () => {
      const fresh = await getHeatmap([lng as number, lat as number]);
      if (cancelled) return;
      // Only replace the cells on success — a failed refetch leaves the
      // previous ones on the map rather than emptying it.
      if (fresh) setPoints(fresh);
      setFetched({ key: requestKey, ok: fresh !== null });
    })();

    return () => {
      cancelled = true;
    };
    // lng/lat are deliberately absent: requestKey already encodes the snapped
    // position, and depending on the raw values would refetch on every GPS tick.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestKey]);

  const refetch = useCallback(() => setNonce((n) => n + 1), []);

  const settled = fetched?.key === requestKey ? fetched : null;
  const status: HeatmapStatus =
    settled === null ? "loading" : settled.ok ? "ready" : "error";

  return { points, status, refetch };
}
