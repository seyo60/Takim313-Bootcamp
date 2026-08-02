import { useState } from "react";
import { Modal, Pressable, StyleSheet, Text, View } from "react-native";
import { router } from "expo-router";
import { Wordmark } from "@/components/brand";
import { colors, radius, spacing, touchTarget } from "@/theme/tokens";

export function MapTopBar({ signedIn }: { signedIn: boolean }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const navigate = (href: "/" | "/auth" | "/profile" | "/my-reports") => {
    setMenuOpen(false);
    router.push(href);
  };
  return (
    <>
      <View style={styles.topBar}>
        <Pressable style={styles.roundButton} accessibilityLabel="Menü" onPress={() => setMenuOpen(true)}><Text style={styles.menu}>≡</Text></Pressable>
        <Wordmark compact />
        <Pressable style={[styles.roundButton, styles.profile]} accessibilityLabel={signedIn ? "Profil" : "Giriş"} onPress={() => router.push(signedIn ? "/profile" : "/auth")}><Text style={styles.profileText}>{signedIn ? "●" : "○"}</Text></Pressable>
      </View>
      <Modal transparent animationType="fade" visible={menuOpen} onRequestClose={() => setMenuOpen(false)}>
        <View style={styles.menuOverlay}>
          <Pressable style={StyleSheet.absoluteFill} accessibilityLabel="Menüyü kapat" onPress={() => setMenuOpen(false)} />
          <View style={styles.menuSheet}>
            <Wordmark />
            <Text style={styles.menuCaption}>Daha fazla bağlamla yürü.</Text>
            <Pressable style={styles.menuItem} onPress={() => navigate("/")}><Text style={styles.menuItemText}>Harita</Text></Pressable>
            <Pressable style={styles.menuItem} onPress={() => navigate(signedIn ? "/my-reports" : "/auth")}><Text style={styles.menuItemText}>{signedIn ? "İhbarlarım" : "Giriş yap"}</Text></Pressable>
            <Pressable style={styles.menuItem} onPress={() => navigate(signedIn ? "/profile" : "/auth")}><Text style={styles.menuItemText}>{signedIn ? "Profil ve hesap" : "Hesap oluştur"}</Text></Pressable>
            <Pressable style={styles.menuClose} onPress={() => setMenuOpen(false)}><Text style={styles.menuCloseText}>Kapat</Text></Pressable>
          </View>
        </View>
      </Modal>
    </>
  );
}

export function MapUnavailable({ reason, onRetry }: { reason: "token" | "load"; onRetry: () => void }) {
  return (
    <View style={styles.fallback}>
      <View style={[styles.gridLine, { top: "20%" }]} /><View style={[styles.gridLine, { top: "45%" }]} /><View style={[styles.gridLine, { top: "70%" }]} />
      <View style={[styles.gridLineVertical, { left: "22%" }]} /><View style={[styles.gridLineVertical, { left: "55%" }]} /><View style={[styles.gridLineVertical, { left: "82%" }]} />
      <View style={styles.fakeRoute} /><View style={styles.mapErrorCard}><View style={styles.mapErrorIcon}><Text style={styles.mapErrorIconText}>!</Text></View><Text style={styles.mapErrorTitle}>Harita şu anda yüklenemiyor</Text><Text style={styles.mapErrorBody}>{reason === "token" ? "Mapbox public token geçersiz veya eksik. İhbar ve hesap akışları çalışır; harita ile katman görüntüsü tam public token girildiğinde açılır." : "Harita stili alınamadı. İnternet bağlantısını kontrol edip yeniden dene."}</Text><Pressable style={styles.retry} onPress={onRetry}><Text style={styles.retryText}>Yeniden dene</Text></Pressable></View>
    </View>
  );
}

export function MapRoundButton({ label, icon, active, onPress }: { label: string; icon: string; active?: boolean; onPress: () => void }) {
  return <Pressable accessibilityRole="button" accessibilityLabel={label} onPress={onPress} style={[styles.mapRound, active && styles.mapRoundActive]}><Text style={[styles.mapRoundText, active && styles.mapRoundTextActive]}>{icon}</Text></Pressable>;
}

