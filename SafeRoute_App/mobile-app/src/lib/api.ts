import axios, { AxiosError } from "axios";
import * as Crypto from "expo-crypto";
import type {
  HexRisk,
  LngLat,
  ReportRequest,
  ReportResponse,
  RouteProfile,
  RouteRequest,
  RouteResponse,
  StreetRiskExplanation,
  AccountDeletionResponse,
  MyReportsResponse,
  UserProfile,
} from "./types";
import { buildMockRouteResponse } from "./mockRoute";
import { addMockReportedHex, getMockHexRisk } from "./mockHeatmap";
import { buildMockStreetRisk } from "./mockStreetRisk";
import { appStorage } from "./secureStorage";
import { supabase } from "./supabase";

/**
 * While the backend endpoints are not live yet, API calls below return local
 * mock data (shaped exactly like src/lib/types.ts). Flip to false once
 * Seymen's backend is reachable — nothing else needs to change.
 *
 * TODO(osman): set to false when POST /api/v1/route is live (§A in end-to-end.md).
 */
const IS_MOCK_ENV = process.env.EXPO_PUBLIC_USE_MOCK_DATA === "true";

const USE_MOCK_ROUTE = IS_MOCK_ENV;
const USE_MOCK_HEATMAP = IS_MOCK_ENV;
const USE_MOCK_REPORT = IS_MOCK_ENV;
const USE_MOCK_STREET_RISK = IS_MOCK_ENV;

/**
 * Backend base URL. Set EXPO_PUBLIC_API_BASE_URL in .env to your teammate's
 * FastAPI address (e.g. a temporary ngrok tunnel like
 * https://something.ngrok-free.dev). Because it's prefixed EXPO_PUBLIC_, Expo
 * inlines it into the bundle at build/start time.
 */
const baseURL = process.env.EXPO_PUBLIC_API_BASE_URL?.replace(/\/$/, "");
if (!baseURL && !IS_MOCK_ENV) {
  throw new Error(
    "EXPO_PUBLIC_API_BASE_URL eksik. Gerçek API veya açıkça etkinleştirilmiş mock veri gerekir."
  );
}

export const api = axios.create({
  baseURL: baseURL ?? "http://mock.invalid",
  timeout: 15000, // fail fast instead of hanging on a dead tunnel
  headers: {
    "ngrok-skip-browser-warning": "true",
  },
});

api.interceptors.request.use(async (request) => {
  if (supabase) {
    let { data } = await supabase.auth.getSession();
    const expiresAt = data.session?.expires_at;
    const nowSec = Math.floor(Date.now() / 1000);
    // Süresi dolmak üzere / dolmuşsa yenile; aksi halde 401 yarışı oluşuyor.
    if (data.session && typeof expiresAt === "number" && expiresAt <= nowSec + 60) {
      const refreshed = await supabase.auth.refreshSession();
      data = refreshed.data;
    }
    if (data.session?.access_token) {
      request.headers.Authorization = `Bearer ${data.session.access_token}`;
    }
  }
  return request;
});

function extractApiErrorDetail(error: unknown): string {
  if (!axios.isAxiosError(error)) return "";
  const data = error.response?.data as
    | { detail?: string | { msg?: string }[]; error?: { message?: string } }
    | undefined;
  if (!data) return "";
  if (typeof data.error?.message === "string" && data.error.message.trim()) {
    return data.error.message.trim();
  }
  if (typeof data.detail === "string" && data.detail.trim()) {
    return data.detail.trim();
  }
  if (Array.isArray(data.detail) && data.detail[0]?.msg) {
    return String(data.detail[0].msg);
  }
  return "";
}

