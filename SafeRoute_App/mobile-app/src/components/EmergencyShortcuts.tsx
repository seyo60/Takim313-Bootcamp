import { Alert, Linking, Pressable, StyleSheet, Text, View } from "react-native";
import {
  directionsUrl,
  findNearestPlace,
  type EmergencyPlaceKind,
  type NearestPlace,
} from "@/lib/emergencyPlaces";
import { formatDistance } from "@/lib/nearbyAlerts";
import type { LngLat } from "@/lib/types";

interface Props {
  /** Where the user is — the report's coordinates. */
  location: LngLat;
}

const KINDS: { kind: EmergencyPlaceKind; icon: string; label: string }[] = [
  { kind: "police", icon: "🚔", label: "En yakın polis merkezi" },
  { kind: "hospital", icon: "🏥", label: "En yakın hastane" },
];

/**
 * Post-report emergency shortcuts (Backlog #10): after an URGENT report is
 * acknowledged, offer one-tap walking directions to the nearest police station
 * and hospital.
 *
 * Directions open in the device's maps app rather than being drawn in SafeRoute
 * — the maps app has live POI data, turn-by-turn voice guidance and works
 * offline-ish, none of which this app has. In an emergency the goal is to get
 * the user moving, not to keep them in our UI.
 */
export function EmergencyShortcuts({ location }: Props) {
  const open = async (place: NearestPlace) => {
    const url = directionsUrl(place);
    try {
      await Linking.openURL(url);
    } catch {
      // No handler for the URL (very unlikely, since it's an https link).
      Alert.alert(
        "Harita açılamadı",
        `${place.name}\n${place.address}\n\nAdresi harita uygulamanıza elle girebilirsin.`
      );
    }
  };

  return (
    <View style={styles.wrapper}>
      <Text style={styles.heading}>Yardıma mı ihtiyacın var?</Text>

      {KINDS.map(({ kind, icon, label }) => {
        const place = findNearestPlace(kind, location);
        if (!place) return null;

        return (
          <Pressable
            key={kind}
            onPress={() => open(place)}
            accessibilityRole="button"
            accessibilityLabel={`${label}: ${place.name}, ${formatDistance(
              place.distance_m
            )}. Yol tarifi için dokunun.`}
            style={({ pressed }) => [styles.card, pressed && styles.cardPressed]}
          >
            <Text style={styles.icon}>{icon}</Text>

            <View style={styles.textColumn}>
              <Text style={styles.label}>{label}</Text>
              <Text style={styles.name} numberOfLines={1}>
                {place.name}
              </Text>
              <Text style={styles.meta} numberOfLines={1}>
                {formatDistance(place.distance_m)} · {place.address}
              </Text>
            </View>

            <Text style={styles.chevron}>›</Text>
          </Pressable>
        );
      })}

      {/* The list is a small hand-entered demo set (see lib/emergencyPlaces.ts).
          Say so rather than letting it look authoritative in an emergency. */}
      <Text style={styles.disclaimer}>
        Konumlar demo verisidir; acil durumda 112&apos;yi arayın.
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: {
    marginTop: 24,
    width: "100%",
    gap: 8,
  },
  heading: {
    fontSize: 13,
    fontWeight: "600",
    color: "#666",
    marginBottom: 2,
  },
  card: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    backgroundColor: "#fff",
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "#e4e4e4",
    paddingVertical: 11,
    paddingHorizontal: 12,
  },
  cardPressed: {
    backgroundColor: "#f4f6f8",
  },
  icon: {
    fontSize: 22,
  },
  textColumn: {
    flex: 1,
  },
  label: {
    fontSize: 11,
    color: "#888",
  },
  name: {
    fontSize: 14,
    fontWeight: "600",
    color: "#111",
    marginTop: 1,
  },
  meta: {
    fontSize: 12,
    color: "#777",
    marginTop: 1,
  },
  chevron: {
    fontSize: 22,
    color: "#bbb",
  },
  disclaimer: {
    marginTop: 2,
    fontSize: 11,
    lineHeight: 15,
    color: "#999",
    textAlign: "center",
  },
});
