# backend/main.py
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
from fastapi import FastAPI, Depends, HTTPException, Query, status, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import contextlib
import h3

from config import settings
import crud
import routing
from llm_service import analyze_report_risk_with_llm

engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Graf dosyasinin yolu (.env: GRAPH_PATH) - Chicago grafi
GRAPH_PATH = settings.graph_path


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


async def process_report_background_task(app_state, latitude: float, longitude: float, text: str):
    """
    Arka planda calisan orkestrator:
    1. Ihbarin H3 hucresini bulur.
    2. LLM'e (veya kural tabanli fallback'e) metni sorup dinamik risk cezasini alir.
    3. Veritabanini gunceller ve AGIRLIKLI FORMULLE hesaplanmis NIHAI
       total_risk degerini geri alir (crud.py - tek dogruluk kaynagi).
    4. RAM'deki grafi bu NIHAI degerle gunceller (ekleme degil, dogrudan yazma) -
       boylece RAM ve DB HER ZAMAN ayni sayiyi gosterir.
    """
    try:
        report_h3_cell = h3.latlng_to_cell(latitude, longitude, routing.H3_RESOLUTION)

        dynamic_risk_penalty = await analyze_report_risk_with_llm(text, latitude, longitude)
        print(f"\n[Arka Plan] İhbar: '{text}' -> Üretilen Ceza Puanı: {dynamic_risk_penalty}")

        # Once DB'yi guncelle, agirlikli formulle hesaplanmis NIHAI degeri al
        async with AsyncSessionLocal() as session:
            new_total_risk = await crud.update_h3_live_risk(session, report_h3_cell, dynamic_risk_penalty)
            print(f"[Arka Plan] {report_h3_cell} hücresi için veritabanı güncellendi (yeni total_risk={new_total_risk:.2f})")

        # Sonra RAM'deki grafi, DB'nin hesapladigi bu NIHAI degerle guncelle
        routing.set_absolute_risk_for_h3(
            app_state.graph,
            app_state.h3_to_edges,
            report_h3_cell,
            new_total_risk
        )
        print(f"[Arka Plan] {report_h3_cell} hücresi için RAM grafı güncellendi.\n")

    except Exception as e:
        print(f"\n[Arka Plan Hatası] İşlem sırasında hata oluştu: {e}\n")


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    # NOT: Sema yonetimi tamamen Alembic'in sorumlulugunda:
    #   alembic upgrade head
    # Docker ortaminda bu komut entrypoint.sh icinde otomatik calisir.

    print(f"Graf yükleniyor: {GRAPH_PATH} (Lütfen bekleyin...)")
    app.state.graph = routing.load_graph(GRAPH_PATH)

    print("Risk ağırlıkları ve Ters Dizin (Inverted Index) oluşturuluyor...")
    async with AsyncSessionLocal() as session:
        heatmap_points = await crud.get_all_heatmap_points(session)
        risk_lookup = routing.build_risk_lookup(heatmap_points)
        app.state.h3_to_edges = routing.apply_risk_weights(app.state.graph, risk_lookup)

    print(f"Sistem hazır. LLM_MODE={settings.llm_mode}, LLM_PROVIDER={settings.llm_provider}. Rota istekleri kabul ediliyor.")
    yield


app = FastAPI(title="Safe Route App - Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- PYDANTIC MODELLERİ (Mobil kontratla birebir) ---
class RouteRequest(BaseModel):
    """Mobil, koordinatlari Mapbox standardinda [lng, lat] dizisi olarak yollar."""
    start: list[float] = Field(..., min_length=2, max_length=2, description="[lng, lat] formatında başlangıç koordinatı")
    end: list[float] = Field(..., min_length=2, max_length=2, description="[lng, lat] formatında bitiş koordinatı")
    hour: int | None = Field(default=None, ge=0, le=23, description="İsteğe bağlı yerel saat (0-23). MVP'de kabul edilir, risk hesabına Faz 2'de katılacak.")


class LineString(BaseModel):
    """GeoJSON LineString - mobil dogrudan bu yapiyi bekler (Feature wrapper YOK)."""
    type: str = "LineString"
    coordinates: list[list[float]]


class RouteResponse(BaseModel):
    route: LineString = Field(..., description="Güvenli rota (GeoJSON LineString, [lng, lat] çiftleri)")
    distance_m: float
    duration_s: float
    risk_score: float = Field(..., description="0 (güvenli) - 100 (tehlikeli)")
    shortest: LineString | None = Field(default=None, description="Kıyaslama için standart en kısa rota")


class HeatmapPoint(BaseModel):
    lat: float
    lng: float
    total_risk: float


class ReportCreate(BaseModel):
    """Mobil kontrat: { text, lat, lng }"""
    text: str = Field(..., min_length=1)
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)


