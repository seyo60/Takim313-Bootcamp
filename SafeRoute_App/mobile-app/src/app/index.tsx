import { useCallback, useRef, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { router, useFocusEffect } from "expo-router";
import Mapbox, {
  Camera,
  CircleLayer,
  HeatmapLayer,
  LineLayer,
  MapView,
  ShapeSource,
  type HeatmapLayerStyle,
} from "@rnmapbox/maps";
import { useUserLocation } from "@/hooks/useUserLocation";
import { useRoute } from "@/hooks/useRoute";
import { useHeatmap } from "@/hooks/useHeatmap";
import { getRouteBounds } from "@/lib/mockRoute";
import { riskPointsToFeatureCollection } from "@/lib/mockHeatmap";
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

// Risk heatmap: weight scales with each point's total_risk (0-100); the color
// ramp goes transparent → green → amber → orange → red as density rises.
const heatmapStyle: HeatmapLayerStyle = {
  heatmapRadius: 40,
  heatmapOpacity: 0.7,
  heatmapWeight: [
    "interpolate",
    ["linear"],
    ["get", "total_risk"],
    0,
    0,
    100,
    1,
  ],
  heatmapIntensity: ["interpolate", ["linear"], ["zoom"], 8, 0.6, 16, 1.6],
  heatmapColor: [
    "interpolate",
    ["linear"],
    ["heatmap-density"],
    0,
    "rgba(0,0,0,0)",
    0.2,
    "rgba(46,158,68,0.35)",
    0.45,
    "rgba(255,193,7,0.55)",
    0.7,
    "rgba(232,137,12,0.75)",
    1,
    "rgba(229,72,77,0.9)",
  ],
};

export default function Index() {
  const { coordinate: userCoordinate, message: locationMessage } =
    useUserLocation();
  const [destination, setDestination] = useState<LngLat | null>(null);

  // Item 5: risk heatmap data + visibility toggle.
  const {
    points: riskPoints,
    status: heatmapStatus,
    refetch: refetchHeatmap,
  } = useHeatmap();
  const [showHeatmap, setShowHeatmap] = useState(true);

  // Item 6: refresh the heatmap when returning from the report modal, so a
  // just-submitted report shows up. Skip the initial focus — the hook already
  // fetches on mount.
  const isFirstFocus = useRef(true);
  useFocusEffect(
    useCallback(() => {
      if (isFirstFocus.current) {
        isFirstFocus.current = false;
        return;
      }
      refetchHeatmap();
    }, [refetchHeatmap])
  );

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
        : (locationMessage ??
          (heatmapStatus === "error" && showHeatmap
            ? "Isı haritası yüklenemedi."
            : null));

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

        {/* Item 5: risk heatmap (green → red as risk density rises). */}
        {showHeatmap && riskPoints.length > 0 ? (
          <ShapeSource
            id="heatmapSource"
            shape={riskPointsToFeatureCollection(riskPoints)}
          >
            <HeatmapLayer id="riskHeatmap" style={heatmapStyle} />
          </ShapeSource>
        ) : null}

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

      {/* Heatmap visibility toggle. */}
      <Pressable
        style={[
          styles.heatmapToggle,
          showHeatmap && styles.heatmapToggleActive,
        ]}
        onPress={() => setShowHeatmap((visible) => !visible)}
      >
        <Text style={styles.heatmapToggleText}>🔥</Text>
      </Pressable>

      {/* Item 6: open the danger report modal (reports the user's location). */}
      <Pressable
        style={styles.reportButton}
        onPress={() =>
          router.push({
            pathname: "/report",
            params: { lng: String(origin[0]), lat: String(origin[1]) },
          })
        }
      >
        <Text style={styles.reportButtonText}>⚠️</Text>
      </Pressable>

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
  heatmapToggle: {
    position: "absolute",
    top: 120,
    right: 16,
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: "#fff",
    alignItems: "center",
    justifyContent: "center",
    shadowColor: "#000",
    shadowOpacity: 0.15,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 2 },
    elevation: 4,
  },
  heatmapToggleActive: {
    backgroundColor: "#FFE8E0",
    borderWidth: 1,
    borderColor: "#E5484D",
  },
  heatmapToggleText: {
    fontSize: 18,
  },
  reportButton: {
    position: "absolute",
    top: 176,
    right: 16,
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: "#E5484D",
    alignItems: "center",
    justifyContent: "center",
    shadowColor: "#000",
    shadowOpacity: 0.2,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 2 },
    elevation: 4,
  },
  reportButtonText: {
    fontSize: 18,
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
