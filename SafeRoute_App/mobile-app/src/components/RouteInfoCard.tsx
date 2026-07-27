import { useMemo } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import BottomSheet, { BottomSheetScrollView } from "@gorhom/bottom-sheet";
import type { RouteKind, RouteOption } from "@/lib/mockRoute";
import type { StreetRiskExplanation } from "@/lib/types";
import type { StreetRiskStatus } from "@/hooks/useStreetRisk";
import { RiskExplanation } from "./RiskExplanation";

interface Props {
  /** The routes to choose between (safe, and shortest when available). */
  options: RouteOption[];
  /** Which route is currently selected (highlighted on the map). */
  selectedKind: RouteKind;
  /** Switch the selected route (item 1, AC #3). */
  onSelect: (kind: RouteKind) => void;
  /** Clears the destination + route (the ✕ button). */
  onClear: () => void;
  /** Item 2: LLM risk explanation for the selected route. */
  explanation: StreetRiskExplanation | null;
  explanationStatus: StreetRiskStatus;
  onRetryExplanation: () => void;
}

/** Line color per route, matching the map layers. */
const ROUTE_COLORS: Record<RouteKind, string> = {
  safe: "#1D6FEB",
  shortest: "#8A8A8A",
};

/** "850 m" below 1 km, "1.4 km" above. */
function formatDistance(meters: number): string {
  if (meters < 1000) return `${Math.round(meters)} m`;
  return `${(meters / 1000).toFixed(1)} km`;
}

/** Rounded walking minutes, e.g. "17 dk". */
function formatDuration(seconds: number): string {
  return `${Math.max(1, Math.round(seconds / 60))} dk`;
}

/**
 * Risk bucket → label + color. Thresholds are a UI choice, not a contract.
 * Null = unknown (the backend doesn't report risk for the shortest route).
 */
function riskInfo(score: number | null): { label: string; color: string } {
  if (score === null) return { label: "Risk bilinmiyor", color: "#8A8A8A" };
  if (score <= 33) return { label: "Düşük risk", color: "#2E9E44" };
  if (score <= 66) return { label: "Orta risk", color: "#E8890C" };
  return { label: "Yüksek risk", color: "#E5484D" };
}

/**
 * Draggable bottom sheet summarizing the selected route: distance, walking time
 * and the 0-100 risk score. When both a safe and a shortest route are available
 * it shows a segmented toggle so the user can switch between them (item 1,
 * AC #2/#3); the map highlights whichever is selected here.
 *
 * Two snap points: collapsed shows the toggle + the three stats, expanded also
 * reveals the LLM risk explanation. Dragging is handled by @gorhom/bottom-sheet
 * (built on Gesture.Pan + Reanimated, both already in the project).
 *
 * No backdrop on purpose — the map above the sheet has to stay pannable while
 * the route panel is open.
 *
 * Visuals are intentionally plain — proper styling lands with the Figma
 * designs (end-to-end.md, item 9).
 */
