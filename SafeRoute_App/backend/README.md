# Safe Route App - Backend

## Gereksinimler
- Python 3.11+ (proje 3.14 ile test edildi)
- Docker Desktop (PostgreSQL + PostGIS için)

## Kurulum

### 1. Bağımlılıkları yükle

```bash
pip install fastapi uvicorn sqlalchemy asyncpg pydantic-settings geoalchemy2 shapely alembic osmnx networkx h3
```

### 2. `.env` dosyasını oluştur

`backend` klasörünün içine `.env` adında bir dosya oluştur, içine şunu yaz (kendi DB bilgilerinle değiştir):
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

Bu komut, `h3_heatmap` ve `reports` tablolarını (ve gelecekteki tüm şema güncellemelerini) veritabanında oluşturur.

### 5. (Opsiyonel) Test verisi yükle

Eğer `data-science/chicago_clean_data.csv` dosyası mevcutsa:

```bash
python seed.py
```

### 6. (Opsiyonel) Test amaçlı yol ağı (graph) oluştur

`/api/v1/route` endpoint'i çalışması için bir OSMnx graf dosyasına ihtiyaç duyar. Gerçek Chicago graf dosyası henüz hazır değilse, küçük bir test bölgesi indirebilirsin:

```bash
python generate_test_graph.py
```

Bu, `test_network.graphml` dosyasını oluşturur (Chicago Loop / downtown bölgesi).

**Not:** Gerçek/tam Chicago graf dosyası hazır olduğunda, `main.py` içindeki `GRAPH_PATH` değişkenini o dosyanın adıyla güncelle.

### 7. Sunucuyu başlat

```bash
uvicorn main:app --reload
```

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

**Önemli:** `Base.metadata.create_all` veya `seed.py` içindeki `drop_all` gibi yöntemlerle şema değiştirmeye çalışma — bu veri kaybına yol açabilir. Şema değişiklikleri her zaman Alembic üzerinden yapılmalı.

## API Endpoint'leri

| Method | Endpoint | Açıklama |
|--------|----------|----------|
| GET | `/` | Sağlık kontrolü |
| POST | `/api/v1/route` | İki nokta arası en güvenli rotayı hesaplar |
| POST | `/api/v1/report` | Kullanıcıdan gelen anlık tehlike ihbarını kaydeder |
| GET | `/api/v1/heatmap` | Tüm risk noktalarını döner |
| GET | `/api/v1/heatmap/nearby` | Belirli bir konuma yakın risk noktalarını döner |

## Proje Yapısı
`
backend/
├── main.py              # FastAPI uygulaması ve endpoint tanımları
├── config.py            # Ortam değişkenleri (.env okuma)
├── models.py            # SQLAlchemy veritabanı modelleri
├── crud.py               # Veritabanı okuma/yazma fonksiyonları
├── routing.py            # Risk ağırlıklı rota hesaplama mantığı
├── seed.py               # CSV'den test verisi yükleme script'i
├── generate_test_graph.py # Test amaçlı küçük bir OSMnx grafı üretir
└── alembic/              # Veritabanı migration dosyaları
`
