import { useEffect, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  Keyboard,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { searchPlaces, type GeocodingResult } from "@/lib/geocoding";
import type { LngLat } from "@/lib/types";

interface Props {
  /** Bias search results toward this point (user location / map center). */
  proximity?: LngLat;
  /** Called when the user picks a search result as the destination. */
  onSelect: (result: GeocodingResult) => void;
}

const DEBOUNCE_MS = 350;

/**
 * Floating search bar for choosing a destination. Debounces keystrokes,
 * queries Mapbox Geocoding, and shows a tappable result list.
 *
 * Visuals are intentionally plain — proper styling lands with the Figma
 * designs (end-to-end.md, item 9).
 */
export function DestinationSearchBar({ proximity, onSelect }: Props) {
  const [query, setQuery] = useState("");
  // The hits we have, tagged with the query they answer. Everything the UI
  // needs — results, "searching…", "searched but empty" — is derived from
  // comparing this tag against the current query, so the effect no longer has
  // to reset three pieces of state on every keystroke that shortens the input.
  const [fetched, setFetched] = useState<{
    query: string;
    hits: GeocodingResult[];
  } | null>(null);

  const trimmed = query.trim();
  const active = trimmed.length >= 2;

  useEffect(() => {
    if (!active) return;

    // The cleanup below clears this on every keystroke, which is the debounce:
    // the request only fires once typing pauses for DEBOUNCE_MS.
    const timer = setTimeout(async () => {
      const hits = await searchPlaces(trimmed, proximity);
      setFetched({ query: trimmed, hits });
    }, DEBOUNCE_MS);

    return () => clearTimeout(timer);
    // proximity is a fresh array each render; track its values instead.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, trimmed, proximity?.[0], proximity?.[1]]);

  const current = active && fetched?.query === trimmed ? fetched : null;
  const results = current?.hits ?? [];
  const searching = active && current === null;
  // Distinguishes "haven't searched yet" from "searched, zero hits".
  const searched = current !== null;

  const handleSelect = (result: GeocodingResult) => {
    // Clearing the query is enough: `active` goes false, so the result list and
    // the "searched" flag collapse on their own.
    setQuery("");
    Keyboard.dismiss();
    onSelect(result);
  };

  return (
    <View style={styles.wrapper}>
      <View style={styles.inputRow}>
        <TextInput
          style={styles.input}
          value={query}
          onChangeText={setQuery}
          placeholder="Nereye gitmek istiyorsun?"
          placeholderTextColor="#8a8a8a"
          autoCorrect={false}
          returnKeyType="search"
        />
        {searching ? <ActivityIndicator size="small" color="#1D6FEB" /> : null}
      </View>

      {results.length > 0 ? (
        <FlatList
          style={styles.results}
          data={results}
          keyboardShouldPersistTaps="handled"
          keyExtractor={(item, index) =>
            `${item.coordinate[0]},${item.coordinate[1]},${index}`
          }
          renderItem={({ item }) => (
            <Pressable
              style={({ pressed }) => [
                styles.resultRow,
                pressed && styles.resultRowPressed,
              ]}
              onPress={() => handleSelect(item)}
            >
              <Text style={styles.resultName} numberOfLines={1}>
                {item.name}
              </Text>
              {item.address ? (
                <Text style={styles.resultAddress} numberOfLines={1}>
                  {item.address}
                </Text>
              ) : null}
            </Pressable>
          )}
        />
      ) : searched && !searching ? (
        <View style={styles.results}>
          <Text style={styles.noResult}>Sonuç bulunamadı.</Text>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: {
    position: "absolute",
    top: 60,
    left: 16,
    right: 16,
  },
  inputRow: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "#fff",
    borderRadius: 12,
    paddingHorizontal: 14,
    height: 48,
    // Soft shadow so the bar reads as floating above the map.
    shadowColor: "#000",
    shadowOpacity: 0.15,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 2 },
    elevation: 4,
  },
  input: {
    flex: 1,
    fontSize: 15,
    color: "#111",
  },
  results: {
    marginTop: 6,
    backgroundColor: "#fff",
    borderRadius: 12,
    maxHeight: 240,
    shadowColor: "#000",
    shadowOpacity: 0.15,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 2 },
    elevation: 4,
  },
  resultRow: {
    paddingVertical: 10,
    paddingHorizontal: 14,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: "#e5e5e5",
  },
  resultRowPressed: {
    backgroundColor: "#f2f6ff",
  },
  resultName: {
    fontSize: 15,
    color: "#111",
  },
  resultAddress: {
    fontSize: 12,
    color: "#777",
    marginTop: 2,
  },
  noResult: {
    padding: 14,
    fontSize: 13,
    color: "#777",
    textAlign: "center",
  },
});
