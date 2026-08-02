import { ActivityIndicator, Pressable, StyleSheet, Text, View } from "react-native";
import type { RiskLevel, RouteRiskExplanation, StreetRiskExplanation } from "@/lib/types";
import type { StreetRiskStatus } from "@/hooks/useStreetRisk";

interface Props {
  explanation: StreetRiskExplanation | RouteRiskExplanation | null;
  status: StreetRiskStatus;
  /** Retry a failed explanation fetch (fallback state). */
  onRetry: () => void;
}

/** Stitch Design System: 5 Risk Levels + No Data Badge Styles */
const LEVEL_STYLE: Record<
  RiskLevel,
  { label: string; bg: string; text: string }
> = {
  low: { label: "Düşük Risk", bg: "#006B54", text: "#FFFFFF" },        // Safety Mint
  low_medium: { label: "Düşük-Orta Risk", bg: "#7CA452", text: "#FFFFFF" },
  medium: { label: "Orta Risk", bg: "#DFC35B", text: "#4A3B00" },
  high: { label: "Yüksek Risk", bg: "#E58E52", text: "#FFFFFF" },
  very_high: { label: "Çok Yüksek Risk", bg: "#D95858", text: "#FFFFFF" }, // Emergency Red
  no_data: { label: "Gözlemlenen Veri Yok", bg: "#8A99AD", text: "#FFFFFF" },
};

/**
 * Stitch Design System Risk Explanation Card.
 * Renders 5-level risk badge / no-data state, Turkish rationale, risk factors,
 * crime/lighting/live channel breakdown, fail-soft retry button, and legal disclaimer.
 */
export function RiskExplanation({ explanation, status, onRetry }: Props) {
  if (status === "idle") return null;

  if (status === "loading") {
    return (
      <View style={styles.card}>
        <View style={styles.loadingRow}>
          <ActivityIndicator size="small" color="#3A5F81" />
          <Text style={styles.loadingText}>Risk açıklaması analizi yapılıyor…</Text>
        </View>
      </View>
    );
  }

  if (status === "error" || !explanation) {
    return (
      <View style={styles.card}>
        <View style={styles.fallbackContainer}>
          <Text style={styles.fallbackText}>
            Risk açıklaması şu anda alınamıyor.
          </Text>
          <Pressable
            onPress={onRetry}
            style={({ pressed }) => [
              styles.retryButton,
              pressed && styles.buttonPressed,
            ]}
            hitSlop={8}
          >
            <Text style={styles.retryButtonText}>Tekrar dene</Text>
          </Pressable>
        </View>
      </View>
    );
  }

  const isNoData = explanation.data_available === false || explanation.risk_level === "no_data";
  const levelKey = isNoData ? "no_data" : explanation.risk_level;
  const level = LEVEL_STYLE[levelKey] ?? LEVEL_STYLE.low;
  const isRouteWide = "route_risk" in explanation || "sampled_cell_count" in explanation;

  const factors = (explanation.factors || []).slice(0, 3);
  const channels = explanation.channels || { crime: 0, lighting: 0, live: 0, total: 0 };

  return (
    <View style={styles.card}>
      {/* Header Row: Title & Risk Level Badge */}
      <View style={styles.headerRow}>
        <Text style={styles.cardTitle}>
          {isRouteWide ? "Rota Risk Analizi" : "Sokak Risk Analizi"}
        </Text>
        <View style={[styles.badge, { backgroundColor: level.bg }]}>
          <Text style={[styles.badgeText, { color: level.text }]}>
            {level.label}
          </Text>
        </View>
      </View>

      {/* Main Rationale */}
      <Text style={styles.explanationText}>{explanation.explanation}</Text>

      {/* Risk Factors */}
      {factors.length > 0 ? (
        <View style={styles.factorsContainer}>
          {factors.map((factor, i) => (
            <View key={i} style={styles.factorRow}>
              <View style={[styles.factorDot, { backgroundColor: level.bg }]} />
              <Text style={styles.factorText}>{factor}</Text>
            </View>
          ))}
        </View>
      ) : null}

      {/* Channel Breakdown (crime / lighting / live) */}
      <View style={styles.channelsRow}>
        <ChannelStat label="Suç (%65)" value={channels.crime} />
        <ChannelStat label="Aydınlatma (%20)" value={channels.lighting} />
        <ChannelStat label="Canlı (%15)" value={channels.live} />
        <ChannelStat label="Toplam" value={channels.total} isTotal />
      </View>

      {/* Legal Disclaimer */}
      <Text style={styles.disclaimerText}>
        {explanation.disclaimer || "Güvenlik skoru kesin güvenlik garantisi değildir."}
      </Text>
    </View>
  );
}

