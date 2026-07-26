import { useCallback, useEffect, useState } from "react";
import { getHeatmap } from "@/lib/api";
import type { HexRisk } from "@/lib/types";

export type HeatmapStatus = "loading" | "ready" | "error";

export interface UseHeatmapResult {
  points: HexRisk[];
  status: HeatmapStatus;
  /** Reloads the risk cells (e.g. after a danger report is submitted). */
  refetch: () => void;
}

/**
 * Loads the hexagon-risk cells on mount; `refetch()` reloads them on demand.
 * While a refetch is in flight the previous cells stay on screen so the
 * layer doesn't flicker.
 *
 * `status` is derived during render by comparing the settled result against the
 * request the current inputs call for, instead of being written into state by
 * the effect — that used to cost a second render pass on every load.
 */
export function useHeatmap(): UseHeatmapResult {
  // Last successful cells. Kept across refetches on purpose: the layer keeps
  // rendering these while the next request is in flight, so it never blinks.
  const [points, setPoints] = useState<HexRisk[]>([]);
  // The settled outcome of a request, tagged with which request it answers.
  const [fetched, setFetched] = useState<{ key: number; ok: boolean } | null>(
    null
  );
  // Bumping this re-runs the fetch effect.
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      const fresh = await getHeatmap();
      if (cancelled) return;
      // Only replace the cells on success — a failed refetch leaves the
      // previous ones on the map rather than emptying it.
      if (fresh) setPoints(fresh);
      setFetched({ key: nonce, ok: fresh !== null });
    })();

    return () => {
      cancelled = true;
    };
  }, [nonce]);

  const refetch = useCallback(() => setNonce((n) => n + 1), []);

  const settled = fetched?.key === nonce ? fetched : null;
  const status: HeatmapStatus =
    settled === null ? "loading" : settled.ok ? "ready" : "error";

  return { points, status, refetch };
}
