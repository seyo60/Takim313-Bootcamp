import { useCallback, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import Mapbox, {
  Camera,
  CircleLayer,
  LineLayer,
  MapView,
  ShapeSource,
} from "@rnmapbox/maps";
import { useUserLocation } from "@/hooks/useUserLocation";
import { useRoute } from "@/hooks/useRoute";
import { getRouteBounds } from "@/lib/mockRoute";
import { DestinationSearchBar } from "@/components/DestinationSearchBar";
import { RouteInfoCard } from "@/components/RouteInfoCard";
import type { GeocodingResult } from "@/lib/geocoding";
import type { LngLat } from "@/lib/types";

Mapbox.setAccessToken(process.env.EXPO_PUBLIC_MAPBOX_TOKEN ?? "");

// Chicago Downtown — fallback origin/camera target. Backend data (crime,
// street graph) is Chicago-based, so the demo lives here.
const CHICAGO: LngLat = [-87.6298, 41.8781];

// Mapbox layer styles (style-spec objects, not React Native styles).
const routeLineStyle = {
  lineColor: "#1D6FEB",
  lineWidth: 5,
  lineCap: "round",
  lineJoin: "round",
} as const;

const destinationPinStyle = {
  circleRadius: 8,
  circleColor: "#E5484D",
  circleStrokeWidth: 3,
  circleStrokeColor: "#fff",
} as const;

export default function Index() {
  const { coordinate: userCoordinate, message: locationMessage } =
    useUserLocation();
  const [destination, setDestination] = useState<LngLat | null>(null);

  // Route origin: the user's real position when we have one, else the Chicago
  // demo center (backend graph only covers Chicago anyway).
  const origin = userCoordinate ?? CHICAGO;

  // Item 3: the route flow now waits for a destination — the hook stays idle
  // until the user picks one (search or map tap).
  const { route, status } = useRoute(destination ? origin : null, destination);

  const handleSearchSelect = useCallback((result: GeocodingResult) => {
    setDestination(result.coordinate);
  }, []);

  const handleMapPress = useCallback((feature: GeoJSON.Feature) => {
    if (feature.geometry.type !== "Point") return;
    const [lng, lat] = feature.geometry.coordinates;
    setDestination([lng, lat]);
  }, []);

  const clearDestination = useCallback(() => setDestination(null), []);

  const bounds = route
    ? getRouteBounds(route.route.coordinates as LngLat[])
    : null;

  // Route fetch problems share the banner slot with location fallbacks.
  // TODO(osman): item 7 — proper loading spinner + retry UX.
  const bannerText =
    status === "error"
      ? "Rota alınamadı — backend'e ulaşılamıyor. (Bağlantıyı kontrol et)"
      : status === "loading"
        ? "Güvenli rota hesaplanıyor…"
        : locationMessage;

  return (
    <View style={styles.container}>
      {/* Light street map, closest to the Google Maps look. */}
      <MapView
        style={styles.map}
        styleURL="mapbox://styles/mapbox/streets-v12"
        onPress={handleMapPress}
      >
        {bounds ? (
          <Camera bounds={bounds} animationDuration={800} />
        ) : (
          <Camera
            zoomLevel={userCoordinate ? 14 : 11}
            centerCoordinate={origin}
            animationDuration={600}
          />
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

        {/* Destination pin (red dot with white ring). */}
        {destination ? (
          <ShapeSource
            id="destinationSource"
            shape={{
              type: "Feature",
              properties: {},
              geometry: { type: "Point", coordinates: destination },
            }}
          >
            <CircleLayer id="destinationPin" style={destinationPinStyle} />
          </ShapeSource>
        ) : null}
      </MapView>

      {/* Floating destination search (Mapbox Geocoding, client-side). */}
      <DestinationSearchBar proximity={origin} onSelect={handleSearchSelect} />

      {/* Item 4: route summary (distance / time / risk) with its own ✕. */}
      {route ? <RouteInfoCard route={route} onClear={clearDestination} /> : null}

      {/* Fallback clear button while there's a destination but no route yet
          (loading or error) — the card isn't on screen to host the ✕. */}
      {destination && !route ? (
        <Pressable style={styles.clearButton} onPress={clearDestination}>
          <Text style={styles.clearButtonText}>✕ Hedefi temizle</Text>
        </Pressable>
      ) : null}

      {/* Non-fatal notices (location fallback, route loading/failure). */}
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
  clearButton: {
    position: "absolute",
    bottom: 40,
    alignSelf: "center",
    backgroundColor: "#fff",
    paddingVertical: 10,
    paddingHorizontal: 18,
    borderRadius: 22,
    shadowColor: "#000",
    shadowOpacity: 0.15,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 2 },
    elevation: 4,
  },
  clearButtonText: {
    fontSize: 14,
    color: "#111",
  },
  banner: {
    position: "absolute",
    bottom: 96,
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
