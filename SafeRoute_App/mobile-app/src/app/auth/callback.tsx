import { useEffect, useState } from "react";
import { router, useLocalSearchParams } from "expo-router";
import { Body, Button, Field, Notice, Screen, Title } from "@/components/ui";
import { requireSupabase } from "@/lib/supabase";

export default function AuthCallback() {
  const params = useLocalSearchParams<{ code?: string; recovery?: string; returnTo?: string; lng?: string; lat?: string; approximate?: string }>();
  const [status, setStatus] = useState("Bağlantı doğrulanıyor…");
  const [password, setPassword] = useState("");
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!params.code) {
      setStatus("Geçersiz veya süresi dolmuş bağlantı.");
      return;
    }
    requireSupabase().auth.exchangeCodeForSession(params.code).then(({ error }) => {
      if (error) setStatus("Bağlantı doğrulanamadı. Yeni bir bağlantı iste.");
      else if (params.recovery === "1") { setStatus("Yeni parolanı belirle."); setReady(true); }
      else if (params.returnTo === "report") router.replace({ pathname: "/report", params: { lng: params.lng, lat: params.lat, approximate: params.approximate } });
      else router.replace("/profile");
    });
  }, [params.approximate, params.code, params.lat, params.lng, params.recovery, params.returnTo]);

  const updatePassword = async () => {
    const { error } = await requireSupabase().auth.updateUser({ password });
    if (error) setStatus("Parola güncellenemedi.");
    else router.replace("/profile");
  };
  return (
    <Screen>
      <Title>Hesap doğrulama</Title><Body>{status}</Body>
      {ready ? <Field secureTextEntry placeholder="Yeni parola (en az 8 karakter)" value={password} onChangeText={setPassword} /> : null}
      {ready ? <Button disabled={password.length < 8} onPress={updatePassword}>Parolayı güncelle</Button> : null}
      {!ready && status.startsWith("Geçersiz") ? <Notice error>{status}</Notice> : null}
      <Button variant="ghost" onPress={() => router.replace("/")}>Haritaya dön</Button>
    </Screen>
  );
}
