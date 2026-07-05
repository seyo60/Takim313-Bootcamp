import { useEffect } from "react";
import { StyleSheet, Text, View } from "react-native";
import Mapbox, { Camera, MapView } from "@rnmapbox/maps";
import { useUserLocation } from "@/hooks/useUserLocation";
import { getMockRoute } from "@/lib/api";

Mapbox.setAccessToken(process.env.EXPO_PUBLIC_MAPBOX_TOKEN ?? "");

// Chicago Downtown — fallback + demo area, since our backend data
// (crime data, street graph) is Chicago-based.
const CHICAGO: [number, number] = [-87.6298, 41.8781];

export default function Index() {
  const { coordinate, status, message } = useUserLocation();

  // Center on the user once we have a real fix, otherwise stay on Chicago.
  const center = coordinate ?? CHICAGO;
  // Zoom in a little tighter when it's the user's actual location.
  const zoom = status === "granted" ? 14 : 11;

  // Task 2: confirm the mobile app can reach the FastAPI backend via ngrok.
  useEffect(() => {
    (async () => {
      const route = await getMockRoute();
      if (route) {
        console.log("[backend] getMockRoute() response:", route);
      } else {
        console.log(
          "[backend] getMockRoute() returned no data — check EXPO_PUBLIC_API_BASE_URL and the tunnel."
        );
      }
    })();
  }, []);

  return (
    <View style={styles.container}>
      {/* Light street map, closest to the Google Maps look. */}
      <MapView style={styles.map} styleURL="mapbox://styles/mapbox/streets-v12">
        <Camera zoomLevel={zoom} centerCoordinate={center} animationDuration={600} />
      </MapView>

      {/* Non-fatal notice when we couldn't use the real location. */}
      {message ? (
        <View style={styles.banner} pointerEvents="none">
          <Text style={styles.bannerText}>{message}</Text>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  map: {
    flex: 1,
  },
  banner: {
    position: "absolute",
    top: 60,
    left: 16,
    right: 16,
    backgroundColor: "rgba(0,0,0,0.75)",
    paddingVertical: 10,
    paddingHorizontal: 14,
    borderRadius: 10,
  },
  bannerText: {
    color: "#fff",
    fontSize: 13,
    textAlign: "center",
  },
});
