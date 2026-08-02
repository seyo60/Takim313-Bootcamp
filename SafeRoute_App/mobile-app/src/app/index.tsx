import { useEffect, useMemo, useRef, useState } from "react";
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from "react-native";
import { router } from "expo-router";
import Mapbox, { Camera, CircleLayer, FillLayer, LineLayer, MapView, ShapeSource, UserLocation, type Camera as CameraRef, type FillLayerStyle, type LineLayerStyle, type MapState } from "@rnmapbox/maps";
import { useNavigationSession } from "@/providers/NavigationProvider";
import { useAuth } from "@/hooks/useAuth";
import { useUserLocation } from "@/hooks/useUserLocation";
import { useRoute } from "@/hooks/useRoute";
import type { StreetRiskStatus } from "@/hooks/useStreetRisk";
import { useEmergencyAlerts } from "@/hooks/useEmergencyAlerts";
import { useMapReports } from "@/hooks/useMapReports";
import { useRiskHeatmap } from "@/hooks/useRiskHeatmap";
import { WitnessAlertModal } from "@/components/WitnessAlertModal";
import { getRouteBounds, getRouteOptions, type RouteKind } from "@/lib/mockRoute";
import { DestinationSearchBar } from "@/components/DestinationSearchBar";
import { RouteInfoCard } from "@/components/RouteInfoCard";
import { StatusBanner, type BannerVariant } from "@/components/StatusBanner";
import { RecentReportsToggle } from "@/components/RecentReportsToggle";
import { ReportDetailModal } from "@/components/ReportDetailModal";
import { H3CellDetailModal } from "@/components/H3CellDetailModal";
import { BottomNav } from "@/components/brand";
import { MapRoundButton, MapTopBar, MapUnavailable } from "@/components/MapChrome";
import type { GeocodingResult } from "@/lib/geocoding";
import type { HeatmapChannel, HeatmapGeoJSONProperties, LngLat, MapReport, RouteProfile } from "@/lib/types";
import { colors, radius, spacing } from "@/theme/tokens";

const MAPBOX_TOKEN = process.env.EXPO_PUBLIC_MAPBOX_TOKEN?.trim() ?? "";
const MAPBOX_TOKEN_USABLE = MAPBOX_TOKEN.startsWith("pk.") && MAPBOX_TOKEN.length >= 50;
if (MAPBOX_TOKEN_USABLE) Mapbox.setAccessToken(MAPBOX_TOKEN);
const CHICAGO: LngLat = [-87.6298, 41.8781];

function lineStyleFor(kind: RouteKind, selected: boolean): LineLayerStyle { return { lineColor: kind === "safe" ? colors.secondary : "#8A8F96", lineWidth: selected ? 7 : 4, lineOpacity: selected ? 1 : 0.5, lineCap: "round", lineJoin: "round", ...(kind === "shortest" ? { lineDasharray: [1.5, 1.5] } : {}) }; }
const originPinStyle = { circleRadius: 9, circleColor: colors.secondary, circleStrokeWidth: 4, circleStrokeColor: "#fff" } as const;
const destinationPinStyle = { circleRadius: 9, circleColor: colors.primary, circleStrokeWidth: 4, circleStrokeColor: "#fff" } as const;
/** Kategoriye göre net renkli marker (Mapbox emoji/symbol güvenilir değil). */
const reportMarkerStyle = {
  circleRadius: 11,
  circleColor: [
    "match",
    ["get", "category"],
    "lighting",
    "#E49A20",
    "obstacle",
    "#C97816",
    "harassment",
    colors.tertiary,
    "crime",
    colors.error,
    "suspicious",
    "#8E44AD",
    colors.primary,
  ],
  circleOpacity: 1,
  circleStrokeWidth: 3,
  circleStrokeColor: "#ffffff",
} as const;
const h3FillStyle: FillLayerStyle = { fillColor: ["case", ["boolean", ["get", "data_available"], true], ["step", ["get", "risk"], "#5AA978", 0.20, "#A9BE65", 0.40, "#DFC35B", 0.60, "#E58E52", 0.80, "#D95858"], "#AAB1BA"], fillOpacity: 0.45, fillOutlineColor: "rgba(255,255,255,0.42)" };

