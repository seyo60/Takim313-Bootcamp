import { ActivityIndicator, Modal, Pressable, StyleSheet, Text, View } from "react-native";
import type { PendingAlert } from "@/lib/api";
import { colors, radius, spacing } from "@/theme/tokens";

interface Props {
  alert: PendingAlert | null;
  busy: boolean;
  statusMessage: string | null;
  onConfirm: () => void;
  onDeny: () => void;
  onUnsure: () => void;
  onClose: () => void;
}

/**
 * 1 km içindeki ihbar için tanık diyaloğu: Gördüm / Görmedim / Emin değilim.
 */
export function WitnessAlertModal({
  alert,
  busy,
  statusMessage,
  onConfirm,
  onDeny,
  onUnsure,
  onClose,
}: Props) {
  const visible = Boolean(alert) || Boolean(statusMessage);
  if (!visible) return null;

  return (
    <Modal visible animationType="slide" transparent onRequestClose={onClose}>
      <View style={styles.backdrop}>
        <View style={styles.card}>
          {statusMessage && !alert ? (
            <>
              <Text style={styles.title}>Bildirim</Text>
              <Text style={styles.body}>{statusMessage}</Text>
              <Pressable style={styles.primary} onPress={onClose}>
                <Text style={styles.primaryText}>Tamam</Text>
              </Pressable>
            </>
          ) : alert ? (
            <>
              <Text style={styles.cap}>
                {alert.phase === "broadcast"
                  ? "DOĞRULANMIŞ İHBAR"
                  : "YAKININIZDA İHBAR"}
              </Text>
              <Text style={styles.title}>{alert.title}</Text>
              <Text style={styles.body}>{alert.body}</Text>
              <Text style={styles.meta}>
                ~{Math.round(alert.distance_m)} m uzaklık
                {alert.phase === "broadcast"
                  ? ` · ${alert.confirm_count} tanık onayı`
                  : ` · ${alert.confirm_count} onay`}
              </Text>
              {busy ? (
                <ActivityIndicator color={colors.primary} style={{ marginTop: 16 }} />
              ) : alert.phase === "broadcast" ? (
                <View style={styles.actions}>
                  <Pressable style={styles.primary} onPress={onClose}>
                    <Text style={styles.primaryText}>Anladım</Text>
                  </Pressable>
                </View>
              ) : (
                <View style={styles.actions}>
                  <Pressable style={styles.primary} onPress={onConfirm}>
                    <Text style={styles.primaryText}>Gördüm</Text>
                  </Pressable>
                  <Pressable style={styles.secondary} onPress={onDeny}>
                    <Text style={styles.secondaryText}>Görmedim</Text>
                  </Pressable>
                  <Pressable style={styles.tertiary} onPress={onUnsure}>
                    <Text style={styles.tertiaryText}>Emin değilim</Text>
                  </Pressable>
                  <Pressable style={styles.later} onPress={onClose}>
                    <Text style={styles.laterText}>Sonra</Text>
                  </Pressable>
                </View>
              )}
            </>
          ) : null}
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    backgroundColor: "rgba(15,23,42,0.45)",
    justifyContent: "flex-end",
  },
  card: {
    backgroundColor: colors.surface,
    borderTopLeftRadius: radius.lg,
    borderTopRightRadius: radius.lg,
    padding: spacing.lg,
    paddingBottom: spacing.xl,
  },
  cap: {
    color: colors.error,
    fontSize: 11,
    fontWeight: "900",
    letterSpacing: 1,
  },
  title: {
    color: colors.text,
    fontSize: 20,
    fontWeight: "900",
    marginTop: 8,
  },
  body: {
    color: colors.textMuted,
    fontSize: 15,
    lineHeight: 22,
    marginTop: 10,
  },
  meta: {
    color: colors.textMuted,
    fontSize: 12,
    marginTop: 12,
    fontWeight: "700",
  },
  actions: { marginTop: 18, gap: 10 },
  primary: {
    minHeight: 52,
    borderRadius: radius.pill,
    backgroundColor: colors.error,
    alignItems: "center",
    justifyContent: "center",
  },
  primaryText: { color: "white", fontWeight: "900" },
  secondary: {
    minHeight: 48,
    borderRadius: radius.pill,
    borderWidth: 1.5,
    borderColor: colors.borderSoft,
    alignItems: "center",
    justifyContent: "center",
  },
  secondaryText: { color: colors.text, fontWeight: "800" },
  tertiary: {
    minHeight: 48,
    borderRadius: radius.pill,
    backgroundColor: colors.surfaceContainer,
    alignItems: "center",
    justifyContent: "center",
  },
  tertiaryText: { color: colors.textMuted, fontWeight: "800" },
  later: { minHeight: 40, alignItems: "center", justifyContent: "center" },
  laterText: { color: colors.textMuted, fontWeight: "700" },
});
