import { useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Keyboard,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { searchPlaces, type GeocodingResult } from "@/lib/geocoding";
import type { LngLat } from "@/lib/types";
import { colors, radius, spacing, touchTarget } from "@/theme/tokens";

interface Props {
  proximity?: LngLat;
  /** Mevcut konum → varış rotası. */
  onSelect: (result: GeocodingResult) => void;
  onExpandedChange?: (expanded: boolean) => void;
}

const DEBOUNCE_MS = 350;
const FALLBACK_PLACES: GeocodingResult[] = [
  {
    name: "Millennium Park",
    address: "201 E Randolph St, Chicago, IL",
    coordinate: [-87.6226, 41.8826],
  },
  {
    name: "Union Station",
    address: "225 S Canal St, Chicago, IL",
    coordinate: [-87.6403, 41.8786],
  },
];

type Phase = "search" | "directions";

export function DestinationSearchBar({
  proximity,
  onSelect,
  onExpandedChange,
}: Props) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<GeocodingResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [searched, setSearched] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [phase, setPhase] = useState<Phase>("search");
  const [destination, setDestination] = useState<GeocodingResult | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const proximityLng = proximity?.[0];
  const proximityLat = proximity?.[1];

  const setExpandedSafe = (value: boolean) => {
    setExpanded(value);
    onExpandedChange?.(value);
  };

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (query.trim().length < 2) {
      setResults([]);
      setSearching(false);
      setSearched(false);
      return;
    }
    setSearching(true);
    debounceRef.current = setTimeout(async () => {
      const searchProximity: LngLat | undefined =
        proximityLng !== undefined && proximityLat !== undefined
          ? [proximityLng, proximityLat]
          : undefined;
      const hits = await searchPlaces(query, searchProximity);
      setResults(hits);
      setSearching(false);
      setSearched(true);
    }, DEBOUNCE_MS);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query, proximityLng, proximityLat]);

  const resetAll = () => {
    setQuery("");
    setResults([]);
    setSearched(false);
    setDestination(null);
    setPhase("search");
    setExpandedSafe(false);
    Keyboard.dismiss();
  };

  const openDirections = (place: GeocodingResult) => {
    setDestination(place);
    setPhase("directions");
    Keyboard.dismiss();
  };

  const createFromGps = () => {
    if (!destination) return;
    const place = destination;
    resetAll();
    onSelect(place);
  };

  const list = query.trim().length >= 2 ? results : FALLBACK_PLACES;

  return (
    <View
      pointerEvents="box-none"
      style={[styles.root, expanded && styles.rootExpanded]}
    >
      {expanded ? (
        <Pressable
          style={styles.scrim}
          onPress={() => {
            if (phase === "directions") {
              setPhase("search");
              setDestination(null);
              return;
            }
            setExpandedSafe(false);
            Keyboard.dismiss();
          }}
        />
      ) : null}

      {/* Kapalı arama çubuğu */}
      {!expanded ? (
        <Pressable
          style={styles.searchShell}
          onPress={() => setExpandedSafe(true)}
        >
          <Text style={styles.searchIcon}>⌕</Text>
          <Text style={styles.placeholder}>Nereye gidiyorsun?</Text>
        </Pressable>
      ) : null}

      {expanded && phase === "search" ? (
        <>
          <View style={styles.searchShellExpanded}>
            <Pressable
              accessibilityLabel="Aramayı kapat"
              style={styles.backButton}
              onPress={() => {
                setExpandedSafe(false);
                Keyboard.dismiss();
              }}
            >
              <Text style={styles.back}>‹</Text>
            </Pressable>
            <TextInput
              style={styles.input}
              value={query}
              autoFocus
              onChangeText={setQuery}
              placeholder="Nereye gidiyorsun?"
              placeholderTextColor="#758391"
              autoCorrect={false}
              returnKeyType="search"
            />
            {searching ? (
              <ActivityIndicator size="small" color={colors.primary} />
            ) : query ? (
              <Pressable style={styles.clear} onPress={() => setQuery("")}>
                <Text style={styles.clearText}>×</Text>
              </Pressable>
            ) : null}
          </View>

          <View style={styles.panel} pointerEvents="auto">
            <ScrollView
              style={styles.scroll}
              contentContainerStyle={styles.scrollContent}
              keyboardShouldPersistTaps="handled"
              showsVerticalScrollIndicator={false}
            >
              <Text style={styles.sectionTitle}>
                {query ? "SONUÇLAR" : "ÖNERİLEN YERLER"}
              </Text>
              {searched && !searching && results.length === 0 ? (
                <Text style={styles.empty}>
                  Sonuç bulunamadı. Adresi daha ayrıntılı yazmayı dene.
                </Text>
              ) : (
                list.map((item, index) => (
                  <Pressable
                    key={`${item.coordinate.join(",")}-${index}`}
                    style={styles.placeRow}
                    onPress={() => openDirections(item)}
                  >
                    <View style={styles.placeIcon}>
                      <Text style={styles.placeIconText}>◷</Text>
                    </View>
                    <View style={styles.placeCopy}>
                      <Text style={styles.placeName}>{item.name}</Text>
                      <Text style={styles.placeAddress} numberOfLines={1}>
                        {item.address}
                      </Text>
                    </View>
                  </Pressable>
                ))
              )}
            </ScrollView>
          </View>
        </>
      ) : null}

      {/* Google Maps benzeri yol tarifi adımı */}
      {expanded && phase === "directions" && destination ? (
        <View style={styles.directionsSheet} pointerEvents="auto">
          <View style={styles.directionsHeader}>
            <Text style={styles.directionsTitle}>Yol tarifi</Text>
            <Pressable
              style={styles.closeBtn}
              onPress={() => {
                setPhase("search");
                setDestination(null);
              }}
              accessibilityLabel="Kapat"
            >
              <Text style={styles.closeBtnText}>×</Text>
            </Pressable>
          </View>

          <View style={styles.routeFields}>
            <View style={styles.routeRail}>
              <View style={styles.railDot} />
              <View style={styles.railLine} />
              <View style={styles.railPin} />
            </View>
            <View style={styles.routeInputs}>
              <View style={styles.startField}>
                <Text style={styles.fieldLabel}>BAŞLANGIÇ</Text>
                <Text style={styles.startHint}>Mevcut konumunuz</Text>
              </View>
              <View style={styles.endField}>
                <Text style={styles.fieldLabel}>VARIŞ</Text>
                <Text style={styles.endName} numberOfLines={2}>
                  {destination.name}
                </Text>
                <Text style={styles.endAddress} numberOfLines={1}>
                  {destination.address}
                </Text>
              </View>
            </View>
          </View>

          <Text style={styles.suggestTitle}>Öneriler</Text>
          <Pressable style={styles.suggestRow} onPress={createFromGps}>
            <View style={styles.suggestIcon}>
              <Text style={styles.suggestIconText}>⌖</Text>
            </View>
            <View style={styles.suggestCopy}>
              <Text style={styles.suggestName}>Konumunuz</Text>
              <Text style={styles.suggestCaption}>Mevcut konumdan başla</Text>
            </View>
          </Pressable>

          <Pressable style={styles.primaryAction} onPress={createFromGps}>
            <Text style={styles.primaryActionText}>Güvenli rota oluştur</Text>
          </Pressable>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    position: "absolute",
    top: 0,
    right: 0,
    bottom: 0,
    left: 0,
    zIndex: 15,
  },
  rootExpanded: {
    zIndex: 40,
    elevation: 24,
  },
  scrim: {
    position: "absolute",
    top: 0,
    right: 0,
    bottom: 0,
    left: 0,
    backgroundColor: "rgba(247,249,252,0.97)",
    zIndex: 1,
  },
  searchShell: {
    position: "absolute",
    top: 109,
    left: spacing.md,
    right: spacing.md,
    height: 52,
    zIndex: 3,
    flexDirection: "row",
    alignItems: "center",
    gap: 9,
    borderRadius: radius.sm,
    paddingHorizontal: 14,
    backgroundColor: colors.surface,
    shadowColor: "#000",
    shadowOpacity: 0.13,
    shadowRadius: 9,
    elevation: 6,
  },
  searchShellExpanded: {
    position: "absolute",
    top: 52,
    left: spacing.md,
    right: spacing.md,
    height: 52,
    zIndex: 3,
    flexDirection: "row",
    alignItems: "center",
    gap: 9,
    borderRadius: radius.sm,
    paddingHorizontal: 10,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.borderSoft,
    elevation: 8,
  },
  searchIcon: { color: colors.textMuted, fontSize: 24 },
  placeholder: { color: "#758391", fontSize: 15, flex: 1 },
  backButton: {
    width: 34,
    height: touchTarget,
    alignItems: "center",
    justifyContent: "center",
  },
  back: { color: colors.text, fontSize: 32 },
  input: { flex: 1, color: colors.text, fontSize: 15 },
  clear: {
    width: 36,
    height: 40,
    alignItems: "center",
    justifyContent: "center",
  },
  clearText: { color: colors.textMuted, fontSize: 24 },
  panel: {
    position: "absolute",
    top: 116,
    left: spacing.md,
    right: spacing.md,
    bottom: 86,
    zIndex: 2,
    backgroundColor: colors.background,
    borderRadius: radius.md,
    paddingHorizontal: 4,
  },
  scroll: { flex: 1 },
  scrollContent: { paddingBottom: 16 },
  sectionTitle: {
    color: colors.textMuted,
    fontSize: 11,
    letterSpacing: 1.1,
    fontWeight: "900",
    marginVertical: 10,
    marginLeft: 4,
  },
  placeRow: {
    minHeight: 63,
    flexDirection: "row",
    alignItems: "center",
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.borderSoft,
    paddingHorizontal: 4,
  },
  placeIcon: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.surfaceContainer,
  },
  placeIconText: { color: colors.primary, fontSize: 18 },
  placeCopy: { flex: 1, paddingLeft: 12 },
  placeName: { color: colors.text, fontWeight: "800" },
  placeAddress: { color: colors.textMuted, fontSize: 12, marginTop: 2 },
  empty: {
    color: colors.textMuted,
    textAlign: "center",
    padding: spacing.lg,
    lineHeight: 20,
  },
  directionsSheet: {
    position: "absolute",
    top: 52,
    left: spacing.md,
    right: spacing.md,
    bottom: 86,
    zIndex: 3,
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: spacing.md,
    borderWidth: 1,
    borderColor: colors.borderSoft,
    shadowColor: "#000",
    shadowOpacity: 0.12,
    shadowRadius: 12,
    elevation: 8,
  },
  directionsHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: 14,
  },
  directionsTitle: {
    color: colors.primary,
    fontSize: 20,
    fontWeight: "900",
  },
  closeBtn: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: colors.surfaceContainer,
    alignItems: "center",
    justifyContent: "center",
  },
  closeBtnText: { color: colors.text, fontSize: 22, fontWeight: "600" },
  routeFields: {
    flexDirection: "row",
    backgroundColor: colors.surfaceContainer,
    borderRadius: radius.md,
    padding: 12,
    marginBottom: 16,
  },
  routeRail: {
    width: 22,
    alignItems: "center",
    paddingTop: 8,
    paddingBottom: 8,
  },
  railDot: {
    width: 12,
    height: 12,
    borderRadius: 6,
    borderWidth: 3,
    borderColor: colors.primary,
    backgroundColor: colors.surface,
  },
  railLine: {
    flex: 1,
    width: 2,
    backgroundColor: colors.borderSoft,
    marginVertical: 4,
  },
  railPin: {
    width: 12,
    height: 12,
    borderRadius: 6,
    backgroundColor: colors.secondary,
  },
  routeInputs: { flex: 1, gap: 10 },
  startField: {
    minHeight: 52,
    justifyContent: "center",
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.borderSoft,
    paddingBottom: 10,
  },
  endField: { minHeight: 52, justifyContent: "center" },
  fieldLabel: {
    color: colors.textMuted,
    fontSize: 10,
    fontWeight: "900",
    letterSpacing: 0.8,
    marginBottom: 3,
  },
  startHint: { color: colors.textMuted, fontSize: 13, fontWeight: "600" },
  endName: { color: colors.text, fontSize: 15, fontWeight: "800" },
  endAddress: { color: colors.textMuted, fontSize: 12, marginTop: 2 },
  suggestTitle: {
    color: colors.textMuted,
    fontSize: 11,
    fontWeight: "900",
    letterSpacing: 1,
    marginBottom: 8,
  },
  suggestRow: {
    minHeight: 58,
    flexDirection: "row",
    alignItems: "center",
    borderRadius: radius.sm,
    paddingHorizontal: 8,
    marginBottom: 6,
    backgroundColor: colors.surfaceContainer,
  },
  suggestIcon: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: colors.primaryContainer,
    alignItems: "center",
    justifyContent: "center",
  },
  suggestIconMap: { backgroundColor: colors.secondaryContainer },
  suggestIconText: { color: colors.primary, fontSize: 18, fontWeight: "800" },
  suggestCopy: { flex: 1, marginLeft: 12 },
  suggestName: { color: colors.text, fontWeight: "800", fontSize: 15 },
  suggestCaption: { color: colors.textMuted, fontSize: 12, marginTop: 2 },
  primaryAction: {
    marginTop: "auto",
    minHeight: 52,
    borderRadius: radius.pill,
    backgroundColor: colors.primary,
    alignItems: "center",
    justifyContent: "center",
  },
  primaryActionText: { color: "white", fontWeight: "900" },
});
