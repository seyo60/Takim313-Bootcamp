# Safe Route App - Backend

> Kapsamlı deploy talimatları (Docker Compose, Render + Supabase adımları)
> için: **[DEPLOYMENT.md](./DEPLOYMENT.md)**. Bu dosya sadece lokal geliştirme
> kurulumunu ve API/mimari referansını anlatır.

## Gereksinimler
- Python 3.11+ (proje 3.14 ile test edildi)
- Docker Desktop (lokal PostGIS için) **veya** bir Supabase projesi

## Kurulum (Docker'sız, lokal Python ile)

### 1. Bağımlılıkları yükle
```bash
pip install -r requirements.txt
```

### 2. `.env` dosyasını oluştur
```bash
cp .env.example .env
```
Ardından `.env` içindeki `DATABASE_URL`'i kendi veritabanınıza göre düzenleyin:

```
# Lokal Docker PostGIS için:
DATABASE_URL=postgresql+asyncpg://saferoute:saferoute@localhost:5432/saferoute

# Supabase (Session Pooler, IPv4 uyumlu) için:
DATABASE_URL=postgresql+asyncpg://postgres.<PROJE_REF>:<SIFRE>@aws-0-<REGION>.pooler.supabase.com:5432/postgres
```

> **Not:** `.env` dosyası `.gitignore` içinde olduğu için repoda bulunmaz ve
> **asla commit edilmemelidir** — içinde gerçek veritabanı şifresi ve LLM API
> anahtarları olur. Her geliştirici/ortam kendi `.env`'ini oluşturur.

> **Supabase kullanıyorsanız:** Direct connection **IPv6** kullanır ve çoğu
> lokal ağ/CI ortamı (ör. Railway'in egress'i) sadece IPv4 destekler. Bu yüzden
> **Session Pooler** bağlantısını kullanın (Supabase panelinde: Connect →
> Connection Method → Session pooler). Ayrıca kullanıcı adının
> `postgres.<PROJE_REF>` formatında olduğuna dikkat edin (sadece `postgres`
> değil).

### 3. Veritabanını hazırla

**Docker ile (lokal PostGIS):**
```bash
docker run --name saferoute-postgres -e POSTGRES_USER=saferoute -e POSTGRES_PASSWORD=saferoute -e POSTGRES_DB=saferoute -p 5432:5432 -d postgis/postgis:16-3.4
```
Container zaten varsa: `docker start saferoute-postgres`

**Supabase ile:** SQL Editor'de bir kere çalıştırın:
```sql
CREATE EXTENSION IF NOT EXISTS postgis;
```

### 4. Migration'ları uygula
```bash
alembic upgrade head
```
Bu komut `h3_heatmap` ve `reports` tablolarını (risk kanalları:
`risk_historical`, `risk_live`, `risk_social`, `total_risk` dahil) oluşturur.

### 5. Test verisi yükle
`../data-science/chicago_clean_data.csv` dosyası mevcutsa:
```bash
python seed.py
```
> `seed.py` yalnızca veri yazar, şema oluşturmaz/değiştirmez — önce mutlaka
> `alembic upgrade head` çalıştırılmış olmalı.
>
> **Bilinen kısıt:** Şu an bu CSV yalnızca birkaç sokak segmenti içeriyor
> (tüm Chicago değil) — data-science ekibinin toplu (batch) çalıştırması
> bekleniyor. Format: `osmid,name,anlik_risk,geometry` (geometry: WKT
> `LINESTRING (lng lat, lng lat, ...)`, `anlik_risk`: 0-10 arası).

### 6. Yol ağı (graph) dosyası
`/api/v1/route` endpoint'i çalışması için bir OSMnx graf dosyasına ihtiyaç
duyar. `.env`'deki `GRAPH_PATH` değişkeni, gerçek Chicago grafını
(`../data-science/chicago.graphml`) işaret eder. Bu dosya büyük olduğu için
repoda bulunmaz, ayrıca temin edilmelidir.

Elinizde henüz yoksa, test amaçlı küçük bir bölge grafı üretebilirsiniz:
```bash
python generate_test_graph.py
```
Bu `test_network.graphml` dosyasını oluşturur (Chicago Loop/downtown). Test
grafını kullanmak için `.env`'de `GRAPH_PATH`'i geçici olarak bu dosyaya
çevirin.

