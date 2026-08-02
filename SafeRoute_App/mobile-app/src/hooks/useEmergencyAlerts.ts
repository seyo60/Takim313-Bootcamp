import { useCallback, useEffect, useRef, useState } from "react";
import * as Location from "expo-location";
import * as Notifications from "expo-notifications";
import { AppState } from "react-native";
import { useAuth } from "@/hooks/useAuth";
import {
  getPendingAlerts,
  registerDevice,
  respondToAlert,
  updateMyLocation,
  type PendingAlert,
} from "@/lib/api";
import { presentLocalNotification } from "@/lib/localNotifications";
import { getNotificationsEnabled } from "@/lib/notificationSettings";
import { getExpoPushTokenAsync } from "@/lib/pushNotifications";
import { appStorage } from "@/lib/secureStorage";
import {
  DISMISSED_EVENTS_KEY,
  JURY_DEMO_RESET_KEY,
  NOTIFIED_EVENTS_KEY,
} from "@/lib/juryDemoReset";

const DISMISSED_KEY = DISMISSED_EVENTS_KEY;
const NOTIFIED_KEY = NOTIFIED_EVENTS_KEY;
const SUPPRESS_MS = 120_000;
const POLL_MS = 60_000;

function eventKey(item: PendingAlert): string {
  return item.event_id || item.alert_id;
}

async function loadIdList(key: string): Promise<string[]> {
  try {
    const raw = await appStorage.get(key);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    return Array.isArray(parsed)
      ? parsed.filter((item): item is string => typeof item === "string")
      : [];
  } catch {
    return [];
  }
}

async function saveIdList(key: string, ids: string[]): Promise<void> {
  await appStorage.set(key, JSON.stringify(ids.slice(-200)));
}

/** Aynı olay için tek kayıt; broadcast varsa onu tercih et. */
function dedupeAlerts(alerts: PendingAlert[]): PendingAlert[] {
  const byKey = new Map<string, PendingAlert>();
  for (const item of alerts) {
    const key = eventKey(item);
    const prev = byKey.get(key);
    if (!prev) {
      byKey.set(key, item);
      continue;
    }
    if (item.phase === "broadcast" && prev.phase !== "broadcast") {
      byKey.set(key, item);
    }
  }
  return Array.from(byKey.values());
}

/**
 * Giriş yapılınca push token + konum kaydı; yakındaki tanık/yayın bildirimlerini çeker.
 */
