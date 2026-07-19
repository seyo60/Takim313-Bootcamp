import { useCallback, useEffect, useState } from "react";
import { getStreetRiskExplanation } from "@/lib/api";
import type { LngLat, StreetRiskExplanation } from "@/lib/types";

export type StreetRiskStatus =
  | "idle" // no route selected yet
  | "loading" // request in flight
  | "ready" // explanation available
  | "error"; // request failed / LLM guardrail (item 6 fallback)

export interface UseStreetRiskResult {
  explanation: StreetRiskExplanation | null;
  status: StreetRiskStatus;
  /** Re-runs the failed request (fallback "Tekrar dene"). */
  retry: () => void;
}

/**
 * Fetches the LLM risk explanation for the currently selected route. Pass null
 * while no route is selected — the hook stays "idle" and does not hit the
 * backend. Re-fetches whenever the location or risk score changes (i.e. when
 * the user toggles between the safe and shortest routes), so the explanation
 * always matches the highlighted route.
 *
 * A stale response from a superseded request is ignored.
 */
export function useStreetRisk(
  location: LngLat | null,
  riskScore: number | null
): UseStreetRiskResult {
  const [result, setResult] = useState<Omit<UseStreetRiskResult, "retry">>({
    explanation: null,
    status: "idle",
  });
  // Bumping this re-runs the fetch effect with the same inputs.
  const [nonce, setNonce] = useState(0);

  // Depend on the values (not array identity) so an equal-but-new array
  // doesn't trigger a refetch.
  const lng = location?.[0];
  const lat = location?.[1];

  useEffect(() => {
    if (lng === undefined || lat === undefined || riskScore === null) {
      setResult({ explanation: null, status: "idle" });
      return;
    }

    let cancelled = false;
    setResult({ explanation: null, status: "loading" });

    (async () => {
      const explanation = await getStreetRiskExplanation([lng, lat], riskScore);
      if (cancelled) return;
      setResult(
        explanation
          ? { explanation, status: "ready" }
          : { explanation: null, status: "error" }
      );
    })();

    return () => {
      cancelled = true;
    };
  }, [lng, lat, riskScore, nonce]);

  const retry = useCallback(() => setNonce((n) => n + 1), []);

  return { ...result, retry };
}
