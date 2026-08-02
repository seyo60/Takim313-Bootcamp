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
- [Kurulum ve Teknik Detaylar](#-kurulum-ve-teknik-detaylar)

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

- Yalnız veya geç saatlerde yürüyen kullanıcılar
- Güvenlik kaygısı yüksek yaya yolcular (özellikle kadınlar)
- Öğrenciler ve kampüs–şehir arasında yürüyenler
- Turistler ve şehri bilmeyen ziyaretçiler
- Mahalle güvenliğine katkı vermek isteyen yerel kullanıcılar
- Misafir olarak harita/rota deneyip gerektiğinde hesap açan kullanıcılar

</td>
<td width="50%">

### Ürün Açıklaması

**SafeRoute**, Chicago’da yaya güvenliğini merkeze alan yapay zeka destekli bir mobil navigasyon uygulamasıdır. Klasik haritaların yalnızca mesafe odaklı yaklaşımının aksine; suç yoğunluğu, sokak aydınlatması ve topluluk ihbarlarını birleştirerek kullanıcıya **en kısa**, **dengeli** ve **daha güvenli** rota alternatifleri sunar.

Uygulama Mapbox haritası üzerinde yer arama, konumdan veya haritadan başlangıç/varış seçimi, risk ısı haritası, doğrulanmış ihbar katmanı ve adım adım canlı navigasyon sağlar. Rota ve sokak riskleri LLM ile kısa Türkçe açıklamalara dönüştürülür; ihbar metinleri NLP ile elenir, geçerli sinyaller yakındaki kullanıcılara sorulur ve onaylanan olaylar haritaya ile canlı riske yansır. Güvenlik skoru bir rehberdir; kesin güvenlik garantisi değildir.

</td>
</tr>
</table>

<details>
<summary><strong>🚀 Ürün Özellikleri (Product Features)</strong></summary>

<br>

| Özellik                            | Açıklama                                                                                        |
| ---------------------------------- | ----------------------------------------------------------------------------------------------- |
| **Onboarding ve misafir deneyimi** | Uygulamayı tanıtan ilk akış; konum izni isteğe bağlı; misafir olarak harita/rota kullanılabilir |
| **Mapbox harita ve konum**         | Chicago odaklı yaya haritası, GPS konumu, “Konumum” ve kuzeye döndürme                          |
| **Arama ve yol tarifi**            | Yer/adres arama; başlangıç ve varışı konumdan veya haritadan seçerek rota oluşturma             |
| **Üç rota profili**                | En Kısa, Dengeli ve Daha Güvenli alternatifleri; mesafe, süre ve risk skoru karşılaştırması     |
| **Rota güvenlik özeti**            | En kısa yola göre risk azalması / ekstra mesafe; suç–aydınlatma–canlı ihbar dökümü              |
| **LLM risk açıklaması**            | Seçilen rota ve sokak/hücre için kısa, anlaşılır Türkçe risk açıklaması ve faktörler            |
| **H3 risk ısı haritası**           | Toplam, suç, aydınlatma ve canlı kanallar; hücre detayında risk skorları                        |
| **Sokak / hücre inceleme**         | Haritaya dokunarak risk seviyesi, veri yok uyarısı ve buradan/buraya rota planlama              |
| **Canlı navigasyon**               | Adım adım yönlendirme, kalan mesafe/süre, sapmada yeniden rota, varış bildirimi                 |
| **Sesli yönlendirme**              | Navigasyonda sesli talimat; Türkçe / İngilizce seçeneği                                         |
| **SOS ve ihbar gönderme**          | Girişli kullanıcı konumuna ihbar bırakır; kategori + metin; acil SOS yolu                       |
| **İhbar içerik analizi (NLP)**     | Güvenlik sinyali taşımayan / konu dışı metinleri eleyerek bildirime sokmaz                      |
| **Yakın alan tanık doğrulama**     | Geçerli ihbar yakındaki kullanıcılara sorulur; onaylanınca haritada yayınlanır                  |
| **Doğrulanmış bildirimler**        | Onaylı olaylar uygulama içi uyarı ve bildirimle duyurulur; profilden aç/kapa                    |
| **Topluluk ihbar katmanı**         | Son bir saatteki doğrulanmış ihbarları anonim marker olarak gösterir ve filtreler               |
| **İhbarlarım**                     | Kullanıcının kendi ihbar geçmişi; durum, kategori, tarih ve metin takibi                        |
| **Hesap ve profil**                | E-posta ile giriş/kayıt, parola sıfırlama, çıkış, hesap silme talebi / iptali                   |
| **Chicago odaklı altyapı**         | Yaya ağı + suç/aydınlatma verisi + H3 risk modeli; doğrulanan ihbar canlı riske işler           |

</details>

<details>
<summary><strong>📋 Product Backlog</strong></summary>

<br>

Ürün backlog'u Notion üzerinde takip edilmektedir:

[![Product Backlog](https://img.shields.io/badge/Notion-Product%20Backlog-000000?style=for-the-badge&logo=notion&logoColor=white)](https://app.notion.com/p/takim313/394780ef363a8083b92feb12eef90a2f?v=c0f780ef363a82ebae3c089f7788f93f&source=copy_link)

</details>

---

## 🏃 Sprint 1

<details open>
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
<summary><strong>🎯 Sprint İçinde Tamamlanması Beklenen Puan</strong></summary>

<br>

- 250 Puan

</details>

<details>
<summary><strong>📈 Puan Tamamlama Mantığı</strong></summary>

<br>

Belirlenen temel altyapı ve tasarım hedefleri doğrultusunda Sprint 1 için planlanan 250 puanlık iş yükü eksiksiz olarak tamamlanmıştır.

| Metrik         | Değer         |
| -------------- | ------------- |
| **Hedef Puan** | 250           |
| **Durum**      | ✅ Tamamlandı |

</details>

<details>
<summary><strong>🔍 Sprint Gözden Geçirilmesi (Sprint Review)</strong></summary>

<br>

- Veri seti üzerindeki eksik koordinatlar temizlendi ve lokasyon veri tipleri standartlaştırıldı.
- Sadece açık alanlarda gerçekleşen, sokak güvenliğini ilgilendiren suçlar filtrelenerek veri analizi (EDA) tamamlandı.
- H3 indeksleri ve yapay zeka risk puanları kullanılarak Chicago graf ağındaki sokak segmentlerine dinamik ağırlık atama pipeline'ı oluşturuldu.
- FastAPI üzerinden `h3_heatmap` ve `user_reports` tabloları için CRUD operasyonları yazılarak `/api/v1/route` ve `/api/v1/heatmap` test uçları çalıştırıldı.
- Swagger API dokümantasyonu hazırlandı ve canlı tünel adresi mobil ekibine teslim edildi.
- Mobil tarafta Mapbox haritası, Chicago Downtown bölgesine odaklanmış şekilde ekrana yansıtıldı.
- iOS ve Android işletim sistemleri için GPS konum izin kodları başarıyla eklendi.
- Figma üzerinde uygulamanın UX ve UI tasarımları oluşturuldu.

</details>

<details>
<summary><strong>👥 Sprint Gözden Geçirme Katılımcıları</strong></summary>

<br>

- Mehmet, Osman, Seymen, Merve, Seda Nur

</details>

<details>
<summary><strong>🔄 Sprint Retrospektifi (Sprint Retrospective)</strong></summary>

<br>

- **Süreç Değerlendirmesi:** Altyapı geliştirirken şelale (waterfall) tuzağına düştüğümüzü fark ettik. Bir sonraki sprintte **Contract-First** yapıya geçme ve **mock** verilerle paralel çalışma kararı aldık.
- **Gelecek Sprint Planları:**
  - Mobil cihazlardan alınacak GPS koordinatları ile backend'e POST istekleri
  - Axios ile mock rota çekme
  - Kullanıcı form alanları ve TextArea state kontrolleri
  - Figma tasarımına uygun UI/UX yerleşimleri
  - Toast/Alert bildirim mekanizmaları

</details>

<details>
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

Sprint 1 daily scrum ekran görüntüleri proje deposunda arşivlenmiştir:

[Sprint 1 Daily Scrum](https://github.com/seyo60/Takim313-Bootcamp/tree/main/Sprint_1/Sprint1_Daily_Scrum)

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

<details>
<summary><strong>📋 Backlog Dağıtma Mantığı (İş Dağılımı)</strong></summary>

<br>

Sprint 2 Notion panosundaki kart atamalarına göre iş dağılımı şöyle yapılandırıldı:

| Üye            | Sorumluluk                                                                                                                                                                                                |
| -------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Seda Nur**   | Lean Canvas, Persona, Kullanıcı Senaryosu, Figma wireframe tasarımı                                                                                                                                       |
| **Merve**      | NLP modeli araştırması, yeni veri setlerinin eklenmesi                                                                                                                                                    |
| **Mehmet Ali** | Sokak güvenlik açıklaması (LLM), anlık ihbar analizi ve yakın kullanıcı bildirimi (LLM); Lean Canvas’a katkı                                                                                              |
| **Seymen**     | Backend: Alembic/seed (BE-01), risk ağırlıklı rota motoru (BE-02), canlı ihbar risk hattı (BE-03), API kontrat uyumu (BE-04), Docker/Render/Supabase (BE-05), otomasyon testleri ve dokümantasyon (BE-06) |
| **Osman**      | Mobil: rota görselleştirme, LLM risk açıklaması UI, heatmap entegrasyonu, URGENT butonu, yakın kullanıcı bildirimi UI, fallback UI, GPS/acil yönlendirme ve mock→gerçek API geçişleri                     |

</details>

<details>
<summary><strong>💬 Daily Scrum Notları</strong></summary>

<br>
Takım içi iletişimimizi çevik (agile) prensiplere uygun olarak WhatsApp ve Meet üzerinden yürüttük. Toplantılarda herkes _"Dün ne yaptım?"_, _"Bugün ne yapacağım?"_ ve _"Beni engelleyen bir sorun var mı?"_ sorularına kısa cevaplar vererek birbirini güncelledi. Ekip üyelerinin müsaitlik durumuna göre yapılan kısa senkronizasyon toplantılarına ait ekran görüntüleri proje dosyalarımız arasında yer almaktadır.
Sprint 2 daily scrum ekran görüntüleri proje deposunda arşivlenmiştir:

[Sprint 2 Daily Scrum](https://github.com/seyo60/Takim313-Bootcamp/tree/main/Sprint_2/Sprint2_Daily_Scrum)

</details>

---

## 🏃 Sprint 3

<details open>
<summary><strong>📱 Ürün Durumu</strong></summary>

<br>

Sprint 3 aşamasında mobil uygulama ekran görüntüleri aşağıdadır:

- **Rota ve harita ekranları:**

<img width="280" alt="Dengeli rota" src="Sprint_3/Sprint3_App_ss/WhatsApp%20Image%202026-08-01%20at%2021.07.12%20(1).jpeg" />

<img width="280" alt="Daha güvenli rota" src="Sprint_3/Sprint3_App_ss/WhatsApp%20Image%202026-08-01%20at%2021.07.12.jpeg" />

<img width="280" alt="Tanık bildirimi" src="Sprint_3/Sprint3_App_ss/WhatsApp%20Image%202026-08-01%20at%2021.07.14%20(4).jpeg" />

<img width="280" alt="Harita katmanları" src="Sprint_3/Sprint3_App_ss/WhatsApp%20Image%202026-08-01%20at%2021.07.14%20(6).jpeg" />

</details>

<details>
<summary><strong>📊 Sprint Board Updates </strong></summary>

<br>

- **Sprint 3 Notion Panosu (Genel Görünüm ve Biten İşler):**
  [SafeRoute - Sprint 3 Panosu](https://app.notion.com/p/takim313/0ff4e2d8c3fa457f8012d127e48196e5?v=3b0780ef363a81cfa9c5000c4822e9c6)
  
<a href="https://github.com/user-attachments/assets/6e0734b7-bad2-40b3-b1c4-59166b3f78e0"><img width="420" alt="Sprint 3 board 1" src="https://github.com/user-attachments/assets/6e0734b7-bad2-40b3-b1c4-59166b3f78e0" /></a>
  <a href="https://github.com/user-attachments/assets/04732aef-df73-4626-9d85-33862091e4b7"><img width="420" alt="Sprint 3 board 2" src="https://github.com/user-attachments/assets/04732aef-df73-4626-9d85-33862091e4b7" /></a>
  <a href="https://github.com/user-attachments/assets/cb72d1cf-1813-4aaf-ab09-9ac9e6748132"><img width="420" alt="Sprint 3 board 3" src="https://github.com/user-attachments/assets/cb72d1cf-1813-4aaf-ab09-9ac9e6748132" /></a>
  <a href="https://github.com/user-attachments/assets/3a5f4d02-2f82-4f6e-9fff-547ac44b575a"><img width="420" alt="Sprint 3 board 4" src="https://github.com/user-attachments/assets/3a5f4d02-2f82-4f6e-9fff-547ac44b575a" /></a>
  <a href="https://github.com/user-attachments/assets/da49de8b-4d37-4ff0-bfdc-6e2aee9c82ce"><img width="420" alt="Sprint 3 board 5" src="https://github.com/user-attachments/assets/da49de8b-4d37-4ff0-bfdc-6e2aee9c82ce" /></a>
  <a href="https://github.com/user-attachments/assets/05be39fc-266d-4019-9e57-56f953b73afe"><img width="420" alt="Sprint 3 board 6" src="https://github.com/user-attachments/assets/05be39fc-266d-4019-9e57-56f953b73afe" /></a>

</details>

<details>
<summary><strong>📝 Sprint Notları</strong></summary>

<br>

- Sprint 3 Notion panosunda planlanan **23 iş kalemi** Done kolonuna taşındı; Backlog / To Do / In Progress boş kaldı.
- Supabase kimlik doğrulama, onboarding ve misafir deneyimi mobil tarafta tamamlandı.
- Profil, İhbarlarım, topluluk ihbar katmanı ve bildirim ayarları entegre edildi.
- 1 km tanık isteği → onay → yayın acil ihbar hattı backend + mobil modal/push ile uçtan uca çalışır hale getirildi.
- Adım adım canlı navigasyon ve sesli yönlendirme (TR/EN) eklendi.
- Compact CSR rota motoru, rota profilleri API’si (En Kısa / Dengeli / Daha Güvenli) ve eşzamanlılık limitleri tamamlandı.
- Chicago suç + 311 aydınlatma ETL hatları, H3 res-10 geçişi ve compact graf / navigasyon sidecar üretimi bitirildi.
- NLP tarafında kategori/ciddiyet, MiniLM shadow kalibrasyonu, konu dışı ihbar eleme ve kümeleme/doğrulama skoru tamamlandı.
- LLM ile rota/sokak risk açıklaması ve acil durum bildirim metinleri (DeepSeek) entegre edildi.
- Sprint 3 Figma ekranları, tanık/acil akış etkileşim tasarımı ve kapanış dokümantasyonu / demo hazırlığı yapıldı.

</details>

<details>
<summary><strong>🎯 Sprint İçinde Tamamlanması Beklenen Puan</strong></summary>

<br>

- 230 Puan _(23 Done iş kalemi)_

</details>

<details>
<summary><strong>📈 Puan Tamamlama Mantığı</strong></summary>

<br>

Sprint 3 Notion panosunda hedeflenen iş kalemlerinin tamamı Done’a alındı (**23/23**). Backlog, To Do ve In Progress kolonları boş kaldığı için sprint kapsamındaki puan yükü eksiksiz tamamlanmış kabul edilmiştir.

| Metrik              | Değer         |
| ------------------- | ------------- |
| **Done**            | 23            |
| **Backlog / To Do / In Progress** | 0 |
| **Durum**           | ✅ Tamamlandı |

</details>

<details>
<summary><strong>🔍 Sprint Gözden Geçirilmesi (Sprint Review)</strong></summary>

<br>

- **Ürün Yönetimi ve Tasarım (Seda Nur):** Sprint 3 yeni ekranların Figma tasarımı (Auth, Onboarding, Profil, Navigasyon); tanık doğrulama ve acil durum akışının etkileşim tasarımı; uygulama içi metin, ikonografi ve erişilebilirlik tutarlılığı; kapanış dokümantasyonu, ekran görüntüleri ve demo sunumu.
- **Backend (Seymen):** Supabase auth ve üretim seviyesi RLS (BE-07); kullanıcı profili, İhbarlarım ve geri alınabilir hesap silme (BE-08); acil ihbar hattı 1 km tanık → onay → yayın (BE-09); Expo push, cihaz ve konum kaydı (BE-10); rota profilleri API’si En Kısa / Dengeli / Daha Güvenli (BE-11); Compact CSR rota motoru, eşzamanlılık limitleri ve hata sözleşmesi (BE-12).
- **Frontend / Mobil (Osman):** Supabase auth ekranları, onboarding ve misafir deneyimi (14); tanık doğrulama modalı, push bildirimi ve bildirim ayarları (16); profil, İhbarlarım ve topluluk ihbar katmanı (17); adım adım canlı navigasyon ve sesli yönlendirme TR/EN (15).
- **Veri Bilimi / Altyapı (Mehmet Ali):** Chicago suç ETL ve `risk_crime` (DS-01); 311 aydınlatma ETL ve `risk_lighting` (DS-02); H3 res-10 geçişi ve ebeveyn yumuşatma (DS-03); compact graf ve navigasyon sidecar (DS-04); rota/sokak risk açıklaması ve acil bildirim metni LLM-03 (DeepSeek).
- **Yapay Zeka / NLP (Merve):** İhbar metni kategori ve ciddiyet modeli (NLP-01); MiniLM gömme ve shadow kalibrasyon (NLP-02); konu dışı ihbar eleme / off-topic guardrail (NLP-03); ihbar kümeleme ve doğrulama skoru V (NLP-04).

</details>

<details>
<summary><strong>👥 Sprint Gözden Geçirme Katılımcıları</strong></summary>

<br>

- Mehmet Ali, Osman, Seymen, Merve, Seda Nur

</details>

<details>
<summary><strong>🔄 Sprint Retrospektifi (Sprint Retrospective)</strong></summary>

<br>

- **Süreç Değerlendirmesi:** Sprint 3’te backend, mobil, NLP, veri boru hattı ve tasarım işleri paralel ilerletildi; Notion panosunda 23 kartın tamamının Done’a alınması takım içi eşzamanlı çalışmanın oturduğunu gösterdi. Auth, tanık doğrulama ve canlı navigasyon gibi uçtan uca akışlar tek sprintte birleştirilerek ürün demoya hazır hale getirildi.
- **İyileştirmeler:** Ortam/konfigürasyon farkları (emülatör vs fiziksel cihaz, API taban URL) demo öncesi erken doğrulanmalı; jüri demosu ve bildirim akışları tek cihaz üzerinden tekrarlanabilir tutulmalı.
- **Gelecek Planlar:** Demo sunumu ve kapanış dokümantasyonunun netleştirilmesi; staging’de uçtan uca prova; performans / son cila maddelerinin izlenmesi.

</details>

<details>
<summary><strong>📋 Backlog Dağıtma Mantığı (İş Dağılımı)</strong></summary>

<br>

Sprint 3 Notion panosundaki kart atamalarına göre iş dağılımı şöyle yapılandırıldı:

| Üye            | Sorumluluk                                                                 |
| -------------- | -------------------------------------------------------------------------- |
| **Seda Nur**   | Figma (Auth/Onboarding/Profil/Navigasyon), tanık-acil etkileşim tasarımı, metin/ikonografi/erişilebilirlik, kapanış dokümantasyonu ve demo |
| **Merve**      | NLP-01…NLP-04: kategori/ciddiyet, MiniLM shadow, off-topic guardrail, kümeleme ve doğrulama skoru |
| **Mehmet Ali** | DS-01…DS-04 (suç/aydınlatma ETL, H3-10, compact graf); LLM-03 rota/sokak risk ve acil bildirim metni |
| **Seymen**     | BE-07…BE-12: Supabase auth/RLS, profil/ihbarlarım, tanık-yayın hattı, Expo push, rota profilleri, Compact CSR motoru |
| **Osman**      | Mobil auth/onboarding/misafir, tanık modalı + bildirimler, profil/İhbarlarım/ihbar katmanı, canlı navigasyon ve sesli yönlendirme |

</details>

<details>
<summary><strong>💬 Daily Scrum Notları</strong></summary>

<br>

Takım içi iletişimimizi çevik (agile) prensiplere uygun olarak WhatsApp ve Meet üzerinden yürüttük. Toplantılarda herkes _"Dün ne yaptım?"_, _"Bugün ne yapacağım?"_ ve _"Beni engelleyen bir sorun var mı?"_ sorularına kısa cevaplar vererek birbirini güncelledi. Ekip üyelerinin müsaitlik durumuna göre yapılan kısa senkronizasyon toplantılarına ait ekran görüntüleri proje dosyalarımız arasında yer almaktadır.

Sprint 3 daily scrum ekran görüntüleri proje deposunda arşivlenmiştir:

[Sprint 3 Daily Scrum](https://github.com/seyo60/Takim313-Bootcamp/tree/main/Sprint_3/Sprint3_Daily_Scrum)

</details>

---

## 🛠️ Kurulum ve Teknik Detaylar

<details>
<summary><strong>⚙️ Gereksinimler</strong></summary>

<br>

| Bileşen | Gereksinim |
| ------- | ---------- |
| **Backend** | Python 3.11+, sanal ortam (`.venv`), PostGIS / Supabase erişimi, `SafeRoute_App/backend/.env` |
| **Mobil** | Node.js + npm, Expo SDK 57, Android emülatör veya geliştirme build’li cihaz, JDK 17 (Android), `SafeRoute_App/mobile-app/.env.local` |
| **Harita** | Mapbox public token (`EXPO_PUBLIC_MAPBOX_TOKEN`) ve native build için download token |
| **Kimlik** | Supabase URL + publishable key (mobil); backend’de ilgili auth ayarları |
| **Not** | Expo Go Mapbox native modülünü yükleyemez; emülatör/cihazda **development build** kullanılmalıdır |

</details>

<details>
<summary><strong>🖥️ Backend nasıl ayağa kaldırılır</strong></summary>

<br>

PowerShell (Windows):

```powershell
Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
cd "SafeRoute_App\backend"
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8002
```

- İlk açılışta compact graf + risk yüklemesi bir süre sürebilir.
- Sağlık kontrolü: tarayıcıda `http://127.0.0.1:8002/docs`
- Port doluysa (`10048`): `netstat -ano | findstr ":8002"` ile PID bulup süreci kapatın, sonra tekrar başlatın.

Detaylı kurulum (migration, seed, Docker PostGIS): `SafeRoute_App/backend/README.md`

</details>

<details>
<summary><strong>📱 Mobil nasıl ayağa kaldırılır</strong></summary>

<br>

Uygulama daha önce build edildiyse native rebuild gerekmez; Metro + kurulu app yeterlidir.

```powershell
$env:JAVA_HOME = "C:\Program Files\Java\jdk-17"
$env:Path = "$env:JAVA_HOME\bin;$env:LOCALAPPDATA\Android\Sdk\platform-tools;$env:Path"
cd "SafeRoute_App\mobile-app"
npx expo start --android
```

- Emülatör API adresi: `.env.local` içinde `EXPO_PUBLIC_API_BASE_URL=http://10.0.2.2:8002`
- Fiziksel cihaz: bilgisayarın LAN IP’si veya `adb reverse` / runbook (`docs/runbooks/physical_android_testing.md`)
- `8081` dolu uyarısında alternatif porta **Y** diyebilir veya eski Metro sürecini kapatabilirsiniz.

İlk kurulum / typecheck / lint: `SafeRoute_App/mobile-app/README.md`

</details>

<details>
<summary><strong>🧪 Test hesapları (lokal)</strong></summary>

<br>

Staging / lokal denemeler için örnek hesaplar (şifre takım içi paylaşımla aynı tutulur):

- `test1@saferoute.local`
- `test2@saferoute.local`
- `test3@saferoute.local`

Jüri demosu: Profil → **İhbar bildirim simülasyonunu başlat** (Magnificent Mile tanık → onay → doğrulanmış bildirim).

</details>

<details>
<summary><strong>📁 Önemli dizinler</strong></summary>

<br>

| Yol | Açıklama |
| --- | ------- |
| `SafeRoute_App/backend` | FastAPI, CRUD, NLP/LLM servisleri, Alembic |
| `SafeRoute_App/mobile-app` | Expo Router mobil istemci |
| `SafeRoute_App/data-science` | Compact graf / ETL çıktıları (büyük dosyalar repoda olmayabilir) |
| `Sprint_1` … `Sprint_3` | Sprint kanıtları (daily scrum, ekran görüntüleri, PM) |

</details>

---

<div align="center">

**Takım 313** · Yapay Zeka ve Teknoloji Akademisi 2026

</div>
