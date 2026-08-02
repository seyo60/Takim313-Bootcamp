import type { PropsWithChildren, ReactNode } from "react";
import {
  ActivityIndicator,
  Pressable,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  type TextInputProps,
  View,
} from "react-native";
import { colors, radius, spacing } from "@/theme/tokens";

export function Screen({ children, top = false }: PropsWithChildren<{ top?: boolean }>) {
  return (
    <SafeAreaView style={styles.safe}>
      <ScrollView contentContainerStyle={[styles.screen, top && styles.screenTop]} keyboardShouldPersistTaps="handled">
        {children}
      </ScrollView>
    </SafeAreaView>
  );
}

export function Title({ children }: PropsWithChildren) {
  return <Text accessibilityRole="header" style={styles.title}>{children}</Text>;
}

export function Body({ children }: PropsWithChildren) {
  return <Text style={styles.body}>{children}</Text>;
}

export function Field(props: TextInputProps) {
  return <TextInput {...props} style={[styles.field, props.style]} placeholderTextColor="#758391" selectionColor={colors.primary} />;
}

export function Button({
  children,
  onPress,
  disabled,
  busy,
  variant = "primary",
  accessibilityLabel,
}: {
  children: ReactNode;
  onPress: () => void;
  disabled?: boolean;
  busy?: boolean;
  variant?: "primary" | "secondary" | "danger" | "ghost";
  accessibilityLabel?: string;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel}
      disabled={disabled || busy}
      onPress={onPress}
      style={({ pressed }) => [
        styles.button,
        styles[`button_${variant}`],
        (disabled || busy) && styles.disabled,
        pressed && styles.pressed,
      ]}
    >
      {busy ? <ActivityIndicator color={variant === "ghost" ? colors.primary : "#fff"} /> : (
        <Text style={[styles.buttonText, variant === "ghost" && styles.ghostText]}>{children}</Text>
      )}
    </Pressable>
  );
}

export function Notice({ children, error = false }: PropsWithChildren<{ error?: boolean }>) {
  return <View style={[styles.notice, error && styles.noticeError]}><Text style={styles.noticeText}>{children}</Text></View>;
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  screen: { flexGrow: 1, padding: spacing.lg, gap: spacing.md, justifyContent: "center" },
  screenTop: { justifyContent: "flex-start", paddingTop: spacing.sm },
  title: { color: colors.text, fontSize: 30, lineHeight: 36, fontWeight: "900", letterSpacing: -0.7 },
  body: { color: colors.textMuted, fontSize: 16, lineHeight: 24 },
  field: { minHeight: 56, borderWidth: 1, borderColor: colors.borderSoft, borderRadius: radius.sm, backgroundColor: colors.surface, paddingHorizontal: 16, color: colors.text, fontSize: 16 },
  button: { minHeight: 52, borderRadius: radius.pill, alignItems: "center", justifyContent: "center", paddingHorizontal: spacing.md },
  button_primary: { backgroundColor: colors.primary },
  button_secondary: { backgroundColor: colors.secondary },
  button_danger: { backgroundColor: colors.error },
  button_ghost: { backgroundColor: "transparent", borderWidth: 1.5, borderColor: colors.primary },
  buttonText: { color: "#fff", fontSize: 16, fontWeight: "700", textAlign: "center" },
  ghostText: { color: colors.primary },
  disabled: { opacity: 0.48 },
  pressed: { opacity: 0.82 },
  notice: { backgroundColor: colors.surfaceContainer, borderRadius: radius.sm, padding: spacing.md },
  noticeError: { borderWidth: 1, borderColor: colors.error },
  noticeText: { color: colors.text, fontSize: 14, lineHeight: 20 },
});