function logRequestError(context: string, error: unknown): void {
  if (axios.isAxiosError(error)) {
    const axiosError = error as AxiosError;
    if (axiosError.response) {
      const status = axiosError.response.status;
      const data = axiosError.response.data as
        | { detail?: string; error?: { message?: string; fields?: string[] } }
        | undefined;
      const detail = extractApiErrorDetail(error);
      const fields = data?.error?.fields?.length
        ? ` fields=${data.error.fields.join(",")}`
        : "";
      const hint =
        status >= 500
          ? " — backend/tunnel is up but not serving. Is the FastAPI server running behind this URL?"
          : "";
      console.warn(
        `[api] ${context} failed: HTTP ${status}${hint}${detail ? ` — ${detail}` : ""}${fields}`
      );
    } else if (axiosError.request) {
      console.warn(
        `[api] ${context} failed: no response (network/timeout). ${axiosError.message}`
      );
    } else {
      console.warn(`[api] ${context} failed: ${axiosError.message}`);
    }
  } else {
    console.warn(`[api] ${context} failed with unknown error:`, error);
  }
}

/**
 * Timer/sleep işlemini AbortSignal ile anında iptal edilebilir yapar.
 */
function cancelableSleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      return reject(new Error("Request aborted during retry sleep"));
    }
    const timer = setTimeout(() => {
      resolve();
    }, ms);

    signal?.addEventListener(
      "abort",
      () => {
        clearTimeout(timer);
        reject(new Error("Request aborted during retry sleep"));
      },
      { once: true }
    );
  });
}

/**
 * Fetches the safest route between two coordinates from the backend
 * (POST /api/v1/route). Includes jittered exponential backoff for HTTP 503 overload.
 */
export async function getRoute(
  start: LngLat,
  end: LngLat,
  maxRetries = 3,
  signal?: AbortSignal,
  profile: RouteProfile = "balanced"
): Promise<RouteResponse | null> {
  if (USE_MOCK_ROUTE) {
    await new Promise((resolve) => setTimeout(resolve, 400));
    return buildMockRouteResponse(start, end, profile);
  }

  const body: RouteRequest = {
    start,
    end,
    hour: new Date().getHours(),
    profile,
    // Rota geneli DeepSeek açıklaması — orta nokta yerine tüm rota bağlamı.
    // Ayrı /street-risk-explanation çağrısını gereksiz kılar.
    include_risk_explanation: true,
  };

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    if (signal?.aborted) {
      console.warn("[api] getRoute request aborted by caller.");
      return null;
    }
    try {
      const response = await api.post<RouteResponse>("/api/v1/route", body, {
        signal,
        timeout: 60000,
      });
      return response.data;
    } catch (error) {
      if (axios.isCancel(error) || signal?.aborted) {
        console.warn("[api] getRoute request cancelled.");
        return null;
      }
      if (
        axios.isAxiosError(error) &&
        error.response?.status === 503 &&
        attempt < maxRetries
      ) {
        const retryAfterHeader = error.response.headers["retry-after"];
        const retryAfterSec = retryAfterHeader ? parseInt(retryAfterHeader, 10) : 10;
        const expMs = Math.pow(2, attempt + 1) * 1000 + Math.random() * 500;
        // Retry-After ve Exponential Backoff arasındaki MAKSİMUM bekleme süresi
        const waitMs = Math.max(retryAfterSec * 1000, expMs);
        console.warn(
          `[api] HTTP 503 Service Unavailable — waiting max(Retry-After ${retryAfterSec}s, ExpBackoff) = ${Math.round(
            waitMs
          )}ms (attempt ${attempt + 1}/${maxRetries})`
        );
        try {
          await cancelableSleep(waitMs, signal);
        } catch {
          console.warn("[api] Retry sleep cancelled via AbortController.");
          return null;
        }
        continue;
      }
      logRequestError("getRoute (POST /api/v1/route)", error);
      return null;
    }
  }
  return null;
}

/**
 * Fetches the hexagon-risk cells for the heatmap layer (GET /api/v1/heatmap).
 */
export async function getHeatmap(signal?: AbortSignal): Promise<HexRisk[] | null> {
  if (USE_MOCK_HEATMAP) {
    await new Promise((resolve) => setTimeout(resolve, 300));
    return getMockHexRisk();
  }

  try {
    const response = await api.get<HexRisk[]>("/api/v1/heatmap", { signal });
    return response.data;
  } catch (error) {
    if (axios.isCancel(error) || signal?.aborted) return null;
    logRequestError("getHeatmap (GET /api/v1/heatmap)", error);
    return null;
  }
}

