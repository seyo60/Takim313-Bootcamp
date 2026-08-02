import { createContext, useCallback, useContext, useMemo, useState, type PropsWithChildren } from "react";
import type { RouteOption } from "@/lib/mockRoute";
import type { LngLat, RouteProfile } from "@/lib/types";

export interface NavigationSession { option: RouteOption; destination: LngLat; profile: RouteProfile; startedAt: string; }
interface NavigationContextValue { session: NavigationSession | null; start: (option: RouteOption, destination: LngLat, profile: RouteProfile) => void; replace: (option: RouteOption) => void; stop: () => void; }
const NavigationContext = createContext<NavigationContextValue | null>(null);

export function NavigationProvider({ children }: PropsWithChildren) {
  const [session, setSession] = useState<NavigationSession | null>(null);
  const start = useCallback((option: RouteOption, destination: LngLat, profile: RouteProfile) => setSession({ option, destination, profile, startedAt: new Date().toISOString() }), []);
  const replace = useCallback((option: RouteOption) => setSession((current) => current ? { ...current, option } : current), []);
  const stop = useCallback(() => setSession(null), []);
  const value = useMemo(() => ({ session, start, replace, stop }), [replace, session, start, stop]);
  return <NavigationContext.Provider value={value}>{children}</NavigationContext.Provider>;
}

export function useNavigationSession() {
  const value = useContext(NavigationContext);
  if (!value) throw new Error("NavigationProvider eksik.");
  return value;
}
