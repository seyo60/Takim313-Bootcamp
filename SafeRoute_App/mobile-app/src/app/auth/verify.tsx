import { useEffect } from "react";
import { router, useLocalSearchParams } from "expo-router";

/** E-posta doğrulama devre dışı — eski bağlantılar giriş ekranına yönlendirilir. */
export default function VerifyEmail() {
  const params = useLocalSearchParams<{ returnTo?: string; lng?: string; lat?: string; approximate?: string }>();
  useEffect(() => {
    router.replace({ pathname: "/auth/sign-in", params });
  }, [params]);
  return null;
}