const styles = StyleSheet.create({
  topBar: { position: "absolute", top: 46, left: spacing.md, right: spacing.md, height: 54, borderRadius: radius.md, backgroundColor: "rgba(255,255,255,0.96)", flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: 4, shadowColor: "#000", shadowOpacity: 0.11, shadowRadius: 10, shadowOffset: { width: 0, height: 4 }, elevation: 5, zIndex: 20 },
  roundButton: { width: touchTarget, height: touchTarget, alignItems: "center", justifyContent: "center", borderRadius: touchTarget / 2 }, menu: { color: colors.primary, fontSize: 25, fontWeight: "700" }, profile: { backgroundColor: colors.primaryContainer }, profileText: { color: colors.primary, fontSize: 18 },
  menuOverlay: { flex: 1, backgroundColor: "rgba(18,28,38,0.34)", justifyContent: "flex-start" }, menuSheet: { width: "78%", maxWidth: 330, minHeight: "100%", backgroundColor: colors.background, paddingTop: 58, paddingHorizontal: spacing.lg, shadowColor: "#000", shadowOpacity: 0.2, shadowRadius: 20, elevation: 12 }, menuCaption: { color: colors.textMuted, fontSize: 13, marginTop: 8, marginBottom: spacing.lg }, menuItem: { minHeight: 54, justifyContent: "center", borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.borderSoft }, menuItemText: { color: colors.text, fontSize: 16, fontWeight: "800" }, menuClose: { minHeight: 48, marginTop: spacing.lg, borderRadius: radius.pill, backgroundColor: colors.surfaceContainer, alignItems: "center", justifyContent: "center" }, menuCloseText: { color: colors.primary, fontWeight: "800" },
  fallback: { position: "absolute", top: 0, right: 0, bottom: 0, left: 0, backgroundColor: "#EAF0F2", overflow: "hidden", alignItems: "center", justifyContent: "center" }, gridLine: { position: "absolute", left: 0, right: 0, height: 10, backgroundColor: "#DCE5E8", transform: [{ rotate: "-5deg" }] }, gridLineVertical: { position: "absolute", top: 0, bottom: 0, width: 10, backgroundColor: "#DCE5E8", transform: [{ rotate: "12deg" }] }, fakeRoute: { position: "absolute", width: 410, height: 8, borderRadius: 4, backgroundColor: "#AEC5D6", transform: [{ rotate: "-48deg" }] },
  mapErrorCard: { width: "82%", maxWidth: 360, backgroundColor: "rgba(255,255,255,0.97)", borderRadius: radius.lg, padding: spacing.lg, alignItems: "center", shadowColor: colors.primary, shadowOpacity: 0.13, shadowRadius: 20, elevation: 5 }, mapErrorIcon: { width: 46, height: 46, borderRadius: 23, alignItems: "center", justifyContent: "center", backgroundColor: colors.errorContainer }, mapErrorIconText: { color: colors.error, fontSize: 22, fontWeight: "900" }, mapErrorTitle: { color: colors.text, fontSize: 18, fontWeight: "900", marginTop: 12, textAlign: "center" }, mapErrorBody: { color: colors.textMuted, fontSize: 13, lineHeight: 19, textAlign: "center", marginTop: 7 }, retry: { minHeight: 46, marginTop: 15, paddingHorizontal: 22, borderRadius: radius.pill, backgroundColor: colors.primary, alignItems: "center", justifyContent: "center" }, retryText: { color: colors.surface, fontWeight: "800" },
  mapRound: { width: 48, height: 48, borderRadius: 24, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.borderSoft, shadowColor: "#000", shadowOpacity: 0.12, shadowRadius: 6, elevation: 4 }, mapRoundActive: { backgroundColor: colors.primaryContainer, borderColor: colors.primary }, mapRoundText: { color: colors.primary, fontSize: 20, fontWeight: "800" }, mapRoundTextActive: { color: colors.onPrimaryContainer },
});
