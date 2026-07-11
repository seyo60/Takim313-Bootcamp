# backend/main.py
from fastapi import FastAPI, Depends, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import contextlib

from config import settings
from models import Base
import crud
import routing

engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Graf dosyasinin yolu - Mehmet Ali'nin gercek Chicago grafi gelince burasi degisecek
GRAPH_PATH = "test_network.graphml"


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Graf dosyasini uygulama baslarken bir kere yukle, belekte tut
    app.state.graph = routing.load_graph(GRAPH_PATH)

    yield


app = FastAPI(title="Safe Route App - Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


@app.get("/")
def read_root():
    return {"message": "Safe Route App Backend Çalışıyor!"}


@app.post("/api/v1/route", response_model=RouteResponse)
async def get_route(payload: RouteRequest, db: AsyncSession = Depends(get_db)):
    graph = app.state.graph

    # 1. Guncel risk verilerini DB'den cek
    heatmap_points = await crud.get_all_heatmap_points(db)
    risk_lookup = routing.build_risk_lookup(heatmap_points)

    # 2. Grafin kenarlarina risk agirliklarini isle
    routing.apply_risk_weights(graph, risk_lookup)

    # 3. Risk-agirlikli en guvenli rotayi hesapla
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
async def add_live_report(payload: ReportCreate, db: AsyncSession = Depends(get_db)):
    try:
        await crud.create_report(db, payload.latitude, payload.longitude, payload.text)
        return ReportResponse(status="success", message="Bildiriminiz başarıyla iletildi")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Bildirim kaydedilemedi: {str(e)}")


@app.get("/api/v1/heatmap", response_model=HeatmapResponse)
async def get_heatmap(db: AsyncSession = Depends(get_db)):
    points = await crud.get_all_heatmap_points(db)
    return HeatmapResponse(points=[HeatmapPoint(lat=p.lat, lng=p.lng, weight=p.risk_weight, h3_index=p.h3_index) for p in points])


@app.get("/api/v1/heatmap/nearby", response_model=HeatmapResponse)
async def get_nearby_heatmap(lat: float = Query(..., ge=-90, le=90), lng: float = Query(..., ge=-180, le=180), radius: int = Query(500, ge=1), db: AsyncSession = Depends(get_db)):
    points = await crud.get_nearby_risk_points(db, lat, lng, radius)
    return HeatmapResponse(points=[HeatmapPoint(lat=p.lat, lng=p.lng, weight=p.risk_weight, h3_index=p.h3_index) for p in points])