# backend/main.py
<<<<<<< Updated upstream
from fastapi import FastAPI, Depends, HTTPException, Query, status, Request, BackgroundTasks, Header
=======
"""
SafeRoute FastAPI backend - mobil (end-to-end.md) kontratlariyla birebir uyumlu.

KONTRAT OZETI (BACKEND_IMPLEMENTATION_MASTER_PLAN.md Bolum 2):
  POST /api/v1/route   : { start: [lng,lat], end: [lng,lat], hour? }
                         -> { route, distance_m, duration_s, risk_score, shortest }
  GET  /api/v1/heatmap : -> [ { lat, lng, total_risk }, ... ]  (flat array)
  POST /api/v1/report  : { text, lat, lng } -> { ok: true, id: "..." }

KAPSAM DISI: /api/v1/webhook/social-risk ucu ve n8n/sosyal medya entegrasyonu
MVP kapsamindan cikarildi; webhook secret'i config'den tamamen kaldirildi.
(Faz 2'de gerekirse git gecmisinden geri alinabilir.)
"""
from datetime import datetime, timezone
from fastapi import FastAPI, Depends, HTTPException, Query, status, Request, BackgroundTasks
>>>>>>> Stashed changes
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import contextlib
import asyncio
import time
import h3

from config import settings
import crud
import routing
from routing_engine import get_routing_engine
from llm_service import analyze_report_risk_with_llm

engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Graf dosyasının yolu - Chicago grafı
GRAPH_PATH = "../data-science/chicago.graphml"


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


<<<<<<< Updated upstream
async def verify_webhook_secret(x_webhook_secret: str = Header(...)):
    """
    n8n gibi dis otomasyon araclarinin webhook'a erisebilmesi icin basit
    bir paylasilan-anahtar kontrolu. .env icindeki WEBHOOK_SECRET ile
    ayni deger 'X-Webhook-Secret' header'inda gonderilmezse istek reddedilir.

    NOT: Bu, production icin minimum seviye bir koruma. Ileride HMAC imza
    dogrulamasi gibi daha guclu bir yonteme gecmek gerekebilir.
    """
    if x_webhook_secret != settings.webhook_secret:
        raise HTTPException(status_code=403, detail="Gecersiz webhook anahtari")


async def process_report_background_task(app_state, latitude: float, longitude: float, text: str):
=======
async def process_report_background_task(app_state, latitude: float, longitude: float, text: str, report_id: str | None = None):
>>>>>>> Stashed changes
    """
    Arka planda calisan orkestrator:
    1. Ihbarin H3 hucresini bulur.
    2. LLM'e metni sorup dinamik risk cezasini alir.
    3. Veritabanini gunceller ve AGIRLIKLI FORMULLE hesaplanmis NIHAI
       total_risk degerini geri alir (crud.py - tek dogruluk kaynagi).
    4. RAM'deki motoru bu NIHAI degerle gunceller (ekleme degil, dogrudan yazma) -
       boylece RAM ve DB HER ZAMAN ayni sayiyi gosterir.
    5. Raporun haritada gösterilebilir statüsünü ('accepted') günceller.
    """
    try:
        report_h3_cell = h3.latlng_to_cell(latitude, longitude, routing.H3_RESOLUTION)

        dynamic_risk_penalty = await analyze_report_risk_with_llm(text)
        print(f"\n[Arka Plan] İhbar: '{text}' -> Üretilen Ceza Puanı: {dynamic_risk_penalty}")

        # Once DB'yi guncelle, agirlikli formulle hesaplanmis NIHAI degeri al
        async with AsyncSessionLocal() as session:
            new_total_risk = await crud.update_h3_live_risk(session, report_h3_cell, dynamic_risk_penalty)
            if report_id:
                await crud.update_report_status(session, report_id, "accepted")
            print(f"[Arka Plan] {report_h3_cell} hücresi için veritabanı güncellendi (yeni total_risk={new_total_risk:.2f})")

        # Sonra RAM'deki motoru, DB'nin hesapladigi bu NIHAI degerle guncelle
        if hasattr(app_state, "engine") and app_state.engine is not None:
            app_state.engine.set_absolute_risk_for_h3(report_h3_cell, new_total_risk)
        elif hasattr(app_state, "graph") and app_state.graph is not None:
            routing.set_absolute_risk_for_h3(app_state.graph, app_state.h3_to_edges, report_h3_cell, new_total_risk)
        print(f"[Arka Plan] {report_h3_cell} hücresi için RAM graf motoru güncellendi.\n")

    except Exception as e:
        print(f"\n[Arka Plan Hatası] İşlem sırasında hata oluştu: {e}\n")