let _cachedInstallationId: string | null = null;
const INSTALLATION_ID_KEY = "saferoute.installation-id.v1";

export async function getOrCreateInstallationId(): Promise<string> {
  if (_cachedInstallationId) {
    return _cachedInstallationId;
  }
  const stored = await appStorage.get(INSTALLATION_ID_KEY);
  if (stored) {
    _cachedInstallationId = stored;
    return stored;
  }
  _cachedInstallationId = Crypto.randomUUID();
  await appStorage.set(INSTALLATION_ID_KEY, _cachedInstallationId);
  return _cachedInstallationId;
}

/**
 * Submits a danger report (POST /api/v1/report).
 */
export type SubmitReportResult =
  | { ok: true; data: ReportResponse }
  | { ok: false; error: string };

export async function submitReport(
  report: ReportRequest,
  signal?: AbortSignal
): Promise<SubmitReportResult> {
  const payload: ReportRequest = {
    ...report,
    reporter_installation_id:
      report.reporter_installation_id || (await getOrCreateInstallationId()),
  };

  if (USE_MOCK_REPORT) {
    const delay = report.priority === "urgent" ? 350 : 600;
    await new Promise((resolve) => setTimeout(resolve, delay));
    addMockReportedHex(report.lng, report.lat);
    return {
      ok: true,
      data: {
        ok: true,
        id: `mock-${Date.now()}`,
        tracking_token: "mock-token",
        status: "pending",
        message: "İhbarınız alındı ve topluluk doğrulaması bekleniyor.",
      },
    };
  }

  try {
    const response = await api.post<ReportResponse>("/api/v1/report", payload, { signal });
    return { ok: true, data: response.data };
  } catch (error) {
    if (axios.isCancel(error) || signal?.aborted) {
      return { ok: false, error: "İstek iptal edildi." };
    }
    logRequestError("submitReport (POST /api/v1/report)", error);
    const detail = extractApiErrorDetail(error);
    return {
      ok: false,
      error:
        detail ||
        "Bildirim gönderilemedi. Bağlantıyı kontrol edip tekrar dene.",
    };
  }
}


/**
 * Queries the real report processing status from backend with IDOR protection (GET /api/v1/reports/{id}?token={trackingToken}).
 */
export async function getReportStatus(
  reportId: string,
  trackingToken?: string,
  signal?: AbortSignal
): Promise<import("./types").ReportDetailResponse | null> {
  if (USE_MOCK_REPORT) {
    await new Promise((resolve) => setTimeout(resolve, 300));
    return {
      id: reportId,
      status: "accepted",
      category: "general",
      created_at: new Date().toISOString(),
    };
  }

  try {
    const response = await api.get<import("./types").ReportDetailResponse>(
      `/api/v1/reports/${reportId}`,
      {
        params: { token: trackingToken || "" },
        signal,
      }
    );
    return response.data;
  } catch (error) {
    if (axios.isCancel(error) || signal?.aborted) return null;
    logRequestError(`getReportStatus (GET /api/v1/reports/${reportId})`, error);
    return null;
  }
}

const activeStreetRiskRequests = new Map<string, Promise<StreetRiskExplanation | null>>();
const streetRiskCache = new Map<string, { data: StreetRiskExplanation; expiresAt: number }>();
const STREET_RISK_CACHE_TTL_MS = 60_000;

/**
 * Fetches the risk explanation for a street/route point
 * (POST /api/v1/street-risk-explanation).
 * Supports AbortSignal, in-flight request deduplication, and client caching.
 */
