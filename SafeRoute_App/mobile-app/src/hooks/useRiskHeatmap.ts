import { useCallback, useEffect, useRef, useState } from "react";
import { AppState, type AppStateStatus } from "react-native";
import { getRiskHeatmapMap } from "@/lib/api";
import type {
  HeatmapChannel,
  HeatmapGeoJSONResponse,
  HeatmapGeoJSONMetadata,
} from "@/lib/types";

export interface UseRiskHeatmapOptions {
  enabled: boolean;
  channel?: HeatmapChannel;
  bbox?: string;
  includeNoData?: boolean;
}

export interface UseRiskHeatmapResult {
  geoJson: HeatmapGeoJSONResponse | null;
  metadata: HeatmapGeoJSONMetadata | null;
  status: "idle" | "loading" | "success" | "error";
  error: string | null;
  refetch: () => Promise<void>;
}

export function useRiskHeatmap({
  enabled,
  channel = "total",
  bbox,
  includeNoData = true,
}: UseRiskHeatmapOptions): UseRiskHeatmapResult {
  const [geoJson, setGeoJson] = useState<HeatmapGeoJSONResponse | null>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [error, setError] = useState<string | null>(null);

  const abortControllerRef = useRef<AbortController | null>(null);
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastFetchTimeRef = useRef<number>(0);

  const fetchHeatmap = useCallback(async () => {
    if (!enabled) {
      setStatus("idle");
      return;
    }

    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;

    setStatus("loading");
    setError(null);

    const res = await getRiskHeatmapMap({
      channel,
      bbox,
      include_no_data: includeNoData,
      signal: controller.signal,
    });

    if (controller.signal.aborted) return;

    if (res) {
      setGeoJson(res);
      setStatus("success");
      lastFetchTimeRef.current = Date.now();
    } else {
      setStatus("error");
      setError("Risk verisi alınamadı.");
    }
  }, [enabled, channel, bbox, includeNoData]);

  useEffect(() => {
    if (!enabled) {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
      setGeoJson(null);
      setStatus("idle");
      return;
    }

    // Debounce bbox / channel changes
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }

    debounceTimerRef.current = setTimeout(() => {
      fetchHeatmap();
    }, 300);

    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
    };
  }, [enabled, channel, bbox, includeNoData, fetchHeatmap]);

  // AppState change listener: pause when backgrounded
  useEffect(() => {
    const handleAppStateChange = (nextState: AppStateStatus) => {
      if (nextState === "active" && enabled) {
        // Only refresh if 60+ seconds passed since last fetch
        if (Date.now() - lastFetchTimeRef.current > 60000) {
          fetchHeatmap();
        }
      }
    };

    const sub = AppState.addEventListener("change", handleAppStateChange);
    return () => sub.remove();
  }, [enabled, fetchHeatmap]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
    };
  }, []);

  return {
    geoJson,
    metadata: geoJson?.metadata ?? null,
    status,
    error,
    refetch: fetchHeatmap,
  };
}
