import { Pressable, StyleSheet, Text, View } from "react-native";
import type { RouteProfile } from "@/lib/types";

interface Props {
  value: RouteProfile;
  onChange: (profile: RouteProfile) => void;
  disabled?: boolean;
}

const PROFILES: {
  value: RouteProfile;
  label: string;
  description: string;
}[] = [
  {
    value: "shortest",
    label: "En Kısa",
    description: "Minimum yürüme mesafesi",
  },
  {
    value: "balanced",
    label: "Dengeli",
    description: "En fazla %20 ek mesafe",
  },
  {
    value: "safer",
    label: "Daha Güvenli",
    description: "En fazla %40 ek mesafe",
  },
];

export function RouteProfileSelector({
  value,
  onChange,
  disabled = false,
}: Props) {
  const selected = PROFILES.find((profile) => profile.value === value);

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Rota tercihi</Text>
      <View
        style={styles.segments}
        accessibilityRole="radiogroup"
        accessibilityLabel="Rota tercihi"
      >
        {PROFILES.map((profile) => {
          const active = profile.value === value;
          return (
            <Pressable
              key={profile.value}
              accessibilityRole="radio"
              accessibilityState={{ checked: active, disabled }}
              accessibilityLabel={profile.label}
              accessibilityHint={profile.description}
              disabled={disabled}
              onPress={() => onChange(profile.value)}
              style={({ pressed }) => [
                styles.segment,
                active && styles.segmentActive,
                pressed && !disabled && styles.segmentPressed,
                disabled && styles.segmentDisabled,
              ]}
            >
              <Text
                numberOfLines={1}
                style={[
                  styles.segmentText,
                  active && styles.segmentTextActive,
                ]}
              >
                {profile.label}
              </Text>
            </Pressable>
          );
        })}
      </View>
      <Text style={styles.description}>{selected?.description}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    marginBottom: 12,
  },
  title: {
    marginBottom: 6,
    color: "#344054",
    fontSize: 12,
    fontWeight: "600",
  },
  segments: {
    flexDirection: "row",
    padding: 3,
    borderRadius: 10,
    backgroundColor: "#EEF2F6",
  },
  segment: {
    flex: 1,
    minHeight: 36,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 5,
    borderRadius: 8,
  },
  segmentActive: {
    backgroundColor: "#1D6FEB",
    shadowColor: "#0B3A7E",
    shadowOpacity: 0.18,
    shadowRadius: 3,
    shadowOffset: { width: 0, height: 1 },
    elevation: 2,
  },
  segmentPressed: {
    opacity: 0.8,
  },
  segmentDisabled: {
    opacity: 0.65,
  },
  segmentText: {
    color: "#52606D",
    fontSize: 11,
    fontWeight: "600",
  },
  segmentTextActive: {
    color: "#FFFFFF",
  },
  description: {
    marginTop: 5,
    color: "#667085",
    fontSize: 11,
  },
});