export async function getStreetRiskExplanation(
  location: LngLat,
  riskScore: number = 0,
  options: import("./types").GetStreetRiskExplanationOptions = {}
): Promise<StreetRiskExplanation | null> {
  const [lng, lat] = location;
  const cacheKey = `${lat.toFixed(4)},${lng.toFixed(4)}`;

  const cached = streetRiskCache.get(cacheKey);
  if (cached && Date.now() < cached.expiresAt) {
    return cached.data;
  }

  let requestPromise = activeStreetRiskRequests.get(cacheKey);

  if (!requestPromise) {
    if (USE_MOCK_STREET_RISK) {
      requestPromise = (async () => {
        await new Promise((resolve) => setTimeout(resolve, 300));
        const res = buildMockStreetRisk(riskScore);
        streetRiskCache.set(cacheKey, { data: res, expiresAt: Date.now() + STREET_RISK_CACHE_TTL_MS });
        return res;
      })();
    } else {
      requestPromise = (async () => {
        try {
          const response = await api.post<StreetRiskExplanation>(
            "/api/v1/street-risk-explanation",
            { lat, lng, hour: new Date().getHours() }
          );
          const data = response.data;
          if (data) {
            streetRiskCache.set(cacheKey, { data, expiresAt: Date.now() + STREET_RISK_CACHE_TTL_MS });
          }
          return data;
        } catch (error: unknown) {
          if (axios.isCancel(error)) {
            return null;
          }

          const status = axios.isAxiosError(error) ? error.response?.status : undefined;
          if (status && status >= 400 && status < 500) {
            logRequestError(
              `getStreetRiskExplanation (HTTP ${status} - No Retry)`,
              error
            );
            return null;
          }

          logRequestError(
            "getStreetRiskExplanation (POST /api/v1/street-risk-explanation)",
            error
          );
          return null;
        } finally {
          activeStreetRiskRequests.delete(cacheKey);
        }
      })();
    }
    activeStreetRiskRequests.set(cacheKey, requestPromise);
  }

  if (options.signal) {
    if (options.signal.aborted) return null;
    return new Promise((resolve) => {
      const onAbort = () => resolve(null);
      options.signal!.addEventListener("abort", onAbort, { once: true });
      requestPromise!.then((res) => {
        options.signal?.removeEventListener("abort", onAbort);
        if (!options.signal?.aborted) resolve(res);
      }).catch(() => {
        options.signal?.removeEventListener("abort", onAbort);
        resolve(null);
      });
    });
  }

  return requestPromise;
}

const activeMapReportRequests = new Map<string, Promise<import("./types").MapReportsResponse | null>>();

/**
 * Fetches recent community reports for the map layer (GET /api/v1/reports/map).
 * Supports AbortSignal and in-flight request deduplication.
 * Fails safely with an empty report structure on error.
 */
export async function getRecentMapReports(
  options: import("./types").GetRecentMapReportsOptions = {}
): Promise<import("./types").MapReportsResponse | null> {
  const { minutes = 60, bbox, category, signal } = options;
  const reqKey = `${minutes}_${bbox || ""}_${category || ""}`;

  if (activeMapReportRequests.has(reqKey)) {
    return activeMapReportRequests.get(reqKey)!;
  }

  const promise = (async () => {
    try {
      const response = await api.get<import("./types").MapReportsResponse>("/api/v1/reports/map", {
        params: { minutes, bbox, category },
        signal,
      });
      return response.data;
    } catch (error) {
      if (axios.isCancel(error) || signal?.aborted) return null;
      logRequestError("getRecentMapReports (GET /api/v1/reports/map)", error);
      return null;
    } finally {
      activeMapReportRequests.delete(reqKey);
    }
  })();

  activeMapReportRequests.set(reqKey, promise);
  return promise;
}

const activeHeatmapMapRequests = new Map<string, Promise<import("./types").HeatmapGeoJSONResponse | null>>();

/**
 * Fetches regional risk heatmap GeoJSON Polygons for Mapbox (GET /api/v1/heatmap/map).
 * Supports in-flight deduplication, AbortSignal, and fail-soft behavior.
 */
export async function getRiskHeatmapMap(
  options: import("./types").GetRiskHeatmapMapOptions = {}
): Promise<import("./types").HeatmapGeoJSONResponse | null> {
  const { bbox, channel = "total", include_no_data = true, signal } = options;
  const reqKey = `heatmap_map:${channel}:${bbox || "all"}:${include_no_data}`;

  if (activeHeatmapMapRequests.has(reqKey)) {
    return activeHeatmapMapRequests.get(reqKey)!;
  }

  const promise = (async () => {
    try {
      const response = await api.get<import("./types").HeatmapGeoJSONResponse>("/api/v1/heatmap/map", {
        params: { bbox, channel, include_no_data },
        signal,
      });
      return response.data;
    } catch (error) {
      if (axios.isCancel(error) || signal?.aborted) return null;
      logRequestError("getRiskHeatmapMap (GET /api/v1/heatmap/map)", error);
      return null;
    } finally {
      activeHeatmapMapRequests.delete(reqKey);
    }
  })();

  activeHeatmapMapRequests.set(reqKey, promise);
  return promise;
}

