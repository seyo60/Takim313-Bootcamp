# SafeRoute AI — Mobil Uçtan Uca Yapılacaklar

> Sahibi: **Osman Kaya (Lead Mobile Developer)** · Kapsam: sadece `SafeRoute_App/mobile-app/`
> Sınırlarım için: [osman_scope.md](./osman_scope.md)
>
> Aşağıdaki liste **baştan sona sırayla** yapılacakları içerir. Sırayla ilerlenir.
> Bir madde başkasına bağlıysa altına **🔗 Bağımlılık** notu düşülmüştür — ama bu
> beklemek zorunda olduğum anlamına gelmez: çoğu maddeyi **mock veriyle** bitirip
> gerçek veri gelince sadece API çağrısını bağlarım.

---

## Yapılacaklar (Sırayla)

### 1. Rotayı haritada çiz (mock GeoJSON ile) — ✅ TAMAMLANDI
`ShapeSource` + `LineLayer` ekle. Elde hazır bir mock `LineString` (Chicago içinde birkaç nokta) ile haritaya çizgi bas, kamerayı rotaya fit et.
**Bitince:** haritada bir rota çizgisi görünüyor. (PDF Sprint 1 kriteri: "Mapbox'ta çizgi çizilir" ✅)
*Bağımlılık yok — lokal mock ile tamamen bağımsız.*
> **Yapıldı:** `src/lib/mockRoute.ts` (mock `LineString` + `getRouteBounds()`), `src/app/index.tsx`'e `ShapeSource`/`LineLayer` + kamera bounds fit eklendi. `tsc --noEmit` temiz. (Cihazda görsel prova kaldı.)

### 2. Rota veri tiplerini ve API çağrısını yaz — ✅ TAMAMLANDI (mock modda)
`src/lib/types.ts` içinde `RouteResponse` tipini tanımla. `src/lib/api.ts`'e origin/dest koordinatlı `getRoute(start, end)` fonksiyonunu ekle (mevcut `getMockRoute` üstüne). 1. adımdaki çizimi mock yerine bu fonksiyonun döndürdüğü veriye bağla.
**Bitince:** gerçek origin→dest koordinatlarıyla backend'den rota çekilip çiziliyor.
> 🔗 **Bağımlılık — Seymen:** `POST /api/v1/route` endpoint'inin çalışır olması ve **kesin JSON şeklinin** (request body + response) verilmesi lazım (bkz. aşağıda "Zorunlu Dış Bağımlılıklar" §A). Gelmezse §A'daki önerdiğim şekille mock JSON kullanıp devam ederim, endpoint gelince tek satır bağlarım.
> **✅ Yapıldı:** `src/lib/types.ts` (tüm API tipleri: `RouteRequest/Response`, `RiskPoint`, `ReportRequest/Response`) · `api.ts`'e `getRoute()` eklendi — gerçek `POST /api/v1/route` kodu yazılı, şimdilik `USE_MOCK_ROUTE = true` anahtarıyla mock dönüyor · `src/hooks/useRoute.ts` (idle/loading/ready/error durumlu fetch hook'u) · `index.tsx` artık rotayı bu akıştan çiziyor, hata durumunda banner gösteriyor · eski `getMockRoute` ping'i kaldırıldı · `tsc` temiz.
> **⏳ Sonraya ayrılan:**
> - **Gerçek backend'e geçiş** — Neden: endpoint henüz canlı değil. Nasıl: `api.ts`'te `USE_MOCK_ROUTE = false` yap; §A body alan adları farklıysa `types.ts` + `getRoute()`'taki body'yi güncelle. UI değişmez.
> - **`hour` parametresi** — Neden: kim gönderecek belli değil (§A). Nasıl: biz göndereceksek `getRoute()`'ta `new Date().getHours()` ekle.
> - **Gerçek origin/dest** — Neden: hedef seçimi Madde 3'ün işi. Nasıl: `index.tsx`'teki `MOCK_START/MOCK_END` yerine kullanıcı konumu + seçilen hedef geçilecek (TODO yorumu yerinde).