class ReportResponse(BaseModel):
    ok: bool
    id: str | None = None


def _ensure_within_chicago(lat: float, lng: float, label: str) -> None:
    """Chicago sinirlari disindaki koordinatlar icin aciklayici HTTP 400 firlatir."""
    if not routing.is_within_chicago(lat, lng):
        b = routing.CHICAGO_BOUNDS
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"{label} koordinatı ({lat:.4f}, {lng:.4f}) servis alanı dışında. "
                f"SafeRoute şu anda yalnızca Chicago sınırları içinde hizmet vermektedir "
                f"(enlem {b['min_lat']}–{b['max_lat']}, boylam {b['min_lng']}–{b['max_lng']})."
            ),
        )


# --- API ENDPOINT'LERİ ---
@app.get("/")
def read_root():
    return {"message": "Safe Route App Backend Çalışıyor!"}


@app.get("/health")
def health_check():
    """Render/Railway health check ucu."""
    return {"status": "ok"}


@app.post("/api/v1/route", response_model=RouteResponse, response_model_exclude_none=True)
async def get_route(payload: RouteRequest, request: Request):
    graph = request.app.state.graph

    # [lng, lat] dizilerini ayristir (Mapbox/GeoJSON koordinat sirasi)
    start_lng, start_lat = payload.start[0], payload.start[1]
    end_lng, end_lat = payload.end[0], payload.end[1]

    # Cografi sinir kontrolu: Chicago disi -> HTTP 400
    _ensure_within_chicago(start_lat, start_lng, "Başlangıç")
    _ensure_within_chicago(end_lat, end_lng, "Bitiş")

    try:
        # 1) Guvenli rota (risk agirlikli)
        safe_coords, distance_m, safety_score = routing.compute_safe_route(
            graph,
            start_lat=start_lat,
            start_lng=start_lng,
            end_lat=end_lat,
            end_lng=end_lng,
        )
        # 2) Kiyaslama icin standart en kisa rota (sadece "length" agirligi)
        shortest_coords, _shortest_distance = routing.compute_shortest_route(
            graph,
            start_lat=start_lat,
            start_lng=start_lng,
            end_lat=end_lat,
            end_lng=end_lng,
        )
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Rota hesaplanamadı. Koordinatlar graf sınırları içinde mi kontrol edin: {str(e)}"
        )

    # Yurume suresi: ortalama 1.2 m/s
    duration_s = distance_m / routing.WALKING_SPEED_MPS

    return RouteResponse(
        route=LineString(coordinates=safe_coords),
        distance_m=round(distance_m, 1),
        duration_s=round(duration_s, 1),
        # Mobil 0=guvenli, 100=tehlikeli bekler; safety_score (100=guvenli) ters cevrilir.
        risk_score=round(100.0 - safety_score, 1),
        shortest=LineString(coordinates=shortest_coords),
    )


@app.post("/api/v1/report", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
async def add_live_report(
    payload: ReportCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    # Chicago disi ihbarlar da reddedilir (suni risk bolgesi olusmasin)
    _ensure_within_chicago(payload.lat, payload.lng, "İhbar")

    try:
        report = await crud.create_report(db, payload.lat, payload.lng, payload.text)

        background_tasks.add_task(
            process_report_background_task,
            app_state=request.app.state,
            latitude=payload.lat,
            longitude=payload.lng,
            text=payload.text
        )

        return ReportResponse(ok=True, id=str(report.id))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Bildirim kaydedilemedi: {str(e)}")


@app.get("/api/v1/heatmap", response_model=list[HeatmapPoint])
async def get_heatmap(db: AsyncSession = Depends(get_db)):
    """Mobil kontrat: wrapper object DEGIL, dogrudan flat array doner."""
    points = await crud.get_all_heatmap_points(db)
    return [HeatmapPoint(lat=p.lat, lng=p.lng, total_risk=p.total_risk) for p in points]


@app.get("/api/v1/heatmap/nearby", response_model=list[HeatmapPoint])
async def get_nearby_heatmap(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    radius: int = Query(500, ge=1),
    db: AsyncSession = Depends(get_db)
):
    points = await crud.get_nearby_risk_points(db, lat, lng, radius)
    return [HeatmapPoint(lat=p.lat, lng=p.lng, total_risk=p.total_risk) for p in points]
