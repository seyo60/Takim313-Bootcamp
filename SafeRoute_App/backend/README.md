# Safe Route App - Backend

## Gereksinimler
- Python 3.11+ (proje 3.14 ile test edildi)
- Docker Desktop (PostgreSQL + PostGIS için)

## Kurulum

### 1. Bağımlılıkları yükle

```bash
pip install -r requirements.txt
```

### 2. `.env` dosyasını oluştur

`backend` klasörünün içine `.env` adında bir dosya oluştur, içine şunları yaz (kendi bilgilerinle değiştir):

```
DATABASE_URL=postgresql+asyncpg://kullanici_adi:sifre@localhost:5432/veritabani_adi
WEBHOOK_SECRET=uzun-rastgele-bir-anahtar-yaz
```

`WEBHOOK_SECRET`, dış otomasyon araçlarının (n8n vb.) `/api/v1/webhook/social-risk` endpoint'ine erişebilmesi için gereken paylaşılan anahtardır.

**Not:** `.env` dosyası `.gitignore` içinde olduğu için repoda bulunmaz, her geliştirici kendi lokalinde oluşturmalı.

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

Bu komut, `h3_heatmap` ve `reports` tablolarını (risk kanalları: `risk_historical`, `risk_live`, `risk_social`, `total_risk` dahil) veritabanında oluşturur.

### 5. Test verisi yükle

Eğer `data-science/chicago_clean_data.csv` dosyası mevcutsa:

```bash
python seed.py
```

**Not:** `seed.py` artık sadece veri yazar, şema (tablo yapısı) oluşturmaz/değiştirmez. Şema yönetimi tamamen Alembic'in sorumluluğundadır — `seed.py`'yi çalıştırmadan önce mutlaka `alembic upgrade head` çalıştırılmış olmalı.

### 6. Yol ağı (graph) dosyası

`/api/v1/route` endpoint'i çalışması için bir OSMnx graf dosyasına ihtiyaç duyar. `main.py` içindeki `GRAPH_PATH` değişkeni, gerçek Chicago grafını (`../data-science/chicago.graphml`) işaret eder. Bu dosya büyük olduğu için (~350 MB) repoda bulunmaz, ayrıca temin edilmesi gerekir.

Eğer bu dosya henüz elinde yoksa, test amaçlı küçük bir bölge indirebilirsin:

```bash
python generate_test_graph.py
```

Bu, `test_network.graphml` dosyasını oluşturur (Chicago Loop / downtown bölgesi). Test grafını kullanmak istersen, `main.py` içindeki `GRAPH_PATH` değişkenini geçici olarak bu dosyaya çevir.

### 7. Sunucuyu başlat

```bash
uvicorn main:app --reload
```

**Not:** Gerçek Chicago grafı (~316.000 kavşak, ~1 milyon sokak parçası) kullanıldığında, sunucunun açılışı (graf yükleme + risk ağırlıklarının hesaplanması) yaklaşık 2 dakika sürer. Bu, sadece açılışta bir kez gerçekleşir — rota istekleri saniyeler değil milisaniyeler içinde cevaplanır.

Swagger API dokümantasyonuna şuradan erişebilirsin: http://127.0.0.1:8000/docs

## Migration ile Şema Değişikliği Yapma

`models.py` içinde bir değişiklik yaptığında (yeni kolon, yeni tablo vb.):

```bash
alembic revision --autogenerate -m "değişikliğin kısa açıklaması"
```

Oluşan dosyayı `alembic/versions/` klasöründe gözden geçir, sonra uygula:

```bash
alembic upgrade head
```

**Önemli:**
- `Base.metadata.create_all` veya elle `DROP TABLE` gibi yöntemlerle şema değiştirmeye çalışma — bu veri kaybına yol açar ve Alembic'in migration geçmişini bozar. Şema değişiklikleri her zaman Alembic üzerinden yapılmalı.
- GeoAlchemy2'nin `Geography` kolonları için otomatik oluşturduğu GIST index ile Alembic'in ayrıca ürettiği `create_index` çağrısı çakışabilir (`DuplicateTableError`). Autogenerate migration'ında `location` kolonu için oluşan `op.create_index(...)` satırlarını kontrol et, gerekirse kaldır.

## API Endpoint'leri

| Method | Endpoint | Açıklama |
|--------|----------|----------|
| GET | `/` | Sağlık kontrolü |
| POST | `/api/v1/route` | İki nokta arası en güvenli rotayı hesaplar |
| POST | `/api/v1/report` | Kullanıcıdan gelen anlık tehlike ihbarını kaydeder (arka planda LLM ile analiz edilir) |
| POST | `/api/v1/webhook/social-risk` | Dış otomasyon araçlarının (n8n vb.) sosyal medya/haber risk verisini gönderdiği uç nokta. `X-Webhook-Secret` header'ı zorunludur |
| GET | `/api/v1/heatmap` | Tüm risk noktalarını (`total_risk`) döner |
| GET | `/api/v1/heatmap/nearby` | Belirli bir konuma yakın risk noktalarını döner |

## Risk Hesaplama Mantığı

Her H3 hücresinin nihai risk skoru (`total_risk`), üç kanalın ağırlıklı toplamıdır:

```
total_risk = (risk_historical × 0.4) + (risk_live × 0.5) + (risk_social × 0.1)
```

- **risk_historical**: Geçmiş suç verisinden (`chicago_clean_data.csv`) gelir, `seed.py` ile yüklenir
- **risk_live**: Kullanıcıların anlık ihbarlarından (`/api/v1/report`), LLM analiziyle birikir
- **risk_social**: Dış kaynaklardan (`/api/v1/webhook/social-risk`) gelir

Bu formül **tek bir yerde** (`crud.py` içindeki `_compute_total_risk`) tanımlıdır — yeni bir hesaplama noktası eklenirse mutlaka bu fonksiyon kullanılmalı, formül başka bir yerde tekrar yazılmamalı.

## Proje Yapısı

```
backend/
├── main.py                  # FastAPI uygulaması ve endpoint tanımları
├── config.py                # Ortam değişkenleri (.env okuma)
├── models.py                 # SQLAlchemy veritabanı modelleri
├── crud.py                    # Veritabanı okuma/yazma fonksiyonları + risk formülü
├── routing.py                 # Risk ağırlıklı rota hesaplama mantığı (OSMnx + NetworkX)
├── llm_service.py             # İhbar metni risk analizi (şu an mock, gerçek LLM'e bağlanacak)
├── seed.py                    # CSV'den test verisi yükleme script'i (sadece veri, şema değil)
├── generate_test_graph.py     # Test amaçlı küçük bir OSMnx grafı üretir
├── check_graph_coverage.py    # Bir graf dosyasının kapsadığı alanı raporlar
├── requirements.txt           # Python bağımlılıkları
└── alembic/                   # Veritabanı migration dosyaları
```
