import { router, useLocalSearchParams } from "expo-router";
import { StyleSheet, Text, View } from "react-native";
import { Body, Button, Notice, Screen, Title } from "@/components/ui";
import { ShieldMark, Wordmark } from "@/components/brand";
import { useAuth } from "@/hooks/useAuth";
import { colors, spacing } from "@/theme/tokens";

export default function AuthWelcome() {
  const { configured } = useAuth();
  const params = useLocalSearchParams<{ returnTo?: string; lng?: string; lat?: string; approximate?: string }>();
  const forwarded = { returnTo: params.returnTo, lng: params.lng, lat: params.lat, approximate: params.approximate };
  return (
    <Screen>
      <View style={styles.brand}><Wordmark /></View>
      <View style={styles.hero}><ShieldMark size={72} /><Title>SafeRoute’a hoş geldin</Title><Body>Şehrinde daha fazla bağlamla, daha bilinçli yürü.</Body></View>
      {!configured ? <Notice error>Kimlik doğrulama henüz yapılandırılmadı. Haritaya misafir olarak devam edebilirsin.</Notice> : null}
      <Button disabled={!configured} onPress={() => router.push({ pathname: "/auth/sign-in", params: forwarded })}>Giriş yap</Button>
      <Button disabled={!configured} variant="ghost" onPress={() => router.push({ pathname: "/auth/sign-up", params: forwarded })}>Hesap oluştur</Button>
      <Button variant="secondary" onPress={() => router.replace("/")}>Hesap açmadan devam et</Button>
      <Text style={styles.note}>İhbar göndermek ve kendi ihbarlarını takip etmek için hesap gerekir.</Text>
    </Screen>
  );
}
const styles = StyleSheet.create({ brand: { position: "absolute", top: spacing.lg, left: spacing.lg }, hero: { alignItems: "center", gap: spacing.md, marginBottom: spacing.md }, note: { textAlign: "center", color: colors.textMuted, fontSize: 12, lineHeight: 17 } });