export function useEmergencyAlerts() {
  const { user } = useAuth();
  const [pending, setPending] = useState<PendingAlert[]>([]);
  const [active, setActive] = useState<PendingAlert | null>(null);
  const [busy, setBusy] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const suppressUntilRef = useRef(0);
  const dismissedRef = useRef<string[]>([]);
  const notifiedRef = useRef<string[]>([]);
  const refreshInFlightRef = useRef(false);
  const hydratedRef = useRef(false);

  useEffect(() => {
    let cancelled = false;
    Promise.all([loadIdList(DISMISSED_KEY), loadIdList(NOTIFIED_KEY)]).then(
      ([dismissed, notified]) => {
        if (cancelled) return;
        dismissedRef.current = dismissed;
        notifiedRef.current = notified;
        hydratedRef.current = true;
      }
    );
    return () => {
      cancelled = true;
    };
  }, []);

  const rememberDismissedEvent = useCallback((item: PendingAlert) => {
    const key = eventKey(item);
    if (dismissedRef.current.includes(key)) return;
    const next = [...dismissedRef.current, key];
    dismissedRef.current = next;
    void saveIdList(DISMISSED_KEY, next);
  }, []);

  const markNotifiedEvent = useCallback((item: PendingAlert) => {
    const key = eventKey(item);
    if (notifiedRef.current.includes(key)) return;
    const next = [...notifiedRef.current, key];
    notifiedRef.current = next;
    void saveIdList(NOTIFIED_KEY, next);
  }, []);

  const refresh = useCallback(async () => {
    if (!user) {
      setPending([]);
      setActive(null);
      return;
    }
    if (refreshInFlightRef.current) return;
    refreshInFlightRef.current = true;
    try {
      // Jüri demosu her basışta istemci engellerini temizler.
      const juryReset = await appStorage.get(JURY_DEMO_RESET_KEY);
      if (juryReset) {
        dismissedRef.current = [];
        notifiedRef.current = [];
        suppressUntilRef.current = 0;
        setStatusMessage(null);
        await appStorage.remove(JURY_DEMO_RESET_KEY);
      } else {
        dismissedRef.current = await loadIdList(DISMISSED_KEY);
        notifiedRef.current = await loadIdList(NOTIFIED_KEY);
      }

      let lat: number | undefined;
      let lng: number | undefined;
      try {
        const pos = await Location.getCurrentPositionAsync({
          accuracy: Location.Accuracy.Balanced,
        });
        lat = pos.coords.latitude;
        lng = pos.coords.longitude;
        await updateMyLocation(lat, lng);
      } catch {
        // Konum yoksa sunucu son kayıtlı konumu kullanır.
      }

      const dismissed = new Set(dismissedRef.current);
      const alerts = dedupeAlerts(await getPendingAlerts(lat, lng)).filter(
        (item) => !dismissed.has(eventKey(item))
      );

      // Olay bazlı tek bildirim (witness → broadcast geçişinde ikinci yağmur olmasın).
      if (hydratedRef.current && (await getNotificationsEnabled())) {
        const already = new Set(notifiedRef.current);
        const nextFresh = alerts.find((item) => !already.has(eventKey(item)));
        if (nextFresh) {
          markNotifiedEvent(nextFresh);
          if (AppState.currentState !== "active") {
            const isBroadcast = nextFresh.phase === "broadcast";
            await presentLocalNotification({
              title: nextFresh.title,
              body: nextFresh.body,
              data: {
                type: isBroadcast ? "emergency_broadcast" : "witness_request",
                event_id: nextFresh.event_id,
                alert_id: nextFresh.alert_id,
                source: "local",
              },
            });
          }
        }
      }

      setPending(alerts);
      setActive((current) => {
        if (
          current &&
          alerts.some((item) => eventKey(item) === eventKey(current))
        ) {
          // Aynı olayda witness → broadcast yükseltmesi: aktif kaydı güncelle.
          const upgraded = alerts.find(
            (item) => eventKey(item) === eventKey(current)
          );
          return upgraded ?? current;
        }
        if (Date.now() < suppressUntilRef.current) {
          return null;
        }
        return alerts[0] ?? null;
      });
    } finally {
      refreshInFlightRef.current = false;
    }
  }, [user, markNotifiedEvent]);

  useEffect(() => {
    if (!user) return;
    let cancelled = false;

    (async () => {
      const token =
        (await getExpoPushTokenAsync()) ??
        `ExponentPushToken[local-fallback-${user.id.slice(0, 8)}]`;
      if (cancelled) return;
      let lat: number | undefined;
      let lng: number | undefined;
      try {
        const { status } = await Location.getForegroundPermissionsAsync();
        if (status === "granted") {
          const pos = await Location.getCurrentPositionAsync({
            accuracy: Location.Accuracy.Balanced,
          });
          lat = pos.coords.latitude;
          lng = pos.coords.longitude;
        }
      } catch {
        /* ignore */
      }
      await registerDevice({ expo_push_token: token, lat, lng });
      if (!cancelled) await refresh();
    })();

    const response = Notifications.addNotificationResponseReceivedListener((event) => {
      const data = event.notification.request.content.data as {
        type?: string;
        event_id?: string;
      };
      if (
        (data?.type === "witness_request" || data?.type === "emergency_broadcast") &&
        data.event_id
      ) {
        suppressUntilRef.current = 0;
        void refresh();
      }
    });

    const interval = setInterval(() => {
      void refresh();
    }, POLL_MS);

    return () => {
      cancelled = true;
      response.remove();
      clearInterval(interval);
    };
  }, [user, refresh]);

  const respond = useCallback(
    async (choice: "confirm" | "deny" | "unsure") => {
      if (!active?.event_id || busy) return;
      if (active.phase === "broadcast") return;
      setBusy(true);
      setStatusMessage(null);
      const result = await respondToAlert(active.event_id, choice);
      setBusy(false);
      if (!result) {
        setStatusMessage("Yanıt gönderilemedi. Tekrar deneyin.");
        return;
      }

      // Onay + yayın: bekleyen listesine bağımlı kalmadan doğrulanmış modalı aç.
      if (choice === "confirm" && result.broadcast_sent) {
        suppressUntilRef.current = 0;
        setStatusMessage(null);
        setBusy(true);
        try {
          let lat: number | undefined;
          let lng: number | undefined;
          try {
            const pos = await Location.getCurrentPositionAsync({
              accuracy: Location.Accuracy.Balanced,
            });
            lat = pos.coords.latitude;
            lng = pos.coords.longitude;
          } catch {
            /* sunucu son konum */
          }
          const alerts = dedupeAlerts(await getPendingAlerts(lat, lng));
          const fromServer =
            alerts.find(
              (item) =>
                item.event_id === active.event_id && item.phase === "broadcast"
            ) ?? alerts.find((item) => item.phase === "broadcast");

          const broadcast: PendingAlert = fromServer ?? {
            alert_id: result.broadcast_alert_id || active.alert_id,
            event_id: active.event_id,
            phase: "broadcast",
            title: "Magnificent Mile: doğrulanmış ihbar",
            body:
              '"Bir kadının çantası çalındı" ihbarı doğrulandı. Magnificent Mile civarında dikkatli olun.',
            latitude: active.latitude,
            longitude: active.longitude,
            distance_m: active.distance_m,
            confirm_count: Math.max(1, (active.confirm_count || 0) + 1),
          };

          if (await getNotificationsEnabled()) {
            await presentLocalNotification({
              title: broadcast.title,
              body: broadcast.body,
              data: {
                type: "emergency_broadcast",
                event_id: broadcast.event_id,
                alert_id: broadcast.alert_id,
                force_foreground: true,
              },
              forceWhenActive: true,
            });
          }

          markNotifiedEvent(broadcast);
          setPending(
            fromServer
              ? alerts
              : dedupeAlerts([broadcast, ...alerts])
          );
          // Modalın kapanıp açılması için kısa sıfırlama.
          setActive(null);
          setTimeout(() => setActive(broadcast), 50);
        } finally {
          setBusy(false);
        }
        return;
      }

      rememberDismissedEvent(active);
      markNotifiedEvent(active);
      suppressUntilRef.current = Date.now() + SUPPRESS_MS;
      const fallback =
        choice === "confirm"
          ? "Teşekkürler. Onayın kaydedildi."
          : choice === "unsure"
            ? "Yanıtın kaydedildi (emin değilim)."
            : "Yanıtın kaydedildi.";
      setStatusMessage(result.message ?? fallback);
      setActive(null);
    },
    [active, busy, rememberDismissedEvent, markNotifiedEvent, refresh]
  );

  const dismiss = useCallback(() => {
    if (active) {
      rememberDismissedEvent(active);
      markNotifiedEvent(active);
    }
    suppressUntilRef.current = Date.now() + SUPPRESS_MS;
    setActive(null);
    setStatusMessage(null);
  }, [active, rememberDismissedEvent, markNotifiedEvent]);

  return {
    pendingCount: pending.length,
    active,
    busy,
    statusMessage,
    respond,
    dismiss,
    refresh,
  };
}