### 7. Sunucuyu başlat
```bash
uvicorn main:app --reload
```
> Gerçek Chicago grafı (~316.000 kavşak) kullanıldığında açılış (graf yükleme
> + risk ağırlıklarının hesaplanması) yaklaşık 2 dakika sürebilir — bu sadece
> açılışta bir kez olur, rota istekleri milisaniyeler içinde cevaplanır.

Swagger dokümantasyonu: http://127.0.0.1:8000/docs

## Docker Compose ile (önerilen — tek komutla DB + backend)
```bash
docker compose up --build
```
`db` servisi (PostGIS) healthcheck'ten geçmeden `web` başlamaz; `web`
container'ı içinde DB'yi bekleme + `alembic upgrade head` + (opsiyonel) seed
otomatik çalışır. Detaylar: [DEPLOYMENT.md](./DEPLOYMENT.md).

## LLM Ayarları

`.env` üzerinden kontrol edilir:

| Değişken | Değerler | Açıklama |
|---|---|---|
| `LLM_MODE` | `mock` / `live` | `mock`: API anahtarı gerekmez, kural tabanlı skor üretir. `live`: gerçek LLM çağrısı yapar |
| `LLM_PROVIDER` | `gemini` / `deepseek` / `openai` | Birincil tercih: **gemini** |
| `GEMINI_API_KEY` | ... | `live` + `gemini` kombinasyonu için zorunlu |

`llm_service.py`, `live` modda `llm_integration/services/report_analyzer.py`
üzerinden gerçek LLM'i çağırır. **Hata dayanıklılığı:** kota aşımı (429), ağ
hatası veya eksik API anahtarında arka plan görevi çökmez — otomatik olarak
kural tabanlı (keyword eşleştirmeli) güvenli fallback skoruna (10-100 arası)
geçer ve durumu loglar.

## Migration ile Şema Değişikliği Yapma

`models.py` içinde bir değişiklik yaptığınızda (yeni kolon, yeni tablo vb.):
```bash
alembic revision --autogenerate -m "değişikliğin kısa açıklaması"
```
Oluşan dosyayı `alembic/versions/` klasöründe gözden geçirin, sonra uygulayın:
```bash
alembic upgrade head
```

**Önemli:**
- `Base.metadata.create_all` veya elle `DROP TABLE` gibi yöntemlerle şema
  değiştirmeye çalışmayın — bu veri kaybına yol açar ve Alembic'in migration
  geçmişini bozar. Şema değişiklikleri her zaman Alembic üzerinden yapılmalı.
- GeoAlchemy2'nin `Geography` kolonları için otomatik oluşturduğu GIST index
  ile Alembic'in ayrıca ürettiği `create_index` çağrısı çakışabilir
  (`DuplicateTableError`). Autogenerate migration'ında `location` kolonu için
  oluşan `op.create_index(...)` satırlarını kontrol edin, gerekirse kaldırın.

## API Endpoint'leri (mobil ile birebir kontrat)

| Method | Endpoint | Açıklama |
|---|---|---|
| GET | `/` | Sağlık kontrolü |
| GET | `/health` | Container/Render/Railway health check |
| POST | `/api/v1/route` | İki nokta arası en güvenli rota + kıyaslama için en kısa rota |
| POST | `/api/v1/report` | Anlık tehlike ihbarı (arka planda LLM ile analiz edilir) |
| GET | `/api/v1/heatmap` | Tüm risk noktalarını düz dizi olarak döner |
| GET | `/api/v1/heatmap/nearby` | Belirli bir konuma yakın risk noktalarını döner |

> **`POST /api/v1/webhook/social-risk` kaldırıldı.** Sosyal medya/n8n
> entegrasyonu MVP kapsamı dışına alındı (bkz.
> `BACKEND_IMPLEMENTATION_MASTER_PLAN.md`). `risk_social` kolonu şemada Faz 2
> için duruyor ama katsayısı 0 olduğundan hesaba katılmıyor.

