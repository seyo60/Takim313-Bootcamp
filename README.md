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

<details>
<summary><strong>🔗 Product Backlog</strong></summary>

<br>

- [Product Backlog — Notion](https://app.notion.com/p/edebiyat/38f780ef363a80579a7dce0ee1e54335?v=38f780ef363a80a9a200000c88d2153f&source=copy_link)

</details>

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
<summary><strong>📊 Proje Yönetimi (Project Management)</strong></summary>

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
<summary><strong>🔄 Sprint Retrospective</strong></summary>

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
<summary><strong>📱 Ürün Durumu & Görseller</strong></summary>

<br>

Sprint 2 aşamasında ürün stratejisini netleştirmek adına ilgili dokümantasyonlar oluşturulmuş ve uygulamanın görünümünü netleştiren tasarımlar projeye dahil edilmiştir.

<br>

<table>
<tr>
<td align="center" width="50%">

#### 🎨 UI/UX Figma Tasarımları

<!-- Görsel yolunu kendi dosyanızla değiştirin -->
<img src="gorsel_yolu.png" alt="Figma Tasarımları" width="100%" />

<sub><code>gorsel_yolu.png</code> → Figma ekran görüntüleri</sub>

</td>
<td align="center" width="50%">

#### 📄 Persona, Lean Canvas & Kullanıcı Hikayeleri

<!-- Görsel yolunu kendi dosyanızla değiştirin -->
<img src="gorsel_yolu.png" alt="Persona ve Dokümantasyonlar" width="100%" />

<sub><code>gorsel_yolu.png</code> → Persona / Lean Canvas / User Stories</sub>

</td>
</tr>
</table>

</details>

<details>
<summary><strong>📊 Proje Yönetimi (Project Management)</strong></summary>

<br>

- **Sprint 2 Notion Panosu (Genel Görünüm ve Biten İşler):**
  [Product Backlog — Sprint 2](https://app.notion.com/p/takim313/394780ef363a8083b92feb12eef90a2f?v=c0f780ef363a82ebae3c089f7788f93f&source=copy_link)

</details>

<details>
<summary><strong>📝 Sprint Notları</strong></summary>

<br>

- Ürün stratejisini ve kullanıcı kitlesini netleştirmek adına Persona, Lean Canvas ve Kullanıcı Hikayeleri dokümantasyonları oluşturuldu.
- Uygulamanın nihai görünümünü yansıtan Figma UI ekran görüntüleri hazırlandı ve projeye dahil edildi.
- Sprint 2 Burn-down chart oluşturuldu ve gün bazlı takip edildi.
- NLP modeli için veri araştırmaları yürütüldü ve veri setleri genişletildi.
- Backend servislerinin deployment süreçleri tamamlandı; mobil uygulama ile API kontratları uyumlu hale getirildi.

</details>

<details>
<summary><strong>🎯 Puan & Tamamlama</strong></summary>

<br>

| Metrik         | Değer                                            |
| -------------- | ------------------------------------------------ |
| **Hedef Puan** | 160                                              |
| **Durum**      | ✅ Tamamlandı (LLM entegrasyonu detayları hariç) |

Belirlenen görev dağılımı doğrultusunda Sprint 2 için ayrılan iş yükü, devam eden LLM entegrasyonu detayları haricinde planlandığı gibi tamamlanmıştır.

</details>

<details>
<summary><strong>🔍 Sprint Review</strong></summary>

<br>

**Ürün Yönetimi & Tasarım**

- Kullanıcı Senaryosu, Persona ve Lean Canvas çalışmaları tamamlandı _(Seda Nur)_

**Backend & Veritabanı**

- Alembic ile versiyonlanmış veritabanı şeması ve güvenli seed sistemi _(BE-01)_
- OSMnx + H3 ile gerçek risk ağırlıklı güvenli rota motoru _(BE-02)_
- Canlı kullanıcı ihbarlarının asenkron risk güncelleme hattı _(BE-03)_
- Mobil–Backend API kontrat uyumu _(BE-04)_
- Render/Supabase deployment altyapısı _(BE-05)_
- Otomasyon testleri ve teknik dokümantasyon _(BE-06)_

**Frontend (Mobil)**

- Rota görselleştirme ekranı (en kısa + güvenli rota hatları) _(Osman)_
- Sokak/Rota risk açıklaması bileşeni (LLM destekli) arayüzü
- Canlı risk verisiyle heatmap katmanı
- İhbar formuna acil durum (URGENT) butonu

**Yapay Zeka & Veri**

- NLP modeli için yeni veri setleri ve eğitim araştırmaları _(Merve)_

**Devam Eden**

- LLM ile sokak güvenlik açıklaması ve anlık ihbar analizi _(Mehmet Ali)_

**Katılımcılar:** Mehmet, Osman, Seymen, Merve, Seda Nur

</details>

<details>
<summary><strong>🔄 Sprint Retrospective</strong></summary>

<br>

**Süreç Değerlendirmesi:** Sprint 1'de koordinasyon eksiklikleri süreçleri yavaşlattı. Sprint 2'de iletişimi iyileştirerek eşzamanlı çalışmayı başardık.

**Gelecek Sprint Planları:**

- LLM servis bağlantılarının frontend'e tam entegrasyonu
- Yakın kullanıcı bildirimi için Fallback UI geliştirmeleri

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
