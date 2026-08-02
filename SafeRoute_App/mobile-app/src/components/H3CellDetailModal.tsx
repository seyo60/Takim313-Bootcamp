import React from "react";
import { Modal, Pressable, StyleSheet, Text, View } from "react-native";
import type { HeatmapGeoJSONProperties, LngLat } from "@/lib/types";

export interface H3CellDetailModalProps {
  cellProperties: HeatmapGeoJSONProperties | null;
  onClose: () => void;
  onPlanRouteToHere?: (coord: LngLat) => void;
}

export function H3CellDetailModal({
  cellProperties,
  onClose,
  onPlanRouteToHere,
}: H3CellDetailModalProps) {
  if (!cellProperties) return null;

  const {
    h3_index,
    lat,
    lng,
    risk_crime,
    risk_lighting,
    risk_live,
    total_risk,
    data_available,
  } = cellProperties;

  const riskPercent = Math.round((total_risk || 0) * 100);
  const crimePercent = Math.round((risk_crime || 0) * 100);
  const lightingPercent = Math.round((risk_lighting || 0) * 100);
  const livePercent = Math.round((risk_live || 0) * 100);

  const coord: LngLat = [lng, lat];

  const getRiskLabel = (val: number) => {
    if (val < 0.2) return { text: "Düşük Gözlemlenen Risk", color: "#5AA978" };
    if (val < 0.4) return { text: "Düşük-Orta Risk", color: "#A9BE65" };
    if (val < 0.6) return { text: "Orta Risk", color: "#DFC35B" };
    if (val < 0.8) return { text: "Yüksek Gözlemlenen Risk", color: "#E58E52" };
    return { text: "Çok Yüksek Risk", color: "#D95858" };
  };

  const riskMeta = getRiskLabel(total_risk || 0);

  return (
    <Modal
      transparent
      animationType="slide"
      visible={!!cellProperties}
      onRequestClose={onClose}
    >
      <Pressable style={styles.overlay} onPress={onClose}>
        <Pressable style={styles.card} onPress={(e) => e.stopPropagation()}>
          <View style={styles.header}>
            <View>
              <Text style={styles.title}>H3 Bölgesel Risk İncelemesi</Text>
              <Text style={styles.subtitle}>Index: {h3_index.substring(0, 12)}…</Text>
            </View>
            <Pressable onPress={onClose} style={styles.closeBtn}>
              <Text style={styles.closeBtnText}>✕</Text>
            </Pressable>
          </View>

          {/* Data available status */}
          {!data_available ? (
            <View style={styles.noDataBadge}>
              <Text style={styles.noDataTitle}>⚠️ Yetersiz Veri / No Data</Text>
              <Text style={styles.noDataDesc}>
                Veri bulunmayan alanlar güvenli anlamına gelmez (&quot;Missing data does not mean this area is safe&quot;).
              </Text>
            </View>
          ) : (
            <>
              {/* Risk Badge */}
              <View style={[styles.badge, { backgroundColor: riskMeta.color }]}>
                <Text style={styles.badgeText}>{riskMeta.text}</Text>
                <Text style={styles.badgeScore}>
                  {total_risk.toFixed(2)} (Skor: {riskPercent}/100)
                </Text>
              </View>

              {/* Channels Breakdown */}
              <View style={styles.section}>
                <Text style={styles.sectionTitle}>Bileşen Risk Kanalı Dökümü</Text>

                <View style={styles.channelRow}>
                  <Text style={styles.channelLabel}>🚔 Suç İstatistiği (Crime):</Text>
                  <Text style={styles.channelVal}>
                    {risk_crime.toFixed(2)} ({crimePercent}/100)
                  </Text>
                </View>
                <View style={styles.progressBg}>
                  <View style={[styles.progressFill, { width: `${crimePercent}%`, backgroundColor: "#E58E52" }]} />
                </View>

                <View style={styles.channelRow}>
                  <Text style={styles.channelLabel}>💡 Sokak Aydınlatması (Lighting):</Text>
                  <Text style={styles.channelVal}>
                    {risk_lighting.toFixed(2)} ({lightingPercent}/100)
                  </Text>
                </View>
                <View style={styles.progressBg}>
                  <View style={[styles.progressFill, { width: `${lightingPercent}%`, backgroundColor: "#F5A623" }]} />
                </View>

                <View style={styles.channelRow}>
                  <Text style={styles.channelLabel}>⚡ Canlı İhbar Riski (Live):</Text>
                  <Text style={styles.channelVal}>
                    {risk_live.toFixed(2)} ({livePercent}/100)
                  </Text>
                </View>
                <View style={styles.progressBg}>
                  <View style={[styles.progressFill, { width: `${livePercent}%`, backgroundColor: "#E5484D" }]} />
                </View>
              </View>
            </>
          )}

          {/* Action buttons — yalnızca varış; kullanıcı o konumda olmadığı için başlangıç seçeneği yok */}
          <View style={styles.actionsRow}>
            {onPlanRouteToHere && (
              <Pressable
                style={[styles.actionBtn, styles.primaryBtn]}
                onPress={() => {
                  onPlanRouteToHere(coord);
                  onClose();
                }}
              >
                <Text style={styles.primaryBtnText}>🎯 Buraya Rota Planla</Text>
              </Pressable>
            )}
          </View>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.4)",
    justifyContent: "flex-end",
  },
  card: {
    backgroundColor: "#ffffff",
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    padding: 20,
    shadowColor: "#000",
    shadowOpacity: 0.2,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: -3 },
    elevation: 8,
  },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "flex-start",
    marginBottom: 14,
  },
  title: {
    fontSize: 18,
    fontWeight: "700",
    color: "#111827",
  },
  subtitle: {
    fontSize: 12,
    color: "#6B7280",
    marginTop: 2,
  },
  closeBtn: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: "#F3F4F6",
    alignItems: "center",
    justifyContent: "center",
  },
  closeBtnText: {
    fontSize: 16,
    color: "#4B5563",
    fontWeight: "600",
  },
  noDataBadge: {
    backgroundColor: "#F3F4F6",
    borderRadius: 10,
    padding: 12,
    borderLeftWidth: 4,
    borderLeftColor: "#AAB1BA",
    marginBottom: 16,
  },
  noDataTitle: {
    fontSize: 14,
    fontWeight: "700",
    color: "#374151",
  },
  noDataDesc: {
    fontSize: 12,
    color: "#6B7280",
    marginTop: 4,
  },
  badge: {
    borderRadius: 10,
    padding: 12,
    marginBottom: 16,
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  badgeText: {
    color: "#ffffff",
    fontWeight: "700",
    fontSize: 14,
  },
  badgeScore: {
    color: "#ffffff",
    fontSize: 13,
    fontWeight: "600",
  },
  section: {
    backgroundColor: "#F9FAFB",
    borderRadius: 10,
    padding: 12,
    marginBottom: 16,
  },
  sectionTitle: {
    fontSize: 13,
    fontWeight: "700",
    color: "#374151",
    marginBottom: 8,
  },
  channelRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    marginTop: 6,
  },
  channelLabel: {
    fontSize: 12,
    color: "#4B5563",
  },
  channelVal: {
    fontSize: 12,
    fontWeight: "600",
    color: "#111827",
  },
  progressBg: {
    height: 6,
    backgroundColor: "#E5E7EB",
    borderRadius: 3,
    marginTop: 4,
    overflow: "hidden",
  },
  progressFill: {
    height: "100%",
    borderRadius: 3,
  },
  actionsRow: {
    gap: 10,
  },
  actionBtn: {
    paddingVertical: 12,
    borderRadius: 10,
    alignItems: "center",
  },
  primaryBtn: {
    backgroundColor: "#1D6FEB",
  },
  primaryBtnText: {
    color: "#ffffff",
    fontWeight: "700",
    fontSize: 14,
  },
  secondaryBtn: {
    backgroundColor: "#F3F4F6",
  },
  secondaryBtnText: {
    color: "#111827",
    fontWeight: "600",
    fontSize: 14,
  },
});