async def process_webhook_background_task(app_state, latitude: float, longitude: float, risk_score: float, source: str):
    """
    Webhook'tan gelen veriyi isler. LLM'e gitmez, skor zaten disaridan hesaplanmis gelir.
    Ayni RAM/DB tutarlilik prensibi burada da uygulanir.
    """
    try:
        report_h3_cell = h3.latlng_to_cell(latitude, longitude, routing.H3_RESOLUTION)

        async with AsyncSessionLocal() as session:
            new_total_risk = await crud.update_h3_social_risk(session, report_h3_cell, risk_score)
            print(f"[Webhook Arka Plan] {source} kaynaklı risk işlendi (yeni total_risk={new_total_risk:.2f})")

        routing.set_absolute_risk_for_h3(
            app_state.graph,
            app_state.h3_to_edges,
            report_h3_cell,
            new_total_risk
        )
        print(f"[Webhook Arka Plan] {report_h3_cell} hücresi için RAM grafı güncellendi.\n")

    except Exception as e:
        print(f"\n[Webhook Arka Plan Hatası]: {e}\n")


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    # NOT: Tablo olusturma/guncelleme artik burada YAPILMIYOR.
    # Sema yonetimi tamamen Alembic'in sorumlulugunda:
    #   alembic upgrade head
    # komutu uygulama baslamadan ONCE calistirilmis olmali.

    engine_type = getattr(settings, "routing_engine", "compact")
    print(f"Rotalama motoru başlatılıyor: {engine_type.upper()}...")

    engine_instance = get_routing_engine(engine_type)
    if engine_type == "compact":
        engine_instance.load_graph(settings.compact_graph_path)
    else:
        engine_instance.load_graph(settings.graph_path)

    print("Risk ağırlıkları veritabanından yükleniyor...")
    async with AsyncSessionLocal() as session:
        heatmap_points = await crud.get_all_heatmap_points(session)
        risk_lookup = routing.build_risk_lookup(heatmap_points)
        engine_instance.apply_risk_weights(risk_lookup, alpha=routing.RISK_AVERSION_ALPHA)

<<<<<<< Updated upstream
    print("Sistem hazır. Rota istekleri kabul ediliyor.")
=======
    app.state.engine = engine_instance
    app.state.graph = getattr(engine_instance, "graph", None)
    app.state.h3_to_edges = getattr(engine_instance, "h3_to_edges", None)

    print(f"Sistem hazır (Motor: {engine_type.upper()}). LLM_MODE={settings.llm_mode}, LLM_PROVIDER={settings.llm_provider}. Rota istekleri kabul ediliyor.")
>>>>>>> Stashed changes
    yield


