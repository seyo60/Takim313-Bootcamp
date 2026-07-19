# Takim313-Bootcamp
Yapay Zeka ve Teknoloji Akademisi 2026 bünyesinde geliştirilen proje için scrum süreçleri, sprint dokümantasyonları ve ürün yönetim şablonu.

# Takım 313
Takım Üyeleri: 
* Mehmet Ali Ballı - Scrum Master & Developer
* Seymen Çiçek - Product Owner & Developer
* Merve Korkut - Developer
* Osman Kaya - Developer
* Seda Nur Tanık - Developer

# Ürün İle İlgili Bilgiler

## Ürün İsmi
Safe Route AI Navigation

## Ürün Açıklaması
Kentsel alanlarda yalnız seyahat eden bireylerin, kadınların ve öğrencilerin fiziksel güvenliğini korumayı amaçlayan yapay zeka destekli bir uygulamadır. Klasik haritaların aksine kullanıcıya sadece en kısa yolu değil; güvenlik verilerini, sokakların aydınlık durumunu ve kullanıcıların anlık tehlike bildirimlerini işleyerek "En Güvenli Yaşayan Rota" alternatifini sunar. Uygulama bünyesinde yer alan dinamik ısı haritası (heat map) modülü sayesinde kullanıcılar, şehrin hangi bölgelerinin daha güvenli veya hangi sokakların anlık olarak daha riskli olduğunu harita üzerinde görsel olarak doğrudan görebilirler. Yapay zeka altyapısıyla şehri anlık olarak tarayan sistem, riskleri önceden tespit ederek kullanıcıyı tehlikeli bölgelerden uzak tutmayı hedefleyen inovatif bir kentsel güvenlik projesidir.

## Ürün Özellikleri (Product Features)

* **Yapay Zeka Destekli Güvenli Rotalama (AI-Powered Safe Routing):** Sadece en kısa ve hızlı yolu değil; geçmiş suç verileri ile fiziksel altyapı eksikliklerini (311 sokak lambası arızaları) harmanlayarak kullanıcı için en güvenli rotayı hesaplar.
* **Canlı İhbar ve Dinamik Risk Haritası (Real-Time Risk Mapping):** Kullanıcıların karşılaştığı anlık tehlikeleri bildirmesine olanak tanır. Doğal Dil İşleme (NLP) ile analiz edilen bu ihbarlar, Uber H3 altıgen mimarisi kullanılarak saniyeler içinde sokak ağındaki (OSMnx) risk ağırlıklarına dönüştürülür.
* **Topluluk Odaklı Uyarı Sistemi (Community-Driven Alerts):** Cihazın GPS koordinatlarını anlık olarak takip ederek, kullanıcının rotası üzerinde yeni oluşan dinamik bir tehlike (örn: olay yeri) varsa proaktif bildirimler (Toast/Alert) üretir.
* **Yüksek Performanslı İnteraktif Harita (Interactive Mapbox Experience):** Mapbox SDK entegrasyonu sayesinde, Chicago başta olmak üzere karmaşık şehir ağlarında akıcı, detaylı ve kullanıcı dostu bir harita navigasyon arayüzü sunar.
* **Hızlı ve Asenkron Veri Senkronizasyonu (Asynchronous Data Sync):** Arka planda çalışan Dockerize edilmiş PostGIS ve FastAPI mimarisi sayesinde, binlerce sokak segmentinin risk skorlarını milisaniyeler içinde günceller ve mobil cihaza kesintisiz aktarır.


## Hedef Kitle
* Seyahat eden bireyler
* Kadınlar
* Öğrenciler

