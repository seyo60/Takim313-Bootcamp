import { useCallback, useEffect, useState } from "react";
import { getHeatmap } from "@/lib/api";
import type { RiskPoint } from "@/lib/types";

export type HeatmapStatus = "loading" | "ready" | "error";

export interface UseHeatmapResult {
  points: RiskPoint[];
  status: HeatmapStatus;
  /** Reloads the risk points (e.g. after a danger report is submitted). */
  refetch: () => void;
}

/**
 * Loads the risk points on mount; `refetch()` reloads them on demand.
 * While a refetch is in flight the previous points stay on screen so the
 * layer doesn't flicker.
 */
export function useHeatmap(): UseHeatmapResult {
  const [points, setPoints] = useState<RiskPoint[]>([]);
  const [status, setStatus] = useState<HeatmapStatus>("loading");
  // Bumping this re-runs the fetch effect.
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setStatus("loading");

    (async () => {
      const fresh = await getHeatmap();
      if (cancelled) return;
      if (fresh) {
        setPoints(fresh);
        setStatus("ready");
      } else {
        setStatus("error");
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [nonce]);

  const refetch = useCallback(() => setNonce((n) => n + 1), []);

  return { points, status, refetch };
}
