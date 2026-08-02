import type { PropsWithChildren, ReactNode } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { router } from "expo-router";
import { colors, radius, spacing, touchTarget } from "@/theme/tokens";

export function ShieldMark({ size = 52 }: { size?: number }) {
  const iconSize = Math.round(size * 0.48);
  return (
    <View
      accessibilityLabel="SafeRoute kalkan simgesi"
      style={[styles.shieldWrap, { width: size, height: size, borderRadius: size * 0.3 }]}
    >
      <View style={[styles.shield, { width: iconSize, height: iconSize, borderRadius: iconSize * 0.24 }]}>
        <Text style={[styles.shieldPerson, { fontSize: Math.max(11, iconSize * 0.55) }]}>●</Text>
      </View>
      <View style={styles.routeDot} />
    </View>
  );
}

export function Wordmark({ compact = false }: { compact?: boolean }) {
  return (
    <View style={styles.wordmark}>
      <ShieldMark size={compact ? 30 : 36} />
      <Text style={[styles.wordmarkText, compact && styles.wordmarkCompact]}>SafeRoute</Text>
    </View>
  );
}

export function PageHeader({ title, back = true, action }: { title?: string; back?: boolean; action?: ReactNode }) {
  return (
    <View style={styles.header}>
      {back ? (
        <Pressable accessibilityRole="button" accessibilityLabel="Geri" onPress={() => router.back()} style={styles.headerButton}>
          <Text style={styles.headerIcon}>‹</Text>
        </Pressable>
      ) : <View style={styles.headerButton} />}
      {title ? <Text style={styles.headerTitle}>{title}</Text> : <Wordmark compact />}
      <View style={styles.headerButton}>{action}</View>
    </View>
  );
}

export function BottomNav({ active = "map" }: { active?: "map" | "reports" | "profile" }) {
  const items = [
    { id: "map" as const, icon: "▥", label: "Harita", href: "/" as const },
    { id: "reports" as const, icon: "▤", label: "İhbarlarım", href: "/my-reports" as const },
    { id: "profile" as const, icon: "○", label: "Profil", href: "/profile" as const },
  ];
  return (
    <View style={styles.bottomNav}>
      {items.map((item) => {
        const selected = item.id === active;
        return (
          <Pressable key={item.id} accessibilityRole="tab" accessibilityState={{ selected }} onPress={() => router.push(item.href)} style={styles.navItem}>
            <View style={[styles.navIconPill, selected && styles.navIconPillSelected]}><Text style={[styles.navIcon, selected && styles.navIconSelected]}>{item.icon}</Text></View>
            <Text style={[styles.navLabel, selected && styles.navLabelSelected]}>{item.label}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

export function TonalCard({ children }: PropsWithChildren) {
  return <View style={styles.tonalCard}>{children}</View>;
}

const styles = StyleSheet.create({
  shieldWrap: { backgroundColor: colors.surface, alignItems: "center", justifyContent: "center", shadowColor: colors.primary, shadowOpacity: 0.12, shadowRadius: 16, shadowOffset: { width: 0, height: 8 }, elevation: 4 },
  shield: { borderWidth: 2, borderColor: colors.primary, alignItems: "center", justifyContent: "center", transform: [{ rotate: "45deg" }] },
  shieldPerson: { color: colors.primary, transform: [{ rotate: "-45deg" }] },
  routeDot: { position: "absolute", right: 7, bottom: 6, width: 7, height: 7, borderRadius: 4, backgroundColor: colors.secondary },
  wordmark: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  wordmarkText: { color: colors.primary, fontSize: 24, fontWeight: "900", letterSpacing: -0.8 },
  wordmarkCompact: { fontSize: 20 },
  header: { minHeight: 56, flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.sm, backgroundColor: colors.background },
  headerButton: { width: touchTarget, minHeight: touchTarget, alignItems: "center", justifyContent: "center" },
  headerIcon: { color: colors.text, fontSize: 34, fontWeight: "300", marginTop: -3 },
  headerTitle: { color: colors.primary, fontSize: 19, fontWeight: "900" },
  bottomNav: { position: "absolute", left: 0, right: 0, bottom: 0, height: 78, flexDirection: "row", backgroundColor: colors.surface, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.borderSoft, paddingTop: 7 },
  navItem: { flex: 1, alignItems: "center", minHeight: touchTarget },
  navIconPill: { minWidth: 54, height: 30, borderRadius: radius.pill, alignItems: "center", justifyContent: "center" },
  navIconPillSelected: { backgroundColor: colors.primaryContainer },
  navIcon: { color: colors.textMuted, fontSize: 21, fontWeight: "700" },
  navIconSelected: { color: colors.primary },
  navLabel: { color: colors.textMuted, fontSize: 11, fontWeight: "700", marginTop: 2 },
  navLabelSelected: { color: colors.primary },
  tonalCard: { backgroundColor: colors.surfaceContainer, borderRadius: radius.md, padding: spacing.md },
});
