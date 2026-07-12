import axios, { AxiosError } from "axios";
import type { LngLat, RouteRequest, RouteResponse } from "./types";
import { buildMockRouteResponse } from "./mockRoute";

/**
 * While the backend endpoints are not live yet, API calls below return local
 * mock data (shaped exactly like src/lib/types.ts). Flip to false once
 * Seymen's backend is reachable — nothing else needs to change.
 *
 * TODO(osman): set to false when POST /api/v1/route is live (§A in end-to-end.md).
 */
const USE_MOCK_ROUTE = true;

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
    // start_lat/start_lng). Also decide who sends `hour`.
    const body: RouteRequest = { start, end };
    const response = await api.post<RouteResponse>("/api/v1/route", body);
    return response.data;
  } catch (error) {
    logRequestError("getRoute (POST /api/v1/route)", error);
    return null;
  }
}