### 3. Hedef seçme UI'ı (arama + haritaya dokunma) — ✅ TAMAMLANDI
`src/lib/geocoding.ts` — Mapbox Geocoding ile adres/yer arama çubuğu. Ayrıca haritaya dokununca oraya hedef pin'i koyma. Origin otomatik olarak kullanıcının konumu (mevcut `useUserLocation`).
**Bitince:** kullanıcı bir hedef seçebiliyor, seçince 2. adımdaki rota akışı tetikleniyor.
*Bağımlılık yok — Mapbox Geocoding client-side, elimdeki `pk.` token yetiyor.*
> **✅ Yapıldı:** `src/lib/geocoding.ts` (Mapbox Geocoding v6, proximity bias'lı `searchPlaces()`, hata durumunda boş liste) · `src/components/DestinationSearchBar.tsx` (350ms debounce, sonuç listesi, "sonuç bulunamadı" durumu) · `index.tsx`: haritaya dokununca hedef pin (kırmızı nokta), arama sonucundan hedef seçme, "✕ Hedefi temizle" butonu, rota artık hedef seçilince tetikleniyor (öncesinde idle), origin = kullanıcı konumu (yoksa Chicago) · "Güvenli rota hesaplanıyor…" yükleme banner'ı · `tsc` temiz.
> **⏳ Sonraya ayrılan:**
> - **Rota geometrisi hedefe uymuyor** — Neden: mock rota sabit Chicago çizgisi; nereye dokunursan dokun aynı çizgi çizilir. Nasıl: `USE_MOCK_ROUTE = false` olunca kendiliğinden düzelir (backend gerçek origin/dest'e göre hesaplar). Kod değişikliği gerekmez.
> - **Görsel cila (arama çubuğu/pin/buton stilleri)** — Neden: Figma bekleniyor (Madde 9). Nasıl: `src/theme/` kurulunca stiller oradan beslenecek.
> - **Cihazda prova** — arama→seçim→çizim akışı gerçek cihazda görsel olarak doğrulanacak (Madde 1'deki provayla birlikte).

### 4. Rota bilgi kartı (mesafe / süre / risk skoru) — ✅ TAMAMLANDI (mock veriyle)
Rota çizilince alt kısımda `RouteInfoCard` göster: mesafe, tahmini süre, rota risk skoru (0–100).
**Bitince:** rota bilgileri kullanıcıya görünür.
> 🔗 **Bağımlılık — Seymen:** kartın gösterdiği `distance_m`, `duration_s`, `risk_score` alanları `POST /api/v1/route` yanıtından gelmeli (§A). Mock ile UI'ı önden bitiririm.
> **✅ Yapıldı:** `src/components/RouteInfoCard.tsx` — alt kart: mesafe (m/km), yürüyüş süresi (dk), risk skoru + renkli etiket (0-33 yeşil "Düşük risk" / 34-66 turuncu "Orta" / 67-100 kırmızı "Yüksek") ve kart içinde ✕ (hedefi temizler). `index.tsx`: rota hazırken kart, rota yokken (loading/error) eski "✕ Hedefi temizle" butonu. `tsc` temiz.
> **⏳ Sonraya ayrılan:**
> - **Gerçek değerler** — Neden: mock sabit (1350m / ~17dk / risk 24). Nasıl: `USE_MOCK_ROUTE = false` olunca backend değerleri otomatik akar; kart koda dokunmadan çalışır.
> - **Risk eşikleri (33/66)** — Neden: UI varsayımı, kontrat değil. Nasıl: Merve'nin skor dağılımına göre gerekirse `riskInfo()` eşikleri güncellenir.
> - **Kart stili** — Figma (Madde 9).

### 5. Heatmap (risk ısı haritası) katmanı — ✅ TAMAMLANDI (mock veriyle)
`getHeatmap()` çağrısı + risk noktalarını haritada göster: `HeatmapLayer` (ağırlık = `total_risk`) veya `CircleLayer` (renk = `total_risk`, yeşil→turuncu→kırmızı). Aç/kapa toggle butonu. Performans için tüm şehir yerine `GET /api/v1/heatmap/nearby` ile sadece yakındaki noktaları çekmeyi değerlendir.
**Bitince:** riskli bölgeler haritada renkleniyor, toggle çalışıyor.
> 🔗 **Bağımlılık — Seymen:** `GET /api/v1/heatmap` (ve `/heatmap/nearby`) endpoint'i ve **risk noktalarının kesin JSON şekli** lazım (§B).
> 🔗 **Bağımlılık — Merve & Mehmet Ali:** katmanın **gerçek** veriyle dolması için batch prediction sonuçlarının Supabase'e yazılmış olması gerekir. Onlar bitene kadar backend'den **mock heatmap** isterim; katmanı mock ile bitiririm.
> **✅ Yapıldı:** `src/lib/mockHeatmap.ts` (3 deterministik risk kümesi: yüksek/orta/düşük + `riskPointsToFeatureCollection()`) · `api.ts`'e `getHeatmap()` (`USE_MOCK_HEATMAP` anahtarı, gerçek GET kodu yazılı) · `src/hooks/useHeatmap.ts` · `index.tsx`: `HeatmapLayer` (`total_risk` ağırlıklı, şeffaf→yeşil→amber→kırmızı rampa), sağ üstte 🔥 toggle (varsayılan açık), yüklenemezse banner. `tsc` temiz.
> **⏳ Sonraya ayrılan:**
> - **Gerçek veriye geçiş** — Neden: endpoint + batch prediction hazır değil. Nasıl: `USE_MOCK_HEATMAP = false`; §B yanıtı FeatureCollection çıkarsa sadece `getHeatmap()` içindeki parse değişir.
> - **`/heatmap/nearby` optimizasyonu** — Neden: tüm şehir payload'ının boyutu bilinmiyor. Nasıl: ağır kalırsa `getHeatmap()`'i nearby endpoint'ine + kullanıcı konumuna geçir (TODO yorumu `api.ts`'te).
> - **Rapor sonrası yenileme** — Neden: Madde 6'nın işi. Nasıl: `useHeatmap`'e `refetch()` eklenecek (TODO yorumu hook'ta).
> - **Rampa/yarıçap ince ayarı** — gerçek veri dağılımı görülünce.

### 6. Tehlike bildirim ekranı — ✅ TAMAMLANDI (mock modda)
`src/app/report.tsx` — serbest metin girişi + "Gönder". `POST /api/v1/report` çağrısı, "bildirimin alındı" onay mesajı. Not: analiz **arka planda LLM ile** yapılıyor, yani risk artışı anında dönmez → onay verip heatmap'i biraz sonra (veya kullanıcı yenileyince) tazelerim.
**Bitince:** kullanıcı tehlike bildirimi yazıp gönderebiliyor, onay görüyor.
> 🔗 **Bağımlılık — Seymen:** `POST /api/v1/report` endpoint'i lazım (§C).
> 🔗 **Bağımlılık — Seda Nur:** NLP/LLM analiz mantığı onun/backend'in işi; ben sadece metni + koordinatı gönderir, dönen onayı gösteririm.
> **✅ Yapıldı:** `src/app/report.tsx` (modal: çok satırlı metin, 280 karakter sayacı, min 5 karakter, gönderim/başarı/hata durumları, başarıda 1.2sn sonra haritaya dönüş) · haritada ⚠️ butonu (kullanıcı konumunu param olarak taşır) · `api.ts`'e `submitReport()` (`USE_MOCK_REPORT` anahtarı, gerçek POST yazılı; mock modda bildirilen yere lokal 90-risk noktası eker → demo'da "bildir → haritada leke çıkar" akışı çalışır) · `useHeatmap`'e `refetch()` + harita ekranına dönünce otomatik tazeleme · `hour` parametresi de artık gerçek `getRoute` body'sinde. `tsc` temiz.
> **📝 Sonradan düzeltme notu (kod hazır, anahtar/ince ayar):** `USE_MOCK_REPORT = false` yapınca gerçek endpoint'e geçer; §C body alan adları farklıysa `types.ts` güncellenir. Mock'un "haritaya anında leke ekleme" davranışı gerçekte YOK (analiz arka planda) — gerçek modda otomatik olarak devre dışı kalır, ekstra iş gerekmez.
> **⏳ Gerçekten sonraya:** yanıt senkron analiz de içerirse sonucu ekranda göstermek (§C netleşince).

### 7. Yükleme & hata UX'i
Rota / heatmap / rapor çağrıları için spinner ve görünür hata banner'ları (mevcut `logRequestError` mantığının üstüne kullanıcıya görünen UI). Backend down iken app çökmemeli.
**Bitince:** her durumda anlaşılır geri bildirim var, çökme yok.
*Bağımlılık yok.*

### 8. "En kısa vs en güvenli" kıyas görünümü
Varsa iki rotayı farklı renkte çiz (güvenli = yeşil, en kısa = gri), farkı vurgula. Demo değeri yüksek.
**Bitince:** kullanıcı iki rotayı karşılaştırabiliyor.
> 🔗 **Bağımlılık — Seymen:** `GET /api/v1/route` yanıtında opsiyonel `shortest` rotasının da dönmesi gerekir (§A).

### 9. Figma tasarımını uygula (polish)
`src/theme/` — renk paleti, tipografi. Buton/kart/arama çubuğu stilleri, ikonlar, splash. Tüm ekranları tasarıma göre düzenle.
**Bitince:** app tasarıma uygun görünüyor.
> 🔗 **Bağımlılık — Seda Nur:** 3 ekranlık Figma tasarımı (harita, rota seçim, bildirim) lazım. Erken alırsam önceki adımlarda da uygularım.

### 10. Sabit backend URL'ine geç
ngrok yerine kalıcı URL. `.env`'deki `EXPO_PUBLIC_API_BASE_URL`'i güncelle.
**Bitince:** app her seferinde URL güncellemeden çalışıyor.
> 🔗 **Bağımlılık — Seymen:** backend'in Render.com'a deploy edilmiş olması gerekir (PDF Sprint 3).

### 11. Demo build & uçtan uca prova
EAS ile preview/dev build al. Gerçek telefonda tam akışı prova et: konum → hedef seç → güvenli rota → heatmap → tehlike bildir.
**Bitince:** PDF teslim kriterleri gerçek cihazda canlı çalışıyor. (2 Ağustos teslim)
> 🔗 **Bağımlılık:** yukarıdaki tüm maddeler tamam olmalı.

---

## Zorunlu Dış Bağımlılıklar (Toplu)

> Bunlar benim yazmadığım ama tükettiğim şeyler. En kritikleri Seymen'den gelecek endpoint kontratları.

### Kararlaştırılan Endpoint Listesi

| Method | Endpoint | Açıklama | Beni ilgilendirir mi? |
| ------ | -------- | -------- | --------------------- |
| GET | `/` | Sağlık kontrolü | ✅ (opsiyonel — bağlantı testi) |
| POST | `/api/v1/route` | İki nokta arası en güvenli rota | ✅ (§A — Madde 2/4/8) |
| POST | `/api/v1/report` | Anlık tehlike ihbarı (arka planda LLM analizi) | ✅ (§C — Madde 6) |
| POST | `/api/v1/webhook/social-risk` | Dış otomasyon (n8n) sosyal medya/haber riski gönderir; `X-Webhook-Secret` zorunlu | ❌ (mobil değil — n8n→backend) |
| GET | `/api/v1/heatmap` | Tüm risk noktaları (`total_risk`) | ✅ (§B — Madde 5) |
| GET | `/api/v1/heatmap/nearby` | Belirli konuma yakın risk noktaları | ✅ (§B — Madde 5, performans) |

> `webhook/social-risk` benim scope'umda değil; onu n8n çağırır, ben çağırmam. Burada sadece kayıt için duruyor.

### Seymen'den — Endpoint Kontratları (kesin JSON şekli)

**§A · `POST /api/v1/route`** (Madde 2, 4, 8'i açar)
```
İstek (body):
{ "start": [lng, lat], "end": [lng, lat], "hour": 21 }   // alan adları netleşecek
Yanıt (önerdiğim şekil):
{
  "route":      { "type": "LineString", "coordinates": [[lng,lat], ...] },
  "distance_m": 1840,
  "duration_s": 1320,
  "risk_score": 27.5,      // rota boyunca, 0-100
  "shortest":   { "type": "LineString", "coordinates": [...] }   // opsiyonel: kıyas için
}
```
Netleştir: (1) request body alan adları/şekli ne? (`start`/`end` dizi mi, ayrı `start_lat`/`start_lng` mi?) (2) coordinates `[lng,lat]` sırasında mı? (3) `risk_score` ortalama mı toplam mı? (4) `hour`'u ben mi göndereceğim? (5) `shortest` dönecek mi?

**§B · `GET /api/v1/heatmap` (+ `/heatmap/nearby`)** (Madde 5'i açar)
```
İstek:  GET /api/v1/heatmap
        GET /api/v1/heatmap/nearby?lat=..&lng=..&radius=..   // param'lar netleşecek
Yanıt (backend "risk noktaları / total_risk" diyor → nokta bazlı bekliyorum):
[
  { "lat": 41.88, "lng": -87.63, "total_risk": 65 },
  ...
]
// ya da GeoJSON FeatureCollection<Point> — hangisi olacak netleşecek
```
Netleştir: (1) düz nokta dizisi mi, GeoJSON `FeatureCollection<Point>` mü? (2) risk alanının adı `total_risk` mi, ölçeği 0-100 mü? (3) `/nearby` query param'ları (`lat`,`lng`,`radius`?) ne? (4) `/heatmap` kaç nokta döndürür (performans)?

**§C · `POST /api/v1/report`** (Madde 6'yı açar)
```
İstek (body):
{ "text": "birisi beni takip ediyor", "lat": .., "lng": .., "user_id": "opsiyonel" }
Yanıt (analiz ARKA PLANDA → muhtemelen sadece onay):
{ "ok": true, "id": "..." }
```
Netleştir: (1) body alan adları? (2) analiz arka planda olduğu için yanıtta risk/skor dönmüyor, değil mi (sadece "alındı" onayı)? (3) ihbar heatmap'e ne zaman yansır (bir sonraki `/heatmap` çağrısında mı)?

**§D · Deploy / URL** — ngrok URL'i değişince bana yeni URL lazım. Sprint 3'te Render'a sabit deploy (Madde 10).

### Seda Nur'dan
- 3 ekranlık Figma tasarımı (Madde 9). NLP mantığı (Madde 6'da metni gönderiyorum, mantık onda/backend'de).

### Merve & Mehmet Ali'den (dolaylı)
- Heatmap'in gerçek veriyle dolması için batch prediction'ın Supabase'e yazılması (Madde 5). O gelene kadar mock heatmap ile ilerlerim.

---

## Klasör Yapısı (Hedef)

```
src/
  app/
    _layout.tsx        → Stack (mevcut)
    index.tsx          → Ana harita ekranı (mevcut; harita+rota+heatmap+arama+rapor butonu)
    report.tsx         → Tehlike bildirim ekranı [YENİ]
  components/          → RouteSearchBar, RouteInfoCard, ReportSheet, HeatmapToggle [YENİ]
  hooks/
    useUserLocation.ts → mevcut
    useRoute.ts        → [YENİ]
    useHeatmap.ts      → [YENİ]
  lib/
    api.ts             → axios client + backend çağrıları (mevcut, genişletilecek)
    types.ts           → RouteResponse, RiskPoint, ReportResponse [YENİ]
    geocoding.ts       → Mapbox Geocoding (hedef arama) [YENİ]
  theme/              → renkler, spacing (Figma'dan) [YENİ]
```

---

## Veri Akışı (Mobil Bakış)

```
Kullanıcı konumu (origin) ─┐
Hedef arama/tap (dest) ────┼─→ POST /api/v1/route ─→ LineLayer çiz + RouteInfoCard
                           │
Harita açılışı ────────────┼─→ GET  /api/v1/heatmap ─→ Heatmap/CircleLayer (total_risk)
                           │
Tehlike bildir ────────────┴─→ POST /api/v1/report ─→ "alındı" onayı (analiz arka planda)
```

---

## Notlar / Riskler
- **Mock ile ilerleme stratejisi:** Endpoint kontratları (§A/B/C) gecikirse, `types.ts`'teki tiplere uygun **lokal mock JSON** ile ilgili UI'ları bitiririm; backend gelince sadece `api.ts` çağrısını bağlarım. Böylece hiçbir maddede beklemem.
- **En büyük risk:** Madde 2/4/5/6/8'in gerçek veriye geçişi §A/B/C'ye bağlı. → Bu 3 kontratı bugün Seymen ile netleştir.
- **Heatmap performansı:** `GET /api/v1/heatmap` çok fazla nokta dönerse render yavaşlar → tüm şehir yerine `GET /api/v1/heatmap/nearby` ile kullanıcının çevresini çekerim.
- **Karar teyidi:** PDF "Supabase-js ile direkt çekme" diyordu; ben axios→FastAPI seçtim. Bunun tüm veri için geçerli olduğunu Seymen ile teyit et.
- **İlk kod adımı:** Madde 1 (mock rota çizimi) — bağımsız, hemen görsel sonuç.
```
