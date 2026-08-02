import { useCallback, useEffect, useState } from "react";
import { Alert, SafeAreaView, ScrollView, StyleSheet, Switch, Text, View } from "react-native";
import { router } from "expo-router";
import { Button, Notice } from "@/components/ui";
import { BottomNav, PageHeader, ShieldMark } from "@/components/brand";
import { useAuth } from "@/hooks/useAuth";
import {
  cancelAccountDeletion,
  getMyProfile,
  requestAccountDeletion,
  startJuryDemoAlert,
} from "@/lib/api";
import {
  getNotificationsEnabled,
  setNotificationsEnabled,
} from "@/lib/notificationSettings";
import { presentLocalNotification } from "@/lib/localNotifications";
import { resetJuryDemoClientState } from "@/lib/juryDemoReset";
import type { UserProfile } from "@/lib/types";
import { colors, radius, spacing } from "@/theme/tokens";

export default function Profile() {
  const { user, signOut } = useAuth();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notificationsOn, setNotificationsOn] = useState(true);
  const [juryBusy, setJuryBusy] = useState(false);

  const load = useCallback(async () => {
    if (!user) return;
    try {
      setProfile(await getMyProfile());
      setError(null);
    } catch {
      setError("Hesap bilgileri alınamadı.");
    }
  }, [user]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    void getNotificationsEnabled().then(setNotificationsOn);
  }, []);

  const onToggleNotifications = async (value: boolean) => {
    setNotificationsOn(value);
    await setNotificationsEnabled(value);
  };

  const scheduleDeletion = () =>
    Alert.alert(
      "Hesap silme talebi",
      "Talep saklama politikasına göre işlenecek. Bekleme süresinde iptal edebilirsin.",
      [
        { text: "Vazgeç", style: "cancel" },
        {
          text: "Talep et",
          style: "destructive",
          onPress: async () => {
            await requestAccountDeletion();
            await load();
          },
        },
      ]
    );

  const startJurySimulation = () =>
    Alert.alert(
      "Jüri ihbar simülasyonu",
      "Magnificent Mile civarında onay bekleyen ihbar oluşturulur. Her basışta simülasyon sıfırlanır; onaylayınca doğrulanmış bildirim düşer.",
      [
        { text: "Vazgeç", style: "cancel" },
        {
          text: "Simülasyonu başlat",
          onPress: () => {
            void (async () => {
              setJuryBusy(true);
              setError(null);
              try {
                await resetJuryDemoClientState();
                const result = await startJuryDemoAlert();
                if (!result) {
                  setError("Simülasyon başlatılamadı. Giriş ve backend bağlantısını kontrol et.");
                  return;
                }
                // Bildirim paneline yaz; ekranda yalnızca haritadaki modal görünsün (çift düşmesin).
                if (notificationsOn) {
                  await presentLocalNotification({
                    title: result.alert.title,
                    body: result.alert.body,
                    data: {
                      type: "witness_request",
                      event_id: result.alert.event_id,
                      alert_id: result.alert.alert_id,
                      source: "jury_demo",
                      force_foreground: true,
                    },
                    forceWhenActive: true,
                  });
                }
                router.replace("/");
              } finally {
                setJuryBusy(false);
              }
            })();
          },
        },
      ]
    );

  return (
    <SafeAreaView style={styles.root}>
      <PageHeader title="Profil" />
      <ScrollView contentContainerStyle={styles.scroll}>
        {!user ? (
          <View style={styles.guest}>
            <ShieldMark size={76} />
            <Text style={styles.title}>Profiline giriş yap</Text>
            <Text style={styles.body}>
              İhbarlarını takip etmek ve hesap ayarlarını yönetmek için giriş yap.
            </Text>
            <Button onPress={() => router.push("/auth")}>Giriş yap veya hesap oluştur</Button>
          </View>
        ) : (
          <>
            <View style={styles.profileCard}>
              <View style={styles.avatar}>
                <Text style={styles.avatarText}>
                  {user.email?.slice(0, 1).toUpperCase() ?? "S"}
                </Text>
              </View>
              <Text style={styles.email}>{user.email}</Text>
              <Text style={styles.role}>
                {profile?.role === "admin" ? "Yönetici" : "SafeRoute üyesi"}
              </Text>
            </View>
            {error ? <Notice error>{error}</Notice> : null}
            {profile?.deletion_requested_at ? (
              <Notice>Hesap silme talebin bekliyor.</Notice>
            ) : null}
            <View style={styles.settings}>
              <Text style={styles.heading}>Bildirimler</Text>
              <View style={styles.switchRow}>
                <View style={styles.switchCopy}>
                  <Text style={styles.switchTitle}>Doğrulanmış uyarılar</Text>
                  <Text style={styles.switchBody}>
                    Yakındaki doğrulanmış acil bildirimleri telefon bildirim çubuğuna düşür.
                  </Text>
                </View>
                <Switch
                  value={notificationsOn}
                  onValueChange={(value) => void onToggleNotifications(value)}
                  trackColor={{
                    false: colors.surfaceContainerHighest,
                    true: colors.primaryContainer,
                  }}
                  thumbColor={notificationsOn ? colors.primary : colors.surface}
                />
              </View>
            </View>
            <View style={styles.settings}>
              <Text style={styles.heading}>Jüri demosu</Text>
              <Text style={styles.switchBody}>
                Magnificent Mile ihbarı; her basışta sıfırlanır. Tanık onayı ve
                doğrulanmış bildirimi bu cihazda simüle eder.
              </Text>
              <Button variant="secondary" busy={juryBusy} onPress={startJurySimulation}>
                İhbar bildirim simülasyonunu başlat
              </Button>
            </View>
            <View style={styles.settings}>
              <Text style={styles.heading}>Hesap</Text>
              <Button variant="ghost" onPress={() => router.push("/my-reports")}>
                İhbarlarımı görüntüle
              </Button>
              <Button variant="ghost" onPress={load}>
                Hesap bilgilerini yenile
              </Button>
              <Button
                variant="ghost"
                onPress={async () => {
                  await signOut();
                  router.replace("/");
                }}
              >
                Çıkış yap
              </Button>
            </View>
            <View style={styles.danger}>
              <Text style={styles.heading}>Hesap yönetimi</Text>
              {profile?.deletion_requested_at ? (
                <Button
                  variant="secondary"
                  onPress={async () => {
                    await cancelAccountDeletion();
                    await load();
                  }}
                >
                  Silme talebini iptal et
                </Button>
              ) : (
                <Button variant="danger" onPress={scheduleDeletion}>
                  Hesabımı sil
                </Button>
              )}
            </View>
          </>
        )}
        <Text style={styles.about}>
          SafeRoute 1.0 · Güvenlik skoru kesin güvenlik garantisi değildir.
        </Text>
      </ScrollView>
      <BottomNav active="profile" />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.background },
  scroll: { padding: spacing.md, paddingBottom: 102, gap: spacing.md },
  guest: {
    gap: spacing.md,
    alignItems: "center",
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: spacing.lg,
  },
  title: { color: colors.text, fontSize: 23, fontWeight: "900" },
  body: { color: colors.textMuted, textAlign: "center", lineHeight: 21 },
  profileCard: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: spacing.lg,
    alignItems: "center",
  },
  avatar: {
    width: 72,
    height: 72,
    borderRadius: 36,
    backgroundColor: colors.primaryContainer,
    alignItems: "center",
    justifyContent: "center",
  },
  avatarText: { color: colors.primary, fontSize: 30, fontWeight: "900" },
  email: { color: colors.text, fontSize: 17, fontWeight: "900", marginTop: 12 },
  role: { color: colors.textMuted, marginTop: 3 },
  settings: {
    gap: 10,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    padding: spacing.md,
  },
  switchRow: { flexDirection: "row", alignItems: "center", gap: 12 },
  switchCopy: { flex: 1, gap: 4 },
  switchTitle: { color: colors.text, fontSize: 15, fontWeight: "800" },
  switchBody: { color: colors.textMuted, fontSize: 12, lineHeight: 17 },
  danger: {
    gap: 10,
    backgroundColor: colors.errorContainer,
    borderRadius: radius.md,
    padding: spacing.md,
  },
  heading: { color: colors.text, fontSize: 17, fontWeight: "900" },
  about: { color: colors.textMuted, textAlign: "center", fontSize: 11, lineHeight: 17 },
});
