import { Pressable, StyleSheet, Text, View } from "react-native";
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
 * Bottom panel summarizing the selected route: distance, walking time and the
 * 0-100 risk score from the backend. When both a safe and a shortest route are
 * available it shows a segmented toggle so the user can switch between them
 * (item 1, AC #2/#3); the map highlights whichever is selected here.
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
  const selected =
    options.find((option) => option.kind === selectedKind) ?? options[0];
  if (!selected) return null;

  const risk = riskInfo(selected.risk_score);
  // Only show the toggle when there's an actual choice to make.
  const showToggle = options.length > 1;

  return (
    <View style={styles.card}>
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
                : Math.round(selected.risk_score)}
            </Text>
            <Text style={[styles.statLabel, { color: risk.color }]}>
              {risk.label}
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

      {/* Item 2: LLM risk explanation for the selected route. */}
      <RiskExplanation
        explanation={explanation}
        status={explanationStatus}
        onRetry={onRetryExplanation}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    position: "absolute",
    bottom: 24,
    left: 16,
    right: 16,
    backgroundColor: "#fff",
    borderRadius: 14,
    paddingVertical: 14,
    paddingHorizontal: 16,
    shadowColor: "#000",
    shadowOpacity: 0.15,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 2 },
    elevation: 4,
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
