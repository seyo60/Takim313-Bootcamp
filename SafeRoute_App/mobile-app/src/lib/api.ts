import axios, { AxiosError } from "axios";

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

/** Narrow, readable error logging shared by the API calls below. */
function logRequestError(context: string, error: unknown): void {
  if (axios.isAxiosError(error)) {
    const axiosError = error as AxiosError;
    if (axiosError.response) {
      // Server responded with a non-2xx status.
      console.error(
        `[api] ${context} failed: ${axiosError.response.status}`,
        axiosError.response.data
      );
    } else if (axiosError.request) {
      // Request was made but no response (network down, timeout, bad tunnel).
      console.error(
        `[api] ${context} failed: no response (network/timeout). ${axiosError.message}`
      );
    } else {
      console.error(`[api] ${context} failed: ${axiosError.message}`);
    }
  } else {
    console.error(`[api] ${context} failed with unknown error:`, error);
  }
}

/**
 * Fetches a (mock, for now) route from the backend. Returns the parsed response
 * data on success, or null on any failure — never throws, so callers/UI don't
 * need try/catch just to render.
 */
export async function getMockRoute(): Promise<unknown | null> {
  try {
    const response = await api.get("/api/v1/route");
    return response.data;
  } catch (error) {
    logRequestError("getMockRoute (GET /api/v1/route)", error);
    return null;
  }
}