export async function registerDevice(payload: {
  expo_push_token: string;
  lat?: number;
  lng?: number;
}): Promise<boolean> {
  try {
    await api.post("/api/v1/me/device", payload);
    return true;
  } catch (error) {
    logRequestError("registerDevice (POST /api/v1/me/device)", error);
    return false;
  }
}

export async function updateMyLocation(lat: number, lng: number): Promise<boolean> {
  try {
    await api.post("/api/v1/me/location", { lat, lng });
    return true;
  } catch (error) {
    logRequestError("updateMyLocation (POST /api/v1/me/location)", error);
    return false;
  }
}

export interface PendingAlert {
  alert_id: string;
  event_id: string | null;
  phase?: "witness_request" | "broadcast" | string;
  title: string;
  body: string;
  latitude: number;
  longitude: number;
  distance_m: number;
  confirm_count: number;
  created_at?: string | null;
  llm_method?: string | null;
}

export async function getPendingAlerts(
  lat?: number,
  lng?: number
): Promise<PendingAlert[]> {
  try {
    const response = await api.get<PendingAlert[]>("/api/v1/me/alerts/pending", {
      params: { lat, lng },
    });
    return response.data ?? [];
  } catch (error) {
    logRequestError("getPendingAlerts (GET /api/v1/me/alerts/pending)", error);
    return [];
  }
}

export async function respondToAlert(
  eventId: string,
  response: "confirm" | "deny" | "unsure"
): Promise<{
  ok: boolean;
  message?: string;
  broadcast_sent?: boolean;
  broadcast_alert_id?: string | null;
} | null> {
  try {
    const result = await api.post<{
      ok: boolean;
      message: string;
      broadcast_sent: boolean;
      broadcast_alert_id?: string | null;
    }>(`/api/v1/alerts/${eventId}/respond`, { response });
    return result.data;
  } catch (error) {
    logRequestError(`respondToAlert (POST /api/v1/alerts/${eventId}/respond)`, error);
    return null;
  }
}

export async function getMyProfile(): Promise<UserProfile> {
  const response = await api.get<UserProfile>("/api/v1/me");
  return response.data;
}

export async function getMyReports(): Promise<MyReportsResponse> {
  const response = await api.get<MyReportsResponse>("/api/v1/me/reports");
  return response.data;
}

export async function deleteMyReport(reportId: string): Promise<boolean> {
  try {
    await api.delete(`/api/v1/me/reports/${encodeURIComponent(reportId)}`);
    return true;
  } catch (error) {
    logRequestError(`deleteMyReport (DELETE /api/v1/me/reports/${reportId})`, error);
    return false;
  }
}

export async function startJuryDemoAlert(
  lat?: number,
  lng?: number
): Promise<{ ok: boolean; alert: PendingAlert; message: string } | null> {
  try {
    const response = await api.post<{
      ok: boolean;
      alert: PendingAlert;
      message: string;
    }>(
      "/api/v1/me/alerts/jury-demo",
      lat != null && lng != null ? { lat, lng } : {}
    );
    return response.data;
  } catch (error) {
    logRequestError("startJuryDemoAlert (POST /api/v1/me/alerts/jury-demo)", error);
    return null;
  }
}

export async function requestAccountDeletion(): Promise<AccountDeletionResponse> {
  const response = await api.delete<AccountDeletionResponse>("/api/v1/me");
  return response.data;
}

export async function cancelAccountDeletion(): Promise<AccountDeletionResponse> {
  const response = await api.post<AccountDeletionResponse>(
    "/api/v1/me/deletion-cancel"
  );
  return response.data;
}
