import { useState } from "react";
import { Modal, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import type { RouteKind, RouteOption } from "@/lib/mockRoute";
import type {
  RouteComparisonStats,
  RouteProfile,
  RouteRiskExplanation,
  StreetRiskExplanation,
} from "@/lib/types";
import type { StreetRiskStatus } from "@/hooks/useStreetRisk";
import { RiskExplanation } from "./RiskExplanation";
import { RouteProfileSelector } from "./RouteProfileSelector";
import { colors, radius, safetyDisclaimer, spacing } from "@/theme/tokens";

interface Props {
  /** The routes to choose between (safe, and shortest when available). */
  options: RouteOption[];
  /** Which route is currently selected (highlighted on the map). */
  selectedKind: RouteKind;
  /** Switch the selected route (item 1, AC #3). */
  onSelect: (kind: RouteKind) => void;
  routeProfile: RouteProfile;
  appliedProfile: RouteProfile;
  onSelectProfile: (profile: RouteProfile) => void;
  profileLoading: boolean;
  profileError: boolean;
  comparison?: RouteComparisonStats;
  /** Clears the destination + route (the ✕ button). */
  onClear: () => void;
  /** Item 2: LLM risk explanation for the selected route (rota geneli). */
  explanation: StreetRiskExplanation | RouteRiskExplanation | null;
  explanationStatus: StreetRiskStatus;
  onRetryExplanation: () => void;
  onStartNavigation: (option: RouteOption) => void;
  destinationName?: string;
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

function comparisonMessage(
  profile: RouteProfile,
  comparison?: RouteComparisonStats
): string {
  if (profile === "shortest") {
    return "Fiziksel olarak en kısa yürüyüş rotası gösteriliyor.";
  }

  if (!comparison) {
    return "Rota, seçtiğiniz mesafe bütçesi içinde daha düşük risk hedeflenerek hesaplandı.";
  }

  if (!comparison.meaningful_safer_alternative) {
    return "Bu mesafe bütçesinde anlamlı derecede daha güvenli bir alternatif bulunamadı; en kısa rota gösteriliyor.";
  }

  if (
    profile === "safer" &&
    comparison.distinct_from_balanced === false
  ) {
    return "Ek %40 mesafe bütçesinde dengeli rotadan daha iyi alternatif bulunamadı; dengeli rota kullanılıyor.";
  }

  return `En kısa yola göre %${comparison.risk_reduction_pct.toFixed(
    1
  )} daha güvenli; ${formatDistance(
    comparison.extra_distance_m
  )} (%${comparison.extra_distance_pct.toFixed(1)}) daha uzun.`;
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
  onSelect: _onSelect,
  routeProfile,
  appliedProfile,
  onSelectProfile,
  profileLoading,
  profileError,
  comparison,
  onClear,
  explanation,
  explanationStatus,
  onRetryExplanation,
  onStartNavigation,
  destinationName = "Seçilen hedef",
}: Props) {
  const [detailsVisible, setDetailsVisible] = useState(false);
  const selected =
    options.find((option) => option.kind === selectedKind) ?? options[0];
  if (!selected) return null;

  const risk = riskInfo(selected.risk_score);
  const saferVsShortestPct =
    appliedProfile !== "shortest" &&
    comparison?.meaningful_safer_alternative &&
    typeof comparison.risk_reduction_pct === "number"
      ? comparison.risk_reduction_pct
      : null;

  return (
    <View style={styles.card}>
      <View style={styles.handle} />
      <View style={styles.destinationHeader}>
        <View><Text style={styles.destinationCap}>SEÇİLEN ROTA</Text><Text style={styles.destination}>{destinationName}</Text></View>
        <Pressable style={styles.close} onPress={onClear} hitSlop={8}><Text style={styles.closeText}>×</Text></Pressable>
      </View>
      <RouteProfileSelector
        value={routeProfile}
        onChange={onSelectProfile}
        disabled={profileLoading}
      />

      <View
        style={[
          styles.decisionBox,
          !comparison?.meaningful_safer_alternative &&
            routeProfile !== "shortest" &&
            styles.decisionBoxNeutral,
        ]}
      >
        <Text style={styles.decisionText}>
          {profileLoading
            ? "Yeni rota profili hesaplanıyor…"
            : profileError
              ? "Yeni profil alınamadı. Bağlantıyı kontrol edip yeniden dene."
              : comparisonMessage(appliedProfile, comparison)}
        </Text>
      </View>

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
              {Math.round(selected.risk_score)}
            </Text>
            <Text style={[styles.statLabel, { color: risk.color }]}>
              {risk.label}
            </Text>
          </View>

          {saferVsShortestPct != null ? (
            <>
              <View style={styles.divider} />
              <View style={styles.stat}>
                <Text style={[styles.statValue, { color: "#2E9E44" }]}>
                  %{saferVsShortestPct.toFixed(0)}
                </Text>
                <Text style={[styles.statLabel, { color: "#2E9E44" }]}>
                  daha güvenli
                </Text>
              </View>
            </>
          ) : null}
        </View>

      </View>

      {/* Yasal / Güvenlik Uyarısı Banner */}
      <View style={styles.disclaimerBox}>
        <Text style={styles.disclaimerText}>
          ⚠️ Güvenlik skoru kesin güvenlik garantisi değildir
        </Text>
      </View>

      <Pressable
        accessibilityRole="button"
        style={styles.startButton}
        onPress={() => onStartNavigation(selected)}
      >
        <Text style={styles.startButtonText}>Yürüyüş navigasyonunu başlat</Text>
      </Pressable>
      <Pressable accessibilityRole="button" style={styles.detailsButton} onPress={() => setDetailsVisible(true)}><Text style={styles.detailsButtonText}>Rota detayları</Text></Pressable>
      <Modal visible={detailsVisible} animationType="slide" onRequestClose={() => setDetailsVisible(false)}>
        <View style={styles.detailsRoot}>
          <View style={styles.detailsHeader}><Pressable style={styles.close} onPress={() => setDetailsVisible(false)}><Text style={styles.closeText}>‹</Text></Pressable><Text style={styles.detailsHeaderTitle}>Rota detayları</Text><View style={styles.close} /></View>
          <ScrollView contentContainerStyle={styles.detailsScroll}>
            <View style={styles.detailToggle}><Text style={styles.detailToggleActive}>Daha güvenli rota</Text><Text style={styles.detailToggleIdle}>En kısa rota</Text></View>
            <View style={styles.scoreCard}><Text style={styles.scoreCap}>GENEL GÜVENLİK SKORU</Text><Text style={styles.score}>{Math.max(0, Math.round(100 - selected.risk_score))}<Text style={styles.scoreOut}> /100</Text></Text><View style={styles.detailStats}><View><Text style={styles.detailStatValue}>{formatDuration(selected.duration_s)}</Text><Text style={styles.detailStatLabel}>Süre</Text></View><View><Text style={styles.detailStatValue}>{formatDistance(selected.distance_m)}</Text><Text style={styles.detailStatLabel}>Mesafe</Text></View><View><Text style={styles.detailStatValue}>{risk.label}</Text><Text style={styles.detailStatLabel}>Ortam</Text></View></View></View>
            <Text style={styles.breakdownTitle}>Risk dökümü</Text>
            <View style={styles.breakdownCard}><View style={styles.breakdownIcon}><Text>◉</Text></View><View style={styles.breakdownCopy}><Text style={styles.breakdownName}>Gözlemlenen rota riski</Text><Text style={[styles.breakdownValue, { color: risk.color }]}>{risk.label}</Text><Text style={styles.breakdownText}>Skor; suç, aydınlatma ve kabul edilmiş güncel ihbar sinyallerinin rota uzunluğuna göre birleşimidir.</Text></View></View>
            <RiskExplanation explanation={explanation} status={explanationStatus} onRetry={onRetryExplanation} />
            <View style={styles.safetyCard}><Text style={styles.safetyText}>{safetyDisclaimer} Veriler eksik, gecikmeli veya doğrulanmamış olabilir; çevrene dikkat et.</Text></View>
            <Pressable style={styles.startButton} onPress={() => { setDetailsVisible(false); onStartNavigation(selected); }}><Text style={styles.startButtonText}>Daha güvenli rotayı başlat</Text></Pressable>
          </ScrollView>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    position: "absolute",
    bottom: 0,
    left: 0,
    right: 0,
    backgroundColor: "#fff",
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    paddingVertical: 14,
    paddingHorizontal: 16,
    shadowColor: "#000",
    shadowOpacity: 0.15,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 2 },
    elevation: 4,
  },
  handle: { width: 40, height: 4, borderRadius: 2, backgroundColor: colors.surfaceContainerHighest, alignSelf: "center", marginBottom: 10 },
  destinationHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: 8 },
  destinationCap: { color: colors.secondary, fontSize: 9, fontWeight: "900", letterSpacing: 1 },
  destination: { color: colors.text, fontSize: 18, fontWeight: "900", marginTop: 2 },
  decisionBox: {
    marginBottom: 10,
    paddingVertical: 7,
    paddingHorizontal: 9,
    borderWidth: 1,
    borderColor: "#B8D1F5",
    borderRadius: 8,
    backgroundColor: "#EEF5FF",
  },
  decisionBoxNeutral: {
    borderColor: "#D5DAE1",
    backgroundColor: "#F7F8FA",
  },
  decisionText: {
    color: "#344054",
    fontSize: 11,
    lineHeight: 15,
    fontWeight: "500",
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
  disclaimerBox: {
    marginTop: 10,
    backgroundColor: "#FFFBEB",
    borderWidth: 1,
    borderColor: "#FCD34D",
    borderRadius: 8,
    paddingVertical: 6,
    paddingHorizontal: 10,
    alignItems: "center",
  },
  disclaimerText: {
    fontSize: 11,
    fontWeight: "500",
    color: "#B45309",
    textAlign: "center",
  },
  startButton: {
    minHeight: 48,
    marginTop: 10,
    borderRadius: 12,
    backgroundColor: "#3A5F81",
    alignItems: "center",
    justifyContent: "center",
  },
  startButtonText: {
    color: "#fff",
    fontSize: 16,
    fontWeight: "700",
  },
  detailsButton: { minHeight: 48, marginTop: 8, borderRadius: radius.pill, borderWidth: 1.5, borderColor: colors.primary, alignItems: "center", justifyContent: "center" },
  detailsButtonText: { color: colors.primary, fontWeight: "800" },
  detailsRoot: { flex: 1, backgroundColor: colors.background },
  detailsHeader: { minHeight: 58, flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.sm, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.borderSoft },
  detailsHeaderTitle: { color: colors.primary, fontSize: 18, fontWeight: "900" },
  detailsScroll: { padding: spacing.md, gap: 12, paddingBottom: spacing.xl },
  detailToggle: { flexDirection: "row", padding: 4, backgroundColor: colors.surfaceContainer, borderRadius: radius.pill },
  detailToggleActive: { flex: 1, backgroundColor: colors.primary, color: "white", borderRadius: radius.pill, paddingVertical: 9, textAlign: "center", fontWeight: "800" },
  detailToggleIdle: { flex: 1, color: colors.textMuted, paddingVertical: 9, textAlign: "center", fontWeight: "700" },
  scoreCard: { backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.md, alignItems: "center", borderWidth: 1, borderColor: colors.borderSoft },
  scoreCap: { color: colors.textMuted, fontSize: 10, letterSpacing: 1, fontWeight: "900" },
  score: { color: colors.primary, fontSize: 40, fontWeight: "900", marginTop: 4 }, scoreOut: { fontSize: 15, color: colors.textMuted },
  detailStats: { width: "100%", flexDirection: "row", justifyContent: "space-around", marginTop: 14 }, detailStatValue: { color: colors.text, fontWeight: "900", textAlign: "center" }, detailStatLabel: { color: colors.textMuted, fontSize: 11, textAlign: "center", marginTop: 2 },
  breakdownTitle: { color: colors.text, fontSize: 18, fontWeight: "900", marginTop: 4 }, breakdownCard: { flexDirection: "row", backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.md, borderWidth: 1, borderColor: colors.borderSoft }, breakdownIcon: { width: 42, height: 42, borderRadius: 21, backgroundColor: colors.primaryContainer, alignItems: "center", justifyContent: "center" }, breakdownCopy: { flex: 1, marginLeft: 12 }, breakdownName: { color: colors.text, fontWeight: "900" }, breakdownValue: { fontSize: 12, fontWeight: "900", marginTop: 2 }, breakdownText: { color: colors.textMuted, fontSize: 12, lineHeight: 17, marginTop: 6 },
  safetyCard: { backgroundColor: colors.surfaceContainer, borderRadius: radius.sm, padding: spacing.md }, safetyText: { color: colors.textMuted, fontSize: 11, lineHeight: 16 },
});
