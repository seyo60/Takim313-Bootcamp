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

### 4.2. Render.com (FastAPI container) — gerçekte uygulanan adımlar

> ✅ Bu adımlarla `https://saferoute-backend-zwaq.onrender.com` gerçekten
> deploy edildi ve `/api/v1/route` canlı test edildi. Aşağıdaki notlar,
> kurulum sırasında karşılaşılan gerçek tuzakları da içerir.

1. **Trial/hesap:** Railway trial bittiyse (kart istemeden devam edilemez),
   Render'ın ücretsiz tier'ı **kart istemeden** kayıt olmaya izin veriyor.
   "Fair Use Policy"yi onaylayıp devam edin.
2. New → **Web Service** → GitHub reponuzu bağlayın → `Takim313-Bootcamp`'i seçin.
3. **Language:** Varsayılan olarak yanlış bir dil (ör. Ruby) gelebilir —
   mutlaka **Docker** olarak değiştirin, aksi halde build tamamen yanlış
   şekilde denenir.
4. **Branch:** `develop` (varsayılan `main` gelir, mutlaka değiştirin).
5. **Root Directory:** `SafeRoute_App`
6. **Docker Build Context Directory:** `.` (Root Directory zaten `SafeRoute_App`
   önekini otomatik ekliyor, bu alana sadece `.` yeterli — toplamda `SafeRoute_App/.`)
7. **Dockerfile Path:** `backend/Dockerfile`
   > ⚠️ **Dikkat — en sık yapılan hata:** Bu alan da Root Directory önekini
   > otomatik ekliyor (`SafeRoute_App/` + sizin yazdığınız). Eğer buraya
   > `SafeRoute_App/backend/Dockerfile` yazarsanız, yol
   > `SafeRoute_App/SafeRoute_App/backend/Dockerfile` olur ve dosya
   > bulunamaz. Sadece `backend/Dockerfile` yazın.
8. **Instance Type:** Free ($0/ay, 512 MB RAM, 0.1 CPU — küçük test grafı ve
   mock LLM için yeterli).
9. **Health Check Path:** `/health`
10. **Environment Variables** (Add Environment Variable veya "Add from .env"
    ile toplu ekleyin):
    ```
    DATABASE_URL=postgresql+asyncpg://postgres.<PROJE_REF>:<ŞİFRE>@aws-0-<REGION>.pooler.supabase.com:5432/postgres
    DB_HOST=aws-0-<REGION>.pooler.supabase.com
    DB_PORT=5432
    DB_USER=postgres.<PROJE_REF>
    GRAPH_PATH=backend_test_graph.graphml
    LLM_MODE=mock
    LLM_PROVIDER=gemini
    GEMINI_API_KEY=
    SEED_ON_START=false
    ```
    > `DATABASE_URL` için **Session Pooler** bağlantısını kullanın (Supabase
    > → Connect → Connection Method → Session pooler) — Direct connection
    > IPv6 gerektirir, Render'ın egress'i IPv4'tür, bağlanamaz.
11. **Docker Command / Pre-Deploy Command:** boş bırakın — `Dockerfile`'ın
    `ENTRYPOINT`'i (`entrypoint.sh`: DB bekleme + `alembic upgrade head` +
    uvicorn başlatma) zaten her şeyi otomatik yapıyor.
12. **Deploy Web Service**'e tıklayın. Loglarda şu sırayı görmelisiniz:
    ```
    [entrypoint] Veritabani bekleniyor... → Veritabani hazir.
    [entrypoint] Alembic migration'lari uygulaniyor...
    [entrypoint] Uvicorn baslatiliyor...
    Graf yükleniyor: backend_test_graph.graphml
    Graf yuklendi: N kavsak, M sokak parcasi
    GET /health HTTP/1.1" 200 OK
    Your service is live 🎉
    ```
13. Deploy sonrası mobil `.env` → `EXPO_PUBLIC_API_BASE_URL=https://<servis>.onrender.com`
    ve `src/lib/api.ts` içindeki `USE_MOCK_*` bayraklarını `false` yapın.

**Gerçek Chicago grafı geldiğinde** yapılması gereken tek şey: dosyayı repoya
ekleyip `GRAPH_PATH` env değişkenini güncellemek — kodda hiçbir değişiklik
gerekmez.

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
| `GET /` | – | `{"message": "..."}` — genel sağlık kontrolü |
| `GET /health` | – | `{"status": "ok"}` — Render/Railway health check ucu |
| `POST /api/v1/route` | `{"start":[lng,lat],"end":[lng,lat],"hour":21}` | `{"route":LineString,"distance_m":..,"duration_s":..,"risk_score":..,"shortest":LineString}` |
| `GET /api/v1/heatmap` | – | `[{"lat":..,"lng":..,"total_risk":..}, ...]` |
| `GET /api/v1/heatmap/nearby` | `?lat=..&lng=..&radius=..` (query param) | `[{"lat":..,"lng":..,"total_risk":..}, ...]` — belirli konuma yakın noktalar |
| `POST /api/v1/report` | `{"text":"...","lat":..,"lng":..}` | `{"ok":true,"id":"..."}` |

- `risk_score`: 0=güvenli, 100=tehlikeli (mobil `types.ts` semantiği; backend'in
  içsel `safety_score`'u ters çevrilerek üretilir).
- `duration_s = distance_m / 1.2` (ortalama yürüyüş hızı 1.2 m/s).
- Chicago bounding box (enlem 41.62–42.05, boylam −87.95–−87.50) dışı istekler
  açıklayıcı mesajla **HTTP 400** döner.
- `POST /api/v1/webhook/social-risk` **kaldırıldı** (sosyal medya kanalı kapsam
  dışı; katsayılar `HISTORICAL=0.5, LIVE=0.5, SOCIAL=0.0`).
