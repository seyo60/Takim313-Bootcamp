import { useState, type ReactNode } from "react";
import { Pressable, SafeAreaView, ScrollView, StyleSheet, Text, View } from "react-native";
import * as Location from "expo-location";
import { router } from "expo-router";
import { appStorage } from "@/lib/secureStorage";
import { Button } from "@/components/ui";
import { ShieldMark, Wordmark } from "@/components/brand";
import { colors, radius, spacing } from "@/theme/tokens";

type Page = "welcome" | "community" | "comparison" | "navigation" | "permissions";
const pages: Page[] = ["welcome", "community", "comparison", "navigation", "permissions"];

function Progress({ index }: { index: number }) {
  return <View style={styles.progress}>{pages.map((page, i) => <View key={page} style={[styles.progressDot, i === index && styles.progressDotActive]} />)}</View>;
}

function CommunityIllustration() {
  return (
    <View style={styles.illustration}>
      <View style={styles.phone}><View style={styles.phoneMap}><View style={styles.mapRoad} /><View style={styles.mapRoadTwo} /><View style={styles.alertPin}><Text style={styles.alertPinText}>!</Text></View></View></View>
      <View style={[styles.floatChip, styles.liveChip]}><View style={styles.liveDot} /><Text style={styles.floatText}>Canlı veri</Text></View>
      <View style={[styles.floatChip, styles.reportChip]}><Text style={styles.reportIcon}>!</Text><Text style={styles.floatText}>Engel bildirildi</Text></View>
    </View>
  );
}

function ComparisonIllustration() {
  return (
    <View style={styles.illustration}>
      <View style={styles.grid}><View style={styles.routeMuted} /><View style={styles.routeSafe} /></View>
      <View style={[styles.routeLabel, styles.routeLabelSafe]}><Text style={styles.routeLabelCap}>DAHA GÜVENLİ</Text><Text style={styles.routeLabelTitle}>İyi aydınlatılmış</Text><Text style={styles.routeLabelSmall}>+3 dk</Text></View>
      <View style={[styles.routeLabel, styles.routeLabelShort]}><Text style={styles.routeLabelCap}>EN KISA</Text><Text style={styles.routeLabelTitle}>Loş bölgeler</Text></View>
    </View>
  );
}

function NavigationIllustration() {
  const features = [
    ["↱", "Adım adım yönlendirme", "Her dönüş için açık ve okunabilir talimatlar."],
    ["◖", "Sesli asistan", "Gözün yoldayken Türkçe ve İngilizce yönlendirme."],
    ["⑂", "Akıllı yeniden rota", "Koşullar değiştiğinde rotanın otomatik yenilenmesi."],
  ];
  return <View style={styles.featureList}>{features.map(([icon, title, body]) => <View key={title} style={styles.featureCard}><View style={styles.featureIcon}><Text style={styles.featureIconText}>{icon}</Text></View><View style={styles.featureCopy}><Text style={styles.featureTitle}>{title}</Text><Text style={styles.featureBody}>{body}</Text></View></View>)}</View>;
}

function PermissionIllustration() {
  return <View style={styles.permissionHero}><ShieldMark size={78} /><Text style={styles.permissionHeroTitle}>Güvenli bir yolculuk</Text></View>;
}

function getContent(): Record<Page, { title: string; body: string; illustration: ReactNode }> { return {
  welcome: { title: "Rotanı daha fazla bağlamla seç", body: "Chicago topluluk verilerine dayanan en kısa ve risk farkındalıklı rota seçeneklerini karşılaştır.", illustration: <View style={styles.welcomeSpace}><Wordmark /></View> },
  community: { title: "Yakın zamandaki yerel bağlamı gör", body: "Son saat içindeki topluluk ihbarlarını ve bölgesel risk verilerini görerek daha bilinçli ilerle.", illustration: <CommunityIllustration /> },
  comparison: { title: "Seçeneklerini karşılaştır", body: "En hızlı yolu hesaplarız; aydınlatma, suç ve güncel topluluk sinyallerine göre daha düşük riskli alternatifi de gösteririz. Seçim her zaman senin.", illustration: <ComparisonIllustration /> },
  navigation: { title: "Canlı yönlendirmeyi takip et", body: "Güvenlik tercihlerine uyarlanan gerçek zamanlı yönlendirmeyle rotada kal.", illustration: <NavigationIllustration /> },
  permissions: { title: "Gerekli izinler sende", body: "SafeRoute, rota hesaplamak ve haritada konumunu göstermek için yalnızca uygulamayı kullanırken konum izni ister.", illustration: <PermissionIllustration /> },
}; }

