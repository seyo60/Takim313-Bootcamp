import { StyleSheet, Text, View } from "react-native";
import Mapbox, {
  Camera,
  LineLayer,
  MapView,
  ShapeSource,
} from "@rnmapbox/maps";
import { useUserLocation } from "@/hooks/useUserLocation";
import { useRoute } from "@/hooks/useRoute";
import { MOCK_START, MOCK_END, getRouteBounds } from "@/lib/mockRoute";
import type { LngLat } from "@/lib/types";

Mapbox.setAccessToken(process.env.EXPO_PUBLIC_MAPBOX_TOKEN ?? "");

// Chicago Downtown — fallback camera target while there's no route to frame.
const CHICAGO: LngLat = [-87.6298, 41.8781];

// Mapbox layer style (a style-spec object, not a React Native style).
const routeLineStyle = {
  lineColor: "#1D6FEB",
  lineWidth: 5,
  lineCap: "round",
  lineJoin: "round",
} as const;

export default function Index() {
  // Used later as the route origin (item 3) and for the fallback banner now.
  const { message } = useUserLocation();

  // Item 2: fetch the route through the API layer (mock-backed until §A is
  // live) and draw whatever it returns.
  // TODO(osman): item 3 — replace MOCK_START/MOCK_END with the user's real
  // location as origin and the searched/tapped destination.
  const { route, status } = useRoute(MOCK_START, MOCK_END);

  const bounds = route
    ? getRouteBounds(route.route.coordinates as LngLat[])
    : null;

  // Route fetch problems surface in the same banner slot as location issues.
  // TODO(osman): item 7 — proper loading spinner + retry UX.
  const bannerText =
    status === "error"
      ? "Rota alınamadı — backend'e ulaşılamıyor. (Bağlantıyı kontrol et)"
      : message;

  return (
    <View style={styles.container}>
      {/* Light street map, closest to the Google Maps look. */}
      <MapView style={styles.map} styleURL="mapbox://styles/mapbox/streets-v12">
        {bounds ? (
          <Camera bounds={bounds} animationDuration={800} />
        ) : (
          <Camera zoomLevel={11} centerCoordinate={CHICAGO} />
        )}

        {/* The safe route line, drawn from the API response. */}
        {route ? (
          <ShapeSource
            id="routeSource"
            shape={{ type: "Feature", properties: {}, geometry: route.route }}
          >
            <LineLayer id="routeLine" style={routeLineStyle} />
          </ShapeSource>
        ) : null}
      </MapView>

      {/* Non-fatal notices (location fallback, route fetch failure). */}
      {bannerText ? (
        <View style={styles.banner} pointerEvents="none">
          <Text style={styles.bannerText}>{bannerText}</Text>
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
