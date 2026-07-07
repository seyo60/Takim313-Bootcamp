# Takim313-Bootcamp
Yapay Zeka ve Teknoloji Akademisi 2026 bünyesinde geliştirilen proje için scrum süreçleri, sprint dokümantasyonları ve ürün yönetim şablonu.

# Takım 313
Takım Üyeleri: 
* Mehmet Ali Ballı - Scrum Master & LLM Entegrasyonu / Veri Boru Hattı
* Seymen Çiçek - Product Owner & Backend Geliştiricisi
* Merve Korkut - Yapay Zeka (NLP) Modeli Eğitimi
* Osman Kaya - Mobil Uygulama (Frontend) Geliştiricisi
* Seda Nur Tanık - UI/UX Tasarımı & Dokümantasyon (Figma)

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

# Sprint 1

## Backlog Dağıtma Mantığı (İş Dağılımı)
Görev dağılımını ekip üyelerimizin uzmanlık alanlarına, ilgi duydukları teknoloji yığınlarına ve projeyi en hızlı şekilde ayağa kaldırma stratejimize göre yapılandırdık. Birbirine bağımlı görevleri paralel yürütebilmek amacıyla net roller belirledik:
* **Seda Nur:** Uygulamanın kullanıcı deneyimini (UX/UI) tasarlamak üzere Figma süreçlerini, Persona ve Yalın Canvas dokümantasyonunu üstlenmiştir.
* **Merve:** İhbarları analiz edip risk skoru üretecek yapay zeka modelinin (NLP) eğitilmesine odaklanmaktadır.
* **Mehmet Ali:** Sürecin LLM (Büyük Dil Modeli) entegrasyonu, veri boru hattı (pipeline) ve harita algoritmalarından sorumludur.
* **Seymen:** Sistem altyapısının sorunsuz çalışması ve verilerin yönetimi için Backend (API/Veritabanı) geliştirmelerini yürütmektedir.
* **Osman:** Kullanıcıyla buluşacak olan Frontend (React Native/Mapbox) arayüzünü kodlamaktadır.

## Daily Scrum Notları
Takım içi iletişimimizi çevik (agile) prensiplere uygun olarak WhatsApp ve Meet üzerinden yürüttük. Toplantılarda herkes "Dün ne yaptım?", "Bugün ne yapacağım?" ve "Beni engelleyen bir sorun var mı?" sorularına kısa cevaplar vererek birbirini güncelledi. Ekip üyelerinin müsaitlik durumuna göre yapılan bu kısa senkronizasyon toplantılarına ait ekran görüntüleri (SS) proje dosyalarımız arasında yer almaktadır.

## Ürün Durumu
İlk sprint olduğu için temel altyapı kurulumları, veri analizi (EDA), veritabanı şemalarının oluşturulması ve uygulamanın harita bazlı ön yüzünün ayağa kaldırılması hedeflenmiş ve görevler başarıyla tamamlanmıştır. Projenin şu anki teknik altyapısını yansıtan ilk ekran görüntüleri ve tasarımlar aşağıdadır:

*(Görseller tasarım ve derleme aşaması tamamlandığında eklenecektir)*
* [Harita Ön Yüz Ekran Görüntüsü Bekleniyor]
* [Figma UI/UX Tasarımları Bekleniyor]
* [Veritabanı Şeması Bekleniyor]

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
* Uygulamanın asıl temasının "açık" (light) olmasına karar verildi.
* Globale yönelik hedefler nedeniyle tasarımların ve uygulamanın İngilizce dili ile yapılmasına karar verildi.

## Sprint İçinde Tamamlanması Beklenen Puan
* 250 Puan

## Puan Tamamlama Mantığı
Belirlenen temel altyapı ve tasarım hedefleri doğrultusunda Sprint 1 için planlanan 250 puanlık iş yükü eksiksiz olarak tamamlanmıştır.

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
* **Süreç Değerlendirmesi:** Altyapı geliştirirken şelale (waterfall) tuzağına düştüğümüzü, yani ekiplerin kod yazmak için birbirini beklemek zorunda kaldığını fark ettik. Bu darboğazı aşmak için bir sonraki sprintte "Contract-First" (Sözleşme Odaklı) yapıya geçme ve "mock" (sahte) verilerle birbirimizi beklemeden paralel çalışma kararı aldık.
* **Gelecek Sprint Planları:** Mobil cihazlardan alınacak anlık GPS koordinatları ile backend uçlarına POST istekleri atacak yapının kurulmasına karar verildi.
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
