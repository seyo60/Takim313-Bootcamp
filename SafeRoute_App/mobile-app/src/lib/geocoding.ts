import axios from "axios";
import type { LngLat } from "./types";

/**
 * Forward geocoding (place/address search) via the Mapbox Geocoding v6 API.
 *
 * This is fully client-side: it uses the same public `pk.` token as the map,
 * so it does NOT depend on our backend at all (see end-to-end.md, item 3).
 */

/** One search hit, simplified to what the UI needs. */
export interface GeocodingResult {
  /** Primary label, e.g. "Millennium Park". */
  name: string;
  /** Secondary label, e.g. full address or region. */
  address: string;
  /** [longitude, latitude] of the place. */
  coordinate: LngLat;
}

/** Shape of the relevant parts of a Mapbox Geocoding v6 response. */
interface MapboxGeocodingResponse {
  features: Array<{
    properties: {
      name?: string;
      full_address?: string;
      place_formatted?: string;
    };
    geometry: {
      type: "Point";
      coordinates: [number, number];
    };
  }>;
}

const GEOCODING_URL = "https://api.mapbox.com/search/geocode/v6/forward";

/**
 * Searches places matching `query`. Results are biased toward `proximity`
 * (pass the user's location or the map center) so nearby hits rank first.
 *
 * Never throws — returns [] on any failure so the UI can just show
 * "no results".
 */
export async function searchPlaces(
  query: string,
  proximity?: LngLat
): Promise<GeocodingResult[]> {
  const token = process.env.EXPO_PUBLIC_MAPBOX_TOKEN;
  const trimmed = query.trim();
  if (!token || trimmed.length < 2) return [];

  try {
    const response = await axios.get<MapboxGeocodingResponse>(GEOCODING_URL, {
      timeout: 8000,
      params: {
        q: trimmed,
        access_token: token,
        limit: 5,
        ...(proximity ? { proximity: `${proximity[0]},${proximity[1]}` } : {}),
      },
    });

    return response.data.features.map((feature) => ({
      name: feature.properties.name ?? trimmed,
      address:
        feature.properties.full_address ??
        feature.properties.place_formatted ??
        "",
      coordinate: feature.geometry.coordinates,
    }));
  } catch (error) {
    console.warn("[geocoding] searchPlaces failed:", error);
    return [];
  }
}
