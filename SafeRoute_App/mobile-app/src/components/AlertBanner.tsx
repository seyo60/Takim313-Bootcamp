import { Pressable, StyleSheet, Text, View } from "react-native";
import { formatDistance } from "@/lib/nearbyAlerts";
import type { NearbyAlert } from "@/lib/types";

interface Props {
  /** Active nearby alerts, nearest first (the hook caps this at 3). */
  alerts: NearbyAlert[];
  /** Dismisses one alert for the session. */
  onDismiss: (alertId: string) => void;
  /** Centers the map on the alert's location (AC #3). */
  onFocus: (alert: NearbyAlert) => void;
}

/** Severity color from the report's 0-100 risk score (same buckets as the LLM). */
function severityColor(riskScore: number): string {
  if (riskScore > 80) return "#E5484D"; // critical — red
  if (riskScore > 60) return "#E8890C"; // high — orange
  if (riskScore > 30) return "#D9A514"; // medium — amber
  return "#5B7083"; // low — muted info
}

/** Category → small leading icon. Kept coarse on purpose. */
function categoryIcon(category: string): string {
  switch (category) {
    case "violent":
      return "🚨";
    case "theft":
      return "🥷";
    case "harassment":
      return "⚠️";
    case "environmental":
      return "💡";
    // Heatmap-derived alerts have no LLM category (see lib/nearbyAlerts.ts).
    case "risk_zone":
      return "🔺";
    default:
      return "👁️";
  }
}

/**
 * Proactive nearby-danger alert stack (item 5): shown when a high or critical
 * risk is active close to the user. Up to three cards, nearest at the top;
 * tapping one flies the map to it, ✕ dismisses just that card.
 *
 * Sits under the search bar and never covers the right-hand button column.
 */
export function AlertBanner({ alerts, onDismiss, onFocus }: Props) {
  if (alerts.length === 0) return null;

  return (
    <View style={styles.stack} pointerEvents="box-none">
      {alerts.map((alert) => {
        const color = severityColor(alert.risk_score);

        return (
          <Pressable
            key={alert.alert_id}
            onPress={() => onFocus(alert)}
            accessibilityRole="button"
            accessibilityLabel={`${alert.title}. ${alert.body} Haritada göstermek için dokunun.`}
            style={({ pressed }) => [
              styles.card,
              { borderLeftColor: color },
              pressed && styles.cardPressed,
            ]}
          >
            <Text style={styles.icon}>{categoryIcon(alert.category)}</Text>

            <View style={styles.textColumn}>
              <View style={styles.headerRow}>
                <Text style={[styles.title, { color }]} numberOfLines={1}>
                  {alert.title}
                </Text>
                {/* AC #2: the numeric risk score, not just the accent color. */}
                <View style={[styles.riskChip, { backgroundColor: color }]}>
                  <Text style={styles.riskChipText}>
                    {Math.round(alert.risk_score)}
                  </Text>
                </View>
              </View>

              {/* AC #2: how far away the danger is. */}
              {alert.distance_m !== undefined ? (
                <Text style={styles.distance}>
                  {formatDistance(alert.distance_m)}
                </Text>
              ) : null}

              <Text style={styles.body} numberOfLines={2}>
                {alert.body}
              </Text>
            </View>

            <Pressable
              onPress={() => onDismiss(alert.alert_id)}
              hitSlop={10}
              accessibilityRole="button"
              accessibilityLabel="Bildirimi kapat"
              style={({ pressed }) => [
                styles.close,
                pressed && styles.closePressed,
              ]}
            >
              <Text style={styles.closeText}>✕</Text>
            </Pressable>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  stack: {
    position: "absolute",
    top: 120,
    left: 16,
    right: 72, // leave the right-hand button column (heatmap/report) tappable
    gap: 8,
  },
  card: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "#fff",
    borderRadius: 12,
    borderLeftWidth: 4,
    paddingVertical: 10,
    paddingLeft: 10,
    paddingRight: 8,
    gap: 8,
    shadowColor: "#000",
    shadowOpacity: 0.18,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 3 },
    elevation: 5,
  },
  cardPressed: {
    backgroundColor: "#F4F6F8",
  },
  icon: {
    fontSize: 22,
  },
  textColumn: {
    flex: 1,
  },
  headerRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },
  title: {
    flex: 1,
    fontSize: 13,
    fontWeight: "700",
  },
  riskChip: {
    minWidth: 26,
    paddingHorizontal: 6,
    paddingVertical: 1,
    borderRadius: 8,
    alignItems: "center",
  },
  riskChipText: {
    fontSize: 11,
    fontWeight: "700",
    color: "#fff",
  },
  distance: {
    marginTop: 1,
    fontSize: 11,
    fontWeight: "600",
    color: "#666",
  },
  body: {
    marginTop: 2,
    fontSize: 13,
    color: "#333",
    lineHeight: 18,
  },
  close: {
    width: 26,
    height: 26,
    borderRadius: 13,
    backgroundColor: "#f2f2f2",
    alignItems: "center",
    justifyContent: "center",
  },
  closePressed: {
    backgroundColor: "#e2e2e2",
  },
  closeText: {
    fontSize: 12,
    color: "#555",
  },
});
