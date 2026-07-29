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
 * Reads a fresh position right now, without going through the hook.
 *
 * The danger report screen needs this: it receives the map's coordinates as
 * route params, and those may be the Chicago demo fallback from when the screen
 * mounted. Filing an emergency report at the wrong place is the one failure
 * this feature cannot afford, so the report is stamped with a fix taken at send
 * time and only falls back to the params if that fails.
 *
 * Never throws and never blocks for long: resolves null on denied permission,
 * on error, or when the fix takes longer than `timeoutMs`.
 */
export async function getCurrentCoordinate(
  timeoutMs = 4000
): Promise<Coordinate | null> {
  try {
    // Don't re-prompt here — the map screen already asked. If it wasn't
    // granted, fall back instead of blocking an urgent report on a dialog.
    const { status } = await Location.getForegroundPermissionsAsync();
    if (status !== Location.PermissionStatus.GRANTED) return null;

    const position = await Promise.race([
      Location.getCurrentPositionAsync({
        accuracy: Location.Accuracy.Balanced,
      }),
      new Promise<null>((resolve) => setTimeout(() => resolve(null), timeoutMs)),
    ]);

    if (!position) return null;
    return [position.coords.longitude, position.coords.latitude];
  } catch (error) {
    console.warn("[getCurrentCoordinate] Failed to get position:", error);
    return null;
  }
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
        // warn, not error: this is handled — we fall back to the Chicago demo
        // centre and the UI says so. console.error trips React Native's
        // full-screen red LogBox, which makes a recovered condition look like a
        // crash. Same rule the API layer follows (see logRequestError).
        console.warn("[useUserLocation] Failed to get position:", error);
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
