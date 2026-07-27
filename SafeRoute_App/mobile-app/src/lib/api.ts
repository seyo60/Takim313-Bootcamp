import axios, { AxiosError } from "axios";
import type {
  HexRisk,
  LngLat,
  NearbyAlert,
  ReportRequest,
  ReportResponse,
  RouteRequest,
  RouteResponse,
  StreetRiskExplanation,
} from "./types";
import { buildMockRouteResponse } from "./mockRoute";
import { addMockReportedHex, getMockHexRisk } from "./mockHeatmap";
import {
  buildGuardrailFallback,
  buildMockStreetRisk,
} from "./mockStreetRisk";
import { addMockDispatchedAlert, getMockNearbyAlerts } from "./mockAlerts";
import { ALERT_RADIUS_METERS, riskPointsToAlerts } from "./nearbyAlerts";

/**
 * Mock flags. Route/heatmap/report went LIVE against Seymen's backend
 * (backend/main.py — contracts verified field-by-field). Set a flag back to
 * true to demo without a running backend; nothing else needs to change.
 *
 * Requires EXPO_PUBLIC_API_BASE_URL in .env pointing at the FastAPI server.
 */
const USE_MOCK_ROUTE = false;

const USE_MOCK_HEATMAP = false;

const USE_MOCK_REPORT = false;

/**
 * Still mock: the backend's street_explainer service is NOT exposed over HTTP
 * yet (no endpoint in main.py). TODO(osman): flip when Seymen wires it
 * (suggested route: POST /api/v1/street-risk-explanation).
 */
const USE_MOCK_STREET_RISK = true;

/**
 * LIVE — but indirectly. The alert_dispatcher service still has no HTTP route,
 * so nearby alerts are derived from the live GET /api/v1/heatmap/nearby risk
 * points instead (see lib/nearbyAlerts.ts for why that's the same signal).
 * Set to true to demo the alert UI without a backend.
 */
const USE_MOCK_ALERTS = false;

/**
 * Backend base URL. Set EXPO_PUBLIC_API_BASE_URL in .env to your teammate's
 * FastAPI address (e.g. a temporary ngrok tunnel like
 * https://something.ngrok-free.dev). Because it's prefixed EXPO_PUBLIC_, Expo
 * inlines it into the bundle at build/start time.
 */
const baseURL = process.env.EXPO_PUBLIC_API_BASE_URL;

if (!baseURL) {
  console.warn(
    "[api] EXPO_PUBLIC_API_BASE_URL is not set — backend requests will fail. " +
      "Add it to .env and restart the dev server."
  );
}

export const api = axios.create({
  baseURL,
  timeout: 10000, // fail fast instead of hanging on a dead tunnel
  headers: {
    // ngrok's free tier shows an interstitial HTML page unless this header is
    // present; it makes the tunnel return the raw API response.
    "ngrok-skip-browser-warning": "true",
  },
});

/**
 * Narrow, readable error logging shared by the API calls below.
 *
 * Uses console.warn (not console.error) on purpose: these are all handled,
 * recovered-from conditions (the caller returns null and the UI keeps working),
 * so they shouldn't trip React Native's full-screen red LogBox overlay as if the
 * app crashed. A down backend should be a warning, not a crash.
 */
