import { useState } from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { router, useLocalSearchParams } from "expo-router";
import { submitReport } from "@/lib/api";
import type { ReportPriority } from "@/lib/types";

type SendState = "idle" | "sending" | "success" | "error";

const MIN_TEXT_LENGTH = 5;
/** Hold duration for the URGENT button before it fires (accident guard, AC #5). */
const URGENT_HOLD_MS = 700;

/**
 * Danger report screen (modal). Two ways to report:
 *
 * - URGENT (item 4, Drew scenario): one gesture — hold the big red button — to
 *   fire the highest-priority alert without filling in the form. The note is
 *   optional; the location is attached automatically. Holding (rather than a
 *   plain tap) guards against accidental presses (AC #5).
 * - Standard: describe what's happening in free text, then "Gönder".
 *
 * Both POST to /api/v1/report; analysis happens in the backend (LLM,
 * background), so we only get an acknowledgement — the UI promises "received".
 *
 * Coordinates arrive as route params from the map screen (the user's live
 * location, or the Chicago fallback), i.e. the location is captured
 * automatically — the user never types it.
 */
export default function Report() {
  const { lng, lat } = useLocalSearchParams<{ lng?: string; lat?: string }>();
  const [text, setText] = useState("");
  const [state, setState] = useState<SendState>("idle");
  // Which path succeeded/failed, so the confirmation matches (AC #4).
  const [sentPriority, setSentPriority] = useState<ReportPriority>("normal");
  // Visual feedback while the URGENT button is being held down.
  const [holding, setHolding] = useState(false);

  const trimmed = text.trim();
  const hasCoords = lng !== undefined && lat !== undefined;
  const busy = state === "sending" || state === "success";
  const canSendNormal =
    trimmed.length >= MIN_TEXT_LENGTH && hasCoords && !busy;

  const send = async (priority: ReportPriority) => {
    if (!hasCoords || busy) return;
    // The standard path needs a description; urgent does not.
    if (priority === "normal" && trimmed.length < MIN_TEXT_LENGTH) return;

    setHolding(false);
    setSentPriority(priority);
    setState("sending");

    const response = await submitReport({
      // Urgent reports may carry no note — send a stand-in so the record isn't empty.
      text: trimmed.length > 0 ? trimmed : "🚨 Acil durum bildirimi (detay girilmedi)",
      lng: Number(lng),
      lat: Number(lat),
      priority,
    });

    if (response?.ok) {
      setState("success");
      // Brief confirmation, then back to the map (which refetches the heatmap).
      setTimeout(() => router.back(), 1400);
    } else {
      setState("error");
    }
  };

  const urgentSending = state === "sending" && sentPriority === "urgent";

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <View style={styles.header}>
        <Text style={styles.title}>⚠️ Tehlike Bildir</Text>
        <Pressable onPress={() => router.back()} hitSlop={12}>
          <Text style={styles.closeText}>✕</Text>
        </Pressable>
      </View>

      {state === "success" ? (
        <Text
          style={[
            styles.success,
            sentPriority === "urgent" && styles.successUrgent,
          ]}
        >
          {sentPriority === "urgent"
            ? "🚨 Acil durum bildirimin iletildi. Yakındaki kullanıcılar uyarılıyor."
            : "✓ Bildirimin alındı. Teşekkürler!"}
        </Text>
      ) : (
        <>
          {/* Item 4: URGENT one-gesture path. */}
          <Pressable
            style={[styles.urgentButton, holding && styles.urgentButtonHolding]}
            onLongPress={() => send("urgent")}
            delayLongPress={URGENT_HOLD_MS}
            onPressIn={() => setHolding(true)}
            onPressOut={() => setHolding(false)}
            disabled={busy}
          >
            {urgentSending ? (
              <ActivityIndicator size="large" color="#fff" />
            ) : (
              <>
                <Text style={styles.urgentIcon}>🚨</Text>
                <Text style={styles.urgentText}>ACİL DURUM</Text>
                <Text style={styles.urgentHint}>
                  {holding
                    ? "Bırakmadan bekleyin…"
                    : "Göndermek için basılı tutun"}
                </Text>
              </>
            )}
          </Pressable>
          <Text style={styles.urgentCaption}>
            Konumun otomatik eklenir. Not girmen zorunlu değil.
          </Text>

          <View style={styles.divider}>
            <View style={styles.dividerLine} />
            <Text style={styles.dividerText}>veya detaylı bildir</Text>
            <View style={styles.dividerLine} />
          </View>

          <TextInput
            style={styles.input}
            value={text}
            onChangeText={(value) => {
              setText(value);
              // Let the user edit and retry after a failure.
              if (state === "error") setState("idle");
            }}
            placeholder='Ne oldu? (örn. "Bu sokakta birisi beni takip ediyor")'
            placeholderTextColor="#8a8a8a"
            multiline
            maxLength={280}
            editable={!busy}
          />
          <Text style={styles.counter}>{trimmed.length}/280</Text>

          {state === "error" ? (
            <Text style={styles.error}>
              Bildirim gönderilemedi — bağlantıyı kontrol edip tekrar dene.
            </Text>
          ) : null}

          <Pressable
            style={[
              styles.sendButton,
              !canSendNormal && styles.sendButtonDisabled,
            ]}
            onPress={() => send("normal")}
            disabled={!canSendNormal}
          >
            {state === "sending" && sentPriority === "normal" ? (
              <ActivityIndicator size="small" color="#fff" />
            ) : (
              <Text style={styles.sendButtonText}>Gönder</Text>
            )}
          </Pressable>
        </>
      )}
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#fff",
    padding: 20,
    paddingTop: 24,
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  title: {
    fontSize: 20,
    fontWeight: "700",
    color: "#111",
  },
  closeText: {
    fontSize: 18,
    color: "#777",
  },
  urgentButton: {
    marginTop: 20,
    minHeight: 130,
    borderRadius: 16,
    backgroundColor: "#E5484D",
    alignItems: "center",
    justifyContent: "center",
    paddingVertical: 16,
    shadowColor: "#E5484D",
    shadowOpacity: 0.4,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 4 },
    elevation: 6,
  },
  urgentButtonHolding: {
    backgroundColor: "#B3201B",
    transform: [{ scale: 0.98 }],
  },
  urgentIcon: {
    fontSize: 40,
  },
  urgentText: {
    marginTop: 6,
    fontSize: 24,
    fontWeight: "800",
    letterSpacing: 1,
    color: "#fff",
  },
  urgentHint: {
    marginTop: 6,
    fontSize: 13,
    color: "rgba(255,255,255,0.9)",
  },
  urgentCaption: {
    marginTop: 8,
    fontSize: 12,
    color: "#888",
    textAlign: "center",
  },
  divider: {
    flexDirection: "row",
    alignItems: "center",
    marginVertical: 20,
    gap: 10,
  },
  dividerLine: {
    flex: 1,
    height: StyleSheet.hairlineWidth,
    backgroundColor: "#ddd",
  },
  dividerText: {
    fontSize: 12,
    color: "#999",
  },
  input: {
    minHeight: 110,
    borderWidth: 1,
    borderColor: "#ddd",
    borderRadius: 12,
    padding: 14,
    fontSize: 15,
    color: "#111",
    textAlignVertical: "top",
  },
  counter: {
    alignSelf: "flex-end",
    marginTop: 4,
    fontSize: 12,
    color: "#999",
  },
  error: {
    marginTop: 10,
    fontSize: 13,
    color: "#E5484D",
  },
  success: {
    marginTop: 40,
    fontSize: 16,
    color: "#2E9E44",
    fontWeight: "600",
    textAlign: "center",
    lineHeight: 24,
  },
  successUrgent: {
    color: "#E5484D",
  },
  sendButton: {
    marginTop: 12,
    height: 48,
    borderRadius: 12,
    backgroundColor: "#1D6FEB",
    alignItems: "center",
    justifyContent: "center",
  },
  sendButtonDisabled: {
    backgroundColor: "#a9c7f5",
  },
  sendButtonText: {
    fontSize: 16,
    fontWeight: "600",
    color: "#fff",
  },
});
