# Osman Kaya — Sorumluluk Kapsamı (Mobile Scope)

> Bu dosyanın amacı: kod yazarken **sınırları netleştirmek**. Buradaki "KAPSAM DIŞI"
> alanlara Claude'un (ve benim) dokunmaması gerekiyor — onlar başka ekip üyelerinin işi.
> İlgili plan: [end-to-end.md](./end-to-end.md).

---

## ✅ KAPSAM İÇİ — Benim Sorumluluğum

**Fiziksel sınır:** yalnızca `SafeRoute_App/mobile-app/` klasörü. Kod değişiklikleri bu klasörün dışına ÇIKMAZ.

### Alanlar
- **UI / Ekranlar** — expo-router ekranları (`src/app/`), tüm React Native bileşenleri, navigasyon akışı, modal/sheet'ler.
- **Harita** — Mapbox `MapView`, `Camera`, `ShapeSource`, `LineLayer` (rota), `FillLayer`/`HeatmapLayer` (risk ısı haritası), marker/pin'ler, kamera fit/animasyon.
- **Konum** — `expo-location`, izin akışı, `useUserLocation` ve türevleri.
- **Hedef arama / geocoding** — Mapbox Geocoding API (client-side), haritaya dokunarak hedef seçme.
- **API tüketimi** — `src/lib/api.ts` (axios client), backend endpoint'lerini **çağırmak**, response'lar için TypeScript tipleri (`src/lib/types.ts`).
- **Tehlike bildirim UI'ı** — serbest metin giriş ekranı ve `POST /report` çağrısı (metni gönderirim; NLP'yi ben çalıştırmam).
- **State & UX** — yükleme/hata/boş durumları, banner'lar, spinner'lar, kullanıcı geri bildirimi.
- **App yapılandırma & build** — `app.config.js`, `.env` / `.env.example`, Mapbox token yönetimi, EAS build (`eas.json`), splash/icon/izin metinleri.
- **Stil** — Seda Nur'un Figma tasarımını uygulamak (renk, tipografi, tema).

### Sahip olduğum dosyalar
```
mobile-app/src/**          (tüm mobil kaynak kod)
mobile-app/app.config.js
mobile-app/.env, .env.example
mobile-app/eas.json
mobile-app/package.json    (mobil bağımlılıklar)
mobile-app/assets/**
```

---

## ⛔ KAPSAM DIŞI — Dokunmuyorum (Başka Ekip Üyeleri)

| Alan | Sorumlu | Klasör / Yer |
|------|---------|--------------|
| **Backend / FastAPI** — endpoint'leri **yazmak**, Dijkstra, rota motoru, CORS, Supabase bağlantısı | **Seymen** | `SafeRoute_App/backend/` |
| **Veri mühendisliği** — OSMnx sokak grafı, suç/ışık ETL, Pandas temizleme, H3 indeksleme | **Mehmet Ali** | `SafeRoute_App/data-science/` |
| **AI / ML** — XGBoost model eğitimi, risk skoru formülü, ağırlık matrisi, batch prediction | **Merve** | `SafeRoute_App/data-science/` |
| **NLP mantığı** — TextBlob sentiment, tehlike skoru üretim fonksiyonu (ben sadece metni gönderirim) | **Seda Nur** | backend/data-science |
| **Veritabanı** — Supabase şeması, PostGIS sorguları, tablolar, RLS | **Seymen / Mehmet Ali** | Supabase cloud |
| **Risk formülü / ağırlıklar** — `w = mesafe × (1 + risk/100)`, suç puanları | **Merve / Seymen** | backend |

> Not: Backend endpoint'lerini **çağırmak** benim işim; bu endpoint'leri **yazmak/değiştirmek** Seymen'in işi. `backend/` veya `data-science/` klasörlerinde kod değişikliği YAPMAM — orada bir şey gerekiyorsa "sorumlusuna şunu iste" diye belirtirim.

---

## 🔗 Ara Yüz (benim tükettiğim kontratlar)
Bunlar benim yazmadığım ama **bağımlı olduğum** sözleşmeler (detay: [end-to-end.md](./end-to-end.md) "Zorunlu Dış Bağımlılıklar"):
- `POST /api/v1/route`          → rota GeoJSON + mesafe/süre/risk
- `GET  /api/v1/heatmap`        → risk noktaları (`total_risk`)
- `GET  /api/v1/heatmap/nearby` → yakın risk noktaları
- `POST /api/v1/report`         → tehlike bildirimi (metin + koordinat), analiz arka planda LLM
- `GET  /`                      → sağlık kontrolü (opsiyonel)
- `POST /api/v1/webhook/social-risk` → **scope dışı** (n8n çağırır, ben değil)

---

## 📌 Claude için çalışma kuralı
Bir görevde çözüm `backend/` veya `data-science/` içinde değişiklik gerektiriyorsa:
1. O değişikliği **yapma**.
2. Bunun kapsam dışı olduğunu ve **hangi ekip üyesinden ne istemem gerektiğini** söyle.
3. Mobil tarafta bekleme yerine ilerleyebilmem için (varsa) **mock/geçici çözüm** öner.

---

## 📌 İlerleme yöntemi: "Biten" vs "Sonraya ayrılan" (ÖNEMLİ — hep uygula)

Bir maddede çalışırken, netleşmemiş detaylar için **beklemem** — makul bir varsayımla (mock/placeholder) ilerlerim. Ama bunun izini **mutlaka bırakırım** ki ileride ne yapılacağı unutulmasın. Her madde bitiminde iki şeyi net yazarım:

**1. ✅ BİTEN — ne tamamlandı**
- Hangi dosyalar/fonksiyonlar yazıldı, ne çalışıyor.
- `end-to-end.md`'de o maddeyi **✅ TAMAMLANDI** işaretle + altına kısa "Yapıldı:" notu.

**2. ⏳ SONRAYA AYRILAN — ne ertelendi, neden, ne yapılmalı**
Her ertelenen iş için 3 şeyi yaz:
- **Ne:** ertelenen parça (örn. gerçek `/report` yanıtına göre UI).
- **Neden:** hangi belirsizliğe/bağımlılığa takıldı (örn. "yanıt şekli sonra karar verilecek").
- **Nasıl bağlanacak:** netleşince ne yapılacak (örn. "`api.ts`'te mock satırını gerçek `api.post` ile değiştir; UI değişmez").

**İzi nereye bırakırım:**
- Kodda: ertelenen yere `// TODO(osman): <ne> — <netleşince ne yapılacak>` yorumu.
- Planda: `end-to-end.md`'de ilgili maddenin altına `⏳ Sonraya:` notu.

**Amaç:** "sonra karar verilecek" dediğimiz her şey, karar gelince **tek dokunuşla** bağlanabilsin; hiçbir belirsizlik kod içinde kaybolmasın. Mock veri her zaman `types.ts`'teki tiplere uygun olsun ki gerçek veriye geçiş sadece veri kaynağını değiştirmek olsun (UI'a dokunmadan).