export default function Onboarding() {
  const [index, setIndex] = useState(0);
  const page = pages[index];
  const content = getContent();
  const finish = async (destination: "/" | "/auth") => {
    await appStorage.set("saferoute.onboarding.v1", "complete");
    router.replace(destination);
  };
  const requestAndFinish = async () => {
    await Location.requestForegroundPermissionsAsync();
    await finish("/");
  };

  if (page === "welcome") {
    return (
      <SafeAreaView style={styles.safe}>
        <View style={styles.welcome}>
          {content.welcome.illustration}
          <View style={styles.welcomeCopy}><Text style={styles.title}>{content.welcome.title}</Text><Text style={styles.body}>{content.welcome.body}</Text></View>
          <View style={styles.actions}>
            <Button onPress={() => setIndex(1)}>Başla</Button>
            <Button variant="ghost" onPress={() => finish("/auth")}>Giriş yap</Button>
            <Pressable style={styles.textButton} onPress={() => finish("/")}><Text style={styles.textButtonLabel}>Hesap açmadan devam et</Text></Pressable>
          </View>
          <Text style={styles.privacy}>Gizlilik politikası</Text>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safe}>
      <ScrollView contentContainerStyle={styles.screen}>
        <View style={styles.topRow}>
          <Pressable accessibilityLabel="Geri" onPress={() => setIndex((value) => Math.max(0, value - 1))} style={styles.topButton}><Text style={styles.back}>‹</Text></Pressable>
          <Progress index={index} />
          {page !== "permissions" ? <Pressable onPress={() => setIndex(4)} style={styles.topButton}><Text style={styles.skip}>Atla</Text></Pressable> : <View style={styles.topButton} />}
        </View>
        {content[page].illustration}
        <View style={styles.copy}><Text style={styles.title}>{content[page].title}</Text><Text style={styles.body}>{content[page].body}</Text></View>
        {page === "community" ? <View style={styles.info}><Text style={styles.infoIcon}>i</Text><Text style={styles.infoText}>Topluluk ihbarları değerli bir bağlam sağlar ancak doğrulanmamış olabilir. Her zaman kişisel güvenliğini önceliklendir.</Text></View> : null}
        {page === "permissions" ? <View style={styles.permissionList}><View style={styles.permissionRow}><View style={styles.permissionIcon}><Text>⌖</Text></View><View style={styles.featureCopy}><Text style={styles.featureTitle}>Konum erişimi</Text><Text style={styles.featureBody}>Güvenli rotaları hesaplamak ve haritadaki konumunu göstermek için.</Text></View></View><View style={styles.info}><Text style={styles.infoIcon}>i</Text><Text style={styles.infoText}>Konumun yalnızca izin verdiğinde ve uygulamayı kullanırken işlenir.</Text></View></View> : null}
        <View style={styles.bottomActions}>
          {page === "permissions" ? <><Button onPress={requestAndFinish}>Konuma izin ver</Button><Button variant="ghost" onPress={() => finish("/")}>Şimdi değil</Button></> : <Button onPress={() => setIndex((value) => Math.min(pages.length - 1, value + 1))}>{page === "navigation" ? "Başlayalım" : "Devam"}  →</Button>}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background }, screen: { flexGrow: 1, padding: spacing.md, paddingBottom: spacing.lg },
  topRow: { height: 48, flexDirection: "row", alignItems: "center", justifyContent: "space-between" }, topButton: { width: 56, minHeight: 48, alignItems: "center", justifyContent: "center" }, back: { fontSize: 34, color: colors.text }, skip: { color: colors.primary, fontWeight: "700" },
  progress: { flexDirection: "row", gap: 6 }, progressDot: { width: 28, height: 5, borderRadius: 3, backgroundColor: colors.surfaceContainerHighest }, progressDotActive: { backgroundColor: colors.primary },
  welcome: { flex: 1, padding: spacing.lg, justifyContent: "flex-end" }, welcomeSpace: { position: "absolute", top: 30, left: spacing.lg }, welcomeCopy: { marginBottom: spacing.xl }, actions: { gap: 12 }, privacy: { textAlign: "center", color: colors.textMuted, fontSize: 12, textDecorationLine: "underline", marginTop: spacing.xl },
  copy: { alignItems: "center", paddingHorizontal: spacing.md }, title: { color: colors.text, fontSize: 29, lineHeight: 35, letterSpacing: -0.8, fontWeight: "900", textAlign: "center" }, body: { color: colors.textMuted, fontSize: 15, lineHeight: 22, textAlign: "center", marginTop: 12 },
  illustration: { height: 285, marginVertical: spacing.md, borderRadius: radius.lg, backgroundColor: colors.surfaceContainer, overflow: "hidden", alignItems: "center", justifyContent: "center" },
  phone: { width: 126, height: 214, borderRadius: 22, backgroundColor: colors.surface, borderWidth: 5, borderColor: colors.text, padding: 7, transform: [{ rotate: "-2deg" }] }, phoneMap: { flex: 1, borderRadius: 12, backgroundColor: "#FAF6ED", overflow: "hidden" }, mapRoad: { position: "absolute", width: 220, height: 14, backgroundColor: "#D4DDE7", transform: [{ rotate: "55deg" }], top: 85, left: -60 }, mapRoadTwo: { position: "absolute", width: 190, height: 10, backgroundColor: "#D4DDE7", transform: [{ rotate: "-25deg" }], top: 120, left: -30 }, alertPin: { position: "absolute", left: 52, top: 75, width: 28, height: 28, borderRadius: 14, backgroundColor: colors.error, alignItems: "center", justifyContent: "center" }, alertPinText: { color: "white", fontWeight: "900" },
  floatChip: { position: "absolute", minHeight: 38, flexDirection: "row", alignItems: "center", gap: 7, backgroundColor: colors.surface, paddingHorizontal: 12, borderRadius: radius.pill, shadowColor: "#000", shadowOpacity: 0.12, shadowRadius: 8, elevation: 4 }, liveChip: { right: 18, top: 26 }, reportChip: { left: 10, top: 126 }, liveDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.secondary }, reportIcon: { color: colors.error, fontWeight: "900" }, floatText: { color: colors.text, fontSize: 12, fontWeight: "800" },
  grid: { position: "absolute", top: 0, right: 0, bottom: 0, left: 0, opacity: 0.85, backgroundColor: "#EEF4FB" }, routeMuted: { position: "absolute", left: 30, bottom: 45, width: 300, height: 6, borderRadius: 3, backgroundColor: "#A8ADB4", transform: [{ rotate: "-37deg" }] }, routeSafe: { position: "absolute", left: 22, bottom: 69, width: 340, height: 8, borderRadius: 4, backgroundColor: colors.secondary, transform: [{ rotate: "-22deg" }] }, routeLabel: { position: "absolute", backgroundColor: colors.surface, borderRadius: radius.sm, padding: 10, shadowColor: "#000", shadowOpacity: 0.1, shadowRadius: 6, elevation: 3 }, routeLabelSafe: { right: 24, top: 35, borderWidth: 2, borderColor: colors.secondary }, routeLabelShort: { left: 20, bottom: 34 }, routeLabelCap: { color: colors.secondary, fontSize: 9, fontWeight: "900" }, routeLabelTitle: { color: colors.text, fontSize: 13, fontWeight: "800" }, routeLabelSmall: { color: colors.textMuted, fontSize: 11 },
  featureList: { gap: 12, marginVertical: spacing.lg }, featureCard: { minHeight: 92, flexDirection: "row", alignItems: "center", backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.md, borderWidth: 1, borderColor: colors.borderSoft }, featureIcon: { width: 48, height: 48, borderRadius: 24, backgroundColor: colors.primaryContainer, alignItems: "center", justifyContent: "center" }, featureIconText: { color: colors.primary, fontSize: 24, fontWeight: "900" }, featureCopy: { flex: 1, marginLeft: 13 }, featureTitle: { color: colors.text, fontSize: 15, fontWeight: "800" }, featureBody: { color: colors.textMuted, fontSize: 13, lineHeight: 18, marginTop: 3 },
  permissionHero: { height: 210, alignItems: "center", justifyContent: "center", gap: 18 }, permissionHeroTitle: { color: colors.primary, fontSize: 19, fontWeight: "900" }, permissionList: { marginTop: spacing.lg, gap: spacing.md }, permissionRow: { flexDirection: "row", alignItems: "center", backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.md }, permissionIcon: { width: 48, height: 48, borderRadius: 24, alignItems: "center", justifyContent: "center", backgroundColor: colors.primaryContainer },
  info: { flexDirection: "row", gap: 10, backgroundColor: colors.surfaceContainer, borderRadius: radius.sm, padding: 13, marginTop: spacing.md }, infoIcon: { width: 20, height: 20, borderRadius: 10, borderWidth: 1, borderColor: colors.primary, textAlign: "center", color: colors.primary, fontWeight: "800" }, infoText: { flex: 1, color: colors.textMuted, fontSize: 12, lineHeight: 17 },
  bottomActions: { marginTop: "auto", paddingTop: spacing.lg, gap: 10 }, textButton: { minHeight: 48, alignItems: "center", justifyContent: "center" }, textButtonLabel: { color: colors.primary, fontWeight: "700" },
});
