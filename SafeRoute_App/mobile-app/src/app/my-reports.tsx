import { useCallback, useState } from "react";
import { Alert, SafeAreaView, ScrollView, StyleSheet, Text, View } from "react-native";
import { router, useFocusEffect } from "expo-router";
import { BottomNav, PageHeader } from "@/components/brand";
import { Button, Notice } from "@/components/ui";
import { useAuth } from "@/hooks/useAuth";
import { deleteMyReport, getMyReports } from "@/lib/api";
import { REPORT_STATUS_CONFIG, type ReportDetailResponse, type ReportStatus } from "@/lib/types";
import { colors, radius, spacing } from "@/theme/tokens";

const FALLBACK_STATUS = REPORT_STATUS_CONFIG.pending;

export default function MyReports() {
  const { user } = useAuth();
  const [reports, setReports] = useState<ReportDetailResponse[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!user) return;
    setLoading(true);
    try {
      const next = (await getMyReports()).reports ?? [];
      setReports(next);
      setError(null);
    } catch (err) {
      const detail =
        err && typeof err === "object" && "message" in err
          ? String((err as { message?: string }).message)
          : "";
      setError(detail ? `İhbarların alınamadı: ${detail}` : "İhbarların alınamadı.");
    } finally {
      setLoading(false);
    }
  }, [user]);

  useFocusEffect(
    useCallback(() => {
      void load();
    }, [load])
  );

  const confirmDelete = (report: ReportDetailResponse) => {
    Alert.alert(
      "İhbarı sil",
      "Bu ihbar listenden kaldırılacak. Devam edilsin mi?",
      [
        { text: "Vazgeç", style: "cancel" },
        {
          text: "Sil",
          style: "destructive",
          onPress: () => {
            void (async () => {
              setDeletingId(report.id);
              const ok = await deleteMyReport(report.id);
              setDeletingId(null);
              if (!ok) {
                setError("İhbar silinemedi. Tekrar dene.");
                return;
              }
              setReports((prev) => prev.filter((item) => item.id !== report.id));
            })();
          },
        },
      ]
    );
  };

  return (
    <SafeAreaView style={styles.root}>
      <PageHeader title="İhbarlarım" />
      <ScrollView contentContainerStyle={styles.scroll}>
        {!user ? (
          <View style={styles.empty}>
            <Text style={styles.emptyTitle}>İhbarlarını takip et</Text>
            <Text style={styles.emptyBody}>
              Kendi ihbar geçmişin yalnızca hesabına giriş yaptığında görünür. Başka
              kullanıcıların ihbarları burada listelenmez; haritada “Son bir saatteki
              ihbarlar” ile görürsün.
            </Text>
            <Button onPress={() => router.push("/auth")}>Giriş yap</Button>
          </View>
        ) : (
          <>
            <Text style={styles.accountHint}>Hesap: {user.email}</Text>
            <View style={styles.summary}>
              <Text style={styles.summaryValue}>{reports.length}</Text>
              <Text style={styles.summaryLabel}>toplam ihbar</Text>
              <Button variant="ghost" busy={loading} onPress={load}>
                Yenile
              </Button>
            </View>
            {error ? <Notice error>{error}</Notice> : null}
            {reports.length === 0 && !loading ? (
              <View style={styles.empty}>
                <Text style={styles.emptyTitle}>Henüz ihbarın yok</Text>
                <Text style={styles.emptyBody}>
                  Haritadaki SOS düğmesini kullanarak bulunduğun yerdeki bir durumu
                  bildirebilirsin. İhbar bu hesaba (`{user.email}`) kaydedilir.
                </Text>
                <Button onPress={() => router.replace("/")}>Haritaya dön</Button>
              </View>
            ) : (
              reports.map((report) => {
                const statusKey = (report.status ?? "pending") as ReportStatus;
                const config = REPORT_STATUS_CONFIG[statusKey] ?? FALLBACK_STATUS;
                return (
                  <View key={report.id} style={styles.card}>
                    <View style={styles.cardHeader}>
                      <Text style={styles.cardTitle}>
                        {report.category ?? "Genel güvenlik"}
                      </Text>
                      <View style={[styles.status, { backgroundColor: config.bgColor }]}>
                        <Text style={[styles.statusText, { color: config.textColor }]}>
                          {config.label}
                        </Text>
                      </View>
                    </View>
                    <Text style={styles.date}>
                      {new Date(report.created_at).toLocaleString("tr-TR")}
                    </Text>
                    {report.description ? (
                      <Text style={styles.description} numberOfLines={4}>
                        {report.description}
                      </Text>
                    ) : null}
                    <Text style={styles.statusMsg} numberOfLines={2}>
                      {report.message ??
                        "İhbar ayrıntısı gizlilik nedeniyle gösterilmiyor."}
                    </Text>
                    <Button
                      variant="danger"
                      busy={deletingId === report.id}
                      onPress={() => confirmDelete(report)}
                    >
                      İhbarı sil
                    </Button>
                  </View>
                );
              })
            )}
          </>
        )}
      </ScrollView>
      <BottomNav active="reports" />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.background },
  scroll: { padding: spacing.md, paddingBottom: 100, gap: 12 },
  accountHint: { color: colors.textMuted, fontSize: 12, fontWeight: "700" },
  summary: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    backgroundColor: colors.surfaceContainer,
    borderRadius: radius.md,
    padding: spacing.md,
  },
  summaryValue: { color: colors.primary, fontSize: 28, fontWeight: "900" },
  summaryLabel: { flex: 1, color: colors.textMuted, fontWeight: "700" },
  empty: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: spacing.lg,
    gap: spacing.md,
    alignItems: "center",
  },
  emptyTitle: { color: colors.text, fontSize: 20, fontWeight: "900" },
  emptyBody: { color: colors.textMuted, lineHeight: 20, textAlign: "center" },
  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    padding: spacing.md,
    borderWidth: 1,
    borderColor: colors.borderSoft,
    gap: 10,
  },
  cardHeader: { flexDirection: "row", alignItems: "flex-start", gap: 8 },
  cardTitle: { flex: 1, color: colors.text, fontSize: 15, fontWeight: "900" },
  status: { borderRadius: radius.pill, paddingVertical: 5, paddingHorizontal: 8 },
  statusText: { fontSize: 9, fontWeight: "900" },
  date: { color: colors.textMuted, fontSize: 11 },
  description: { color: colors.text, fontSize: 14, lineHeight: 20, fontWeight: "600" },
  statusMsg: { color: colors.textMuted, fontSize: 12, lineHeight: 17 },
});