### `POST /api/v1/route`
```json
// İstek
{ "start": [-87.630, 41.878], "end": [-87.624, 41.884], "hour": 21 }

// Yanıt
{
  "route":      { "type": "LineString", "coordinates": [[lng, lat], ...] },
  "distance_m": 1840.0,
  "duration_s": 1533.3,
  "risk_score": 27.5,
  "shortest":   { "type": "LineString", "coordinates": [[lng, lat], ...] }
}
```
- `risk_score`: 0 (güvenli) – 100 (tehlikeli).
- `duration_s = distance_m / 1.2` (ortalama yürüyüş hızı).
- `shortest`: risk ağırlığı kullanmadan, NetworkX üzerinde sadece `length`
  baz alınarak hesaplanan standart en kısa rota (kıyaslama ekranı için).
- Chicago bounding box dışı koordinatlar için: **HTTP 400** + açıklayıcı mesaj.

### `GET /api/v1/heatmap`
```json
[
  { "lat": 41.88, "lng": -87.63, "total_risk": 65.0 },
  { "lat": 41.89, "lng": -87.64, "total_risk": 12.5 }
]
```

### `POST /api/v1/report`
```json
// İstek
{ "text": "sokakta silahlı biri var", "lat": 41.876, "lng": -87.632 }

// Yanıt (HTTP 201)
{ "ok": true, "id": "42" }
```
Analiz **arka planda** yapılır (senkron dönmez) — LLM/kural tabanlı skor
hesaplanıp `h3_heatmap.risk_live` güncellenir, RAM'deki rota grafı O(1)
karmaşıklıkla (yalnızca ilgili sokak segmentleri) güncellenir.

## Risk Hesaplama Mantığı

Her H3 hücresinin nihai risk skoru (`total_risk`), **2 kanallı** ağırlıklı
toplamdır (MVP kararı — sosyal medya kanalı kapsam dışı):

```
total_risk = (risk_historical × 0.5) + (risk_live × 0.5) + (risk_social × 0.0)
```

- `risk_historical`: Geçmiş suç verisinden (`chicago_clean_data.csv`) gelir,
  `seed.py` ile yüklenir.
- `risk_live`: Kullanıcıların anlık ihbarlarından (`/api/v1/report`), LLM
  analiziyle birikir.
- `risk_social`: Şemada duruyor ama **kullanılmıyor** (katsayı 0.0, Faz 2).

Bu formül **tek bir yerde** (`crud.py` içindeki `HISTORICAL_WEIGHT` /
`LIVE_WEIGHT` / `SOCIAL_WEIGHT` sabitleri ve `_compute_total_risk`) tanımlıdır
— `seed.py` bu sabitleri `crud.py`'den import eder, kendi kopyasını tutmaz.
Yeni bir hesaplama noktası eklenirse mutlaka bu fonksiyon/sabitler
kullanılmalı, formül başka bir yerde tekrar yazılmamalıdır.

## Test

```bash
pip install pytest httpx
python -m pytest tests/ -v
```
DB gerektirmeyen 12 test: güvenli rota vs en kısa rota, O(1) risk güncellemesi,
üç endpoint'in mobil kontrat doğrulaması, Chicago-dışı → HTTP 400, webhook'un
kaldırıldığının doğrulanması, LLM graceful fallback.

## Proje Yapısı

```
backend/
├── main.py                  # FastAPI uygulaması ve endpoint tanımları
├── config.py                 # Ortam değişkenleri (.env okuma, tek Settings kaynağı)
├── models.py                 # SQLAlchemy veritabanı modelleri
├── crud.py                    # Veritabanı okuma/yazma fonksiyonları + risk formülü
├── routing.py                 # Risk ağırlıklı rota + en kısa rota hesaplama (OSMnx + NetworkX)
├── llm_service.py             # İhbar metni risk analizi (live LLM + kural tabanlı fallback)
├── llm_integration/            # Gemini/DeepSeek/OpenAI istemcisi, guardrail'ler, promptlar
├── seed.py                    # CSV'den test verisi yükleme script'i (sadece veri, şema değil)
├── generate_test_graph.py     # Test amaçlı küçük bir OSMnx grafı üretir
├── check_graph_coverage.py    # Bir graf dosyasının kapsadığı alanı raporlar
├── tests/                     # pytest test suite'i (DB gerektirmez)
├── requirements.txt           # Python bağımlılıkları
├── Dockerfile                  # Container imajı (entrypoint.sh ile)
├── entrypoint.sh                # DB bekleme + otomatik migration + uvicorn başlatma
├── .env.example                 # Örnek ortam değişkenleri (gerçek .env asla commit edilmez)
└── alembic/                    # Veritabanı migration dosyaları
```