function ChannelStat({ label, value, isTotal = false }: { label: string; value: number; isTotal?: boolean }) {
  return (
    <View style={[styles.channelItem, isTotal && styles.channelItemTotal]}>
      <Text style={[styles.channelValue, isTotal && styles.channelValueTotal]}>
        %{value.toFixed(1)}
      </Text>
      <Text style={styles.channelLabel}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    marginTop: 12,
    padding: 16,
    backgroundColor: "#F4F7F9", // Soft pastel surface
    borderRadius: 20,            // 20px radius card
    borderWidth: 1,
    borderColor: "#E2E8F0",
  },
  headerRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: 8,
  },
  cardTitle: {
    fontSize: 15,
    fontWeight: "700",
    color: "#3A5F81", // Stitch Primary Blue
  },
  badge: {
    paddingVertical: 4,
    paddingHorizontal: 10,
    borderRadius: 12,
  },
  badgeText: {
    fontSize: 12,
    fontWeight: "700",
  },
  explanationText: {
    fontSize: 14,
    lineHeight: 20,
    color: "#2D3748",
    marginBottom: 10,
  },
  factorsContainer: {
    marginBottom: 12,
    gap: 6,
  },
  factorRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  factorDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
  },
  factorText: {
    fontSize: 13,
    color: "#4A5568",
    flex: 1,
  },
  channelsRow: {
    flexDirection: "row",
    marginTop: 4,
    gap: 6,
  },
  channelItem: {
    flex: 1,
    alignItems: "center",
    backgroundColor: "#FFFFFF",
    borderRadius: 12,
    paddingVertical: 8,
    paddingHorizontal: 2,
    borderWidth: 1,
    borderColor: "#EDF2F7",
  },
  channelItemTotal: {
    backgroundColor: "#EBF8FF",
    borderColor: "#BEE3F8",
  },
  channelValue: {
    fontSize: 13,
    fontWeight: "700",
    color: "#3A5F81",
  },
  channelValueTotal: {
    color: "#2B6CB0",
  },
  channelLabel: {
    fontSize: 10,
    color: "#718096",
    marginTop: 2,
    textAlign: "center",
  },
  loadingRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    paddingVertical: 12,
  },
  loadingText: {
    fontSize: 13,
    color: "#3A5F81",
    fontWeight: "500",
  },
  fallbackContainer: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    minHeight: 48,
  },
  fallbackText: {
    fontSize: 13,
    color: "#718096",
    flex: 1,
  },
  retryButton: {
    minHeight: 48,
    minWidth: 48,
    justifyContent: "center",
    alignItems: "center",
    paddingHorizontal: 14,
    backgroundColor: "#3A5F81",
    borderRadius: 12,
  },
  buttonPressed: {
    opacity: 0.8,
  },
  retryButtonText: {
    fontSize: 13,
    fontWeight: "600",
    color: "#FFFFFF",
  },
  disclaimerText: {
    marginTop: 12,
    fontSize: 11,
    color: "#A0AEC0",
    fontStyle: "italic",
    textAlign: "center",
  },
});
