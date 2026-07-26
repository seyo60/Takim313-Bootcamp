# 🗺️ Chicago Güvenli Rota Risk Veritabanı

> **Güncelleme (2026-07-25):** `chicago_clean_data.csv` artık gerçek, koordinatlı
> Chicago Açık Veri Portalı kayıtlarından üretiliyor (5.099 H3 hücresi).
> `build_risk_dataset.py` script'i ile üretilir — bkz. aşağıdaki "Güncel
> Üretim Pipeline'ı" bölümü. `Chicago_Route_Scores.json` (2.859 blok-bazlı
> skor) artık **kullanılmıyor**; ayrıntı için altındaki not.

## 📊 Veri Kaynakları ve Harmanlama (Data Fusion)
Skorlar, Chicago Açık Veri Portalı'ndan (Socrata API, `data.cityofchicago.org`)
canlı çekilen iki ana veri setinin H3 (çözünürlük 9) hücresi bazında
birleştirilmesiyle oluşturulur:
1. **Suç Verileri** (`ijzp-q8t2` — Crimes 2001-Present): son 12 ay, yalnızca
   açık/kamusal alanlarda gerçekleşen (sokak, kaldırım, ara sokak, park,
   otopark, CTA durağı vb.) olaylar filtrelenir.
2. **311 Sokak Lambası Arızaları** (`v6vf-nfxy` — birleşik 311 sistemi,
   `sr_type='Street Light Out Complaint'` / `'Alley Light Out Complaint'`):
   son 24 ay.

## 🧮 Skorlama Matematiği (Heuristic Scoring)
H3 hücresi risk skorları `0` ile `100` arasında yüzdelik dilim (Percentile
Ranking) yöntemiyle hesaplanır — her kanal kendi içinde ayrı ayrı
sıralanıp 0-100'e ölçeklenir, sonra ağırlıklı toplanır:
* **Formül:** `(Suç Yüzdelik Dilimi * 0.75) + (Lamba Arıza Yüzdelik Dilimi * 0.25)`
* **0 Puan:** Görece en güvenli hücre (veri setindeki diğerlerine göre).
* **100 Puan:** Suç ve karanlık oranının en yüksek olduğu hücre.

> ⚠️ **Ölçek notu:** Eski JSON `1.0-10.0` aralığındaydı. Backend'in
> `crud.py`'deki ağırlıklı formülü (`total_risk = historical*0.5 + live*0.5`)
> `live` kanalını (kullanıcı ihbarları, LLM skoru) `0-100` ölçekte üretiyor —
> eski `1-10` skorla birleştirildiğinde `historical` kanalı pratikte hiç
> ağırlık taşımıyordu. Yeni pipeline `0-100`'e taşıyarak bunu düzeltiyor.

## 🔄 Güncel Üretim Pipeline'ı — `build_risk_dataset.py`
```bash
cd SafeRoute_App/data-science
<backend_venv>/python.exe build_risk_dataset.py
```
Bu script sırasıyla: (1) Socrata API'den suç + 311 lamba verisini sayfalama
ile çeker, (2) ham veriyi `raw/` altına kaydeder (XGBoost/model eğitimi için
hammadde), (3) her kaydı H3 (res 9) hücresine indirger, (4) yüzdelik dilim +
ağırlıklı formülü uygular, (5) `chicago_clean_data.csv`'yi
`backend/seed.py`'nin beklediği şemada (`osmid,name,anlik_risk,geometry`)
yeniden yazar. Backend tarafında `alembic upgrade head` + `python seed.py`
çalıştırıldığında bu veri `h3_heatmap` tablosuna gerçek risk değerleriyle dolar.

`fetch_bonus_datasets.py` ek özellik (feature) hammaddesi çeker (boş bina
şikayetleri, CTA otobüs durakları) — şu anki formüle dahil değil, ileride
XGBoost modeli için `raw/` altında saklanır.

## ⛔ Neden eski `Chicago_Route_Scores.json` artık kullanılmıyor
JSON'daki anahtarlar sokak adı değil, **blok bazlı adres**
("100A N LOTUS AVE"). Bunları harita koordinatına bağlamak 2.859 adresi tek
tek geocode etmeyi ya da OSM sokak adlarıyla kırılgan metin eşleştirmesi
yapmayı gerektiriyordu. Yeni pipeline bunun yerine zaten kendi enlem/boylamıyla
gelen ham suç/311 verisini doğrudan kullanıyor — hem daha güvenilir hem de
2.859 yerine binlerce şehir çapında hücre kapsıyor.