app = FastAPI(title="Safe Route App - Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- PYDANTIC MODELLERİ ---
class RouteRequest(BaseModel):
    start_lat: float = Field(ge=-90, le=90, description="Başlangıç noktası enlem")
    start_lng: float = Field(ge=-180, le=180, description="Başlangıç noktası boylam")
    end_lat: float = Field(ge=-90, le=90, description="Bitiş noktası enlem")
    end_lng: float = Field(ge=-180, le=180, description="Bitiş noktası boylam")


class GeoJSONGeometry(BaseModel):
    type: str = "LineString"
    coordinates: list[list[float]]


<<<<<<< Updated upstream
class GeoJSONFeature(BaseModel):
    type: str = "Feature"
    properties: dict = {}
    geometry: GeoJSONGeometry


class RouteResponse(BaseModel):
    status: str
    distance_meters: float
    safety_score: float
    geojson: GeoJSONFeature
=======
class RouteDetailStats(BaseModel):
    geometry: LineString
    distance_m: float
    duration_s: float
    route_risk: float
    risk_score: float
    safety_score: float
    risk_coverage: float = Field(default=95.0, description="Dinamik risk verisiyle eşleşen kenar oranı (%)")


class RouteComparisonStats(BaseModel):
    risk_reduction_pct: float
    extra_distance_m: float
    extra_distance_pct: float
    time_difference_s: float


class RouteMetadata(BaseModel):
    response_generated_at: str
    risk_snapshot_at: str
    crime_data_updated_at: str | None = None
    lighting_data_updated_at: str | None = None
    routing_engine: str = "compact"
    algorithm: str = "scipy_dijkstra"


class RouteResponse(BaseModel):
    safe_route: RouteDetailStats
    shortest_route: RouteDetailStats
    comparison: RouteComparisonStats
    metadata: RouteMetadata

    # Geriye dönük uyumluluk üst düzey alanları
    route: LineString
    distance_m: float
    duration_s: float
    risk_score: float
    safety_score: float
    route_risk: float
    risk_reduction_pct: float
    extra_distance_m: float
    extra_distance_pct: float
    shortest: LineString
>>>>>>> Stashed changes


class HeatmapPoint(BaseModel):
    h3_index: str = ""
    lat: float
    lng: float
<<<<<<< Updated upstream
    weight: float
    h3_index: str


class HeatmapResponse(BaseModel):
    points: list[HeatmapPoint]
=======
    risk_crime: float = 0.0
    risk_lighting: float = 0.0
    risk_live: float = 0.0
    total_risk: float
>>>>>>> Stashed changes


class HeatmapGeoJSONProperties(BaseModel):
    h3_index: str
    lat: float
    lng: float
    risk: float | None = None
    risk_crime: float = 0.0
    risk_lighting: float = 0.0
    risk_live: float = 0.0
    total_risk: float = 0.0
    data_available: bool = True


class PolygonGeometry(BaseModel):
    type: str = "Polygon"
    coordinates: list[list[list[float]]]


class HeatmapGeoJSONFeature(BaseModel):
    type: str = "Feature"
    id: str
    geometry: PolygonGeometry
    properties: HeatmapGeoJSONProperties


class HeatmapGeoJSONMetadata(BaseModel):
    generated_at: str
    risk_snapshot_at: str | None = None
    crime_data_updated_at: str | None = None
    lighting_data_updated_at: str | None = None
    h3_resolution: int = 9
    channel: str = "total"
    feature_count: int = 0
    data_coverage_pct: float = 0.0


class HeatmapGeoJSONResponse(BaseModel):
    type: str = "FeatureCollection"
    metadata: HeatmapGeoJSONMetadata
    features: list[HeatmapGeoJSONFeature]


class ReportCreate(BaseModel):
<<<<<<< Updated upstream
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    text: str = Field(..., min_length=1)


class ReportResponse(BaseModel):
    status: str
    message: str
=======
    """Mobil kontrat: { text, lat, lng, category? }"""
    text: str = Field(..., min_length=10, max_length=500, description="İhbar açıklaması (10-500 karakter)")
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    category: str = Field(default="general", description="Kategori: general, lighting, crime, harassment, obstacle")


class ReportResponse(BaseModel):
    ok: bool
    id: str | None = None
    tracking_token: str | None = None
    status: str = "pending"


class ReportDetailResponse(BaseModel):
    id: str
    status: str = "accepted"
    category: str = "general"
    created_at: str


class PublicMapReportItem(BaseModel):
    public_id: str
    category: str
    lat: float
    lng: float
    reported_at: str
    status: str = "accepted"
    verification_label: str = "community_report"
    minutes_ago: int


class PublicMapReportsResponse(BaseModel):
    generated_at: str
    window_minutes: int
    count: int
    reports: list[PublicMapReportItem]
>>>>>>> Stashed changes


class WebhookSocialRisk(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    risk_score: float = Field(..., ge=0, le=100, description="LLM tarafından dışarıda hesaplanmış skor")
    source: str = Field(default="social_media", description="Örn: twitter, blog, haber")
    text_snippet: str = Field(default="", description="Loglama için yakalanan metin")


from starlette.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

# Sınırlı Rotalama Semaphore ve Bekleme Kuyruğu Sayaçları
_route_semaphore = asyncio.Semaphore(settings.routing_max_concurrency)
_waiting_request_count = 0


from fastapi import Response

# --- API ENDPOINT'LERİ ---
@app.get("/")
def read_root():
    return {"message": "Safe Route App Backend Çalışıyor!"}


<<<<<<< Updated upstream
@app.post("/api/v1/route", response_model=RouteResponse)
async def get_route(payload: RouteRequest, request: Request):
    graph = request.app.state.graph

    try:
        coordinates, distance_meters, safety_score = routing.compute_safe_route(
            graph,
            start_lat=payload.start_lat,
            start_lng=payload.start_lng,
            end_lat=payload.end_lat,
            end_lng=payload.end_lng,
        )
=======
@app.get("/health")
def health_check():
    """Render/Railway health check ucu."""
    return {"status": "ok"}


@app.post("/api/v1/route", response_model=RouteResponse, response_model_exclude_none=True)
async def get_route(payload: RouteRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    global _waiting_request_count
    eng = request.app.state.engine

    # [lng, lat] dizilerini ayristir (Mapbox/GeoJSON koordinat sirasi)
    start_lng, start_lat = payload.start[0], payload.start[1]
    end_lng, end_lat = payload.end[0], payload.end[1]

    # Cografi sinir kontrolu: Chicago disi -> HTTP 400
    _ensure_within_chicago(start_lat, start_lng, "Başlangıç")
    _ensure_within_chicago(end_lat, end_lng, "Bitiş")

    # Aşırı Yük Koruması (Overload Protection): Kuyruk sınırı aşıldıysa HTTP 503 + Retry-After
    if _waiting_request_count >= settings.routing_queue_limit:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sistem yüksek yük altında. Lütfen birkaç saniye sonra tekrar deneyin.",
            headers={"Retry-After": str(settings.retry_after_seconds)}
        )

    t_request_start = time.time()
    _waiting_request_count += 1

    try:
        t_queue_start = time.time()
        async with _route_semaphore:
            t_compute_start = time.time()
            queue_wait_ms = (t_compute_start - t_queue_start) * 1000.0

            # 1) Guvenli rota (risk agirlikli) - Event loop bloklanmasin diye threadpool'da calistir
            safe_coords, distance_m, safety_score, route_risk, safe_coverage = await run_in_threadpool(
                eng.compute_safe_route,
                start_lat=start_lat,
                start_lng=start_lng,
                end_lat=end_lat,
                end_lng=end_lng,
            )
            # 2) Kiyaslama icin standart en kisa rota
            shortest_coords, _shortest_distance, _shortest_safety, _shortest_risk, shortest_coverage = await run_in_threadpool(
                eng.compute_shortest_route,
                start_lat=start_lat,
                start_lng=start_lng,
                end_lat=end_lat,
                end_lng=end_lng,
            )
            t_compute_end = time.time()
            routing_compute_ms = (t_compute_end - t_compute_start) * 1000.0

>>>>>>> Stashed changes
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Rota hesaplanamadı. Koordinatlar graf sınırları içinde mi kontrol edin: {str(e)}"
        )
    finally:
        _waiting_request_count = max(0, _waiting_request_count - 1)

    t_request_end = time.time()
    total_latency_ms = (t_request_end - t_request_start) * 1000.0

<<<<<<< Updated upstream
    geometry = GeoJSONGeometry(coordinates=coordinates)
    feature = GeoJSONFeature(geometry=geometry)

    return RouteResponse(
        status="success",
        distance_meters=distance_meters,
        safety_score=safety_score,
        geojson=feature,
=======
    # Yurume suresi: ortalama 1.2 m/s
    duration_s = distance_m / routing.WALKING_SPEED_MPS
    shortest_duration_s = _shortest_distance / routing.WALKING_SPEED_MPS

    # Ekstra mesafe, süre farkı ve risk azalma yüzdesi metrikleri
    extra_dist_m = max(0.0, distance_m - _shortest_distance)
    extra_dist_pct = round((extra_dist_m / _shortest_distance * 100.0), 1) if _shortest_distance > 0 else 0.0
    risk_red_pct = round(((_shortest_risk - route_risk) / max(0.0001, _shortest_risk) * 100.0), 1) if _shortest_risk > route_risk else 0.0
    time_diff_s = max(0.0, duration_s - shortest_duration_s)

    # ETL Güncellik Verilerini Sorgula
    etl_info = await crud.get_latest_etl_runs(db)

    # Gecikme ayrıştırma başlıklarını ekle (queue_wait_ms, routing_compute_ms, total_latency_ms)
    response.headers["X-Queue-Wait-Ms"] = f"{queue_wait_ms:.2f}"
    response.headers["X-Routing-Compute-Ms"] = f"{routing_compute_ms:.2f}"
    response.headers["X-Total-Latency-Ms"] = f"{total_latency_ms:.2f}"

    safe_stats = RouteDetailStats(
        geometry=LineString(coordinates=safe_coords),
        distance_m=round(distance_m, 1),
        duration_s=round(duration_s, 1),
        route_risk=round(route_risk, 4),
        risk_score=round(route_risk * 100.0, 1),
        safety_score=round((1.0 - route_risk) * 100.0, 1),
        risk_coverage=safe_coverage
    )

    shortest_stats = RouteDetailStats(
        geometry=LineString(coordinates=shortest_coords),
        distance_m=round(_shortest_distance, 1),
        duration_s=round(shortest_duration_s, 1),
        route_risk=round(_shortest_risk, 4),
        risk_score=round(_shortest_risk * 100.0, 1),
        safety_score=round((1.0 - _shortest_risk) * 100.0, 1),
        risk_coverage=shortest_coverage
    )

    comparison_stats = RouteComparisonStats(
        risk_reduction_pct=risk_red_pct,
        extra_distance_m=round(extra_dist_m, 1),
        extra_distance_pct=extra_dist_pct,
        time_difference_s=round(time_diff_s, 1)
    )

    metadata_stats = RouteMetadata(
        response_generated_at=datetime.now(timezone.utc).isoformat(),
        risk_snapshot_at=etl_info["risk_snapshot_at"],
        crime_data_updated_at=etl_info["crime_data_updated_at"],
        lighting_data_updated_at=etl_info["lighting_data_updated_at"],
        routing_engine=getattr(settings, "routing_engine", "compact"),
        algorithm="scipy_dijkstra"
    )

    return RouteResponse(
        safe_route=safe_stats,
        shortest_route=shortest_stats,
        comparison=comparison_stats,
        metadata=metadata_stats,
        # Geriye dönük uyumluluk
        route=LineString(coordinates=safe_coords),
        distance_m=round(distance_m, 1),
        duration_s=round(duration_s, 1),
        risk_score=round(route_risk * 100.0, 1),
        safety_score=round((1.0 - route_risk) * 100.0, 1),
        route_risk=round(route_risk, 4),
        risk_reduction_pct=risk_red_pct,
        extra_distance_m=round(extra_dist_m, 1),
        extra_distance_pct=extra_dist_pct,
        shortest=LineString(coordinates=shortest_coords),
>>>>>>> Stashed changes
    )


_report_rate_limit_tracker: dict[str, list[float]] = {}
VALID_REPORT_CATEGORIES = {"general", "lighting", "crime", "harassment", "obstacle"}


def _check_report_rate_limit(client_ip: str, max_requests: int = 5, window_seconds: int = 60) -> None:
    if client_ip in ("testclient", "127.0.0.1_test"):
        return
    now = time.time()
    timestamps = _report_rate_limit_tracker.get(client_ip, [])
    valid_timestamps = [t for t in timestamps if now - t < window_seconds]
    if len(valid_timestamps) >= max_requests:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Çok fazla ihbar isteği gönderildi. Lütfen bir dakika sonra tekrar deneyin."
        )
    valid_timestamps.append(now)
    _report_rate_limit_tracker[client_ip] = valid_timestamps


@app.post("/api/v1/report", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
async def add_live_report(
    payload: ReportCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
<<<<<<< Updated upstream
    try:
        await crud.create_report(db, payload.latitude, payload.longitude, payload.text)
=======
    # Chicago disi ihbarlar da reddedilir (suni risk bolgesi olusmasin)
    _ensure_within_chicago(payload.lat, payload.lng, "İhbar")

    # Kategori kontrolü
    category = payload.category.lower() if payload.category else "general"
    if category not in VALID_REPORT_CATEGORIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Geçersiz kategori '{category}'. İzin verilen kategoriler: {list(VALID_REPORT_CATEGORIES)}"
        )

    # Rate Limiting
    client_ip = request.client.host if request.client else "127.0.0.1"
    _check_report_rate_limit(client_ip)

    # Mükerrer ihbar kontrolü (50m ve 10dk içinde)
    is_duplicate = await crud.check_duplicate_report(db, payload.lat, payload.lng)
    if is_duplicate:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bu konumda yakın zamanda benzer bir ihbar bildirilmiş. Lütfen daha sonra tekrar deneyin."
        )

    try:
        try:
            report = await crud.create_report(
                db,
                payload.lat,
                payload.lng,
                payload.text,
                category=category,
                ip_address=client_ip
            )
        except TypeError:
            report = await crud.create_report(db, payload.lat, payload.lng, payload.text)

        report_id = getattr(report, "uuid_id", None) or str(getattr(report, "id", "1"))
        report_token = getattr(report, "tracking_token", None)

        # Loglarda hassas kullanıcı metinlerini maskeleme
        print(f"[İhbar Kaydedildi] UUID: {report_id}, Kategori: {category}, Konum: ({payload.lat:.4f}, {payload.lng:.4f}), Metin: [MASKELENDİ]")
>>>>>>> Stashed changes

        background_tasks.add_task(
            process_report_background_task,
            app_state=request.app.state,
<<<<<<< Updated upstream
            latitude=payload.latitude,
            longitude=payload.longitude,
            text=payload.text
        )

        return ReportResponse(status="success", message="Bildiriminiz ulaştı. Yapay zeka durumu analiz ediyor.")
=======
            latitude=payload.lat,
            longitude=payload.lng,
            text=payload.text,
            report_id=report_id
        )

        return ReportResponse(
            ok=True,
            id=report_id,
            tracking_token=report_token,
            status="pending"
        )
    except HTTPException:
        raise
