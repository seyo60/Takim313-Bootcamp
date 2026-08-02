import { useState } from "react";
import { ActivityIndicator, KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { router, useLocalSearchParams } from "expo-router";
import { submitReport } from "@/lib/api";
import type { ReportPriority } from "@/lib/types";
import { useAuth } from "@/hooks/useAuth";
import { PageHeader } from "@/components/brand";
import { colors, radius, spacing } from "@/theme/tokens";

type SendState = "idle" | "sending" | "success" | "error";
const CATEGORIES = [{ id: "general", icon: "!", label: "Güvenlik" }, { id: "lighting", icon: "☼", label: "Aydınlatma" }, { id: "obstacle", icon: "▱", label: "Yol engeli" }, { id: "crime", icon: "◇", label: "Suç / şüpheli" }];
const BACKEND_MIN_TEXT = 10;
const URGENT_HOLD_MS = 700;

export default function Report() {
  const { user } = useAuth(); const { lng, lat, approximate } = useLocalSearchParams<{ lng?: string; lat?: string; approximate?: string }>();
  const [text, setText] = useState(""); const [category, setCategory] = useState("general"); const [state, setState] = useState<SendState>("idle"); const [sentPriority, setSentPriority] = useState<ReportPriority>("normal"); const [holding, setHolding] = useState(false); const [locationAccepted, setLocationAccepted] = useState(approximate !== "1");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const trimmed = text.trim(); const coordsValid = Number.isFinite(Number(lng)) && Number.isFinite(Number(lat)); const busy = state === "sending" || state === "success";
  // Anlamlı güvenlik metni zorunlu (boş/şablon metin analizde reddedilir).
  const canSend = Boolean(user && coordsValid && locationAccepted && !busy && trimmed.length >= BACKEND_MIN_TEXT);
  const authParams = { returnTo: "report", lng, lat, approximate };
  const send = async (priority: ReportPriority) => {
    if (!user) { router.replace({ pathname: "/auth", params: authParams }); return; }
    if (!coordsValid || !locationAccepted || busy) return;
    if (trimmed.length < BACKEND_MIN_TEXT) {
      setErrorMessage("Ne olduğunu en az birkaç kelimeyle yaz (örn. kavga, kaza, soygun).");
      setState("error");
      return;
    }
    setHolding(false);
    setSentPriority(priority);
    setErrorMessage(null);
    setState("sending");
    const response = await submitReport({
      text: trimmed,
      lng: Number(lng),
      lat: Number(lat),
      category,
      priority,
    });
    if (response.ok) {
      setState("success");
      // İhbarlarım sekmesi odaklanınca yenilensin diye doğrudan oraya dön.
      setTimeout(() => router.replace("/my-reports"), 1200);
    } else {
      setErrorMessage(response.error);
      setState("error");
    }
  };
  return <KeyboardAvoidingView style={styles.root} behavior={Platform.OS === "ios" ? "padding" : undefined}><PageHeader title="İhbar gönder" /><ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
    <View style={styles.hero}><View style={styles.heroIcon}><Text style={styles.heroIconText}>!</Text></View><Text style={styles.heroTitle}>Yakınındaki durumu bildir</Text><Text style={styles.heroBody}>Metin önce analiz edilir. Geçerli güvenlik ihbarı 1 km içindekilere sorulur; bir kişi “Gördüm” derse haritada yayınlanır.</Text></View>
    {!user ? <View style={styles.errorCard}><Text style={styles.errorText}>İhbar göndermek için giriş yapmalısın.</Text><Pressable style={styles.inlineButton} onPress={() => router.replace({ pathname: "/auth", params: authParams })}><Text style={styles.inlineButtonText}>Giriş yap</Text></Pressable></View> : null}
    {state === "success" ? <View style={styles.success}><Text style={styles.successIcon}>✓</Text><Text style={styles.successTitle}>{sentPriority === "urgent" ? "Acil bildirimin alındı" : "Bildirimin alındı"}</Text><Text style={styles.successBody}>Yakındakilere tanık sorusu gönderildi. İhbarlarım listesine yönlendiriliyorsun…</Text></View> : <>
      <Text style={styles.sectionTitle}>Ne tür bir durum?</Text><View style={styles.categories}>{CATEGORIES.map((item) => <Pressable key={item.id} onPress={() => setCategory(item.id)} style={[styles.category, category === item.id && styles.categorySelected]}><View style={[styles.categoryIcon, category === item.id && styles.categoryIconSelected]}><Text style={[styles.categoryIconText, category === item.id && styles.categoryTextSelected]}>{item.icon}</Text></View><Text style={[styles.categoryText, category === item.id && styles.categoryTextSelected]}>{item.label}</Text></Pressable>)}</View>
      <Text style={styles.sectionTitle}>Ne oldu?</Text><View style={styles.inputShell}><TextInput value={text} onChangeText={(value) => { setText(value); if (state === "error") { setState("idle"); setErrorMessage(null); } }} style={styles.input} placeholder="Örn. Burada kavga var / trafik kazası oldu…" placeholderTextColor="#758391" multiline maxLength={280} editable={!busy} /><Text style={styles.counter}>{trimmed.length}/280</Text></View>
      <View style={[styles.locationCard, approximate === "1" && !locationAccepted && styles.locationWarning]}><View style={styles.locationIcon}><Text style={styles.locationIconText}>⌖</Text></View><View style={styles.locationCopy}><Text style={styles.locationTitle}>{approximate === "1" ? "Kesin konum alınamadı" : "Konum otomatik eklendi"}</Text><Text style={styles.locationBody}>{coordsValid ? `${Number(lat).toFixed(5)}, ${Number(lng).toFixed(5)}` : "Konum bilgisi yok"}</Text></View>{approximate === "1" && !locationAccepted ? <Pressable style={styles.acceptLocation} onPress={() => setLocationAccepted(true)}><Text style={styles.acceptLocationText}>Bu noktayı kullan</Text></Pressable> : <Text style={styles.locationCheck}>✓</Text>}</View>
      {state === "error" ? <View style={styles.errorCard}><Text style={styles.errorText}>{errorMessage || "Bildirim gönderilemedi. Tekrar dene."}</Text></View> : null}
      <Pressable disabled={!canSend} style={[styles.send, !canSend && styles.disabled]} onPress={() => send("normal")}>{state === "sending" && sentPriority === "normal" ? <ActivityIndicator color="white" /> : <Text style={styles.sendText}>İhbarı gönder</Text>}</Pressable>
      <View style={styles.divider}><View style={styles.line} /><Text style={styles.dividerText}>acil durum</Text><View style={styles.line} /></View>
      <Pressable disabled={!user || !coordsValid || !locationAccepted || busy} onLongPress={() => send("urgent")} delayLongPress={URGENT_HOLD_MS} onPressIn={() => setHolding(true)} onPressOut={() => setHolding(false)} style={[styles.urgent, holding && styles.urgentHolding, (!user || !coordsValid || !locationAccepted) && styles.disabled]}>{state === "sending" && sentPriority === "urgent" ? <ActivityIndicator color="white" /> : <><Text style={styles.urgentTitle}>SOS · ACİL DURUM</Text><Text style={styles.urgentHint}>{holding ? "Göndermek için basılı tut…" : "Yanlış dokunmayı önlemek için basılı tut"}</Text></>}</Pressable><Text style={styles.disclaimer}>Acil tehlikede uygulamaya güvenmek yerine yerel acil yardım numarasını ara.</Text>
    </>}
  </ScrollView></KeyboardAvoidingView>;
}

const styles = StyleSheet.create({ root: { flex: 1, backgroundColor: colors.background }, scroll: { padding: spacing.md, paddingBottom: spacing.xl }, hero: { alignItems: "center", padding: spacing.md }, heroIcon: { width: 58, height: 58, borderRadius: 29, alignItems: "center", justifyContent: "center", backgroundColor: colors.errorContainer }, heroIconText: { color: colors.error, fontSize: 28, fontWeight: "900" }, heroTitle: { color: colors.text, fontSize: 22, fontWeight: "900", marginTop: 12 }, heroBody: { color: colors.textMuted, fontSize: 13, lineHeight: 18, textAlign: "center", marginTop: 5 }, sectionTitle: { color: colors.text, fontSize: 15, fontWeight: "900", marginTop: spacing.md, marginBottom: 9 }, categories: { flexDirection: "row", gap: 8 }, category: { flex: 1, minHeight: 75, alignItems: "center", justifyContent: "center", backgroundColor: colors.surface, borderRadius: radius.sm, borderWidth: 1, borderColor: colors.borderSoft }, categorySelected: { backgroundColor: colors.primaryContainer, borderColor: colors.primary }, categoryIcon: { width: 30, height: 30, borderRadius: 15, backgroundColor: colors.surfaceContainer, alignItems: "center", justifyContent: "center" }, categoryIconSelected: { backgroundColor: colors.primary }, categoryIconText: { color: colors.text, fontWeight: "900" }, categoryText: { color: colors.textMuted, fontSize: 10, fontWeight: "800", marginTop: 5 }, categoryTextSelected: { color: colors.primary }, inputShell: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.borderSoft, borderRadius: radius.md, padding: 12 }, input: { minHeight: 95, color: colors.text, fontSize: 15, textAlignVertical: "top" }, counter: { color: colors.textMuted, fontSize: 11, alignSelf: "flex-end" }, locationCard: { flexDirection: "row", alignItems: "center", minHeight: 70, backgroundColor: colors.surfaceContainer, borderRadius: radius.md, padding: 12, marginTop: spacing.md }, locationWarning: { backgroundColor: colors.warningSurface, borderWidth: 1, borderColor: "#E2A728" }, locationIcon: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.primaryContainer, alignItems: "center", justifyContent: "center" }, locationIconText: { color: colors.primary, fontSize: 20 }, locationCopy: { flex: 1, marginLeft: 10 }, locationTitle: { color: colors.text, fontWeight: "900" }, locationBody: { color: colors.textMuted, fontSize: 11, marginTop: 2 }, locationCheck: { color: colors.secondary, fontSize: 19, fontWeight: "900" }, acceptLocation: { minHeight: 38, borderRadius: radius.pill, backgroundColor: colors.primary, paddingHorizontal: 10, alignItems: "center", justifyContent: "center" }, acceptLocationText: { color: "white", fontSize: 10, fontWeight: "800" }, send: { minHeight: 52, borderRadius: radius.pill, backgroundColor: colors.primary, alignItems: "center", justifyContent: "center", marginTop: spacing.md }, sendText: { color: "white", fontWeight: "900" }, disabled: { opacity: 0.42 }, divider: { flexDirection: "row", alignItems: "center", gap: 10, marginVertical: spacing.md }, line: { flex: 1, height: StyleSheet.hairlineWidth, backgroundColor: colors.borderSoft }, dividerText: { color: colors.textMuted, fontSize: 11 }, urgent: { minHeight: 76, borderRadius: radius.md, backgroundColor: colors.error, alignItems: "center", justifyContent: "center" }, urgentHolding: { backgroundColor: "#8E1010", transform: [{ scale: 0.985 }] }, urgentTitle: { color: "white", fontWeight: "900", fontSize: 17 }, urgentHint: { color: "rgba(255,255,255,0.88)", fontSize: 11, marginTop: 4 }, disclaimer: { color: colors.textMuted, textAlign: "center", fontSize: 10, lineHeight: 15, marginTop: 8 }, errorCard: { backgroundColor: colors.errorContainer, borderRadius: radius.sm, padding: 12, marginVertical: 8 }, errorText: { color: colors.error, fontWeight: "700", lineHeight: 19 }, inlineButton: { minHeight: 42, borderRadius: radius.pill, backgroundColor: colors.error, alignItems: "center", justifyContent: "center", marginTop: 10 }, inlineButtonText: { color: "white", fontWeight: "800" }, success: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.xl, alignItems: "center" }, successIcon: { width: 60, height: 60, borderRadius: 30, textAlign: "center", textAlignVertical: "center", backgroundColor: colors.secondaryContainer, color: colors.secondary, fontSize: 28, fontWeight: "900" }, successTitle: { color: colors.text, fontSize: 21, fontWeight: "900", marginTop: 14 }, successBody: { color: colors.textMuted, textAlign: "center", marginTop: 6 } });
