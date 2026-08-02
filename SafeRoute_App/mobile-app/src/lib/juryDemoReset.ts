import { appStorage } from "@/lib/secureStorage";

export const DISMISSED_EVENTS_KEY = "saferoute.dismissed-events.v1";
export const NOTIFIED_EVENTS_KEY = "saferoute.notified-events.v1";
export const JURY_DEMO_RESET_KEY = "saferoute.jury-demo-reset.v1";

/** Her simülasyon basışında istemci bildirim durumunu sıfırlar. */
export async function resetJuryDemoClientState(): Promise<void> {
  await appStorage.set(DISMISSED_EVENTS_KEY, "[]");
  await appStorage.set(NOTIFIED_EVENTS_KEY, "[]");
  await appStorage.set(JURY_DEMO_RESET_KEY, String(Date.now()));
}
