import { useCallback, useEffect, useRef, useState } from "react";
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
  type LineLayerStyle,
} from "@rnmapbox/maps";
import { useUserLocation } from "@/hooks/useUserLocation";
import { useRoute } from "@/hooks/useRoute";
import { useHeatmap } from "@/hooks/useHeatmap";
import { getRouteBounds, getRouteOptions, type RouteKind } from "@/lib/mockRoute";
import { hexRiskToFeatureCollection } from "@/lib/mockHeatmap";
import { DestinationSearchBar } from "@/components/DestinationSearchBar";
import { RouteInfoCard } from "@/components/RouteInfoCard";
import { StatusBanner, type BannerVariant } from "@/components/StatusBanner";
import type { GeocodingResult } from "@/lib/geocoding";
import type { LngLat } from "@/lib/types";

Mapbox.setAccessToken(process.env.EXPO_PUBLIC_MAPBOX_TOKEN ?? "");

// Chicago Downtown — fallback origin/camera target. Backend data (crime,
// street graph) is Chicago-based, so the demo lives here.
const CHICAGO: LngLat = [-87.6298, 41.8781];

// Line color per route kind. Safe is a solid blue; the shortest is a dashed
// gray so the two read as clearly different even before highlighting.
// (Plan said green for the safe route, but green would blend into the
// heatmap's low-risk ramp — blue vs gray reads clearer on this basemap.)
const SAFE_COLOR = "#1D6FEB";
const SHORTEST_COLOR = "#8A8A8A";

// Item 1 (AC #3): the selected route is drawn bold and opaque; the other one
// fades back so the choice is unmistakable on the map.
function lineStyleFor(kind: RouteKind, selected: boolean): LineLayerStyle {
  return {
    lineColor: kind === "safe" ? SAFE_COLOR : SHORTEST_COLOR,
    lineWidth: selected ? 6 : 4,
    lineOpacity: selected ? 1 : 0.3,
    lineCap: "round",
    lineJoin: "round",
    ...(kind === "shortest" ? { lineDasharray: [1.5, 1.5] } : {}),
  };
}

const destinationPinStyle = {
  circleRadius: 8,
  circleColor: "#E5484D",
  circleStrokeWidth: 3,
  circleStrokeColor: "#fff",
} as const;

// Risk heatmap (item 3): weight scales with each H3 cell's risk_score (0-100);
// the color ramp goes transparent → green → amber → orange → red as density
// rises. heatmapRadius scales with zoom so dense cells stay smooth when zoomed
// out and don't smear when zoomed in (AC #2). Opacity 0.7 keeps the route line
// readable on top (AC #5).
const heatmapStyle: HeatmapLayerStyle = {
  heatmapRadius: ["interpolate", ["linear"], ["zoom"], 10, 18, 14, 40, 16, 60],
  heatmapOpacity: 0.7,
  heatmapWeight: [
    "interpolate",
    ["linear"],
    ["get", "risk_score"],
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

  // Item 3/5: hexagon risk data + visibility toggle.
  const {
    points: riskHexes,
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
  const {
    route,
    status,
    retry: retryRoute,
  } = useRoute(destination ? origin : null, destination);

  // Item 1: normalized list of routes to draw + toggle between (safe, and the
  // shortest when present), plus which one is currently selected.
  const routeOptions = route ? getRouteOptions(route) : [];
  const [selectedKind, setSelectedKind] = useState<RouteKind>("safe");

  // A freshly fetched route always starts on the safe option.
  useEffect(() => {
    setSelectedKind("safe");
  }, [route]);

  const handleSearchSelect = useCallback((result: GeocodingResult) => {
    setDestination(result.coordinate);
  }, []);

  const handleMapPress = useCallback((feature: GeoJSON.Feature) => {
    if (feature.geometry.type !== "Point") return;
    const [lng, lat] = feature.geometry.coordinates;
    setDestination([lng, lat]);
  }, []);

  const clearDestination = useCallback(() => setDestination(null), []);

  // Frame every route (safe + shortest) when a comparison is available.
  const bounds = routeOptions.length
    ? getRouteBounds(
        routeOptions.flatMap(
          (option) => option.geometry.coordinates as LngLat[]
        )
      )
    : null;

  // Item 7: one banner slot, priority: route error > route loading >
  // heatmap error > location fallback info.
  const banner: {
    variant: BannerVariant;
    text: string;
    onRetry?: () => void;
  } | null =
    status === "error"
      ? {
          variant: "error",
          text: "Rota alınamadı — backend'e ulaşılamıyor.",
          onRetry: retryRoute,
        }
      : status === "loading"
        ? { variant: "loading", text: "Güvenli rota hesaplanıyor…" }
        : heatmapStatus === "error" && showHeatmap
          ? {
              variant: "error",
              text: "Isı haritası yüklenemedi.",
              onRetry: refetchHeatmap,
            }
          : locationMessage
            ? { variant: "info", text: locationMessage }
            : null;

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

        {/* Item 3: hexagon risk heatmap (green → red as risk rises). */}
        {showHeatmap && riskHexes.length > 0 ? (
          <ShapeSource
            id="heatmapSource"
            shape={hexRiskToFeatureCollection(riskHexes)}
          >
            <HeatmapLayer id="riskHeatmap" style={heatmapStyle} />
          </ShapeSource>
        ) : null}

        {/* Item 1: both routes, unselected drawn first so the selected (bold,
            opaque) one always sits on top and reads as the active choice. */}
        {routeOptions
          .slice()
          .sort((a, b) => {
            const aSel = a.kind === selectedKind ? 1 : 0;
            const bSel = b.kind === selectedKind ? 1 : 0;
            return aSel - bSel;
          })
          .map((option) => (
            <ShapeSource
              key={option.kind}
              id={`routeSource-${option.kind}`}
              shape={{
                type: "Feature",
                properties: {},
                geometry: option.geometry,
              }}
            >
              <LineLayer
                id={`routeLine-${option.kind}`}
                style={lineStyleFor(option.kind, option.kind === selectedKind)}
              />
            </ShapeSource>
          ))}

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

      {/* Item 1: route detail panel — selected route's distance / time / risk,
          with the safe⇄shortest toggle and its own ✕. */}
      {routeOptions.length ? (
        <RouteInfoCard
          options={routeOptions}
          selectedKind={selectedKind}
          onSelect={setSelectedKind}
          onClear={clearDestination}
        />
      ) : null}

      {/* Fallback clear button while there's a destination but no route yet
          (loading or error) — the card isn't on screen to host the ✕. */}
      {destination && !route ? (
        <Pressable style={styles.clearButton} onPress={clearDestination}>
          <Text style={styles.clearButtonText}>✕ Hedefi temizle</Text>
        </Pressable>
      ) : null}

      {/* Item 7: non-fatal notices with spinner/retry (single slot). */}
      {banner ? (
        <StatusBanner
          variant={banner.variant}
          text={banner.text}
          onRetry={banner.onRetry}
        />
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
});
