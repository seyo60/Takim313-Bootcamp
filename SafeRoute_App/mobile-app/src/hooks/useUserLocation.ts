import { useEffect, useState } from "react";
import * as Location from "expo-location";

/** Mapbox expects coordinates as [longitude, latitude]. */
export type Coordinate = [number, number];

export type LocationStatus =
  | "loading" // still asking for permission / fetching the fix
  | "granted" // we have a real position
  | "denied" // user said no
  | "unavailable"; // permission ok but we couldn't get a fix (GPS off, timeout…)

export interface UserLocation {
  coordinate: Coordinate | null;
  status: LocationStatus;
  /** Human-readable reason, only set when status is "denied" | "unavailable". */
  message: string | null;
}

/**
 * Requests foreground location permission on mount and, once granted, reads the
 * device's current position. Never throws — on denial or failure it resolves to
 * a non-"granted" status with a message so the caller can fall back gracefully
 * (e.g. keep the Chicago demo center).
 */
export function useUserLocation(): UserLocation {
  const [state, setState] = useState<UserLocation>({
    coordinate: null,
    status: "loading",
    message: null,
  });

  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        const { status } = await Location.requestForegroundPermissionsAsync();

        if (status !== Location.PermissionStatus.GRANTED) {
          if (!cancelled) {
            setState({
              coordinate: null,
              status: "denied",
              message:
                "Location permission denied — showing Chicago (demo area) instead.",
            });
          }
          return;
        }

        const position = await Location.getCurrentPositionAsync({
          accuracy: Location.Accuracy.Balanced,
        });

        if (!cancelled) {
          setState({
            coordinate: [
              position.coords.longitude,
              position.coords.latitude,
            ],
            status: "granted",
            message: null,
          });
        }
      } catch (error) {
        // GPS disabled, timeout, etc. Permission was fine but we have no fix.
        console.error("[useUserLocation] Failed to get position:", error);
        if (!cancelled) {
          setState({
            coordinate: null,
            status: "unavailable",
            message:
              "Couldn't read your location — showing Chicago (demo area) instead.",
          });
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  return state;
}