>>>>>>> Stashed changes
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Bildirim kaydedilemedi: {str(e)}")


<<<<<<< Updated upstream
@app.post(
    "/api/v1/webhook/social-risk",
    response_model=ReportResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(verify_webhook_secret)],  # <-- Guvenlik kontrolu eklendi
)
async def receive_social_risk_webhook(
    payload: WebhookSocialRisk,
    request: Request,
    background_tasks: BackgroundTasks
=======
@app.get("/api/v1/reports/map", response_model=PublicMapReportsResponse)
async def get_map_reports(
    minutes: int = Query(60, ge=5, le=60, description="Kaç dakika öncesine kadarki ihbarların getirileceği"),
    bbox: str | None = Query(None, description="west,south,east,north formatında coğrafi sınırlama"),
    category: str | None = Query(None, description="İhbar kategorisi filtresi"),
    limit: int = Query(500, ge=1, le=1000, description="Maksimum ihbar sayısı"),
    db: AsyncSession = Depends(get_db)
):
    """
    Son N dakika içinde bildirilen anonim ihbarları haritada göstermek üzere döner.
    Hassas kişisel veriler, IP adresleri ve tracking token'lar ASLA döndürülmez.
    """
    data = await crud.get_recent_map_reports(
        db,
        minutes=minutes,
        bbox=bbox,
        category=category,
        limit=limit
    )
    return data


@app.get("/api/v1/reports/{uuid_id}", response_model=ReportDetailResponse)
async def get_report_status(
    uuid_id: str,
    token: str = Query(..., min_length=1, description="İhbar oluşturan cihazın takip jetonu"),
    db: AsyncSession = Depends(get_db)
):
    """
    IDOR Saldırılarına karşı korumalı ihbar durum sorgulama.
    Hassas kullanıcı metinlerini veya raw LLM çıktılarını DÖNDÜRMEDDEN sterilize durum bilgisi sunar.
    """
    report = await crud.get_report_by_uuid_and_token(db, uuid_id, token)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Erişim yetkiniz bulunmamaktadır veya geçersiz ihbar takip jetonu."
        )
    created_iso = report.created_at.isoformat() if report.created_at else datetime.now(timezone.utc).isoformat()
    return ReportDetailResponse(
        id=report.uuid_id or str(report.id),
        status=report.status or "accepted",
        category=report.category or "general",
        created_at=created_iso
    )