## Product Backlog URL
* [Product Backlog](https://app.notion.com/p/edebiyat/38f780ef363a80579a7dce0ee1e54335?v=38f780ef363a80a9a200000c88d2153f&source=copy_link)

---

# CI/CD

Proje, GitHub Actions ile iki bağımsız pipeline kullanır. Workflow dosyaları
`.github/workflows/` altındadır ve yalnızca ilgili klasör değiştiğinde (path
filtreleri) tetiklenir.

## Pipeline'lar

| Workflow | Tetikleyici | Ne yapar |
|---|---|---|
| **`backend-ci.yml`** | `SafeRoute_App/backend/**` veya `data-science/**` → `push`/`PR` (main, develop) | Python 3.12 kurar (pip cache), sistem kütüphanelerini (geos/spatialindex) yükler, `pip install -r requirements.txt`, **ruff** lint, **pytest** çalıştırır. `main`'e push'ta testler geçerse → Render deploy. |
| **`mobile-ci.yml`** | `SafeRoute_App/mobile-app/**` → `push`/`PR` (main, develop) | Node 20 + `npm ci`, `tsc --noEmit` type-check, `expo lint` (bloke etmez), (varsa) Jest. `main`'e push'ta → `eas build --platform all`. |

## Deploy akışı (backend → Render.com)

1. `main`'e merge → `backend-ci` testleri koşar.
2. Testler geçerse `deploy` job'ı **`production`** environment'ına girer.
3. Environment'a **required reviewers** tanımlıysa, deploy biri **manuel onaylayana**
   kadar bekler. Onay ekranından önce workflow bir **RLS & CORS hatırlatması**
   (uyarı) basar — prod'a çıkmadan Supabase RLS ve CORS ayarları gözden geçirilmeli.
4. Onaydan sonra `RENDER_DEPLOY_HOOK_URL`'e `curl POST` ile Render deploy tetiklenir.

## Gerekli GitHub Secrets

Repo **Settings → Secrets and variables → Actions** altına eklenmeli
(değerler koda ASLA gömülmez):

| Secret | Kullanıldığı yer | Açıklama |
|---|---|---|
| `RENDER_DEPLOY_HOOK_URL` | backend deploy | Render servisinin "Deploy Hook" URL'i |
| `EXPO_TOKEN` | mobile build | Expo hesabı erişim token'ı (EAS Build) |

> Backend testleri DB'yi ve grafı stub'lar, LLM `mock` modda koşar — bu yüzden
> **CI testleri için gerçek secret gerekmez**. `DATABASE_URL`, `GEMINI_API_KEY`
> gibi gerçek prod değerleri Render'ın kendi ortam değişkenlerinde tutulur
> (bkz. `SafeRoute_App/backend/.env.example` ve `backend/DEPLOYMENT.md`).

## Manuel onay kapısını kurma (bir kerelik)

Repo **Settings → Environments → New environment → `production`** → **Required
reviewers** ekleyin. Böylece `main`'e her merge otomatik prod'a çıkmaz; gözden
geçirme sonrası elle onaylanır.

---

# Sprint 1

## Uygulama Ekran Görüntüleri
[Projenizin Prototip veya Expo ilk ekran görüntülerini buraya ekleyebilirsiniz]

---

## Uygulama Akış Şeması (App Map)
[Kullanıcı akış diyagramını buraya ekleyebilirsiniz]

---

## Proje Yönetimi (Project Management)
<img width="1577" height="736" alt="Ekran Alıntısı" src="https://github.com/user-attachments/assets/8962b5b9-10da-4418-ace6-2a597b9d5427" />

---

## Sprint Notları
* Navigasyon ağının çıkarılması için OSMnx kullanılarak Chicago yaya graf ağı modellendi ve çıkmaz sokaklar temizlendi.
* Canlı rota pipeline'ı için Uber H3 (Seviye 9) indeksleme altyapısı entegre edildi.
* Veritabanı mimarisi, Docker üzerinde PostgreSQL ve PostGIS kullanılarak asenkron SQLAlchemy yapısıyla ayağa kaldırıldı.
* Backend API uçları FastAPI ile oluşturuldu, CORS izinleri ayarlandı ve Ngrok üzerinden dış dünyaya açıldı.
* Mobil uygulama arayüzü React Native ve Expo ile başlatılıp Mapbox SDK entegrasyonu tamamlandı.
* Daily scrum toplantıları Whatsapp ve Meet uygulamaları takım müsaitlik durumuna göre kullanılarak gerçekleştirildi.
* Uygulamanın asıl temasının açık olmasına karar verildi.
* Globale yönelik hedefler nedeniyle İngilizce dili ile tasarımların ve uygulamanın yapılmasına karar verildi.

## Sprint İçinde Tamamlanması Beklenen Puan
* 250 Puan

## Puan Tamamlama Mantığı
* İlk sprint olduğu için temel altyapı kurulumları, veri analizi (EDA), veritabanı şemalarının oluşturulması ve uygulamanın harita bazlı ön yüzünün ayağa kaldırılması hedeflenmiş ve görevler başarıyla tamamlanmıştır.

## Product Backlog URL
* [Product Backlog](https://app.notion.com/p/edebiyat/38f780ef363a80579a7dce0ee1e54335?v=38f780ef363a80a9a200000c88d2153f&source=copy_link)

## Sprint Gözden Geçirilmesi (Sprint Review)
* Veri seti üzerindeki eksik koordinatlar temizlendi ve lokasyon veri tipleri standartlaştırıldı.
* Sadece açık alanlarda gerçekleşen, sokak güvenliğini ilgilendiren suçlar filtrelenerek veri analizi (EDA) tamamlandı.
* H3 indeksleri ve yapay zeka risk puanları kullanılarak, Chicago graf ağındaki sokak segmentlerine dinamik ağırlık atama pipeline'ı oluşturuldu.
* FastAPI üzerinden `h3_heatmap` ve `user_reports` tabloları için CRUD operasyonları yazılarak `/api/v1/route` ve `/api/v1/heatmap` test uçları çalıştırıldı.
* Swagger API dokümantasyonu hazırlandı ve canlı tünel adresi mobil ekibine teslim edildi.
* Mobil tarafta Mapbox haritası, Chicago Downtown bölgesine odaklanmış şekilde ekrana yansıtıldı.
* iOS ve Android işletim sistemleri için GPS konum izin kodları başarıyla eklendi.
* Figma üzerinde uygulamanın kullanıcı deneyimi (UX) ve arayüz (UI) tasarımları oluşturuldu.

## Sprint Gözden Geçirme Katılımcıları
* Mehmet, Osman, Seymen, Merve, Seda Nur

## Sprint Retrospektifi (Sprint Retrospective)
* Bir sonraki sprintte mobil cihazlardan alınacak anlık GPS koordinatları ile backend uçlarına POST istekleri atacak yapının kurulmasına karar verildi.
* Axios kütüphanesi entegre edilerek Seymen'in hazırladığı API servislerinden mock rotaların çekilmesi hedeflendi.
* Kullanıcı form alanları ve metin (TextArea) durum (state) kontrollerinin kodlanmasına odaklanılması kararlaştırıldı.
* Seda Nur'dan gelecek Figma tasarımına uygun olarak mobil uygulamanın UI/UX yerleşimlerinin tamamlanması planlandı.
* Başarılı istekler sonucunda kullanıcıya gösterilecek bildirim ve uyarı (Toast/Alert) mekanizmalarının yapılmasına karar verildi.

---

# Sprint 2
*Bekleniyor...*

---

# Sprint 3
*Bekleniyor...*