function haversineMeters(a: LngLat, b: LngLat): number {
  const toRad = (deg: number) => (deg * Math.PI) / 180;
  const dLat = toRad(b[1] - a[1]);
  const dLng = toRad(b[0] - a[0]);
  const lat1 = toRad(a[1]);
  const lat2 = toRad(b[1]);
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2;
  return 6371000 * 2 * Math.asin(Math.sqrt(h));
}

export default function Index() {
  const cameraRef = useRef<CameraRef | null>(null);
  const navigationSession = useNavigationSession();   const { user } = useAuth();
  const {
    active: activeWitnessAlert,
    busy: witnessBusy,
    statusMessage: witnessStatus,
    respond: respondWitness,
    dismiss: dismissWitness,
  } = useEmergencyAlerts();
  const { coordinate: userCoordinate, message: locationMessage } = useUserLocation();
  const gpsOrigin = userCoordinate ?? CHICAGO;
  const [customOrigin, setCustomOrigin] = useState<LngLat | null>(null);
  const origin = customOrigin ?? gpsOrigin;
  const [destination, setDestination] = useState<LngLat | null>(null); const [destinationName, setDestinationName] = useState("Seçilen hedef"); const [routeProfile, setRouteProfile] = useState<RouteProfile>("balanced");
  const [viewportBbox, setViewportBbox] = useState<string | undefined>();
  const [heatmapEnabled, setHeatmapEnabled] = useState(false); const [selectedChannel, setSelectedChannel] = useState<HeatmapChannel>("total"); const [selectedH3Cell, setSelectedH3Cell] = useState<HeatmapGeoJSONProperties | null>(null);
  const { geoJson: heatmap, metadata: heatmapMetadata, status: heatmapStatus } = useRiskHeatmap({ enabled: heatmapEnabled && Boolean(viewportBbox), channel: selectedChannel, bbox: viewportBbox });
  const [reportsEnabled, setReportsEnabled] = useState(false); const [selectedCategory, setSelectedCategory] = useState("all"); const [selectedReport, setSelectedReport] = useState<MapReport | null>(null);
  // Sayı her zaman gelsin; haritada gösterim reportsEnabled ile ayrı kontrol edilir.
  const { reports: mapReports, error: mapReportsError } = useMapReports({ enabled: Boolean(viewportBbox), category: selectedCategory, minutes: 60, bbox: viewportBbox });
  const [selectionMode, setSelectionMode] = useState(false);
  const [selectionKind, setSelectionKind] = useState<"origin" | "destination">("destination");
  const [pendingPoint, setPendingPoint] = useState<LngLat | null>(null);
  const [pendingSearchDestination, setPendingSearchDestination] = useState<GeocodingResult | null>(null);
  const [searchExpanded, setSearchExpanded] = useState(false);
  const [mapPhase, setMapPhase] = useState<"loading" | "loaded" | "error">(MAPBOX_TOKEN_USABLE ? "loading" : "error"); const [mapKey, setMapKey] = useState(0);
  const mapReportsGeoJSON: GeoJSON.FeatureCollection<GeoJSON.Point> = useMemo(
    () => ({
      type: "FeatureCollection",
      features: mapReports.map((item) => ({
        type: "Feature",
        id: item.public_id,
        properties: {
          public_id: item.public_id,
          category: item.category,
          reported_at: item.reported_at,
          minutes_ago: item.minutes_ago,
        },
        geometry: { type: "Point", coordinates: [item.lng, item.lat] },
      })),
    }),
    [mapReports]
  );
  const openNearestReport = (lng: number, lat: number, maxMeters = 130): MapReport | null => {
    let best: MapReport | null = null;
    let bestDist = maxMeters;
    for (const item of mapReports) {
      const dist = haversineMeters([lng, lat], [item.lng, item.lat]);
      if (dist <= bestDist) {
        bestDist = dist;
        best = item;
      }
    }
    return best;
  };
  const openNearestHeatmapCell = (
    lng: number,
    lat: number,
    maxMeters = 180
  ): HeatmapGeoJSONProperties | null => {
    if (!heatmap?.features?.length) return null;
    let best: HeatmapGeoJSONProperties | null = null;
    let bestDist = maxMeters;
    for (const feature of heatmap.features) {
      const props = feature.properties;
      if (!props || !Number.isFinite(props.lat) || !Number.isFinite(props.lng)) continue;
      const dist = haversineMeters([lng, lat], [props.lng, props.lat]);
      if (dist <= bestDist) {
        bestDist = dist;
        best = props;
      }
    }
    return best;
  };
  const { route, status, retry: retryRoute } = useRoute(destination ? origin : null, destination, routeProfile); const routeOptions = useMemo(() => route ? getRouteOptions(route) : [], [route]); const [selectedKind, setSelectedKind] = useState<RouteKind>("safe"); useEffect(() => setSelectedKind("safe"), [route]);
  const activeOption = routeOptions.find((option) => option.kind === selectedKind);
  // Rota geneli LLM açıklaması artık POST /api/v1/route içinde geliyor
  // (include_risk_explanation). Orta nokta /street-risk-explanation çağrısı
  // kaldırıldı — gösterilen risk ile açıklama tutarlı olsun diye.
  const explanation = route?.risk_explanation ?? null;
  const explanationStatus: StreetRiskStatus =
    !destination || status === "idle"
      ? "idle"
      : status === "loading"
        ? "loading"
        : explanation
          ? "ready"
          : status === "ready"
            ? "error"
            : "idle";
  const cameraBounds = useMemo(() => routeOptions.length ? getRouteBounds(routeOptions.flatMap((option) => option.geometry.coordinates as LngLat[])) : null, [routeOptions]);
  const retryMap = () => { setMapPhase(MAPBOX_TOKEN_USABLE ? "loading" : "error"); setMapKey((value) => value + 1); };
  const centerOnUser = () => { if (!MAPBOX_TOKEN_USABLE) { retryMap(); return; } cameraRef.current?.setCamera({ centerCoordinate: gpsOrigin, zoomLevel: 14.5, animationDuration: 650 }); };
  const resetHeading = () => { if (!MAPBOX_TOKEN_USABLE) { retryMap(); return; } cameraRef.current?.setCamera({ heading: 0, animationDuration: 350 }); };
  const openReport = () => { const params = { lng: String(gpsOrigin[0]), lat: String(gpsOrigin[1]), approximate: userCoordinate ? "0" : "1" }; if (!user) { router.push({ pathname: "/auth", params: { returnTo: "report", ...params } }); return; } router.push({ pathname: "/report", params }); };
  const beginMapPick = (kind: "origin" | "destination", prefill?: LngLat) => {
    setSelectedReport(null);
    setSelectedH3Cell(null);
    setSelectionKind(kind);
    setPendingPoint(prefill ?? null);
    setSelectionMode(true);
  };
  const exitMapPick = () => {
    setSelectionMode(false);
    setPendingPoint(null);
    setPendingSearchDestination(null);
  };
  const confirmMapPick = () => {
    if (!pendingPoint) return;
    setSelectedReport(null);
    setSelectedH3Cell(null);
    if (selectionKind === "origin") {
      setCustomOrigin(pendingPoint);
      if (pendingSearchDestination) {
        setDestinationName(pendingSearchDestination.name);
        setDestination(pendingSearchDestination.coordinate);
      }
      exitMapPick();
      return;
    }
    // Varış haritadan; başlangıç GPS (veya daha önce seçilmiş customOrigin)
    setDestinationName("Haritadan seçilen konum");
    setDestination(pendingPoint);
    exitMapPick();
  };
  const selectDestination = (result: GeocodingResult) => {
    setSelectedReport(null);
    setSelectedH3Cell(null);
    setCustomOrigin(null);
    setDestinationName(result.name);
    setDestination(result.coordinate);
  };
  const clearRoute = () => {
    setDestination(null);
    setCustomOrigin(null);
  };
  const handleMapPress = (event: any) => {
    // @rnmapbox/maps sürümlerine göre koordinat alanı değişebiliyor.
    const coordinates =
      (Array.isArray(event?.geometry?.coordinates) &&
        event.geometry.coordinates) ||
      (Array.isArray(event?.coordinates) && event.coordinates) ||
      (Array.isArray(event?.features?.[0]?.geometry?.coordinates) &&
        event.features[0].geometry.coordinates) ||
      null;
    if (!Array.isArray(coordinates) || coordinates.length < 2) return;
    const lng = Number(coordinates[0]);
    const lat = Number(coordinates[1]);
    if (!Number.isFinite(lng) || !Number.isFinite(lat)) return;
    const point: LngLat = [lng, lat];

    if (selectionMode) {
      setPendingPoint(point);
      return;
    }

    // İhbar her zaman heatmap'ten önce
    if (reportsEnabled) {
      const nearbyReport = openNearestReport(lng, lat);
      if (nearbyReport) {
        setSelectedH3Cell(null);
        setSelectedReport(nearbyReport);
        return;
      }
    }

    if (heatmapEnabled) {
      const cell = openNearestHeatmapCell(lng, lat);
      if (cell) {
        setSelectedReport(null);
        setSelectedH3Cell(cell);
      }
      return;
    }

    // Heatmap kapalı: boş haritaya dokunuş → varış seçimi (başlangıç = GPS)
    setCustomOrigin(null);
    beginMapPick("destination", point);
  };
  const handleMapIdle = (state: MapState) => { const { sw, ne } = state.properties.bounds; if (!Array.isArray(sw) || !Array.isArray(ne) || sw.length < 2 || ne.length < 2) return; const values = [Number(sw[0]), Number(sw[1]), Number(ne[0]), Number(ne[1])]; if (!values.every(Number.isFinite)) return; const next = values.map((value) => value.toFixed(5)).join(","); setViewportBbox((current) => current === next ? current : next); };
  const freshness = useMemo(() => { const raw = heatmapMetadata?.generated_at; if (!raw) return "Veri hazır"; return `Veri güncellendi · ${new Date(raw).toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" })}`; }, [heatmapMetadata?.generated_at]);
  const banner = useMemo(() => { if (status === "error") return { variant: "error" as BannerVariant, text: "Rota alınamadı. Bağlantıyı kontrol edip yeniden dene.", onRetry: retryRoute }; if (heatmapStatus === "error" && heatmapEnabled) return { variant: "info" as BannerVariant, text: "Bölgesel risk verisi yüklenemedi.", autoDismiss: true }; if (mapReportsError && reportsEnabled) return { variant: "info" as BannerVariant, text: "Topluluk ihbarları yüklenemedi.", autoDismiss: true }; if (locationMessage && !destination) return { variant: "info" as BannerVariant, text: locationMessage, autoDismiss: true }; return null; }, [status, retryRoute, heatmapStatus, heatmapEnabled, mapReportsError, reportsEnabled, locationMessage, destination]);
  const showHomeChrome = !routeOptions.length && !selectionMode;

  return <View style={styles.container}>
    {MAPBOX_TOKEN_USABLE ? <MapView key={mapKey} style={styles.map} styleURL={Mapbox.StyleURL.Light} onPress={handleMapPress} onMapIdle={handleMapIdle} onDidFinishLoadingMap={() => setMapPhase("loaded")} onMapLoadingError={() => setMapPhase("error")}>
      <Camera ref={cameraRef} defaultSettings={{ centerCoordinate: CHICAGO, zoomLevel: 13 }} bounds={cameraBounds ?? undefined} padding={{ paddingLeft: 38, paddingRight: 38, paddingTop: 150, paddingBottom: 250 }} animationDuration={800} />
      {userCoordinate ? <UserLocation visible /> : null}
      {heatmapEnabled && heatmap?.features.length ? (
        <ShapeSource id="h3RiskHeatmapSource" shape={heatmap}>
          <FillLayer id="h3RiskHeatmapFill" style={h3FillStyle} />
        </ShapeSource>
      ) : null}
      {reportsEnabled && mapReportsGeoJSON.features.length ? (
        <ShapeSource id="mapReportsSource" shape={mapReportsGeoJSON}>
          <CircleLayer id="mapReportsCircle" style={reportMarkerStyle} />
        </ShapeSource>
      ) : null}
      {routeOptions.map((option) => <ShapeSource key={option.kind} id={`routeSource-${option.kind}`} shape={{ type: "Feature", properties: {}, geometry: option.geometry }}><LineLayer id={`routeLine-${option.kind}`} style={lineStyleFor(option.kind, option.kind === selectedKind)} /></ShapeSource>)}
      {(selectionMode && selectionKind === "origin" ? pendingPoint : customOrigin) ? (
        <ShapeSource
          id="originSource"
          shape={{
            type: "Feature",
            properties: {},
            geometry: {
              type: "Point",
              coordinates: (selectionMode && selectionKind === "origin"
                ? pendingPoint
                : customOrigin)!,
            },
          }}
        >
          <CircleLayer id="originPin" style={originPinStyle} />
        </ShapeSource>
      ) : null}
      {(selectionMode && selectionKind === "destination"
        ? pendingPoint
        : destination) ? (
        <ShapeSource
          id="destinationSource"
          shape={{
            type: "Feature",
            properties: {},
            geometry: {
              type: "Point",
              coordinates: (selectionMode && selectionKind === "destination"
                ? pendingPoint
                : destination)!,
            },
          }}
        >
          <CircleLayer id="destinationPin" style={destinationPinStyle} />
        </ShapeSource>
      ) : null}
    </MapView> : <MapUnavailable reason="token" onRetry={retryMap} />}
    {MAPBOX_TOKEN_USABLE && mapPhase === "error" ? <MapUnavailable reason="load" onRetry={retryMap} /> : null}
    {MAPBOX_TOKEN_USABLE && mapPhase === "loading" ? <View style={styles.mapLoading}><ActivityIndicator color={colors.primary} /><Text style={styles.mapLoadingText}>Harita hazırlanıyor…</Text></View> : null}

    {selectionMode ? (
      <>
        <View style={styles.selectionHeader}>
          <Pressable style={styles.headerBack} onPress={exitMapPick}>
            <Text style={styles.headerBackText}>‹</Text>
          </Pressable>
          <Text style={styles.selectionTitle}>
            {selectionKind === "origin" ? "Başlangıç seç" : "Varış seç"}
          </Text>
          <View style={styles.headerBack} />
        </View>
        <View style={styles.selectionCard}>
          <Text style={styles.selectionCap}>
            {selectionKind === "origin"
              ? "BAŞLANGIÇ · HARİTADAN"
              : "BAŞLANGIÇ · MEVCUT KONUM / SEÇİLEN"}
          </Text>
          <Text style={styles.selectionHint}>
            {selectionKind === "origin"
              ? "Haritada başlangıç noktasına dokun, sonra güvenli rotayı oluştur."
              : "Haritada varış noktasına dokun, sonra güvenli rotayı oluştur."}
          </Text>
          <Text style={styles.pointLabel}>
            {selectionKind === "origin" ? "Seçilen başlangıç" : "Seçilen varış"}
          </Text>
          <Text style={styles.pointValue}>
            {pendingPoint
              ? `${pendingPoint[1].toFixed(5)}, ${pendingPoint[0].toFixed(5)}`
              : "Henüz seçilmedi"}
          </Text>
          <Pressable
            disabled={!pendingPoint}
            style={[styles.confirm, !pendingPoint && styles.confirmDisabled]}
            onPress={confirmMapPick}
          >
            <Text style={styles.confirmText}>Güvenli rota oluştur</Text>
          </Pressable>
        </View>
      </>
    ) : <>
      {!searchExpanded ? <MapTopBar signedIn={Boolean(user)} /> : null}
      {showHomeChrome ? (
        <DestinationSearchBar
          proximity={gpsOrigin}
          onSelect={selectDestination}
          onExpandedChange={setSearchExpanded}
        />
      ) : null}
      {showHomeChrome ? <View style={styles.mapControls}><RecentReportsToggle reportsEnabled={reportsEnabled} onToggleReports={(value) => { setReportsEnabled(value); if (value) { setHeatmapEnabled(false); setSelectedH3Cell(null); } }} selectedCategory={selectedCategory} onSelectCategory={setSelectedCategory} reportCount={mapReports.length} heatmapEnabled={heatmapEnabled} onToggleHeatmap={(value) => { setHeatmapEnabled(value); if (value) { setReportsEnabled(false); setSelectedReport(null); } }} selectedChannel={selectedChannel} onSelectChannel={setSelectedChannel} /><MapRoundButton label="Konumum" icon="⌖" onPress={centerOnUser} /><MapRoundButton label="Kuzeye döndür" icon="➤" onPress={resetHeading} /></View> : null}
      {showHomeChrome ? <View style={styles.freshness}><Text style={styles.freshnessText}>{freshness}</Text></View> : null}
      {showHomeChrome ? <Pressable accessibilityLabel="İhbar gönder" style={styles.sos} onPress={openReport}><Text style={styles.sosText}>SOS</Text></Pressable> : null}
    </>}

    {status === "loading" && destination ? <View style={styles.routeLoadingSheet}><View style={styles.routeLoadingHandle} /><View style={styles.routeLoadingIcon}><Text style={styles.routeLoadingIconText}>♢</Text></View><Text style={styles.routeLoadingTitle}>Güvenli rotalar bulunuyor</Text><Text style={styles.routeLoadingBody}>Rota hesaplanıyor ve risk açıklaması hazırlanıyor…</Text><View style={styles.progressTrack}><View style={styles.progressFill} /></View><Pressable style={styles.cancelRoute} onPress={clearRoute}><Text style={styles.cancelRouteText}>İptal</Text></Pressable></View> : null}
    <WitnessAlertModal alert={activeWitnessAlert} busy={witnessBusy} statusMessage={witnessStatus} onConfirm={() => void respondWitness("confirm")} onDeny={() => void respondWitness("deny")} onUnsure={() => void respondWitness("unsure")} onClose={dismissWitness} />
    <ReportDetailModal
      report={selectedReport}
      onClose={() => setSelectedReport(null)}
    />
    <H3CellDetailModal
      cellProperties={selectedH3Cell}
      onClose={() => setSelectedH3Cell(null)}
      onPlanRouteToHere={(coord) => {
        setSelectedH3Cell(null);
        setSelectedReport(null);
        setDestinationName("Seçilen bölge");
        setDestination(coord);
      }}
    />
    {routeOptions.length ? <RouteInfoCard options={routeOptions} selectedKind={selectedKind} onSelect={setSelectedKind} routeProfile={routeProfile} appliedProfile={route?.comparison?.selected_profile ?? route?.metadata?.routing_profile ?? routeProfile} onSelectProfile={(profile) => { setSelectedKind("safe"); setRouteProfile(profile); }} profileLoading={status === "loading"} profileError={status === "error"} comparison={route?.comparison} onClear={clearRoute} explanation={explanation} explanationStatus={explanationStatus} onRetryExplanation={retryRoute} onStartNavigation={(option) => { if (!destination) return; navigationSession.start(option, destination, routeProfile); router.push("/navigation"); }} destinationName={destinationName} /> : null}
    {banner ? <StatusBanner variant={banner.variant} text={banner.text} onRetry={banner.onRetry} autoDismiss={banner.autoDismiss} /> : null}
    {showHomeChrome ? <BottomNav active="map" /> : null}
  </View>;
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background }, map: { flex: 1 }, mapLoading: { position: "absolute", top: "45%", alignSelf: "center", flexDirection: "row", alignItems: "center", gap: 10, backgroundColor: colors.surface, borderRadius: radius.pill, paddingVertical: 12, paddingHorizontal: 18 }, mapLoadingText: { color: colors.text, fontWeight: "700" },
  mapControls: { position: "absolute", right: spacing.md, top: 172, gap: 10, zIndex: 10 }, freshness: { position: "absolute", bottom: 92, alignSelf: "center", backgroundColor: "rgba(255,255,255,0.95)", paddingVertical: 7, paddingHorizontal: 12, borderRadius: radius.pill }, freshnessText: { color: colors.textMuted, fontSize: 11, fontWeight: "700" }, sos: { position: "absolute", right: spacing.md, bottom: 91, width: 52, height: 52, borderRadius: 26, backgroundColor: colors.error, alignItems: "center", justifyContent: "center", shadowColor: colors.error, shadowOpacity: 0.32, shadowRadius: 10, elevation: 6 }, sosText: { color: "white", fontWeight: "900", fontSize: 13 },
  selectionHeader: { position: "absolute", top: 44, left: 0, right: 0, height: 58, backgroundColor: colors.background, flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.sm }, headerBack: { width: 48, height: 48, alignItems: "center", justifyContent: "center" }, headerBackText: { color: colors.text, fontSize: 34 }, selectionTitle: { color: colors.primary, fontSize: 19, fontWeight: "900" }, selectionCard: { position: "absolute", left: spacing.md, right: spacing.md, bottom: spacing.lg, backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.md, shadowColor: "#000", shadowOpacity: 0.14, shadowRadius: 12, elevation: 6 }, selectionCap: { color: colors.textMuted, fontSize: 10, letterSpacing: 1, fontWeight: "900" }, selectionHint: { color: colors.text, fontSize: 14, fontWeight: "600", marginTop: 6, marginBottom: 12, lineHeight: 20 }, pointLabel: { color: colors.textMuted, fontSize: 11, fontWeight: "800" }, pointValue: { color: colors.text, fontSize: 15, fontWeight: "800", marginTop: 4, marginBottom: 14 }, confirm: { minHeight: 52, borderRadius: radius.pill, backgroundColor: colors.primary, alignItems: "center", justifyContent: "center" }, confirmDisabled: { opacity: 0.45 }, confirmText: { color: "white", fontWeight: "900" },
  routeLoadingSheet: { position: "absolute", left: 0, right: 0, bottom: 0, backgroundColor: "rgba(247,249,255,0.98)", borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg, padding: spacing.lg, alignItems: "center" }, routeLoadingHandle: { width: 40, height: 4, borderRadius: 2, backgroundColor: colors.surfaceContainerHighest, marginBottom: 18 }, routeLoadingIcon: { width: 58, height: 58, borderRadius: 29, backgroundColor: colors.primaryContainer, alignItems: "center", justifyContent: "center" }, routeLoadingIconText: { color: colors.primary, fontSize: 27, fontWeight: "900" }, routeLoadingTitle: { color: colors.text, fontSize: 20, fontWeight: "900", marginTop: 14 }, routeLoadingBody: { color: colors.textMuted, textAlign: "center", marginTop: 6 }, progressTrack: { width: "100%", height: 7, borderRadius: 4, backgroundColor: colors.surfaceContainerHighest, marginTop: 18, overflow: "hidden" }, progressFill: { width: "63%", height: "100%", backgroundColor: colors.primary }, cancelRoute: { width: "100%", minHeight: 50, borderRadius: radius.pill, borderWidth: 1.5, borderColor: colors.primary, alignItems: "center", justifyContent: "center", marginTop: 18 }, cancelRouteText: { color: colors.primary, fontWeight: "900" },
});