@app.get("/api/v1/heatmap", response_model=list[HeatmapPoint])
async def get_heatmap(db: AsyncSession = Depends(get_db)):
    """Mobil kontrat: h3_index, risk_crime, risk_lighting, risk_live ve total_risk alanlarını döner."""
    points = await crud.get_all_heatmap_points(db)
    return [
        HeatmapPoint(
            h3_index=getattr(p, "h3_index", "") or "",
            lat=getattr(p, "lat", 0.0),
            lng=getattr(p, "lng", 0.0),
            risk_crime=round(getattr(p, "risk_crime", getattr(p, "risk_historical", 0.0)) or 0.0, 4),
            risk_lighting=round(getattr(p, "risk_lighting", 0.0) or 0.0, 4),
            risk_live=round(getattr(p, "risk_live", 0.0) or 0.0, 4),
            total_risk=round(getattr(p, "total_risk", 0.0) or 0.0, 4)
        )
        for p in points
    ]


@app.get("/api/v1/heatmap/nearby", response_model=list[HeatmapPoint])
async def get_nearby_heatmap(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    radius: int = Query(500, ge=1),
    db: AsyncSession = Depends(get_db)
>>>>>>> Stashed changes
):
    """
    Dış otomasyon araçlarının (n8n vb.) sosyal medyada tehlike tespit ettiğinde
    veriyi fırlatacağı kapı. Erişim için 'X-Webhook-Secret' header'ı zorunludur.
    """
    try:
        background_tasks.add_task(
            process_webhook_background_task,
            app_state=request.app.state,
            latitude=payload.latitude,
            longitude=payload.longitude,
            risk_score=payload.risk_score,
            source=payload.source
        )
        return ReportResponse(status="success", message="Sosyal medya risk verisi arka planda işleniyor.")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Webhook işlenemedi: {str(e)}")


