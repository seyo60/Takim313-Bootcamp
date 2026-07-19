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

type SendState = "idle" | "sending" | "success" | "error";

const MIN_TEXT_LENGTH = 5;

/**
 * Danger report screen (modal). The user describes what's happening in free
 * text; we send it with their coordinates to POST /api/v1/report. Analysis
 * happens in the backend (LLM, background) — we only get an acknowledgement,
 * so the UI promises "received", not "risk updated".
 *
 * Coordinates arrive as route params from the map screen (the user's location,
 * or the Chicago fallback).
 */
export default function Report() {
  const { lng, lat } = useLocalSearchParams<{ lng?: string; lat?: string }>();
  const [text, setText] = useState("");
  const [state, setState] = useState<SendState>("idle");

  const trimmed = text.trim();
  const canSend =
    trimmed.length >= MIN_TEXT_LENGTH &&
    lng !== undefined &&
    lat !== undefined &&
    state !== "sending" &&
    state !== "success";

  const handleSend = async () => {
    if (!canSend) return;
    setState("sending");

    const response = await submitReport({
      text: trimmed,
      lng: Number(lng),
      lat: Number(lat),
    });

    if (response?.ok) {
      setState("success");
      // Brief confirmation, then back to the map (which refetches the heatmap).
      setTimeout(() => router.back(), 1200);
    } else {
      setState("error");
    }
  };

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

      <Text style={styles.subtitle}>
        Bulunduğun konumda ne olduğunu yaz. Bildirimin analiz edilip risk
        haritasına işlenecek.
      </Text>

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
        autoFocus
        editable={state !== "sending" && state !== "success"}
      />
      <Text style={styles.counter}>{trimmed.length}/280</Text>

      {state === "error" ? (
        <Text style={styles.error}>
          Bildirim gönderilemedi — bağlantıyı kontrol edip tekrar dene.
        </Text>
      ) : null}

      {state === "success" ? (
        <Text style={styles.success}>✓ Bildirimin alındı. Teşekkürler!</Text>
      ) : (
        <Pressable
          style={[styles.sendButton, !canSend && styles.sendButtonDisabled]}
          onPress={handleSend}
          disabled={!canSend}
        >
          {state === "sending" ? (
            <ActivityIndicator size="small" color="#fff" />
          ) : (
            <Text style={styles.sendButtonText}>Gönder</Text>
          )}
        </Pressable>
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
  subtitle: {
    fontSize: 14,
    color: "#555",
    marginTop: 8,
    lineHeight: 20,
  },
  input: {
    marginTop: 16,
    minHeight: 120,
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
    marginTop: 16,
    fontSize: 16,
    color: "#2E9E44",
    fontWeight: "600",
    textAlign: "center",
  },
  sendButton: {
    marginTop: 16,
    height: 48,
    borderRadius: 12,
    backgroundColor: "#E5484D",
    alignItems: "center",
    justifyContent: "center",
  },
  sendButtonDisabled: {
    backgroundColor: "#f0aeb1",
  },
  sendButtonText: {
    fontSize: 16,
    fontWeight: "600",
    color: "#fff",
  },
});
