import React, { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import type { HeatmapGeoJSONMetadata } from "@/lib/types";

export interface HeatmapLegendProps {
  metadata: HeatmapGeoJSONMetadata | null;
  visible: boolean;
}

export function HeatmapLegend({ metadata, visible }: HeatmapLegendProps) {
  const [collapsed, setCollapsed] = useState(false);

  if (!visible) return null;

  const coveragePct = metadata?.data_coverage_pct ?? 0.0;
  const channelName = metadata?.channel ? metadata.channel.toUpperCase() : "TOTAL";
  const h3Resolution = metadata?.h3_resolution ?? 9;

  return (
    <View style={styles.container}>
      <View style={styles.headerRow}>
        <Text style={styles.title}>🗺️ Risk Skalası ({channelName})</Text>
        <Pressable onPress={() => setCollapsed((c) => !c)} hitSlop={8}>
          <Text style={styles.collapseBtn}>{collapsed ? "▲" : "▼"}</Text>
        </Pressable>
      </View>

      {!collapsed && (
        <>
          {/* Risk scale color bar */}
          <View style={styles.colorBarContainer}>
            <View style={[styles.colorChip, { backgroundColor: "#AAB1BA" }]} />
            <View style={[styles.colorChip, { backgroundColor: "#5AA978" }]} />
            <View style={[styles.colorChip, { backgroundColor: "#A9BE65" }]} />
            <View style={[styles.colorChip, { backgroundColor: "#DFC35B" }]} />
            <View style={[styles.colorChip, { backgroundColor: "#E58E52" }]} />
            <View style={[styles.colorChip, { backgroundColor: "#D95858" }]} />
          </View>

          <View style={styles.labelsRow}>
            <Text style={styles.label}>Veri Yok</Text>
            <Text style={styles.label}>Düşük</Text>
            <Text style={styles.label}>Orta</Text>
            <Text style={styles.label}>Yüksek</Text>
          </View>

          <View style={styles.metaRow}>
            <Text style={styles.metaText}>Kapsama: %{coveragePct.toFixed(1)}</Text>
            <Text style={styles.metaText}>Çözünürlük: H3 Res-{h3Resolution}</Text>
          </View>

          <Text style={styles.disclaimerText}>
            Risk tahminleri güvenlik garantisi vermez.
          </Text>
        </>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    position: "absolute",
    bottom: 180,
    left: 16,
    backgroundColor: "rgba(255, 255, 255, 0.94)",
    borderRadius: 12,
    padding: 10,
    width: 210,
    shadowColor: "#000",
    shadowOpacity: 0.15,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 2 },
    elevation: 5,
    zIndex: 20,
  },
  headerRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  title: {
    fontSize: 12,
    fontWeight: "700",
    color: "#111827",
  },
  collapseBtn: {
    fontSize: 11,
    color: "#6B7280",
    paddingHorizontal: 4,
  },
  colorBarContainer: {
    flexDirection: "row",
    height: 8,
    borderRadius: 4,
    overflow: "hidden",
    marginTop: 8,
  },
  colorChip: {
    flex: 1,
    height: "100%",
  },
  labelsRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    marginTop: 4,
  },
  label: {
    fontSize: 9,
    color: "#4B5563",
    fontWeight: "500",
  },
  metaRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    marginTop: 6,
    borderTopWidth: 1,
    borderTopColor: "#E5E7EB",
    paddingTop: 4,
  },
  metaText: {
    fontSize: 10,
    color: "#6B7280",
  },
  disclaimerText: {
    fontSize: 9,
    color: "#9CA3AF",
    fontStyle: "italic",
    marginTop: 4,
    textAlign: "center",
  },
});
