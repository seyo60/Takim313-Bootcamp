# Safe Route App - Backend

## Gereksinimler
- Python 3.11+ (proje Python 3.14 ile doğrulandı)
- Docker Desktop (PostgreSQL + PostGIS için)

## Kurulum

### 1. Bağımlılıkları yükle

```bash
pip install -r requirements.txt
```

### 2. `.env` dosyasını oluştur

`backend` klasörünün içine `.env` adında bir dosya oluştur ve veritabanı bağlantı bilgilerini yaz:

```env
DATABASE_URL=postgresql+asyncpg://kullanici_adi:sifre@localhost:5432/veritabani_adi
WEBHOOK_SECRET=uzun-rastgele-bir-anahtar-yaz
```

`WEBHOOK_SECRET`, dış otomasyon araçlarının (`/api/v1/webhook/social-risk`) endpoint'ine erişebilmesi için gereken paylaşılan anahtardır.

**Not:** `.env` dosyası `.gitignore` içinde olduğu için repoda bulunmaz, her geliştirici kendi lokalinde oluşturmalıdır.

### 3. PostgreSQL + PostGIS container'ını başlat

```bash
docker run --name saferoute-postgres -e POSTGRES_PASSWORD=<sifre> -p 5432:5432 -d postgis/postgis
```

Eğer container zaten varsa:
```bash
docker start saferoute-postgres
```

### 4. Veritabanı migration'larını uygula

```bash
cd backend
alembic upgrade head
```

Bu komut, `h3_heatmap`, `reports` ve `etl_runs` tablolarını (risk kanalları: `risk_crime`, `risk_lighting`, `risk_live`, `total_risk` dahil) veritabanında oluşturur.

### 5. Test verisi yükle

Eğer `data-science/chicago_clean_data.csv` dosyası mevcutsa:

```bash
python seed.py
```

**Not:** `seed.py` sadece veri yazar, şema oluşturmaz. Şema yönetimi tamamen Alembic'in sorumluluğundadır — `seed.py` çalıştırılmadan önce `alembic upgrade head` çalıştırılmış olmalıdır.

### 6. Yol ağı (graph) ve Compact CSR motoru

Sistem production ortamında yüksek performanslı **SciPy Compact CSR Dijkstra** motorunu (`CompactCSREngine`) kullanır. 
`compact_graph.npz` dosyası veya OSMnx graf dosyası (`chicago.graphml`) yüklenerek milisaniyeler içinde rota hesaplaması gerçekleştirilir.

Eğer test amaçlı küçük bir bölge grafı üretmek istersen:

```bash
python generate_test_graph.py
```

### 7. Sunucuyu başlat

```bash
uvicorn main:app --reload
```

Swagger API dokümantasyonuna şuradan erişebilirsin: http://127.0.0.1:8000/docs

---

## Pytest Testlerini Çalıştırma

Tüm backend test takımını çalıştırmak için `backend` klasöründe:

```bash
pytest
```

---

## Migration ile Şema Değişikliği Yapma

`models.py` içinde bir değişiklik yaptığında (yeni kolon, yeni tablo vb.):

```bash
alembic revision --autogenerate -m "değişikliğin kısa açıklaması"
alembic upgrade head
```

---

## API Endpoint'leri

| Method | Endpoint | Açıklama |
|--------|----------|----------|
| GET | `/health` veya `/` | Sistem sağlık ve durum kontrolü |
| POST | `/api/v1/route` | Güvenli ve en kısa rotaları, risk karşılaştırmasını ve veri güncellik zamanlarını döner |
| GET | `/api/v1/heatmap/map` | Mapbox için H3 Resolution 9 GeoJSON poligon risk katmanı (`channel`, `bbox`, `include_no_data` destekli) |
| GET | `/api/v1/reports/map` | Harita gösterimi için son 60 dakikaya ait anonimleştirilmiş topluluk ihbarları |
| GET | `/api/v1/reports/{id}` | IDOR korumalı, takip jetonlu sterilize ihbar durum sorgulama |
| POST | `/api/v1/report` | Kullanıcıdan gelen anlık tehlike ihbarını kaydeder ve arka planda işler |
| GET | `/api/v1/heatmap` | Geriye dönük uyumlu tüm risk noktalarını (`total_risk`, `risk_crime`, `risk_lighting`, `risk_live`) döner |
| GET | `/api/v1/heatmap/nearby` | Belirli bir konuma yakın risk noktalarını döner |
| POST | `/api/v1/webhook/social-risk` | Dış kaynaklardan risk verisi beslemesi |

---

## Risk Hesaplama Mantığı

Her H3 hücresinin nihai risk skoru (`total_risk`), 3 kanalın ağırlıklı toplamıdır:

```
total_risk = (risk_crime × 0.65) + (risk_lighting × 0.20) + (risk_live × 0.15)
```

- **risk_crime (%65)**: Chicago Polis Departmanı tarihsel suç verilerinden (`etl_crime.py`) hesaplanır.
- **risk_lighting (%20)**: Chicago 311 Sokak Aydınlatma Arızası verilerinden (`etl_lighting.py`) hesaplanır.
- **risk_live (%15)**: Kullanıcıların anlık ihbarlarından (`/api/v1/report`), sınırlı birikim (bounded accumulation) formülüyle güncellenir:
  $$R_{\text{live, yeni}} = 1.0 - (1.0 - R_{\text{live, eski}}) \times (1.0 - \text{Etki})$$

Bu formül **tek bir yerde** (`crud.py` içindeki `_compute_total_risk`) tanımlıdır.

---

## Proje Yapısı

```
backend/
├── main.py                  # FastAPI uygulaması ve endpoint tanımları
├── config.py                # Ortam değişkenleri okuma (.env)
├── models.py                # SQLAlchemy veritabanı modelleri
├── crud.py                  # Veritabanı fonksiyonları + risk hesaplama mantığı
├── routing_engine.py        # SciPy Compact CSR Dijkstra & NetworkX rotalama motorları
├── routing.py               # Rotalama yardımcı fonksiyonları ve dönüştürücüler
├── etl_crime.py             # Suç verisi ETL güncelleme betiği
├── etl_lighting.py          # Sokak aydınlatma verisi ETL güncelleme betiği
├── seed.py                  # CSV'den test verisi yükleme script'i
├── generate_test_graph.py    # Test amaçlı küçük OSMnx grafı üretir
├── requirements.txt          # Python bağımlılıkları
├── alembic/                 # Veritabanı migration dosyaları
└── tests/                   # Pytest birim ve entegrasyon test takımı (49 test)
```
