import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";

export type BannerVariant = "info" | "loading" | "error";

interface Props {
  variant: BannerVariant;
  text: string;
  /** When set (error variant), shows a "Tekrar dene" button. */
  onRetry?: () => void;
}

/**
 * Floating status banner (item 7): loading gets a spinner, errors get a red
 * tint and an optional retry action, info stays neutral. Never blocks the map —
 * only the retry button is tappable.
 */
export function StatusBanner({ variant, text, onRetry }: Props) {
  return (
    <View
      style={[styles.banner, variant === "error" && styles.bannerError]}
      pointerEvents={onRetry ? "box-none" : "none"}
    >
      {variant === "loading" ? (
        <ActivityIndicator size="small" color="#fff" style={styles.spinner} />
      ) : null}

      <Text style={styles.text}>{text}</Text>

      {variant === "error" && onRetry ? (
        <Pressable
          style={({ pressed }) => [styles.retry, pressed && styles.retryPressed]}
          onPress={onRetry}
          hitSlop={8}
        >
          <Text style={styles.retryText}>Tekrar dene</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  banner: {
    position: "absolute",
    bottom: 116,
    left: 16,
    right: 16,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "rgba(0,0,0,0.78)",
    paddingVertical: 10,
    paddingHorizontal: 14,
    borderRadius: 10,
  },
  bannerError: {
    backgroundColor: "rgba(179,38,30,0.92)",
  },
  spinner: {
    marginRight: 8,
  },
  text: {
    flexShrink: 1,
    color: "#fff",
    fontSize: 13,
    textAlign: "center",
  },
  retry: {
    marginLeft: 10,
    paddingVertical: 4,
    paddingHorizontal: 10,
    borderRadius: 8,
    backgroundColor: "rgba(255,255,255,0.22)",
  },
  retryPressed: {
    backgroundColor: "rgba(255,255,255,0.35)",
  },
  retryText: {
    color: "#fff",
    fontSize: 13,
    fontWeight: "600",
  },
});
