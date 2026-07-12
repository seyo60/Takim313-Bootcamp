import { useEffect, useState } from "react";
import { getHeatmap } from "@/lib/api";
import type { RiskPoint } from "@/lib/types";

export type HeatmapStatus = "loading" | "ready" | "error";

export interface UseHeatmapResult {
  points: RiskPoint[];
  status: HeatmapStatus;
}

/**
 * Loads the risk points once on mount. The heatmap data doesn't depend on any
 * user input, so there's nothing to re-fetch reactively yet.
 *
 * TODO(osman): item 6 — after a danger report is submitted, re-fetch so the
 * new report shows up (expose a refetch() when we get there).
 */
export function useHeatmap(): UseHeatmapResult {
  const [result, setResult] = useState<UseHeatmapResult>({
    points: [],
    status: "loading",
  });

  useEffect(() => {
    let cancelled = false;

    (async () => {
      const points = await getHeatmap();
      if (cancelled) return;
      setResult(
        points
          ? { points, status: "ready" }
          : { points: [], status: "error" }
      );
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  return result;
}
