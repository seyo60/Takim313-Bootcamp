import { ActivityIndicator, Pressable, StyleSheet, Text, View } from "react-native";
import type { RiskLevel, StreetRiskExplanation } from "@/lib/types";
import type { StreetRiskStatus } from "@/hooks/useStreetRisk";

interface Props {
  explanation: StreetRiskExplanation | null;
  status: StreetRiskStatus;
  /** Retry a failed explanation fetch (fallback state). */
  onRetry: () => void;
}

/** Badge label + colors per risk level (AC #1). */
const LEVEL_STYLE: Record<
  RiskLevel,
  { label: string; bg: string; text: string }
> = {
  low: { label: "Düşük risk", bg: "#2E9E44", text: "#ffffff" },
  medium: { label: "Orta risk", bg: "#F5C518", text: "#4A3B00" },
  high: { label: "Yüksek risk", bg: "#E8890C", text: "#ffffff" },
  critical: { label: "Kritik risk", bg: "#E5484D", text: "#ffffff" },
};

/**
 * LLM-backed risk explanation for the selected route (item 2): a colored risk
 * badge, a ≤2 sentence Turkish rationale, up to 3 risk factors, and the
 * historical/live/social channel breakdown.
 *
 * Handles loading and a placeholder error/fallback state (AC #6). The full
 * guardrail/error treatment lands with item 6.
 */
export function RiskExplanation({ explanation, status, onRetry }: Props) {
  if (status === "idle") return null;

  if (status === "loading") {
    return (
      <View style={styles.section}>
        <View style={styles.loadingRow}>
          <ActivityIndicator size="small" color="#888" />
          <Text style={styles.loadingText}>Risk açıklaması hazırlanıyor…</Text>
        </View>
      </View>
    );
  }

  // AC #6: placeholder fallback when the LLM errors / guardrail blocks output.
  // TODO(osman): richer guardrail messaging lands with item 6 (fallback UI).
  if (status === "error" || !explanation) {
    return (
      <View style={styles.section}>
        <View style={styles.fallback}>
          <Text style={styles.fallbackText}>
            Risk açıklaması şu an alınamıyor.
          </Text>
          <Pressable onPress={onRetry} hitSlop={8}>
            <Text style={styles.retryText}>Tekrar dene</Text>
          </Pressable>
        </View>
      </View>
    );
  }

  const level = LEVEL_STYLE[explanation.risk_level];
  // Defensive clamp: keep to ≤3 factors even if the backend sends more (AC #3).
  const factors = explanation.factors.slice(0, 3);
  const { historical, live, social } = explanation.channels;

  return (
    <View style={styles.section}>
      <View style={[styles.badge, { backgroundColor: level.bg }]}>
        <Text style={[styles.badgeText, { color: level.text }]}>
          {level.label}
        </Text>
      </View>

      <Text style={styles.explanation}>{explanation.explanation}</Text>

      {factors.length > 0 ? (
        <View style={styles.factors}>
          {factors.map((factor, i) => (
            <View key={i} style={styles.factorRow}>
              <View style={styles.factorDot} />
              <Text style={styles.factorText}>{factor}</Text>
            </View>
          ))}
        </View>
      ) : null}

      {/* Channel breakdown (historical / live / social) from the mock JSON. */}
      <View style={styles.channels}>
        <ChannelStat label="Geçmiş" value={historical} />
        <ChannelStat label="Canlı" value={live} />
        <ChannelStat label="Sosyal" value={social} />
      </View>
    </View>
  );
}

function ChannelStat({ label, value }: { label: string; value: number }) {
  return (
    <View style={styles.channel}>
      <Text style={styles.channelValue}>{value}</Text>
      <Text style={styles.channelLabel}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  section: {
    marginTop: 12,
    paddingTop: 12,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: "#e5e5e5",
  },
  loadingRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  loadingText: {
    fontSize: 13,
    color: "#888",
  },
  fallback: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  fallbackText: {
    fontSize: 13,
    color: "#888",
    flex: 1,
  },
  retryText: {
    fontSize: 13,
    fontWeight: "600",
    color: "#1D6FEB",
  },
  badge: {
    alignSelf: "flex-start",
    paddingVertical: 4,
    paddingHorizontal: 10,
    borderRadius: 12,
  },
  badgeText: {
    fontSize: 12,
    fontWeight: "700",
  },
  explanation: {
    marginTop: 8,
    fontSize: 14,
    lineHeight: 20,
    color: "#333",
  },
  factors: {
    marginTop: 10,
    gap: 6,
  },
  factorRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  factorDot: {
    width: 5,
    height: 5,
    borderRadius: 2.5,
    backgroundColor: "#999",
  },
  factorText: {
    fontSize: 13,
    color: "#555",
    flex: 1,
  },
  channels: {
    flexDirection: "row",
    marginTop: 12,
    gap: 8,
  },
  channel: {
    flex: 1,
    alignItems: "center",
    backgroundColor: "#f6f6f6",
    borderRadius: 8,
    paddingVertical: 6,
  },
  channelValue: {
    fontSize: 15,
    fontWeight: "600",
    color: "#333",
  },
  channelLabel: {
    fontSize: 11,
    color: "#888",
    marginTop: 1,
  },
});
