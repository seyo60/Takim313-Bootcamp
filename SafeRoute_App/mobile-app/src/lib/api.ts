import axios, { AxiosError } from "axios";
import type {
  HexRisk,
  LngLat,
  ReportRequest,
  ReportResponse,
  RouteRequest,
  RouteResponse,
} from "./types";
import { buildMockRouteResponse } from "./mockRoute";
import { addMockReportedHex, getMockHexRisk } from "./mockHeatmap";

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
 * Fetches the hexagon-risk cells for the heatmap layer (GET /api/v1/heatmap).
 * Each cell is one H3 hexagon scored by the XGBoost batch prediction. Returns
 * null on failure — never throws.
 *
 * While USE_MOCK_HEATMAP is true, resolves with a local mock hexagon grid.
 *
 * TODO(osman): §B pending — response may be a GeoJSON FeatureCollection
 * instead of a flat array; adjust the parsing here (only here) if so.
 * TODO(osman): if the full-city payload turns out too heavy, switch to
 * GET /api/v1/heatmap/nearby with the user's location + radius.
 */
export async function getHeatmap(): Promise<HexRisk[] | null> {
  if (USE_MOCK_HEATMAP) {
    await new Promise((resolve) => setTimeout(resolve, 300));
    return getMockHexRisk();
  }

  try {
    const response = await api.get<HexRisk[]>("/api/v1/heatmap");
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
 * In mock mode also plants a local high-risk hexagon at the reported location,
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
    addMockReportedHex(report.lng, report.lat);
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