@app.get("/api/v1/heatmap", response_model=HeatmapResponse)
async def get_heatmap(db: AsyncSession = Depends(get_db)):
    points = await crud.get_all_heatmap_points(db)
    return HeatmapResponse(points=[HeatmapPoint(lat=p.lat, lng=p.lng, weight=p.total_risk, h3_index=p.h3_index) for p in points])


@app.get("/api/v1/heatmap/nearby", response_model=HeatmapResponse)
async def get_nearby_heatmap(lat: float = Query(..., ge=-90, le=90), lng: float = Query(..., ge=-180, le=180), radius: int = Query(500, ge=1), db: AsyncSession = Depends(get_db)):
    points = await crud.get_nearby_risk_points(db, lat, lng, radius)
<<<<<<< Updated upstream
    return HeatmapResponse(points=[HeatmapPoint(lat=p.lat, lng=p.lng, weight=p.total_risk, h3_index=p.h3_index) for p in points])
=======
    return [HeatmapPoint(lat=p.lat, lng=p.lng, total_risk=p.total_risk) for p in points]


@app.get("/api/v1/heatmap/map", response_model=HeatmapGeoJSONResponse)
async def get_heatmap_map(
    bbox: str | None = Query(None, description="west,south,east,north biçiminde opsiyonel coğrafi sınırlama"),
    channel: str = Query("total", description="Risk kanalı: total, crime, lighting, live"),
    include_no_data: bool = Query(True, description="Verisi bulunmayan H3 hücrelerinin dahil edilip edilmeyeceği"),
    format: str = Query("geojson", description="Çıktı formatı (varsayılan: geojson)"),
    h3_resolution: int = Query(9, ge=9, le=9, description="H3 çözünürlüğü (sabit 9)"),
    db: AsyncSession = Depends(get_db)
):
    """
    Mapbox harita katmanı için Chicago genelindeki H3 Resolution 9 poligon risk verilerini GeoJSON olarak döner.
    Verisi bulunmayan alanlar 'data_available: false' ve 'risk: null' olarak gri katman için sunulur.
    """
    valid_channels = {"total", "crime", "lighting", "live"}
    clean_channel = channel.lower() if channel else "total"
    if clean_channel not in valid_channels:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Geçersiz risk kanalı '{channel}'. İzin verilen kanallar: {list(valid_channels)}"
        )

    data = await crud.get_heatmap_geojson_map(
        db,
        bbox=bbox,
        channel=clean_channel,
        include_no_data=include_no_data
    )
    return data
>>>>>>> Stashed changes
