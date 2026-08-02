import { AppState, Platform } from "react-native";
import * as Device from "expo-device";
import * as Notifications from "expo-notifications";
import Constants from "expo-constants";

Notifications.setNotificationHandler({
  handleNotification: async (notification) => {
    const data = notification.request.content.data as {
      force_foreground?: boolean | string;
    };
    const forceForeground =
      data?.force_foreground === true || data?.force_foreground === "true";
    const foreground = AppState.currentState === "active";

    // Uygulama açıkken ekranda yalnızca in-app modal; çift banner olmasın.
    // force_foreground: bildirimi yine SafeRoute olarak bildirim listesine yaz.
    if (foreground && forceForeground) {
      return {
        shouldShowAlert: false,
        shouldPlaySound: true,
        shouldSetBadge: false,
        shouldShowBanner: false,
        shouldShowList: true,
      };
    }

    if (foreground) {
      return {
        shouldShowAlert: false,
        shouldPlaySound: false,
        shouldSetBadge: false,
        shouldShowBanner: false,
        shouldShowList: false,
      };
    }

    return {
      shouldShowAlert: true,
      shouldPlaySound: true,
      shouldSetBadge: false,
      shouldShowBanner: true,
      shouldShowList: true,
    };
  },
});

/**
 * Expo push token alır. Emülatörde / izinsiz durumda null döner.
 */
export async function getExpoPushTokenAsync(): Promise<string | null> {
  if (!Device.isDevice && Platform.OS === "ios") {
    // iOS simülatör push desteklemez; Android emülatör bazen çalışır.
    console.warn("[push] Fiziksel cihaz önerilir (iOS simülatör desteklenmez).");
  }

  const { status: existing } = await Notifications.getPermissionsAsync();
  let finalStatus = existing;
  if (existing !== "granted") {
    const requested = await Notifications.requestPermissionsAsync();
    finalStatus = requested.status;
  }
  if (finalStatus !== "granted") {
    return null;
  }

  if (Platform.OS === "android") {
    await Notifications.setNotificationChannelAsync("emergency", {
      name: "Acil durum uyarıları",
      importance: Notifications.AndroidImportance.MAX,
      vibrationPattern: [0, 250, 250, 250],
      lightColor: "#D95858",
    });
  }

  const projectId =
    Constants.easConfig?.projectId ??
    Constants.expoConfig?.extra?.eas?.projectId;
  if (!projectId) {
    console.warn("[push] EAS projectId bulunamadı — yerel test token kullanılacak.");
    return `ExponentPushToken[local-dev-${Platform.OS}]`;
  }

  try {
    const token = await Notifications.getExpoPushTokenAsync({ projectId });
    return token.data ?? null;
  } catch (error) {
    // Emülatör / FCM yoksa push alınamaz; konum + in-app modal için yerel token.
    console.warn("[push] Expo token alınamadı, yerel test token:", error);
    return `ExponentPushToken[local-dev-${Platform.OS}]`;
  }
}
