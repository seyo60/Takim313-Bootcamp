# 🗺️ Chicago Güvenli Rota Risk Veritabanı

Bu klasör, projenin navigasyon ve rota algoritmasını besleyecek olan statik risk skorlarını (`Chicago_Route_Scores.json`) içerir. Toplamda **2859 eşsiz sokağın** güvenlik profili çıkarılarak API entegrasyonuna hazır hale getirilmiştir.

## 📊 Veri Kaynakları ve Harmanlama (Data Fusion)
Bu skorlar, Chicago Açık Veri Portalı'ndan alınan iki ana veri setinin birleştirilmesiyle oluşturulmuştur:
1. **Suç Verileri:** Sokak bazlı geçmiş güvenlik ihlalleri.
2. **311 Sokak Lambası Arızaları:** Sokakların aydınlatma durumu ve fiziksel tehlike potansiyeli.

## 🧮 Skorlama Matematiği (Heuristic Scoring)
Sokak risk skorları `1.0` ile `10.0` arasında yüzdelik dilim (Percentile Ranking) yöntemiyle hesaplanmıştır.
* **Formül:** `(Suç Skoru * 0.75) + (Lamba Arıza Skoru * 0.25)`
* **1.0 Puan:** En güvenli, risksiz sokak.
* **10.0 Puan:** Suç ve karanlık oranının en yüksek olduğu, rotadan kaçınılması gereken yüksek riskli sokak.

## 💻 Geliştirici Ekipler İçin Entegrasyon Notları (Mobil & Backend)
Harita API'si (Google Maps, OSRM vb.) A noktasından B noktasına alternatif rotalar çizerken bu JSON dosyasını bir **maliyet (cost)** sözlüğü olarak kullanmalıdır.
* JSON dosyasında `Key` olarak sokağın adını aratın.
* Dönen `Value` değerini mesafe maliyetine ekleyin.
* **Önemli Not:** Haritada olan ancak JSON dosyamızda bulunmayan sokakların skorunu varsayılan olarak `1.0` (Tam Güvenli) olarak kabul edebilirsiniz.