export function RouteInfoCard({
  options,
  selectedKind,
  onSelect,
  onClear,
  explanation,
  explanationStatus,
  onRetryExplanation,
}: Props) {
  // Collapsed height fits the toggle + stats row; expanded gives the risk
  // explanation room without covering the whole map.
  const snapPoints = useMemo(() => [200, "62%"], []);

  const selected =
    options.find((option) => option.kind === selectedKind) ?? options[0];
  if (!selected) return null;

  const risk = riskInfo(selected.risk_score);
  // Only show the toggle when there's an actual choice to make.
  const showToggle = options.length > 1;

  return (
    <BottomSheet
      index={0}
      snapPoints={snapPoints}
      // The ✕ clears the destination; panning the sheet away would leave a
      // route drawn on the map with no way to read its stats.
      enablePanDownToClose={false}
      backgroundStyle={styles.sheetBackground}
      handleIndicatorStyle={styles.sheetHandle}
    >
      <BottomSheetScrollView contentContainerStyle={styles.content}>
        {/* Item 1: route selection toggle (segmented control). */}
        {showToggle ? (
          <View style={styles.toggle}>
            {options.map((option) => {
              const active = option.kind === selectedKind;
              return (
                <Pressable
                  key={option.kind}
                  style={[styles.segment, active && styles.segmentActive]}
                  onPress={() => onSelect(option.kind)}
                >
                  <View
                    style={[
                      styles.segmentDot,
                      { backgroundColor: ROUTE_COLORS[option.kind] },
                    ]}
                  />
                  <Text
                    style={[
                      styles.segmentText,
                      active && styles.segmentTextActive,
                    ]}
                  >
                    {option.label}
                  </Text>
                </Pressable>
              );
            })}
          </View>
        ) : null}

        <View style={styles.mainRow}>
          <View style={styles.stats}>
            <View style={styles.stat}>
              <Text style={styles.statValue}>
                {formatDistance(selected.distance_m)}
              </Text>
              <Text style={styles.statLabel}>Mesafe</Text>
            </View>

            <View style={styles.divider} />

            <View style={styles.stat}>
              <Text style={styles.statValue}>
                {formatDuration(selected.duration_s)}
              </Text>
              <Text style={styles.statLabel}>Yürüyüş</Text>
            </View>

            <View style={styles.divider} />

            <View style={styles.stat}>
              <Text style={[styles.statValue, { color: risk.color }]}>
                {selected.risk_score === null
                  ? "—"
                  : // "~" marks a client-side estimate from the heatmap rather
                    // than the routing engine's own score.
                    `${selected.risk_estimated ? "~" : ""}${Math.round(
                      selected.risk_score,
                    )}`}
              </Text>
              <Text style={[styles.statLabel, { color: risk.color }]}>
                {selected.risk_estimated
                  ? `${risk.label} (tahmini)`
                  : risk.label}
              </Text>
            </View>
          </View>

          <Pressable
            style={({ pressed }) => [
              styles.close,
              pressed && styles.closePressed,
            ]}
            onPress={onClear}
            hitSlop={8}
          >
            <Text style={styles.closeText}>✕</Text>
          </Pressable>
        </View>

        {/* Item 2: LLM risk explanation for the selected route. Sits below the
            collapsed fold — drag the sheet up to read it. */}
        <RiskExplanation
          explanation={explanation}
          status={explanationStatus}
          onRetry={onRetryExplanation}
        />
      </BottomSheetScrollView>
    </BottomSheet>
  );
}

const styles = StyleSheet.create({
  sheetBackground: {
    backgroundColor: "#fff",
    borderTopLeftRadius: 16,
    borderTopRightRadius: 16,
    shadowColor: "#000",
    shadowOpacity: 0.15,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: -2 },
    elevation: 8,
  },
  sheetHandle: {
    backgroundColor: "#d0d0d0",
    width: 40,
  },
  content: {
    paddingHorizontal: 16,
    paddingBottom: 24,
  },
  toggle: {
    flexDirection: "row",
    backgroundColor: "#f2f2f2",
    borderRadius: 10,
    padding: 3,
    marginBottom: 12,
  },
  segment: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
    paddingVertical: 7,
    borderRadius: 8,
  },
  segmentActive: {
    backgroundColor: "#fff",
    shadowColor: "#000",
    shadowOpacity: 0.1,
    shadowRadius: 3,
    shadowOffset: { width: 0, height: 1 },
    elevation: 2,
  },
  segmentDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
  },
  segmentText: {
    fontSize: 13,
    color: "#777",
    fontWeight: "500",
  },
  segmentTextActive: {
    color: "#111",
    fontWeight: "600",
  },
  mainRow: {
    flexDirection: "row",
    alignItems: "center",
  },
  stats: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
  },
  stat: {
    flex: 1,
    alignItems: "center",
  },
  statValue: {
    fontSize: 17,
    fontWeight: "600",
    color: "#111",
  },
  statLabel: {
    fontSize: 12,
    color: "#777",
    marginTop: 2,
  },
  divider: {
    width: StyleSheet.hairlineWidth,
    height: 28,
    backgroundColor: "#ddd",
  },
  close: {
    marginLeft: 8,
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: "#f2f2f2",
    alignItems: "center",
    justifyContent: "center",
  },
  closePressed: {
    backgroundColor: "#e2e2e2",
  },
  closeText: {
    fontSize: 13,
    color: "#555",
  },
});
