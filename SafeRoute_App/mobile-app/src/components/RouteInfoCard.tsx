import { Pressable, StyleSheet, Text, View } from "react-native";
import type { RouteResponse } from "@/lib/types";

interface Props {
  route: RouteResponse;
  /** Clears the destination + route (the ✕ button). */
  onClear: () => void;
}

/** "850 m" below 1 km, "1.4 km" above. */
function formatDistance(meters: number): string {
  if (meters < 1000) return `${Math.round(meters)} m`;
  return `${(meters / 1000).toFixed(1)} km`;
}

/** Rounded walking minutes, e.g. "17 dk". */
function formatDuration(seconds: number): string {
  return `${Math.max(1, Math.round(seconds / 60))} dk`;
}

/** Risk bucket → label + color. Thresholds are a UI choice, not a contract. */
function riskInfo(score: number): { label: string; color: string } {
  if (score <= 33) return { label: "Düşük risk", color: "#2E9E44" };
  if (score <= 66) return { label: "Orta risk", color: "#E8890C" };
  return { label: "Yüksek risk", color: "#E5484D" };
}

/**
 * Bottom card summarizing the fetched route: distance, walking time and the
 * 0-100 risk score from the backend.
 *
 * Visuals are intentionally plain — proper styling lands with the Figma
 * designs (end-to-end.md, item 9).
 */
export function RouteInfoCard({ route, onClear }: Props) {
  const risk = riskInfo(route.risk_score);

  return (
    <View style={styles.card}>
      <View style={styles.stats}>
        <View style={styles.stat}>
          <Text style={styles.statValue}>{formatDistance(route.distance_m)}</Text>
          <Text style={styles.statLabel}>Mesafe</Text>
        </View>

        <View style={styles.divider} />

        <View style={styles.stat}>
          <Text style={styles.statValue}>{formatDuration(route.duration_s)}</Text>
          <Text style={styles.statLabel}>Yürüyüş</Text>
        </View>

        <View style={styles.divider} />

        <View style={styles.stat}>
          <Text style={[styles.statValue, { color: risk.color }]}>
            {Math.round(route.risk_score)}
          </Text>
          <Text style={[styles.statLabel, { color: risk.color }]}>
            {risk.label}
          </Text>
        </View>
      </View>

      <Pressable
        style={({ pressed }) => [styles.close, pressed && styles.closePressed]}
        onPress={onClear}
        hitSlop={8}
      >
        <Text style={styles.closeText}>✕</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    position: "absolute",
    bottom: 24,
    left: 16,
    right: 16,
    flexDirection: "row",
    alignItems: "center",
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
