import { Pressable, StyleSheet, Text, View } from "react-native";
import type { NearbyAlert } from "@/lib/types";

interface Props {
  /** Active nearby alerts, nearest first; the most relevant one is shown. */
  alerts: NearbyAlert[];
  /** Dismisses the shown alert for the session. */
  onDismiss: (alertId: string) => void;
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
    default:
      return "👁️";
  }
}

/**
 * Proactive nearby-danger alert card (item 5): shown when the backend's
 * report-analysis pipeline dispatched an alert for something reported close
 * to the user. Renders the highest-priority (first) alert; a counter hints at
 * additional ones — dismissing reveals the next.
 *
 * Sits under the search bar and never covers the right-hand button column.
 */
export function AlertBanner({ alerts, onDismiss }: Props) {
  const alert = alerts[0];
  if (!alert) return null;

  const color = severityColor(alert.risk_score);
  const remaining = alerts.length - 1;

  return (
    <View style={[styles.card, { borderLeftColor: color }]}>
      <Text style={styles.icon}>{categoryIcon(alert.category)}</Text>

      <View style={styles.textColumn}>
        <Text style={[styles.title, { color }]} numberOfLines={1}>
          {alert.title}
        </Text>
        <Text style={styles.body} numberOfLines={2}>
          {alert.body}
        </Text>
        {remaining > 0 ? (
          <Text style={styles.more}>+{remaining} bildirim daha</Text>
        ) : null}
      </View>

      <Pressable
        onPress={() => onDismiss(alert.alert_id)}
        hitSlop={10}
        style={({ pressed }) => [styles.close, pressed && styles.closePressed]}
      >
        <Text style={styles.closeText}>✕</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    position: "absolute",
    top: 120,
    left: 16,
    right: 72, // leave the right-hand button column (heatmap/report) tappable
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
  icon: {
    fontSize: 22,
  },
  textColumn: {
    flex: 1,
  },
  title: {
    fontSize: 13,
    fontWeight: "700",
  },
  body: {
    marginTop: 2,
    fontSize: 13,
    color: "#333",
    lineHeight: 18,
  },
  more: {
    marginTop: 4,
    fontSize: 11,
    color: "#888",
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
