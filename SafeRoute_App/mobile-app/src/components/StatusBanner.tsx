import { useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Animated,
  Pressable,
  StyleSheet,
  Text,
} from "react-native";

export type BannerVariant = "info" | "loading" | "error";

/** How long a dismissible banner stays before it starts fading out. */
const AUTO_DISMISS_MS = 3000;
/** Duration of the fade-out itself (gradual, not instant). */
const FADE_OUT_MS = 700;

interface Props {
  variant: BannerVariant;
  text: string;
  /** When set (error variant), shows a "Tekrar dene" button. */
  onRetry?: () => void;
  /**
   * When true, the banner fades out and hides itself ~3s after appearing.
   * Used for the transient location-fallback notice; errors/loading stay put.
   */
  autoDismiss?: boolean;
}

/**
 * Floating status banner (item 7): loading gets a spinner, errors get a red
 * tint and an optional retry action, info stays neutral. Never blocks the map —
 * only the retry button is tappable.
 *
 * With `autoDismiss`, the banner disappears on its own after a few seconds via
 * a gentle fade instead of lingering forever.
 */
export function StatusBanner({ variant, text, onRetry, autoDismiss }: Props) {
  const opacity = useRef(new Animated.Value(1)).current;
  const [hidden, setHidden] = useState(false);

  useEffect(() => {
    // Reset visibility whenever the banner's content changes, so switching
    // (e.g. a faded info notice → a new error) shows the new one fully.
    opacity.setValue(1);
    setHidden(false);

    if (!autoDismiss) return;

    const timer = setTimeout(() => {
      Animated.timing(opacity, {
        toValue: 0,
        duration: FADE_OUT_MS,
        useNativeDriver: true,
      }).start(({ finished }) => {
        if (finished) setHidden(true);
      });
    }, AUTO_DISMISS_MS);

    return () => clearTimeout(timer);
  }, [autoDismiss, text, variant, opacity]);

  if (hidden) return null;

  return (
    <Animated.View
      style={[
        styles.banner,
        variant === "error" && styles.bannerError,
        { opacity },
      ]}
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
    </Animated.View>
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
