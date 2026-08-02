import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { router, useLocalSearchParams } from "expo-router";
import { Body, Button, Field, Notice, Screen, Title } from "@/components/ui";
import { PageHeader, ShieldMark } from "@/components/brand";
import { requireSupabase } from "@/lib/supabase";
import { colors, radius, spacing } from "@/theme/tokens";

export default function SignIn() {
  const params = useLocalSearchParams<{ returnTo?: string; lng?: string; lat?: string; approximate?: string }>();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submit = async () => {
    setBusy(true); setError(null);
    try {
      const { error: authError } = await requireSupabase().auth.signInWithPassword({ email: email.trim(), password });
      if (authError) throw authError;
      if (params.returnTo === "report") router.replace({ pathname: "/report", params: { lng: params.lng, lat: params.lat, approximate: params.approximate } });
      else router.replace("/");
    } catch { setError("Giriş yapılamadı. E-posta ve parolayı kontrol et."); }
    finally { setBusy(false); }
  };
  return (
    <View style={styles.root}>
      <PageHeader title="SafeRoute" />
      <Screen>
        <View style={styles.card}>
          <View style={styles.icon}><ShieldMark size={58} /></View>
          <Title>Tekrar hoş geldin</Title><Body>SafeRoute hesabına giriş yap.</Body>
          <Text style={styles.label}>E-posta</Text><Field accessibilityLabel="E-posta" autoCapitalize="none" autoComplete="email" keyboardType="email-address" placeholder="E-posta adresin" value={email} onChangeText={setEmail} />
          <Text style={styles.label}>Parola</Text><Field accessibilityLabel="Parola" autoCapitalize="none" secureTextEntry placeholder="Parolan" value={password} onChangeText={setPassword} />
          <Pressable style={styles.forgot} onPress={() => router.push("/auth/reset-password")}><Text style={styles.link}>Parolamı unuttum</Text></Pressable>
          {error ? <Notice error>{error}</Notice> : null}
          <Button busy={busy} disabled={!email || !password} onPress={submit}>Giriş yap</Button>
          <Button variant="ghost" onPress={() => router.replace("/")}>Hesap açmadan devam et</Button>
          <Pressable onPress={() => router.push({ pathname: "/auth/sign-up", params })}><Text style={styles.center}>SafeRoute’ta yeni misin? <Text style={styles.link}>Hesap oluştur</Text></Text></Pressable>
        </View>
      </Screen>
    </View>
  );
}
const styles = StyleSheet.create({ root: { flex: 1, backgroundColor: colors.background }, card: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.lg, gap: 12, shadowColor: colors.primary, shadowOpacity: 0.08, shadowRadius: 20, elevation: 3 }, icon: { alignItems: "center", marginBottom: 4 }, label: { color: colors.text, fontWeight: "800", fontSize: 13 }, forgot: { alignSelf: "flex-end", minHeight: 36, justifyContent: "center" }, link: { color: colors.primary, fontWeight: "800" }, center: { color: colors.textMuted, textAlign: "center", lineHeight: 21 } });
