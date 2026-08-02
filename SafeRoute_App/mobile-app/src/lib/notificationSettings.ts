import { appStorage } from "./secureStorage";

const KEY = "saferoute.notifications.enabled.v1";

/** Varsayılan: açık */
export async function getNotificationsEnabled(): Promise<boolean> {
  try {
    const raw = await appStorage.get(KEY);
    if (raw == null) return true;
    return raw !== "0" && raw !== "false";
  } catch {
    return true;
  }
}

export async function setNotificationsEnabled(enabled: boolean): Promise<void> {
  await appStorage.set(KEY, enabled ? "1" : "0");
}