function logRequestError(context: string, error: unknown): void {
  if (axios.isAxiosError(error)) {
    const axiosError = error as AxiosError;
    if (axiosError.response) {
      const status = axiosError.response.status;
      // Server responded with a non-2xx status. A 5xx here is usually the tunnel
      // itself (e.g. ngrok 502) reporting the backend isn't up / wrong port.
      const hint =
        status >= 500
          ? " — backend/tunnel is up but not serving. Is the FastAPI server running behind this ngrok URL?"
          : "";
      console.warn(
        `[api] ${context} failed: HTTP ${status}${hint}`,
        axiosError.response.data
      );
    } else if (axiosError.request) {
      // Request was made but no response (network down, timeout, bad tunnel).
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

/** Result of getRoute: the route, or a human-readable failure reason. */
export interface RouteFetchResult {
  route: RouteResponse | null;
  /**
   * Backend's explanatory 4xx detail when available (e.g. the coordinates are
   * outside Chicago's service area) — shown to the user instead of a generic
   * "backend unreachable" message. Null for network/5xx failures.
   */
  errorDetail: string | null;
}

/**
 * Fetches the safest route between two coordinates from the backend
 * (POST /api/v1/route — CONFIRMED contract: {start, end, hour?} with [lng,lat]
 * arrays). Never throws; on failure `route` is null and `errorDetail` may
 * carry the backend's message (Chicago-bounds rejections are HTTP 400 with a
 * user-appropriate Turkish detail).
 *
 * While USE_MOCK_ROUTE is true, resolves with local mock data instead.
 */
export async function getRoute(
  start: LngLat,
  end: LngLat
): Promise<RouteFetchResult> {
  if (USE_MOCK_ROUTE) {
    // Small delay so loading states are visible/testable in the UI.
    await new Promise((resolve) => setTimeout(resolve, 400));
    return { route: buildMockRouteResponse(start, end), errorDetail: null };
  }

  try {
    // Local hour rides along so risk can match the time of day (accepted by
    // the backend now, used in the risk formula in Faz 2).
    const body: RouteRequest = { start, end, hour: new Date().getHours() };
    const response = await api.post<RouteResponse>("/api/v1/route", body);
    return { route: response.data, errorDetail: null };
  } catch (error) {
    logRequestError("getRoute (POST /api/v1/route)", error);
    // Surface the backend's 4xx explanation (e.g. out of service area).
    if (axios.isAxiosError(error) && error.response) {
      const status = error.response.status;
      const detail = (error.response.data as { detail?: unknown })?.detail;
      if (status >= 400 && status < 500 && typeof detail === "string") {
        return { route: null, errorDetail: detail };
      }
    }
    return { route: null, errorDetail: null };
  }
}

/** Wire shape of GET /api/v1/heatmap — CONFIRMED flat array (main.py HeatmapPoint). */
interface BackendHeatmapPoint {
  lat: number;
  lng: number;
  total_risk: number;
}

/**
 * `total_risk` is on the same 0-100 scale the UI works in, so it maps straight
 * across. Clamped only to defend against a bad payload.
 *
 * History, because this was briefly wrong in both directions: an earlier
 * version multiplied by 10 here. That was inferred from the formulas in
 * backend/routing.py (`safety_score = 100 - avg_risk * 10`) at a time when the
 * only evidence available was a 12-row seed file holding one repeated value
 * (anlik_risk 9.8). The real dataset landed on 2026-07-25 (5.099 cells) and
 * settles it — data-science/ROUTE_SCORES_INFO.md states the pipeline was moved
 * to 0-100 precisely so the historical channel would carry weight against the
 * live channel, which crud.py already scores 0-100.
 *
 * With real data the ×10 was severe: 79% of all cells clamped to a flat 100 and
 * 86% crossed the nearby-alert threshold — a solid red heatmap and a permanent
 * critical alert.
 *
 * Note the alert threshold now behaves as designed rather than by accident.
 * `total_risk = historical*0.5 + live*0.5`, so a cell carrying only historical
 * risk tops out at 50 and never alerts on its own; it takes an actual live
 * report (LLM-scored) to push a cell past 60. Alerts mean "something was
 * reported near you", not "this is a statistically rough area" — which is
 * exactly what item 5 promises.
 */
function normalizeRisk(totalRisk: number): number {
  return Math.max(0, Math.min(100, totalRisk));
}

/**
 * Fetches the hexagon-risk cells for the heatmap layer (GET /api/v1/heatmap).
 * The backend keeps H3 indexing server-side and returns {lat, lng, total_risk}
 * per cell centroid; we map total_risk → risk_score here so the rest of the
 * app only knows the HexRisk shape. Returns null on failure — never throws.
 *
 * While USE_MOCK_HEATMAP is true, resolves with a local mock hexagon grid.
 *
 * TODO(osman): if the full-city payload turns out too heavy, switch to
 * GET /api/v1/heatmap/nearby (already live) with the user's location + radius.
 */
export async function getHeatmap(): Promise<HexRisk[] | null> {
  if (USE_MOCK_HEATMAP) {
    await new Promise((resolve) => setTimeout(resolve, 300));
    return getMockHexRisk();
  }

  try {
    const response = await api.get<BackendHeatmapPoint[]>("/api/v1/heatmap");
    return response.data.map((point) => ({
      lat: point.lat,
      lng: point.lng,
      risk_score: normalizeRisk(point.total_risk),
    }));
  } catch (error) {
    logRequestError("getHeatmap (GET /api/v1/heatmap)", error);
    return null;
  }
}

/** Result of submitReport: the acknowledgement, or a human-readable reason. */
export interface ReportSubmitResult {
  response: ReportResponse | null;
  /**
   * Backend's explanatory 4xx detail when available (e.g. the report is
   * outside Chicago's service area). Null for network/5xx failures.
   */
  errorDetail: string | null;
}

/**
 * Submits a danger report (POST /api/v1/report). The backend acknowledges and
 * analyzes the text in the background (LLM) — no risk score in the response.
 * Returns null on failure — never throws.
 *
 * In mock mode also plants a local high-risk hexagon at the reported location,
 * mimicking what the backend pipeline will eventually do, so the
 * "report → new hot spot on the heatmap" flow is demoable today.
 *
 * CONFIRMED contract (main.py): {text, lat, lng} → HTTP 201 {ok, id}. The
 * report is analyzed by the LLM in a background task and the heatmap risk is
 * updated server-side — refetching the heatmap after a report shows the new
 * hot spot for real now.
 *
 * The optional `priority` field ("urgent") rides along in the body; the
 * backend's pydantic model ignores unknown fields, so it's harmless until
 * supported. TODO(osman): ask Seymen to persist priority for urgent alerts.
 */
export async function submitReport(
  report: ReportRequest
): Promise<ReportSubmitResult> {
  if (USE_MOCK_REPORT) {
    // Urgent reports resolve faster to mimic a high-priority path.
    const delay = report.priority === "urgent" ? 350 : 600;
    await new Promise((resolve) => setTimeout(resolve, delay));
    addMockReportedHex(report.lng, report.lat);
    if (USE_MOCK_ALERTS) {
      addMockDispatchedAlert(
        report.lng,
        report.lat,
        report.priority === "urgent"
      );
    }
    return {
      response: { ok: true, id: `mock-${Date.now()}` },
      errorDetail: null,
    };
  }

  try {
    const response = await api.post<ReportResponse>("/api/v1/report", report);
    // Item 5, mock-only side effect: while the alert endpoint doesn't exist,
    // mimic the server-side dispatcher so "report → nearby alert" is demoable
    // even against the live backend. Removed when USE_MOCK_ALERTS flips.
    if (USE_MOCK_ALERTS && response.data?.ok) {
      addMockDispatchedAlert(
        report.lng,
        report.lat,
        report.priority === "urgent"
      );
    }
    return { response: response.data, errorDetail: null };
  } catch (error) {
    logRequestError("submitReport (POST /api/v1/report)", error);
    // The backend rejects out-of-area reports with an explanatory Turkish 400
    // (main.py _ensure_within_chicago) — show that instead of "gönderilemedi".
    if (axios.isAxiosError(error) && error.response) {
      const status = error.response.status;
      const detail = (error.response.data as { detail?: unknown })?.detail;
      if (status >= 400 && status < 500 && typeof detail === "string") {
        return { response: null, errorDetail: detail };
      }
    }
    return { response: null, errorDetail: null };
  }
}

/**
 * Fetches active danger alerts near the user (item 5) from the LIVE
 * GET /api/v1/heatmap/nearby endpoint: the risk points within
 * ALERT_RADIUS_METERS of the user, keeping only the high/critical ones and
 * shaping them into `NearbyAlert` cards (lib/nearbyAlerts.ts explains why the
 * heatmap is the right source until the LLM dispatcher is exposed).
 *
 * Returns null on failure — never throws, so the alert UI can simply stay
 * hidden rather than taking the map down with it.
 *
 * TODO(osman): when Seymen adds GET /api/v1/alerts/nearby, replace the request
 * below with it and drop the riskPointsToAlerts() call — the response already
 * matches `NearbyAlert`, so the UI does not change.
 */
export async function getNearbyAlerts(
  location: LngLat
): Promise<NearbyAlert[] | null> {
  if (USE_MOCK_ALERTS) {
    await new Promise((resolve) => setTimeout(resolve, 250));
    return getMockNearbyAlerts(location);
  }

  try {
    const [lng, lat] = location;
    const response = await api.get<BackendHeatmapPoint[]>(
      "/api/v1/heatmap/nearby",
      { params: { lat, lng, radius: ALERT_RADIUS_METERS } }
    );
    const points: HexRisk[] = response.data.map((point) => ({
      lat: point.lat,
      lng: point.lng,
      risk_score: normalizeRisk(point.total_risk),
    }));
    return riskPointsToAlerts(points, location);
  } catch (error) {
    logRequestError("getNearbyAlerts (GET /api/v1/heatmap/nearby)", error);
    return null;
  }
}

/**
 * Fetches the LLM risk explanation for a street/route point
 * (POST /api/v1/street-risk-explanation). Returns the parsed response on
 * success, or null on any failure — never throws, so the caller can render a
 * fallback state (item 2, AC #6 / item 6).
 *
 * While USE_MOCK_STREET_RISK is true, resolves with a synthesized explanation
 * derived from `riskScore` (same StreetRiskExplanation shape).
 *
 * @param location  representative point on the route being explained.
 * @param riskScore the route's 0-100 risk score — a MOCK-ONLY hint used to
 *   pick the level/text. Null when unknown (e.g. the shortest route, whose
 *   risk the backend doesn't report); the real backend derives risk from the
 *   location anyway, and the mock falls back to a mid-level answer.
 */
export async function getStreetRiskExplanation(
  location: LngLat,
  riskScore: number | null
): Promise<StreetRiskExplanation | null> {
  if (USE_MOCK_STREET_RISK) {
    await new Promise((resolve) => setTimeout(resolve, 500));
    // No risk data (e.g. the shortest route) → same safe answer the backend's
    // guardrails produce for insufficient data (item 6). With data, a normal
    // synthesized analysis.
    return riskScore === null
      ? buildGuardrailFallback()
      : buildMockStreetRisk(riskScore);
  }

  try {
    // TODO(osman): §D — confirm request shape (location + hour?) and the exact
    // route once develop's LLM module is wired to a public endpoint.
    const [lng, lat] = location;
    const response = await api.post<StreetRiskExplanation>(
      "/api/v1/street-risk-explanation",
      { lat, lng, hour: new Date().getHours() }
    );
    return response.data;
  } catch (error) {
    logRequestError(
      "getStreetRiskExplanation (POST /api/v1/street-risk-explanation)",
      error
    );
    return null;
  }
}
