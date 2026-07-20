import { Pressable, StyleSheet, Text, View } from "react-native";

interface Props {
  /** Leading emoji/icon, e.g. "⚠️" for errors, "ℹ️" for limited data. */
  icon: string;
  title: string;
  /** One short supporting sentence. */
  message: string;
  /** When set, renders a "Tekrar dene" action. */
  onRetry?: () => void;
}

/**
 * Neutral fallback card for LLM error/guardrail states (item 6): used when an
 * AI-backed section can't show real content — either the request failed
 * (retryable) or the LLM's guardrails returned a safe "insufficient data"
 * answer (not retryable, informational). Deliberately calm: no red panic
 * styling, the app keeps working around it.
 */
export function FallbackCard({ icon, title, message, onRetry }: Props) {
  return (
    <View style={styles.card}>
      <Text style={styles.icon}>{icon}</Text>
      <View style={styles.textColumn}>
        <Text style={styles.title}>{title}</Text>
        <Text style={styles.message}>{message}</Text>
      </View>
      {onRetry ? (
        <Pressable
          onPress={onRetry}
          hitSlop={8}
          style={({ pressed }) => [styles.retry, pressed && styles.retryPressed]}
        >
          <Text style={styles.retryText}>Tekrar dene</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    backgroundColor: "#f7f7f7",
    borderRadius: 10,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: "#e2e2e2",
    paddingVertical: 10,
    paddingHorizontal: 12,
  },
  icon: {
    fontSize: 18,
  },
  textColumn: {
    flex: 1,
  },
  title: {
    fontSize: 13,
    fontWeight: "600",
    color: "#444",
  },
  message: {
    marginTop: 2,
    fontSize: 12,
    color: "#777",
    lineHeight: 17,
  },
  retry: {
    paddingVertical: 6,
    paddingHorizontal: 10,
    borderRadius: 8,
    backgroundColor: "#e9f0fd",
  },
  retryPressed: {
    backgroundColor: "#d8e5fb",
  },
  retryText: {
    fontSize: 12,
    fontWeight: "600",
    color: "#1D6FEB",
  },
});
