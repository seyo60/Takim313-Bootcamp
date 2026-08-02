import { DefaultTheme, Stack, ThemeProvider, usePathname, useRouter } from "expo-router";
import * as SplashScreen from "expo-splash-screen";
import { useEffect, useState, type PropsWithChildren } from "react";
import { StyleSheet, Text, View } from "react-native";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { AuthProvider } from "@/providers/AuthProvider";
import { NavigationProvider } from "@/providers/NavigationProvider";
import { appStorage } from "@/lib/secureStorage";
import { colors } from "@/theme/tokens";
import { ShieldMark } from "@/components/brand";

void SplashScreen.preventAutoHideAsync();

function LaunchGate({ children }: PropsWithChildren) {
  const [ready, setReady] = useState(false);
  const pathname = usePathname();
  const router = useRouter();
  useEffect(() => {
    let active = true;
    appStorage.get("saferoute.onboarding.v1").then((value) => {
      if (!active) return;
      if (value !== "complete" && pathname !== "/onboarding") router.replace("/onboarding");
      setReady(true);
      void SplashScreen.hideAsync();
    });
    return () => { active = false; };
  }, [pathname, router]);
  if (!ready) return <View style={styles.loading}><ShieldMark size={82} /><Text style={styles.loadingTitle}>SafeRoute</Text><Text style={styles.loadingSubtitle}>Daha fazla bağlamla yürü</Text><View style={styles.loadingDots}><View style={styles.loadingDot} /><View style={styles.loadingDot} /><View style={[styles.loadingDot, styles.loadingDotActive]} /></View></View>;
  return children;
}

export default function RootLayout() {
  return (
    <GestureHandlerRootView style={styles.root}>
      <ThemeProvider value={DefaultTheme}>
        <AuthProvider>
          <NavigationProvider>
            <LaunchGate>
              <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.background } }}>
                <Stack.Screen name="index" />
                <Stack.Screen name="onboarding" />
                <Stack.Screen name="auth" />
                <Stack.Screen name="profile" />
                <Stack.Screen name="my-reports" />
                <Stack.Screen name="report" options={{ presentation: "modal" }} />
                <Stack.Screen name="navigation" />
              </Stack>
            </LaunchGate>
          </NavigationProvider>
        </AuthProvider>
      </ThemeProvider>
    </GestureHandlerRootView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  loading: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: "#DDEBFA" },
  loadingTitle: { color: colors.primary, fontSize: 25, fontWeight: "900", marginTop: 18 },
  loadingSubtitle: { color: colors.textMuted, fontSize: 13, marginTop: 5 },
  loadingDots: { position: "absolute", bottom: 45, flexDirection: "row", gap: 7 },
  loadingDot: { width: 5, height: 5, borderRadius: 3, backgroundColor: "#91A6BA" },
  loadingDotActive: { backgroundColor: colors.primary },
});
