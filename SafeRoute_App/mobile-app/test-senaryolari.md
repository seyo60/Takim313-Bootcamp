# SafeRoute Mobil — Uçtan Uca Test Senaryoları (Madde 1–8)

> Ortam: dev build (`npx expo start --dev-client`) + gerçek cihaz/emülatör.
> `.env` dolu olmalı (`EXPO_PUBLIC_MAPBOX_TOKEN`). Mock modda backend GEREKMEZ.
> Her kutuyu test ettikçe işaretle: `[ ]` → `[x]`

## Açılış & Konum (Madde 1-2 altyapısı)
- [ ] **A1.** App açılır → Mapbox sokak haritası gelir, çökme yok.
- [ ] **A2.** Konum izni İSTENIRSE ver → harita senin konumuna yakınlaşır (zoom ~14).
- [ ] **A3.** (İzin reddedilirse) → "Location permission denied — showing Chicago…" bilgisi banner'da, harita Chicago'ya gider. App çalışmaya devam eder.
- [ ] **A4.** Açılışta rota ÇİZİLMEZ (hedef seçilmeden çizgi olmamalı — Madde 3 sonrası davranış).

## Isı Haritası (Madde 5)
- [ ] **B1.** Chicago'ya bak (konum iznin yoksa zaten oradasın; varsa haritayı Chicago'ya kaydır) → 3 renkli leke: Loop'un batısı kırmızı/turuncu (yüksek), River North amber (orta), Millennium Park civarı soluk yeşil (düşük).
- [ ] **B2.** Zoom in/out → lekeler yumuşakça yoğunlaşıp dağılır, performans akıcı.
- [ ] **B3.** Sağ üstteki 🔥 butonuna bas → lekeler kaybolur, buton beyazlaşır. Tekrar bas → geri gelir (buton kırmızı çerçeveli).

## Hedef Seçme (Madde 3)
- [ ] **C1.** Arama çubuğuna "Millennium Park" yaz → ~0.5 sn sonra sonuç listesi düşer (isim + adres).
- [ ] **C2.** Bir sonuca dokun → klavye kapanır, kırmızı pin düşer.
- [ ] **C3.** Haritada rastgele bir yere dokun → pin oraya taşınır, rota yeniden hesaplanır.
- [ ] **C4.** "asdqwezxc" gibi saçma bir şey yaz → "Sonuç bulunamadı." kutusu, çökme yok.
- [ ] **C5.** Tek harf yaz → liste hiç açılmaz (2 karakter altı istek atılmaz).

## Rota Çizimi & Kıyas (Madde 1+2+8)
- [ ] **D1.** Hedef seçince → kısa "Güvenli rota hesaplanıyor…" (spinner'lı) banner → sonra **mavi düz çizgi** (güvenli) + **gri kesikli çizgi** (en kısa) birlikte çizilir.
- [ ] **D2.** Kamera her iki rotayı da kadraja alacak şekilde otomatik fit olur.
- [ ] **D3.** İki çizgi farklı hatlardan gider (mavi dolambaçlı, gri direkt). ⚠️ Not: mock modda çizgiler SABİT Chicago hattıdır, seçtiğin hedefe gitmez — backend gelince düzelir, hata değil.

## Rota Bilgi Kartı (Madde 4+8)
- [ ] **E1.** Rota çizilince altta beyaz kart: "1.4 km · 17 dk · 24 Düşük risk" (risk yeşil renkte).
- [ ] **E2.** Kartın üstünde lejant: mavi "Güvenli rota" · gri kesikli "En kısa (riskli olabilir)".
- [ ] **E3.** Karttaki ✕'e bas → kart + pin + her iki çizgi birlikte temizlenir.

## Tehlike Bildirimi (Madde 6)
- [ ] **F1.** Sağdaki ⚠️ (kırmızı) butona bas → modal açılır: "⚠️ Tehlike Bildir" + metin kutusu.
- [ ] **F2.** 5 karakterden az yaz → "Gönder" pasif (soluk). 5+ karakter → aktifleşir.
- [ ] **F3.** "Bu sokakta birisi beni takip ediyor" yaz + Gönder → kısa spinner → "✓ Bildirimin alındı. Teşekkürler!" → ~1 sn sonra otomatik haritaya döner.
- [ ] **F4.** Haritaya dönünce heatmap tazelenir; bulunduğun konumda YENİ bir kırmızı leke belirir (mock modun "arka plan analizi" simülasyonu).
- [ ] **F5.** Modaldaki ✕ ile göndermeden çık → hiçbir şey değişmez.
- [ ] **F6.** 280 karakter sınırı: sayaç sağ altta artar, 280'de durur.

## Yükleme & Hata UX (Madde 7)
- [ ] **G1.** Rota hesaplanırken banner'da spinner + "Güvenli rota hesaplanıyor…" görünür (mock 400ms — hızlı, dikkatli bak).
- [ ] **G2 (backend hata simülasyonu).** `src/lib/api.ts`'te `USE_MOCK_ROUTE = false` yap (backend kapalıyken), app'i yenile, hedef seç → KIRMIZI banner "Rota alınamadı…" + "Tekrar dene" butonu. Bas → tekrar dener, yine kırmızı. App çökmez. Testten sonra `true`'ya geri al!
- [ ] **G3.** Aynısını `USE_MOCK_HEATMAP = false` ile → "Isı haritası yüklenemedi." + Tekrar dene. Geri al.
- [ ] **G4.** Aynısını `USE_MOCK_REPORT = false` ile → bildirim gönderiminde kırmızı hata metni modal içinde, metin düzenlenebilir kalır. Geri al.

## Genel
- [ ] **H1.** Hiçbir senaryoda kırmızı tam ekran hata (LogBox crash) yok.
- [ ] **H2.** `npx tsc --noEmit` temiz.

---
İlgili plan: [end-to-end.md](./end-to-end.md) · Kapsam: [osman_scope.md](./osman_scope.md)
