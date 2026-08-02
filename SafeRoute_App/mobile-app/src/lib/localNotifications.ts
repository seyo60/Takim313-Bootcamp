import { AppState, Platform } from "react-native";
import * as Notifications from "expo-notifications";
import { getNotificationsEnabled } from "./notificationSettings";

let channelReady = false;

async function ensureChannel(): Promise<void> {
  if (channelReady || Platform.OS !== "android") return;
  await Notifications.setNotificationChannelAsync("emergency", {
    name: "Acil durum uyarıları",
    importance: Notifications.AndroidImportance.MAX,
    vibrationPattern: [0, 250, 250, 250],
    lightColor: "#D95858",
  });
  channelReady = true;
}

/**
 * Sistem bildirim çubuğuna en fazla bir yerel bildirim düşürür.
 * Uygulama öndeyken varsayılan sessizdir; jüri demosu için forceWhenActive kullan.
 */
export async function presentLocalNotification(params: {
  title: string;
  body: string;
  data?: Record<string, unknown>;
  /** true ise uygulama açıkken de bildirim çubuğuna düşer (jüri videosu). */
  forceWhenActive?: boolean;
}): Promise<void> {
  const enabled = await getNotificationsEnabled();
  if (!enabled) return;

  // Ön planda banner yağmurunu engelle (zorunlu değilse).
  if (AppState.currentState === "active" && !params.forceWhenActive) return;

  const { status: existing } = await Notifications.getPermissionsAsync();
  let status = existing;
  if (existing !== "granted") {
    const requested = await Notifications.requestPermissionsAsync();
    status = requested.status;
  }
  if (status !== "granted") return;

  await ensureChannel();

  // Aynı anda birden fazla bekleyen yerel bildirimi temizle.
  await Notifications.dismissAllNotificationsAsync().catch(() => undefined);
  await Notifications.cancelAllScheduledNotificationsAsync().catch(() => undefined);

  await Notifications.scheduleNotificationAsync({
    content: {
      title: params.title,
      body: params.body,
      data: {
        ...(params.data ?? {}),
        source: "local",
        ...(params.forceWhenActive ? { force_foreground: true } : {}),
      },
      sound: true,
      ...(Platform.OS === "android" ? { channelId: "emergency" } : {}),
    },
    trigger: null,
  });
}
