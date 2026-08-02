import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { router, useFocusEffect } from "expo-router";
import Mapbox, { Camera, LineLayer, MapView, ShapeSource, UserLocation } from "@rnmapbox/maps";
import * as Location from "expo-location";
import * as Speech from "expo-speech";
import { useNavigationSession } from "@/providers/NavigationProvider";
import { distanceMeters, projectOnRoute } from "@/lib/navigationMath";
import { getRoute } from "@/lib/api";
import { getRouteOptions } from "@/lib/mockRoute";
import type { LngLat } from "@/lib/types";
import { colors, radius, safetyDisclaimer, spacing, touchTarget } from "@/theme/tokens";
import { MapUnavailable } from "@/components/MapChrome";

type NavigationState = "locating" | "active" | "rerouting" | "degraded" | "arrived";
const OFF_ROUTE_THRESHOLD_M = 35;
const MAPBOX_TOKEN = process.env.EXPO_PUBLIC_MAPBOX_TOKEN?.trim() ?? "";
const MAPBOX_TOKEN_USABLE = MAPBOX_TOKEN.startsWith("pk.") && MAPBOX_TOKEN.length >= 50;
if (MAPBOX_TOKEN_USABLE) Mapbox.setAccessToken(MAPBOX_TOKEN);

export default function ActiveNavigation() {
  const { session, replace, stop } = useNavigationSession();
  const [position, setPosition] = useState<LngLat | null>(null);
  const [state, setState] = useState<NavigationState>("locating");
  const [voiceEnabled, setVoiceEnabled] = useState(true);
  const [language, setLanguage] = useState<"tr-TR" | "en-US">("tr-TR");
  const [offRouteSamples, setOffRouteSamples] = useState(0);
  const [mapFailed, setMapFailed] = useState(!MAPBOX_TOKEN_USABLE);
  const [mapKey, setMapKey] = useState(0);
  const offRouteSamplesRef = useRef(0);
  const spokenRef = useRef(new Set<string>());
  const rerouteGeneration = useRef(0);
  const reroutingRef = useRef(false);

  useEffect(() => { if (!session) router.replace("/"); }, [session]);
  const coordinates = useMemo(
    () => (session?.option.geometry.coordinates ?? []) as LngLat[],
    [session?.option.geometry.coordinates]
  );
  const projection = useMemo(() => position ? projectOnRoute(position, coordinates) : null, [coordinates, position]);
  const steps = useMemo(() => session?.option.detail.steps ?? [], [session?.option.detail.steps]);
  const currentStep = useMemo(() => {
    if (!position || !steps.length) return steps[0];
    return steps.reduce((best, step) => distanceMeters(position, step.location) < distanceMeters(position, best.location) ? step : best, steps[0]);
  }, [position, steps]);

  const reroute = useCallback(async (origin: LngLat) => {
    if (!session || reroutingRef.current) return;
    reroutingRef.current = true;
    const generation = ++rerouteGeneration.current;
    setState("rerouting");
    const response = await getRoute(origin, session.destination, 1, undefined, session.profile);
    if (generation !== rerouteGeneration.current) return;
    const replacement = response ? getRouteOptions(response)[0] : undefined;
    if (replacement) {
      replace(replacement);
      offRouteSamplesRef.current = 0;
      setOffRouteSamples(0);
      setState("active");
      spokenRef.current.clear();
    } else setState("degraded");
    reroutingRef.current = false;
  }, [replace, session]);

  useFocusEffect(useCallback(() => {
    let subscription: Location.LocationSubscription | null = null;
    let alive = true;
    (async () => {
      const permission = await Location.requestForegroundPermissionsAsync();
      if (!alive || permission.status !== "granted") { setState("degraded"); return; }
      subscription = await Location.watchPositionAsync({ accuracy: Location.Accuracy.High, distanceInterval: 4, timeInterval: 2000 }, (sample) => {
        if (!alive) return;
        const next: LngLat = [sample.coords.longitude, sample.coords.latitude];
        setPosition(next); setState((value) => value === "locating" ? "active" : value);
        const match = projectOnRoute(next, coordinates);
        const reliable = (sample.coords.accuracy ?? 999) <= 30;
        if (match && reliable && match.distanceFromRouteM > OFF_ROUTE_THRESHOLD_M) {
          offRouteSamplesRef.current += 1;
          setOffRouteSamples(offRouteSamplesRef.current);
          if (offRouteSamplesRef.current >= 3) void reroute(next);
        } else if (reliable) {
          offRouteSamplesRef.current = 0;
          setOffRouteSamples(0);
        }
        if (match && match.remainingM < 15) setState("arrived");
      });
    })();
    return () => { alive = false; subscription?.remove(); Speech.stop(); };
  }, [coordinates, reroute]));

  useEffect(() => {
    if (!voiceEnabled || !currentStep || spokenRef.current.has(currentStep.step_id)) return;
    spokenRef.current.add(currentStep.step_id);
    try { Speech.speak(currentStep.instruction, { language, rate: 0.95 }); } catch { /* visual guidance remains available */ }
  }, [currentStep, language, voiceEnabled]);

  if (!session) return null;
  const finish = () => { rerouteGeneration.current += 1; Speech.stop(); stop(); router.replace("/"); };
  return (
    <View style={styles.container}>
      {MAPBOX_TOKEN_USABLE && !mapFailed ? <MapView key={mapKey} style={styles.map} styleURL={Mapbox.StyleURL.Light} compassEnabled onMapLoadingError={() => setMapFailed(true)}>
        <Camera centerCoordinate={position ?? coordinates[0]} zoomLevel={17} animationDuration={500} followUserLocation={Boolean(position)} followZoomLevel={17} />
        <UserLocation visible showsUserHeadingIndicator />
        <ShapeSource id="activeRoute" shape={{ type: "Feature", properties: {}, geometry: session.option.geometry }}><LineLayer id="activeRouteLine" style={{ lineColor: colors.primary, lineWidth: 7, lineCap: "round", lineJoin: "round" }} /></ShapeSource>
      </MapView> : <MapUnavailable reason={MAPBOX_TOKEN_USABLE ? "load" : "token"} onRetry={() => { setMapFailed(!MAPBOX_TOKEN_USABLE); setMapKey((value) => value + 1); }} />}
      <View style={styles.instruction} accessibilityLiveRegion="polite">
        <Text style={styles.state}>{state === "rerouting" ? "Rota yeniden hesaplanıyor…" : state === "degraded" ? "Konum zayıf — görsel rota devam ediyor" : state === "arrived" ? "Hedefe ulaştın" : offRouteSamples > 0 ? "Konum doğrulanıyor…" : "Aktif navigasyon"}</Text>
        <Text style={styles.maneuver}>{currentStep?.instruction ?? "Rotayı takip et"}</Text>
        <Text style={styles.remaining}>{Math.round(projection?.remainingM ?? session.option.distance_m)} m · yaklaşık {Math.max(1, Math.round((projection?.remainingM ?? session.option.distance_m) / 80))} dk</Text>
        <Text style={styles.disclaimer}>{safetyDisclaimer}</Text>
      </View>
      <View style={styles.controls}>
        <Pressable style={styles.control} onPress={() => setVoiceEnabled((value) => !value)}><Text style={styles.controlText}>{voiceEnabled ? "Sesi kapat" : "Sesi aç"}</Text></Pressable>
        <Pressable style={styles.control} onPress={() => setLanguage((value) => value === "tr-TR" ? "en-US" : "tr-TR")}><Text style={styles.controlText}>{language === "tr-TR" ? "TR" : "EN"}</Text></Pressable>
        <Pressable style={[styles.control, styles.stop]} onPress={finish}><Text style={styles.stopText}>Bitir</Text></Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({ container: { flex: 1, backgroundColor: colors.background }, map: { flex: 1 }, instruction: { position: "absolute", top: 54, left: spacing.md, right: spacing.md, padding: spacing.md, borderRadius: radius.md, backgroundColor: colors.surface, shadowColor: "#000", shadowOpacity: 0.16, shadowRadius: 8, elevation: 5 }, state: { color: colors.secondary, fontSize: 13, fontWeight: "800" }, maneuver: { color: colors.text, fontSize: 23, fontWeight: "800", marginTop: 6 }, remaining: { color: colors.textMuted, marginTop: 6 }, disclaimer: { color: colors.textMuted, fontSize: 11, marginTop: spacing.sm }, controls: { position: "absolute", bottom: 28, left: spacing.md, right: spacing.md, flexDirection: "row", gap: spacing.sm }, control: { minHeight: touchTarget, flex: 1, backgroundColor: colors.surface, borderRadius: radius.sm, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border }, controlText: { color: colors.primary, fontWeight: "800" }, stop: { backgroundColor: colors.error, borderColor: colors.error }, stopText: { color: "#fff", fontWeight: "800" } });
