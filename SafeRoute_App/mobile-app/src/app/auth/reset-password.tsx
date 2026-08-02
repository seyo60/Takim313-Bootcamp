import { useState } from "react";
import { StyleSheet, Text, View } from "react-native";
import * as Linking from "expo-linking";
import { router } from "expo-router";
import { Body, Button, Field, Notice, Screen, Title } from "@/components/ui";
import { PageHeader } from "@/components/brand";
import { requireSupabase } from "@/lib/supabase";
import { colors, radius, spacing } from "@/theme/tokens";

export default function ResetPassword() {
  const [email, setEmail] = useState(""); const [sent, setSent] = useState(false); const [busy, setBusy] = useState(false); const [error, setError] = useState<string | null>(null);
  const submit = async () => { setBusy(true); setError(null); try { const { error: authError } = await requireSupabase().auth.resetPasswordForEmail(email.trim(), { redirectTo: Linking.createURL("/auth/callback", { queryParams: { recovery: "1" } }) }); if (authError) throw authError; setSent(true); } catch { setError("Sıfırlama e-postası gönderilemedi. Biraz sonra tekrar dene."); } finally { setBusy(false); } };
  return <View style={styles.root}><PageHeader /><Screen><View style={styles.card}><View style={styles.icon}><Text style={styles.iconText}>↶</Text></View><Title>Parolanı mı unuttun?</Title><Body>Hesabınla ilişkili e-posta adresini yaz; parolanı sıfırlamak için güvenli bir bağlantı gönderelim.</Body><Text style={styles.label}>E-posta adresi</Text><Field accessibilityLabel="E-posta" autoCapitalize="none" keyboardType="email-address" placeholder="ornek@eposta.com" value={email} onChangeText={setEmail} />{sent ? <Notice>E-posta kutunu kontrol et. Güvenlik nedeniyle hesabın var olup olmadığını açıklamıyoruz.</Notice> : null}{error ? <Notice error>{error}</Notice> : null}<Button busy={busy} disabled={!email.includes("@")} onPress={submit}>Sıfırlama bağlantısı gönder  →</Button><Button variant="ghost" onPress={() => router.back()}>←  Girişe dön</Button></View><Text style={styles.support}>Sorun mu yaşıyorsun? <Text style={styles.link}>Destekle iletişime geç</Text></Text></Screen></View>;
}
const styles = StyleSheet.create({ root: { flex: 1, backgroundColor: colors.background }, card: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.lg, gap: 14, shadowColor: colors.primary, shadowOpacity: 0.08, shadowRadius: 16, elevation: 3 }, icon: { width: 64, height: 64, borderRadius: 32, backgroundColor: colors.primaryContainer, alignSelf: "center", alignItems: "center", justifyContent: "center" }, iconText: { color: colors.primary, fontSize: 31, fontWeight: "900" }, label: { color: colors.text, fontSize: 13, fontWeight: "800" }, support: { textAlign: "center", color: colors.textMuted, fontSize: 12 }, link: { color: colors.primary, fontWeight: "800" } });
