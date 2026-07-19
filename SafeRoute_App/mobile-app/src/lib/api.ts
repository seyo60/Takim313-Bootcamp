import axios, { AxiosError } from "axios";
import type {
  LngLat,
  ReportRequest,
  ReportResponse,
  RiskPoint,
  RouteRequest,
  RouteResponse,
  StreetRiskExplanation,
} from "./types";
import { buildMockRouteResponse } from "./mockRoute";
import { addMockReportedPoint, getMockRiskPoints } from "./mockHeatmap";
import { buildMockStreetRisk } from "./mockStreetRisk";

/**
 * While the backend endpoints are not live yet, API calls below return local
 * mock data (shaped exactly like src/lib/types.ts). Flip to false once
 * Seymen's backend is reachable — nothing else needs to change.
 *
 * TODO(osman): set to false when POST /api/v1/route is live (§A in end-to-end.md).
 */
const USE_MOCK_ROUTE = true;

/** TODO(osman): set to false when GET /api/v1/heatmap is live (§B). */
const USE_MOCK_HEATMAP = true;

/** TODO(osman): set to false when POST /api/v1/report is live (§C). */
const USE_MOCK_REPORT = true;

/**
 * TODO(osman): set to false when POST /api/v1/street-risk-explanation is live
 * (§D). Note: develop already has a live LLM module — coordinate with Seymen on
 * the exact route + payload before flipping this.
 */
const USE_MOCK_STREET_RISK = true;

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

/**
 * Fetches the safest route between two coordinates from the backend
 * (POST /api/v1/route). Returns the parsed response on success, or null on any
 * failure — never throws, so callers/UI don't need try/catch just to render.
 *
 * While USE_MOCK_ROUTE is true, resolves with local mock data instead of
 * hitting the network (same RouteResponse shape).
 */
export async function getRoute(
  start: LngLat,
  end: LngLat
): Promise<RouteResponse | null> {
  if (USE_MOCK_ROUTE) {
    // Small delay so loading states are visible/testable in the UI.
    await new Promise((resolve) => setTimeout(resolve, 400));
    return buildMockRouteResponse(start, end);
  }

  try {
    // TODO(osman): body field names pending §A (start/end arrays vs
    // start_lat/start_lng) — adjust here + types.ts if Seymen picks otherwise.
    // We send the device's local hour so risk matches the time of day; drop it
    // if the backend decides to derive the hour server-side.
    const body: RouteRequest = { start, end, hour: new Date().getHours() };
    const response = await api.post<RouteResponse>("/api/v1/route", body);
    return response.data;
  } catch (error) {
    logRequestError("getRoute (POST /api/v1/route)", error);
    return null;
  }
}

/**
 * Fetches all risk points for the heatmap layer (GET /api/v1/heatmap).
 * Returns null on failure — never throws.
 *
 * While USE_MOCK_HEATMAP is true, resolves with local mock clusters instead.
 *
 * TODO(osman): §B pending — response may be a GeoJSON FeatureCollection
 * instead of a flat array; adjust the parsing here (only here) if so.
 * TODO(osman): if the full-city payload turns out too heavy, switch to
 * GET /api/v1/heatmap/nearby with the user's location + radius.
 */
export async function getHeatmap(): Promise<RiskPoint[] | null> {
  if (USE_MOCK_HEATMAP) {
    await new Promise((resolve) => setTimeout(resolve, 300));
    return getMockRiskPoints();
  }

  try {
    const response = await api.get<RiskPoint[]>("/api/v1/heatmap");
    return response.data;
  } catch (error) {
    logRequestError("getHeatmap (GET /api/v1/heatmap)", error);
    return null;
  }
}

/**
 * Submits a danger report (POST /api/v1/report). The backend acknowledges and
 * analyzes the text in the background (LLM) — no risk score in the response.
 * Returns null on failure — never throws.
 *
 * In mock mode also plants a local high-risk point at the reported location,
 * mimicking what the backend pipeline will eventually do, so the
 * "report → new hot spot on the heatmap" flow is demoable today.
 *
 * TODO(osman): §C pending — confirm body field names and that the response is
 * acknowledgement-only; if analysis comes back synchronously, surface it in
 * the report screen.
 */
export async function submitReport(
  report: ReportRequest
): Promise<ReportResponse | null> {
  if (USE_MOCK_REPORT) {
    await new Promise((resolve) => setTimeout(resolve, 600));
    addMockReportedPoint(report.lng, report.lat);
    return { ok: true, id: `mock-${Date.now()}` };
  }

  try {
    const response = await api.post<ReportResponse>("/api/v1/report", report);
    return response.data;
  } catch (error) {
    logRequestError("submitReport (POST /api/v1/report)", error);
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
 *   pick the level/text. The real backend derives risk from the location and
 *   ignores this; kept in the signature so mock mode has interesting output.
 */
export async function getStreetRiskExplanation(
  location: LngLat,
  riskScore: number
): Promise<StreetRiskExplanation | null> {
  if (USE_MOCK_STREET_RISK) {
    await new Promise((resolve) => setTimeout(resolve, 500));
    return buildMockStreetRisk(riskScore);
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
