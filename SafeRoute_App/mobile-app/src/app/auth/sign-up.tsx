import { useMemo, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { router, useLocalSearchParams } from "expo-router";
import { Body, Button, Field, Notice, Screen, Title } from "@/components/ui";
import { PageHeader } from "@/components/brand";
import { requireSupabase } from "@/lib/supabase";
import { colors, radius, spacing } from "@/theme/tokens";

export default function SignUp() {
  const params = useLocalSearchParams<{ returnTo?: string; lng?: string; lat?: string; approximate?: string }>();
  const [email, setEmail] = useState(""); const [password, setPassword] = useState(""); const [confirm, setConfirm] = useState("");
  const [consent, setConsent] = useState(false); const [busy, setBusy] = useState(false); const [error, setError] = useState<string | null>(null);
  const strength = useMemo(() => password.length >= 12 ? 3 : password.length >= 8 ? 2 : password.length ? 1 : 0, [password]);
  const goAfterAuth = () => {
    if (params.returnTo === "report") {
      router.replace({ pathname: "/report", params: { lng: params.lng, lat: params.lat, approximate: params.approximate } });
      return;
    }
    router.replace("/");
  };
  const submit = async () => {
    setBusy(true); setError(null);
    try {
      const trimmedEmail = email.trim();
      const { data, error: authError } = await requireSupabase().auth.signUp({ email: trimmedEmail, password });
      if (authError) throw authError;
      if (!data.session) {
        const { error: signInError } = await requireSupabase().auth.signInWithPassword({ email: trimmedEmail, password });
        if (signInError) throw signInError;
      }
      goAfterAuth();
    } catch { setError("Kayıt tamamlanamadı. E-posta ve parola kurallarını kontrol et."); }
    finally { setBusy(false); }
  };
  const valid = email.includes("@") && password.length >= 8 && password === confirm && consent;
  return <View style={styles.root}><PageHeader title="Hesap oluştur" /><Screen top><View style={styles.card}><Title>SafeRoute’a katıl</Title><Body>Güven ve farkındalıkla ilerle. Gizlilik için ad, soyad ve telefon istemiyoruz.</Body>
    <Text style={styles.label}>E-posta</Text><Field accessibilityLabel="E-posta" autoCapitalize="none" keyboardType="email-address" placeholder="ornek@eposta.com" value={email} onChangeText={setEmail} />
    <Text style={styles.label}>Parola</Text><Field accessibilityLabel="Parola" secureTextEntry placeholder="En az 8 karakter" value={password} onChangeText={setPassword} />
    <View style={styles.strength}>{[1,2,3].map((value) => <View key={value} style={[styles.strengthBar, value <= strength && styles.strengthBarActive]} />)}</View><Text style={styles.strengthText}>Parola gücü: {strength === 3 ? "Güçlü" : strength === 2 ? "Orta" : "Zayıf"}</Text>
    <Text style={styles.label}>Parolayı doğrula</Text><Field accessibilityLabel="Parola doğrulama" secureTextEntry placeholder="Parolanı tekrar yaz" value={confirm} onChangeText={setConfirm} />
    <Pressable accessibilityRole="checkbox" accessibilityState={{ checked: consent }} onPress={() => setConsent((value) => !value)} style={styles.consent}><View style={[styles.box, consent && styles.boxChecked]}><Text style={styles.check}>{consent ? "✓" : ""}</Text></View><Text style={styles.consentText}>Kullanım koşullarını ve gizlilik politikasını okudum.</Text></Pressable>
    {password !== confirm && confirm ? <Notice error>Parolalar eşleşmiyor.</Notice> : null}{error ? <Notice error>{error}</Notice> : null}
    <Button busy={busy} disabled={!valid} onPress={submit}>Hesap oluştur  →</Button><Pressable onPress={() => router.replace({ pathname: "/auth/sign-in", params })}><Text style={styles.center}>Zaten hesabın var mı? <Text style={styles.link}>Giriş yap</Text></Text></Pressable>
  </View></Screen></View>;
}
const styles = StyleSheet.create({ root: { flex: 1, backgroundColor: colors.background }, card: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.lg, gap: 10 }, label: { color: colors.text, fontWeight: "800", fontSize: 13 }, strength: { flexDirection: "row", gap: 5 }, strengthBar: { flex: 1, height: 4, borderRadius: 2, backgroundColor: colors.surfaceContainerHighest }, strengthBarActive: { backgroundColor: colors.primary }, strengthText: { color: colors.textMuted, fontSize: 12 }, consent: { flexDirection: "row", alignItems: "center", gap: 10, minHeight: 48 }, box: { width: 23, height: 23, borderRadius: 5, borderWidth: 1, borderColor: colors.border, alignItems: "center", justifyContent: "center" }, boxChecked: { backgroundColor: colors.primary, borderColor: colors.primary }, check: { color: colors.surface, fontWeight: "900" }, consentText: { color: colors.text, flex: 1, fontSize: 13 }, center: { color: colors.textMuted, textAlign: "center", paddingTop: 6 }, link: { color: colors.primary, fontWeight: "800" } });
