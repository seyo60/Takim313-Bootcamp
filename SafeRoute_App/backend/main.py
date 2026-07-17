# backend/main.py
from fastapi import FastAPI, Depends, HTTPException, Query, status, Request, BackgroundTasks, Header
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

# Graf dosyasının yolu - Chicago grafı
GRAPH_PATH = "../data-science/chicago.graphml"


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


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
    """
    Arka planda calisan orkestrator:
    1. Ihbarin H3 hucresini bulur.
    2. LLM'e metni sorup dinamik risk cezasini alir.
    3. Veritabanini gunceller ve AGIRLIKLI FORMULLE hesaplanmis NIHAI
       total_risk degerini geri alir (crud.py - tek dogruluk kaynagi).
    4. RAM'deki grafi bu NIHAI degerle gunceller (ekleme degil, dogrudan yazma) -
       boylece RAM ve DB HER ZAMAN ayni sayiyi gosterir.
    """
    try:
        report_h3_cell = h3.latlng_to_cell(latitude, longitude, routing.H3_RESOLUTION)

        dynamic_risk_penalty = await analyze_report_risk_with_llm(text)
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

    print(f"Graf yükleniyor: {GRAPH_PATH} (Lütfen bekleyin...)")
    app.state.graph = routing.load_graph(GRAPH_PATH)

    print("Risk ağırlıkları ve Ters Dizin (Inverted Index) oluşturuluyor...")
    async with AsyncSessionLocal() as session:
        heatmap_points = await crud.get_all_heatmap_points(session)
        risk_lookup = routing.build_risk_lookup(heatmap_points)
        app.state.h3_to_edges = routing.apply_risk_weights(app.state.graph, risk_lookup)

    print("Sistem hazır. Rota istekleri kabul ediliyor.")
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


class GeoJSONFeature(BaseModel):
    type: str = "Feature"
    properties: dict = {}
    geometry: GeoJSONGeometry


class RouteResponse(BaseModel):
    status: str
    distance_meters: float
    safety_score: float
    geojson: GeoJSONFeature


class HeatmapPoint(BaseModel):
    lat: float
    lng: float
    weight: float
    h3_index: str


class HeatmapResponse(BaseModel):
    points: list[HeatmapPoint]


class ReportCreate(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    text: str = Field(..., min_length=1)


class ReportResponse(BaseModel):
    status: str
    message: str


class WebhookSocialRisk(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    risk_score: float = Field(..., ge=0, le=100, description="LLM tarafından dışarıda hesaplanmış skor")
    source: str = Field(default="social_media", description="Örn: twitter, blog, haber")
    text_snippet: str = Field(default="", description="Loglama için yakalanan metin")


# --- API ENDPOINT'LERİ ---
@app.get("/")
def read_root():
    return {"message": "Safe Route App Backend Çalışıyor!"}


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
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Rota hesaplanamadı. Koordinatlar graf sınırları içinde mi kontrol edin: {str(e)}"
        )

    geometry = GeoJSONGeometry(coordinates=coordinates)
    feature = GeoJSONFeature(geometry=geometry)

    return RouteResponse(
        status="success",
        distance_meters=distance_meters,
        safety_score=safety_score,
        geojson=feature,
    )


@app.post("/api/v1/report", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
async def add_live_report(
    payload: ReportCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    try:
        await crud.create_report(db, payload.latitude, payload.longitude, payload.text)

        background_tasks.add_task(
            process_report_background_task,
            app_state=request.app.state,
            latitude=payload.latitude,
            longitude=payload.longitude,
            text=payload.text
        )

        return ReportResponse(status="success", message="Bildiriminiz ulaştı. Yapay zeka durumu analiz ediyor.")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Bildirim kaydedilemedi: {str(e)}")


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
    return HeatmapResponse(points=[HeatmapPoint(lat=p.lat, lng=p.lng, weight=p.total_risk, h3_index=p.h3_index) for p in points])