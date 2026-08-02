import { useCallback, useEffect, useRef, useState } from "react";
import { AppState, type AppStateStatus } from "react-native";
import { getRecentMapReports } from "@/lib/api";
import type { MapReport } from "@/lib/types";

interface UseMapReportsOptions {
  enabled: boolean;
  category?: string;
  minutes?: number;
  bbox?: string;
}

interface UseMapReportsReturn {
  reports: MapReport[];
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

export function useMapReports({
  enabled,
  category,
  minutes = 60,
  bbox,
}: UseMapReportsOptions): UseMapReportsReturn {
  const [reports, setReports] = useState<MapReport[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const abortControllerRef = useRef<AbortController | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchReports = useCallback(async () => {
    if (!enabled) return;

    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;

    setLoading(true);
    setError(null);

    try {
      const res = await getRecentMapReports({
        minutes,
        bbox,
        category: category === "all" ? undefined : category,
        signal: controller.signal,
      });

      if (!controller.signal.aborted) {
        if (res && Array.isArray(res.reports)) {
          setReports(res.reports);
        } else {
          setReports([]);
        }
      }
    } catch {
      if (!controller.signal.aborted) {
        setError("Topluluk ihbarları yüklenemedi");
      }
    } finally {
      if (!controller.signal.aborted) {
        setLoading(false);
      }
    }
  }, [enabled, bbox, category, minutes]);

  useEffect(() => {
    if (!enabled) {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
        abortControllerRef.current = null;
      }
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      setReports([]);
      setLoading(false);
      setError(null);
      return;
    }

    // 1. Initial fetch when enabled
    fetchReports();

    // 2. Setup 60s polling
    intervalRef.current = setInterval(() => {
      fetchReports();
    }, 60000);

    // 3. AppState listener (pause when backgrounded, resume when active)
    const subscription = AppState.addEventListener(
      "change",
      (nextState: AppStateStatus) => {
        if (nextState === "active") {
          fetchReports();
          if (!intervalRef.current) {
            intervalRef.current = setInterval(() => {
              fetchReports();
            }, 60000);
          }
        } else {
          if (intervalRef.current) {
            clearInterval(intervalRef.current);
            intervalRef.current = null;
          }
        }
      }
    );

    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
        abortControllerRef.current = null;
      }
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      subscription.remove();
    };
  }, [enabled, fetchReports]);

  return {
    reports,
    loading,
    error,
    refetch: fetchReports,
  };
}
