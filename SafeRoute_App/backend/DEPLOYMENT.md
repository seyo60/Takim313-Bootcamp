# SafeRoute Backend — Kurulum ve Deployment Kılavuzu

Bu doküman, birleştirilmiş backend'in (P0–P3) lokal ve bulut ortamında nasıl
çalıştırılacağını anlatır.

## 1. Lokal Geliştirme (Docker Compose) — Önerilen

```bash
cd SafeRoute_App
# Chicago graf dosyasını data-science/ altına koyun: data-science/chicago.graphml
docker compose up --build
```

- `db` servisi (PostGIS 16) `pg_isready` healthcheck'inden geçmeden `web` başlamaz
  (`depends_on: condition: service_healthy`).
- `web` container'ının `entrypoint.sh`'i sırasıyla: DB'yi bekler → `alembic upgrade head`
  uygular → (`SEED_ON_START=true` ise) `seed.py` çalıştırır → uvicorn'u başlatır.
- İlk kurulumda compose dosyasında `SEED_ON_START: "true"` yapıp Chicago suç verisini
  yükleyin, sonra tekrar `false`'a alın.
- API: http://localhost:8000 — dokümantasyon: http://localhost:8000/docs

## 2. Lokal Geliştirme (Docker'sız)

```bash
cd SafeRoute_App/backend
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env    # DATABASE_URL ve LLM ayarlarını düzenleyin
alembic upgrade head
python seed.py          # ilk kurulumda bir kere
uvicorn main:app --reload
```

## 3. LLM Modu

`.env` üzerinden kontrol edilir:

| Değişken | Değerler | Açıklama |
|---|---|---|
| `LLM_MODE` | `mock` / `live` | mock: API anahtarı gerekmez, kural tabanlı skor. live: gerçek LLM |
| `LLM_PROVIDER` | `gemini` / `deepseek` / `openai` | Birincil tercih: **gemini** |
| `GEMINI_API_KEY` | ... | live + gemini için zorunlu |

**Hata dayanıklılığı:** live modda kota aşımı (429), ağ hatası veya anahtar
eksikliğinde arka plan görevi çökmez; `llm_service.py` kural tabanlı fallback
skoruna (10–100) otomatik geçer ve durumu loglar.

## 4. Bulut Deployment (Render/Railway + Supabase)

### 4.1. Supabase (PostGIS veritabanı)
1. https://supabase.com → yeni proje oluşturun, **Region: East US** (Chicago verisine yakın).
2. SQL Editor'de: `CREATE EXTENSION IF NOT EXISTS postgis;`
3. Project Settings → Database → Connection string'i alın ve `asyncpg` şemasına çevirin:
   `postgresql+asyncpg://postgres:<ŞİFRE>@db.<PROJE>.supabase.co:5432/postgres`

### 4.2. Render.com (FastAPI container)
1. New → Web Service → repo'yu bağlayın.
2. Runtime: **Docker**, Dockerfile Path: `SafeRoute_App/backend/Dockerfile`,
   Docker Build Context: `SafeRoute_App`.
3. Region: **Ohio (US East)** (Chicago'ya en yakın Render bölgesi; Railway'de `us-central`).
4. Environment Variables:
   - `DATABASE_URL` = Supabase asyncpg URL'si
   - `DB_HOST` = `db.<PROJE>.supabase.co`, `DB_USER` = `postgres`
   - `GRAPH_PATH` = `/data-science/chicago.graphml`
   - `LLM_MODE` = `live`, `LLM_PROVIDER` = `gemini`, `GEMINI_API_KEY` = `<anahtar>`
   - İlk deploy'da bir kereliğine `SEED_ON_START` = `true`
5. Health Check Path: `/health`
6. Deploy sonrası mobil `.env` → `EXPO_PUBLIC_API_BASE_URL=https://<servis>.onrender.com`
   ve `src/lib/api.ts` içindeki `USE_MOCK_*` bayraklarını `false` yapın.

> **Not:** `chicago.graphml` repo'da yoksa `generate_test_graph.py` ile küçük bir
> bölge grafı üretilebilir ya da gerçek graf dosyası `data-science/` altına
> eklenmelidir. Graf lifespan'de RAM'e bir kez yüklenir; Render'da en az 512MB
> (gerçek Chicago grafı için 2GB+) RAM'li plan önerilir.

## 5. Test

```bash
cd SafeRoute_App/backend
pip install pytest httpx
python -m pytest tests/ -v
```

12 test: routing (güvenli vs en kısa rota, O(1) risk güncellemesi), üç
endpoint'in mobil kontrat doğrulaması, Chicago-dışı → HTTP 400, webhook'un
kaldırıldığı ve LLM graceful fallback.

## 6. API Kontrat Özeti (mobil ile birebir)

| Uç | İstek | Yanıt |
|---|---|---|
| `POST /api/v1/route` | `{"start":[lng,lat],"end":[lng,lat],"hour":21}` | `{"route":LineString,"distance_m":..,"duration_s":..,"risk_score":..,"shortest":LineString}` |
| `GET /api/v1/heatmap` | – | `[{"lat":..,"lng":..,"total_risk":..}, ...]` |
| `POST /api/v1/report` | `{"text":"...","lat":..,"lng":..}` | `{"ok":true,"id":"..."}` |

- `risk_score`: 0=güvenli, 100=tehlikeli (mobil `types.ts` semantiği; backend'in
  içsel `safety_score`'u ters çevrilerek üretilir).
- `duration_s = distance_m / 1.2` (ortalama yürüyüş hızı 1.2 m/s).
- Chicago bounding box (enlem 41.62–42.05, boylam −87.95–−87.50) dışı istekler
  açıklayıcı mesajla **HTTP 400** döner.
- `POST /api/v1/webhook/social-risk` **kaldırıldı** (sosyal medya kanalı kapsam
  dışı; katsayılar `HISTORICAL=0.5, LIVE=0.5, SOCIAL=0.0`).
