import React from "react";
import { Modal, Pressable, StyleSheet, Text, View } from "react-native";
import type { MapReport } from "@/lib/types";

interface ReportDetailModalProps {
  report: MapReport | null;
  onClose: () => void;
}

const CATEGORY_MAP: Record<string, { label: string; icon: string; color: string }> = {
  safety_concern: { label: "Güvenlik İkazı", icon: "◉", color: "#E5484D" },
  harassment: { label: "Taciz / Rahatsızlık", icon: "⚠", color: "#E5484D" },
  crime: { label: "Suç / şüpheli", icon: "⚠", color: "#E5484D" },
  lighting: { label: "Aydınlatma Arızası", icon: "☼", color: "#F5A623" },
  obstacle: { label: "Yol Engeli / Kapama", icon: "▣", color: "#F5A623" },
  traffic_signal: { label: "Sinyalizasyon Arızası", icon: "⊕", color: "#2E7D32" },
  suspicious: { label: "Şüpheli Durum", icon: "◎", color: "#8E44AD" },
  general: { label: "Genel İhbar", icon: "◉", color: "#208AEF" },
};

export function ReportDetailModal({
  report,
  onClose,
}: ReportDetailModalProps) {
  if (!report) return null;

  const catInfo = CATEGORY_MAP[report.category] || {
    label: report.category || "Genel İhbar",
    icon: "📌",
    color: "#208AEF",
  };

  const minutesText =
    report.minutes_ago === 0
      ? "Az önce bildirildi"
      : `${report.minutes_ago} dakika önce bildirildi`;

  return (
    <Modal
      transparent
      animationType="slide"
      visible={!!report}
      onRequestClose={onClose}
    >
      <Pressable style={styles.overlay} onPress={onClose}>
        <Pressable style={styles.content} onPress={(e) => e.stopPropagation()}>
          <View style={styles.handle} />

          {/* Header */}
          <View style={styles.header}>
            <View style={[styles.iconContainer, { backgroundColor: catInfo.color + "20" }]}>
              <Text style={styles.iconText}>{catInfo.icon}</Text>
            </View>
            <View style={styles.titleContainer}>
              <Text style={styles.categoryTitle}>{catInfo.label}</Text>
              <Text style={styles.timeText}>{minutesText}</Text>
            </View>
            <Pressable style={styles.closeButton} onPress={onClose}>
              <Text style={styles.closeButtonText}>✕</Text>
            </Pressable>
          </View>

          {/* Body Info */}
          <View style={styles.infoBox}>
            <Text style={styles.areaText}>
              📍 Yaklaşık Bölge: [{report.lat.toFixed(4)}, {report.lng.toFixed(4)}]
            </Text>
            <View style={styles.badgeContainer}>
              <Text style={styles.badgeText}>
                🛡️ Topluluk Tarafından Doğrulanmış İhbar
              </Text>
              <Text style={styles.badgeSubtext}>
                (Bağımsız bildirimler ve NLP analizi ile doğrulanmış canlı risk olayı)
              </Text>
            </View>
          </View>

          <Pressable style={styles.dismissButton} onPress={onClose}>
            <Text style={styles.dismissButtonText}>Kapat</Text>
          </Pressable>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: "rgba(0, 0, 0, 0.4)",
    justifyContent: "flex-end",
  },
  content: {
    backgroundColor: "#ffffff",
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    padding: 20,
    paddingBottom: 34,
  },
  handle: {
    width: 40,
    height: 4,
    backgroundColor: "#D0D0D0",
    borderRadius: 2,
    alignSelf: "center",
    marginBottom: 16,
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    marginBottom: 16,
  },
  iconContainer: {
    width: 44,
    height: 44,
    borderRadius: 22,
    justifyContent: "center",
    alignItems: "center",
    marginRight: 12,
  },
  iconText: {
    fontSize: 22,
  },
  titleContainer: {
    flex: 1,
  },
  categoryTitle: {
    fontSize: 18,
    fontWeight: "700",
    color: "#111827",
  },
  timeText: {
    fontSize: 13,
    color: "#6B7280",
    marginTop: 2,
  },
  closeButton: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: "#F3F4F6",
    justifyContent: "center",
    alignItems: "center",
  },
  closeButtonText: {
    fontSize: 16,
    color: "#4B5563",
    fontWeight: "600",
  },
  infoBox: {
    backgroundColor: "#F9FAFB",
    borderRadius: 12,
    padding: 14,
    marginBottom: 16,
    borderWidth: 1,
    borderColor: "#E5E7EB",
  },
  areaText: {
    fontSize: 13,
    fontWeight: "500",
    color: "#374151",
    marginBottom: 8,
  },
  badgeContainer: {
    backgroundColor: "#EFF6FF",
    borderRadius: 8,
    padding: 10,
    borderLeftWidth: 3,
    borderLeftColor: "#2563EB",
  },
  badgeText: {
    fontSize: 12,
    fontWeight: "600",
    color: "#1E40AF",
  },
  badgeSubtext: {
    fontSize: 11,
    color: "#3B82F6",
    marginTop: 2,
  },
  actionButton: {
    backgroundColor: "#1D6FEB",
    borderRadius: 12,
    paddingVertical: 14,
    alignItems: "center",
    marginBottom: 10,
  },
  actionButtonText: {
    color: "#ffffff",
    fontSize: 15,
    fontWeight: "600",
  },
  dismissButton: {
    backgroundColor: "#F3F4F6",
    borderRadius: 12,
    paddingVertical: 12,
    alignItems: "center",
  },
  dismissButtonText: {
    color: "#4B5563",
    fontSize: 14,
    fontWeight: "600",
  },
});
