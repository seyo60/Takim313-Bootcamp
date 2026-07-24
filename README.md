<div align="center">

# Takım 313 · Safe Route AI Navigation

**Yapay Zeka ve Teknoloji Akademisi 2026** · Scrum süreçleri, sprint dokümantasyonları ve ürün yönetim merkezi

[![Product Backlog](https://img.shields.io/badge/Notion-Product%20Backlog-000000?style=for-the-badge&logo=notion&logoColor=white)](https://app.notion.com/p/takim313/394780ef363a8083b92feb12eef90a2f?v=c0f780ef363a82ebae3c089f7788f93f&source=copy_link)
[![Sprint](https://img.shields.io/badge/Sprint-2%20Tamamlandı-2ea44f?style=for-the-badge)]()
[![Team](https://img.shields.io/badge/Ekip-5%20Kişi-0969da?style=for-the-badge)]()

</div>

---

## İçindekiler

- [Takım](#-takım-313)
- [Ürün Özeti](#-ürün-özeti)
- [CI/CD](#-cicd)
- [Sprint 1](#-sprint-1)
- [Sprint 2](#-sprint-2)
- [Sprint 3](#-sprint-3)

---

## 👥 Takım 313

| Üye                  | Rol                                               |
| -------------------- | ------------------------------------------------- |
| **Mehmet Ali Ballı** | Scrum Master & LLM Entegrasyonu / Veri Boru Hattı |
| **Seymen Çiçek**     | Product Owner & Backend Geliştiricisi             |
| **Merve Korkut**     | Yapay Zeka (NLP) Modeli Eğitimi                   |
| **Osman Kaya**       | Mobil Uygulama (Frontend) Geliştiricisi           |
| **Seda Nur Tanık**   | UI/UX Tasarımı & Dokümantasyon (Figma)            |

---

## 📦 Ürün Özeti

<table>
<tr>
<td width="50%">

### Ürün İsmi

**Safe Route AI Navigation**

### Hedef Kitle

- Seyahat eden bireyler
- Kadınlar
- Öğrenciler

</td>
<td width="50%">

### Ürün Açıklaması

Kentsel alanlarda yalnız seyahat eden bireylerin fiziksel güvenliğini korumayı amaçlayan yapay zeka destekli bir uygulamadır. Klasik haritaların aksine yalnızca en kısa yolu değil; güvenlik verilerini, sokak aydınlatmasını ve anlık tehlike bildirimlerini işleyerek **En Güvenli Yaşayan Rota** alternatifini sunar.

</td>
</tr>
</table>

<details>
<summary><strong>🚀 Ürün Özellikleri (Product Features)</strong></summary>

<br>

| Özellik                           | Açıklama                                                                                               |
| --------------------------------- | ------------------------------------------------------------------------------------------------------ |
| **AI-Powered Safe Routing**       | Geçmiş suç verileri ile altyapı eksikliklerini harmanlayarak en güvenli rotayı hesaplar                |
| **Real-Time Risk Mapping**        | NLP ile analiz edilen ihbarları H3 altıgen mimarisiyle saniyeler içinde risk ağırlığına dönüştürür     |
| **Community-Driven Alerts**       | GPS takibi ile rota üzerindeki dinamik tehlikeler için proaktif bildirimler üretir                     |
| **Interactive Mapbox Experience** | Chicago başta olmak üzere karmaşık şehir ağlarında akıcı harita navigasyonu                            |
| **Asynchronous Data Sync**        | Dockerize PostGIS + FastAPI ile binlerce sokak segmentinin risk skorunu milisaniyeler içinde günceller |

</details>


---

## ⚙️ CI/CD

Proje, GitHub Actions ile iki bağımsız pipeline kullanır. Workflow dosyaları `.github/workflows/` altındadır ve yalnızca ilgili klasör değiştiğinde (path filtreleri) tetiklenir.

### Pipeline'lar

| Workflow | Tetikleyici | Ne yapar |
|---|---|---|
| **`backend-ci.yml`** | `SafeRoute_App/backend/**` veya `data-science/**` → `push`/`PR` (main, develop) | Python 3.12 kurar (pip cache), sistem kütüphanelerini (geos/spatialindex) yükler, `pip install -r requirements.txt`, **ruff** lint, **pytest** çalıştırır. `main`'e push'ta testler geçerse → Render deploy. |
| **`mobile-ci.yml`** | `SafeRoute_App/mobile-app/**` → `push`/`PR` (main, develop) | Node 20 + `npm ci`, `tsc --noEmit` type-check, `expo lint` (bloke etmez), (varsa) Jest. `main`'e push'ta → `eas build --platform all`. |

### Deploy akışı (backend → Render.com)

1. `main`'e merge → `backend-ci` testleri koşar.
2. Testler geçerse `deploy` job'ı **`production`** environment'ına girer.
3. Environment'a **required reviewers** tanımlıysa, deploy biri **manuel onaylayana** kadar bekler. Onay ekranından önce workflow bir **RLS & CORS hatırlatması** (uyarı) basar — prod'a çıkmadan Supabase RLS ve CORS ayarları gözden geçirilmeli.
4. Onaydan sonra `RENDER_DEPLOY_HOOK_URL`'e `curl POST` ile Render deploy tetiklenir.

### Gerekli GitHub Secrets

Repo **Settings → Secrets and variables → Actions** altına eklenmeli (değerler koda ASLA gömülmez):

| Secret | Kullanıldığı yer | Açıklama |
|---|---|---|
| `RENDER_DEPLOY_HOOK_URL` | backend deploy | Render servisinin "Deploy Hook" URL'i |
| `EXPO_TOKEN` | mobile build | Expo hesabı erişim token'ı (EAS Build) |

> Backend testleri DB'yi ve grafı stub'lar, LLM `mock` modda koşar — bu yüzden **CI testleri için gerçek secret gerekmez**. `DATABASE_URL`, `GEMINI_API_KEY` gibi gerçek prod değerleri Render'ın kendi ortam değişkenlerinde tutulur (bkz. `SafeRoute_App/backend/.env.example` ve `backend/DEPLOYMENT.md`).

### Manuel onay kapısını kurma (bir kerelik)

Repo **Settings → Environments → New environment → `production`** → **Required reviewers** ekleyin. Böylece `main`'e her merge otomatik prod'a çıkmaz; gözden geçirme sonrası elle onaylanır.

---

## 🏃 Sprint 1

<details open>
<summary><strong>📋 Backlog Dağıtma Mantığı (İş Dağılımı)</strong></summary>

<br>

Görev dağılımını ekip üyelerimizin uzmanlık alanlarına, ilgi duydukları teknoloji yığınlarına ve projeyi en hızlı şekilde ayağa kaldırma stratejimize göre yapılandırdık:

| Üye            | Sorumluluk                                                |
| -------------- | --------------------------------------------------------- |
| **Seda Nur**   | Figma UX/UI, Persona ve Lean Canvas dokümantasyonu        |
| **Merve**      | İhbar analizi ve risk skoru üreten NLP modeli eğitimi     |
| **Mehmet Ali** | LLM entegrasyonu, veri boru hattı ve harita algoritmaları |
| **Seymen**     | Backend (API / Veritabanı) geliştirmeleri                 |
| **Osman**      | Frontend (React Native / Mapbox) arayüzü                  |

</details>

<details>
<summary><strong>💬 Daily Scrum Notları</strong></summary>

<br>

Takım içi iletişimimizi çevik (agile) prensiplere uygun olarak WhatsApp ve Meet üzerinden yürüttük. Toplantılarda herkes _"Dün ne yaptım?"_, _"Bugün ne yapacağım?"_ ve _"Beni engelleyen bir sorun var mı?"_ sorularına kısa cevaplar vererek birbirini güncelledi. Ekip üyelerinin müsaitlik durumuna göre yapılan kısa senkronizasyon toplantılarına ait ekran görüntüleri proje dosyalarımız arasında yer almaktadır.

</details>

<details>
<summary><strong>📱 Ürün Durumu</strong></summary>

<br>

İlk sprint olduğu için temel altyapı kurulumları, veri analizi (EDA), veritabanı şemalarının oluşturulması ve uygulamanın harita bazlı ön yüzünün ayağa kaldırılması hedeflenmiş ve görevler başarıyla tamamlanmıştır.

> _Görseller tasarım ve derleme aşaması tamamlandığında eklenecektir._

- [ ] Harita Ön Yüz Ekran Görüntüsü
- [ ] Figma UI/UX Tasarımları
- [ ] Veritabanı Şeması

</details>

<details>
<summary><strong>📊 Sprint Board Updates </strong></summary>

<br>

<img width="1577" height="736" alt="Sprint 1 Proje Yönetimi" src="https://github.com/user-attachments/assets/8962b5b9-10da-4418-ace6-2a597b9d5427" />

</details>

<details>
<summary><strong>📝 Sprint Notları</strong></summary>

<br>

- Navigasyon ağının çıkarılması için OSMnx kullanılarak Chicago yaya graf ağı modellendi ve çıkmaz sokaklar temizlendi.
- Canlı rota pipeline'ı için Uber H3 (Seviye 9) indeksleme altyapısı entegre edildi.
- Veritabanı mimarisi, Docker üzerinde PostgreSQL ve PostGIS kullanılarak asenkron SQLAlchemy yapısıyla ayağa kaldırıldı.
- Backend API uçları FastAPI ile oluşturuldu, CORS izinleri ayarlandı ve Ngrok üzerinden dış dünyaya açıldı.
- Mobil uygulama arayüzü React Native ve Expo ile başlatılıp Mapbox SDK entegrasyonu tamamlandı.
- Uygulamanın asıl temasının **açık (light)** olmasına karar verildi.
- Global hedefler nedeniyle tasarımların ve uygulamanın **İngilizce** dili ile yapılmasına karar verildi.

</details>

<details>
<summary><strong>🎯 Puan & Tamamlama</strong></summary>

<br>

| Metrik         | Değer         |
| -------------- | ------------- |
| **Hedef Puan** | 250           |
| **Durum**      | ✅ Tamamlandı |

Belirlenen temel altyapı ve tasarım hedefleri doğrultusunda Sprint 1 için planlanan 250 puanlık iş yükü eksiksiz olarak tamamlanmıştır.

</details>

<details>
<summary><strong>🔍 Sprint Review</strong></summary>

<br>

- Veri seti üzerindeki eksik koordinatlar temizlendi ve lokasyon veri tipleri standartlaştırıldı.
- Sadece açık alanlarda gerçekleşen, sokak güvenliğini ilgilendiren suçlar filtrelenerek veri analizi (EDA) tamamlandı.
- H3 indeksleri ve yapay zeka risk puanları kullanılarak Chicago graf ağındaki sokak segmentlerine dinamik ağırlık atama pipeline'ı oluşturuldu.
- FastAPI üzerinden `h3_heatmap` ve `user_reports` tabloları için CRUD operasyonları yazılarak `/api/v1/route` ve `/api/v1/heatmap` test uçları çalıştırıldı.
- Swagger API dokümantasyonu hazırlandı ve canlı tünel adresi mobil ekibine teslim edildi.
- Mobil tarafta Mapbox haritası, Chicago Downtown bölgesine odaklanmış şekilde ekrana yansıtıldı.
- iOS ve Android işletim sistemleri için GPS konum izin kodları başarıyla eklendi.
- Figma üzerinde uygulamanın UX ve UI tasarımları oluşturuldu.

**Katılımcılar:** Mehmet, Osman, Seymen, Merve, Seda Nur

</details>

<details>
<summary><strong>🔄 Sprint Retrospektifi (Sprint Retrospective)</strong></summary>

<br>

**Süreç Değerlendirmesi:** Altyapı geliştirirken şelale (waterfall) tuzağına düştüğümüzü fark ettik. Bir sonraki sprintte **Contract-First** yapıya geçme ve **mock** verilerle paralel çalışma kararı aldık.

**Gelecek Sprint Planları:**

- Mobil cihazlardan alınacak GPS koordinatları ile backend'e POST istekleri
- Axios ile mock rota çekme
- Kullanıcı form alanları ve TextArea state kontrolleri
- Figma tasarımına uygun UI/UX yerleşimleri
- Toast/Alert bildirim mekanizmaları

</details>

---

## 🏃 Sprint 2

<details open>
<summary><strong>📱 Ürün Durumu</strong></summary>

<br>

Sprint 2 aşamasında ürün stratejisini netleştirmek adına ilgili dokümantasyonlar oluşturulmuş ve uygulamanın görünümünü netleştiren tasarımlar projeye dahil edilmiştir. Tamamlanan süreçlere ait dosyalar aşağıdadır:

- **UI/UX Figma Tasarımları:**

![Figma Tasarımları](Sprint_2/Sprint2_PM/User%20Scenario%203.png)

- **Persona, Lean Canvas ve Kullanıcı Hikayeleri:**

![Dokümantasyonlar](Sprint_2/Sprint2_PM/Lean%20Canvas%20.jpg)

![SafeRoute Mimarisi](Sprint_2/Sprint2_PM/SafeRoute%20Mimarisi_%20Dinamik%20Risk%20ve%20Rota%20Entegrasyon%20Akışı.png)

- [Persona (PDF)](Sprint_2/Sprint2_PM/SafeRoute%20-%20Persona_compressed.pdf)
- [Kullanıcı Senaryoları (PDF)](<Sprint_2/Sprint2_PM/SafeRoute%20-Users%20Scenario_compressed%20(1)_compressed.pdf>)

</details>

<details>
<summary><strong>📊 Sprint Board Updates </strong></summary>

<br>

- **Sprint 2 Notion Panosu (Genel Görünüm ve Biten İşler):**
  [Product Backlog](https://app.notion.com/p/takim313/394780ef363a8083b92feb12eef90a2f?v=c0f780ef363a82ebae3c089f7788f93f&source=copy_link)
  <img width="1583" height="980" alt="image" src="https://github.com/user-attachments/assets/28d55439-7ee1-4230-8c2d-9e8e72780fcb" />


</details>

<details>
<summary><strong>📝 Sprint Notları</strong></summary>

<br>

- Ürün stratejisini ve kullanıcı kitlesini netleştirmek adına Persona, Yalın Canvas (Lean Canvas) ve Kullanıcı Hikayeleri dokümantasyonları başarıyla oluşturuldu.
- Uygulamanın nihai görünümünü yansıtan Figma UI ekran görüntüleri hazırlandı ve projeye dahil edildi.
- Sprint 2 Burn-down chart (Kalan İş Grafiği) oluşturuldu ve gün bazlı takip edildi.
- NLP modeli için veri araştırmaları yürütüldü ve projenin yapay zeka omurgası için veri setleri genişletildi.
- Backend servislerinin deployment süreçleri tamamlandı ve mobil uygulama ile API arasındaki kontratlar tam uyumlu hale getirildi.

</details>

<details>
<summary><strong>🎯 Sprint İçinde Tamamlanması Beklenen Puan</strong></summary>

<br>

- 160 Puan

</details>

<details>
<summary><strong>📈 Puan Tamamlama Mantığı</strong></summary>

<br>

Belirlenen görev dağılımı doğrultusunda Sprint 2 için ayrılan iş yükü, devam eden LLM entegrasyonu detayları haricinde planlandığı gibi tamamlanmıştır.

</details>

<details>
<summary><strong>🔍 Sprint Gözden Geçirilmesi (Sprint Review)</strong></summary>

<br>

- **Ürün Yönetimi ve Tasarım:** Seda Nur tarafından yürütülen Kullanıcı Senaryosu, Persona ve Lean Canva çalışmaları başarıyla tamamlanarak 'Done' statüsüne alındı.
- **Backend ve Veritabanı (BE):** Alembic ile versiyonlanmış veritabanı şeması ve güvenli seed sistemi oluşturuldu (BE-01).
- OSMnx ve H3 altyapısı kullanılarak gerçek risk ağırlıklı güvenli rota motoru entegrasyonu sağlandı (BE-02).
- Canlı kullanıcı ihbarlarının asenkron risk güncelleme hattı kuruldu (BE-03).
- Mobil uygulama ile Backend API kontratlarının uyumlanması tamamlandı (BE-04).
- Backend dockerize edilerek Render/Supabase deployment altyapısı başarıyla kuruldu (BE-05).
- Backend otomasyon testleri yazıldı ve teknik çalıştırma dokümantasyonu hazırlandı (BE-06).
- **Frontend (Mobil Uygulama):** Osman tarafından Rota görselleştirme ekranı (en kısa ve güvenli rota hatları ile detay paneli) kodlandı.
- Sokak/Rota risk açıklaması bileşeni (LLM Destekli) arayüzü hazırlandı.
- Canlı risk verisiyle heatmap katmanı entegrasyonu yapıldı.
- İhbar formuna acil durum (URGENT) butonu eklendi.
- **Yapay Zeka ve Veri:** Merve tarafından NLP modeli için yeni veri setleri eklendi ve model eğitim araştırmaları yapıldı.
- **Bekleyen İşler (In Progress):** Mehmet Ali tarafından geliştirilen LLM ile sokak güvenlik açıklaması ve anlık ihbar analizi kodlamaları büyük ölçüde tamamlandı.

</details>

<details>
<summary><strong>👥 Sprint Gözden Geçirme Katılımcıları</strong></summary>

<br>

- Mehmet, Osman, Seymen, Merve, Seda Nur

</details>

<details>
<summary><strong>🔄 Sprint Retrospektifi (Sprint Retrospective)</strong></summary>

<br>

- **Süreç Değerlendirmesi:** Sprint 1'de takım olarak organize olmakta ve birlikte çalışmakta çeşitli güçlükler çektik. Farklı dallarda çalışırken yaşanan koordinasyon eksiklikleri süreçleri yavaşlattı. Ancak bu sprintte sorunların üstüne giderek iletişim süreçlerimizi iyileştirdik. Sprint 2'de takım içi organizasyonu çok daha başarılı yürüttük ve bu zorlukların üstesinden gelerek gerçek bir takım olarak eşzamanlı çalışmayı başardık.
- **Gelecek Sprint Planları:** Beklemede olan (In Progress) LLM servis bağlantılarının frontend tarafına tam entegrasyonunun sağlanması planlandı.
- Yakın kullanıcı bildirimi için Fallback UI (Hata Durumu Arayüzü) geliştirmelerinin bitirilmesi hedeflendi.

</details>

---

## 🏃 Sprint 3

<details>
<summary><strong>⏳ Sprint 3 — Bekleniyor</strong></summary>

<br>

> _Bu bölüm Sprint 3 başladığında güncellenecektir._

</details>

---

<div align="center">

**Takım 313** · Yapay Zeka ve Teknoloji Akademisi 2026

</div>
