/**
 * Nearest police station / hospital lookup for the emergency flow (Backlog #10).
 *
 * ⚠️ DEMO DATA. These coordinates are hand-entered landmarks for the Chicago
 * demo area, not a maintained dataset. They are good enough to prove the flow
 * (which is what the ticket asks for: "statik/mock lokasyon verisiyle, gerçek
 * bir API entegrasyonu şart değil"), but they are NOT good enough to route a
 * real person in a real emergency — the list is short, it will go stale, and a
 * closed or relocated facility would send someone to the wrong place.
 *
 * TODO(osman): before this app is used for real, replace `PLACES` with a live
 * POI source (Mapbox Search Box category API: `category/police`,
 * `category/hospital`, with the user's location as proximity). Only this file
 * changes — `findNearestPlace()` keeps its shape, the UI is untouched.
 */

import { distanceMeters } from "./nearbyAlerts";
import type { LngLat } from "./types";

export type EmergencyPlaceKind = "police" | "hospital";

export interface EmergencyPlace {
  kind: EmergencyPlaceKind;
  name: string;
  /** Street address, shown under the name so the user can sanity-check it. */
  address: string;
  latitude: number;
  longitude: number;
}

/** A place plus how far the user is from it. */
export interface NearestPlace extends EmergencyPlace {
  distance_m: number;
}

const PLACES: EmergencyPlace[] = [
  // --- Police (Chicago PD district stations) ---
  {
    kind: "police",
    name: "CPD 1. Bölge (Central)",
    address: "1718 S State St",
    latitude: 41.8583,
    longitude: -87.627,
  },
  {
    kind: "police",
    name: "CPD 18. Bölge (Near North)",
    address: "1160 N Larrabee St",
    latitude: 41.9033,
    longitude: -87.6433,
  },
  {
    kind: "police",
    name: "CPD 12. Bölge (Near West)",
    address: "1412 S Blue Island Ave",
    latitude: 41.8634,
    longitude: -87.6614,
  },
  {
    kind: "police",
    name: "CPD 2. Bölge (Wentworth)",
    address: "5101 S Wentworth Ave",
    latitude: 41.8022,
    longitude: -87.631,
  },
  // --- Hospitals (emergency departments) ---
  {
    kind: "hospital",
    name: "Northwestern Memorial Hospital",
    address: "251 E Huron St",
    latitude: 41.8947,
    longitude: -87.6213,
  },
  {
    kind: "hospital",
    name: "Rush University Medical Center",
    address: "1653 W Congress Pkwy",
    latitude: 41.8747,
    longitude: -87.6689,
  },
  {
    kind: "hospital",
    name: "University of Illinois Hospital",
    address: "1740 W Taylor St",
    latitude: 41.8692,
    longitude: -87.672,
  },
  {
    kind: "hospital",
    name: "Insight Hospital (Mercy)",
    address: "2525 S Michigan Ave",
    latitude: 41.8462,
    longitude: -87.6236,
  },
];

/**
 * Closest place of the requested kind to `location`, or null if the list is
 * somehow empty. Straight-line distance — good enough to rank a handful of
 * candidates; the actual walking route comes from the maps app.
 */
export function findNearestPlace(
  kind: EmergencyPlaceKind,
  location: LngLat
): NearestPlace | null {
  const [lng, lat] = location;

  let best: NearestPlace | null = null;
  for (const place of PLACES) {
    if (place.kind !== kind) continue;
    const distance = distanceMeters(lat, lng, place.latitude, place.longitude);
    if (best === null || distance < best.distance_m) {
      best = { ...place, distance_m: distance };
    }
  }
  return best;
}

/**
 * Universal maps URL for walking directions to a place. Uses the Google Maps
 * web endpoint on purpose: it opens the native app when installed and falls
 * back to the browser otherwise, on both iOS and Android, so there is no
 * platform branch and no "no maps app" dead end.
 */
export function directionsUrl(place: EmergencyPlace): string {
  const destination = `${place.latitude},${place.longitude}`;
  return (
    "https://www.google.com/maps/dir/?api=1" +
    `&destination=${encodeURIComponent(destination)}` +
    "&travelmode=walking"
  );
}
