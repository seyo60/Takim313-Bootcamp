# backend/main.py
"""
SafeRoute FastAPI backend - mobil (end-to-end.md) kontratlarıyla birebir uyumlu.
"""
from datetime import datetime, timezone
from typing import Literal
from fastapi import FastAPI, Depends, HTTPException, Query, status, Request, BackgroundTasks, Response
from fastapi.exceptions import RequestValidationError

from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, or_

from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse
from prometheus_client import Counter, Gauge, Histogram, CONTENT_TYPE_LATEST, generate_latest
import contextlib
import asyncio
import logging
import time
import math
import uuid
import h3


from config import settings
from models import ReportEventModel, ReportModel
import crud
from services.report_nlp import get_nlp_analyzer
from h3_policy import LEGACY_H3_RESOLUTION, validate_h3_resolution
from routing_profiles import parse_candidate_alphas

import routing
from navigation import build_navigation_contract
from routing_engine import get_routing_engine
from services.street_risk_service import build_street_risk_explanation
from services.route_explanation_service import build_route_risk_explanation
from errors import ConfigurationError, PersistenceError
from auth import AuthenticatedUser, get_current_user, get_optional_user, require_current_user


logger = logging.getLogger("saferoute.api")
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

engine = create_async_engine(settings.database_url, echo=False, pool_pre_ping=True, pool_recycle=300)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

HTTP_REQUESTS = Counter(
    "saferoute_http_requests_total",
    "HTTP requests grouped by stable route template.",
    ("method", "route", "status"),
)
HTTP_LATENCY = Histogram(
    "saferoute_http_request_duration_seconds",
    "HTTP request latency grouped by stable route template.",
    ("method", "route"),
)
ROUTE_REQUESTS = Counter(
    "saferoute_route_requests_total",
    "Routing outcomes by profile.",
    ("profile", "outcome"),
)
REPORT_REQUESTS = Counter(
    "saferoute_report_requests_total",
    "Report creation outcomes without user content or coordinates.",
    ("category", "outcome"),
)
PERSISTENCE_FAILURES = Counter(
    "saferoute_persistence_failures_total",
    "Controlled persistence failures.",
)
ROUTING_QUEUE_DEPTH = Gauge(
    "saferoute_routing_queue_depth",
    "Requests waiting for or using a routing worker.",
)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


def _ensure_within_chicago(lat: float, lng: float, name: str = "Konum") -> None:
    if not (routing.CHICAGO_BOUNDS["min_lat"] <= lat <= routing.CHICAGO_BOUNDS["max_lat"] and
            routing.CHICAGO_BOUNDS["min_lng"] <= lng <= routing.CHICAGO_BOUNDS["max_lng"]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{name} koordinatı Chicago hizmet alanı dışında ({lat:.4f}, {lng:.4f})."
        )



async def apply_accepted_report_live_risk(
    app_state,
    latitude: float,
    longitude: float,
    report_h3_cell: str | None = None,
) -> None:
    """Kabul edilmiş ihbar sonrası risk_live ve bellek içi grafı günceller."""
    try:
        if report_h3_cell is None:
            report_h3_cell = h3.latlng_to_cell(
                latitude,
                longitude,
                validate_h3_resolution(
                    getattr(settings, "report_h3_resolution", LEGACY_H3_RESOLUTION)
                ),
            )

        async with AsyncSessionLocal() as session:
            new_total_risk = await crud.recalculate_h3_live_risk(session, report_h3_cell)
            routing_resolution = validate_h3_resolution(
                getattr(settings, "routing_h3_resolution", LEGACY_H3_RESOLUTION)
            )
            routing_h3_cell = h3.latlng_to_cell(
                latitude,
                longitude,
                routing_resolution,
            )
            if routing_h3_cell != report_h3_cell:
                new_total_risk = await crud.project_parent_live_risk_to_child(
                    session,
                    parent_h3_index=report_h3_cell,
                    child_h3_index=routing_h3_cell,
                )

            if hasattr(app_state, "engine") and app_state.engine is not None:
                app_state.engine.set_absolute_risk_for_h3(
                    routing_h3_cell,
                    new_total_risk,
                )
            elif hasattr(app_state, "graph") and app_state.graph is not None:
                routing.set_absolute_risk_for_h3(
                    app_state.graph,
                    app_state.h3_to_edges,
                    routing_h3_cell,
                    new_total_risk,
                )
            logger.info("report_event_risk_applied")
    except Exception:
        logger.exception("report_live_risk_apply_failed")


async def _run_witness_request_dispatch(*, event_id: int, report_id: int) -> None:
    """Acil ihbar sonrası 1 km tanık isteğini arka planda gönderir."""
    try:
        from services.emergency_alert_service import dispatch_witness_request

        async with AsyncSessionLocal() as session:
            event = await session.get(ReportEventModel, event_id)
            report = await session.get(ReportModel, report_id)
            if event is None or report is None:
                return
            await dispatch_witness_request(session, event=event, report=report)
    except Exception:
        logger.exception("witness_request_dispatch_failed")


async def _run_verified_community_notify(*, event_id: int, report_id: int) -> None:
    """Normal (acil olmayan) doğrulanmış ihbarları yakındakilere duyurur."""
    try:
        from services.emergency_alert_service import dispatch_verified_community_alert

        async with AsyncSessionLocal() as session:
            event = await session.get(ReportEventModel, event_id)
            report = await session.get(ReportModel, report_id)
            if event is None or report is None:
                return
            await dispatch_verified_community_alert(session, event=event, report=report)
    except Exception:
        logger.exception("verified_community_notify_failed")


async def process_report_background_task(app_state, latitude: float, longitude: float, text: str, report_id: str | None = None):
    try:
        report_h3_cell = h3.latlng_to_cell(
            latitude,
            longitude,
            validate_h3_resolution(
                getattr(settings, "report_h3_resolution", LEGACY_H3_RESOLUTION)
            ),
        )

        async with AsyncSessionLocal() as session:
            report = None
            if report_id:
                stmt = select(ReportModel).where(
                    or_(ReportModel.uuid_id == report_id, ReportModel.id == (int(report_id) if report_id.isdigit() else -1))
                )
                res = await session.execute(stmt)
                report = res.scalars().first()

            if report:
                event = await crud.process_report_and_event_clustering(session, report)
                if event and event.status == "accepted":
                    await apply_accepted_report_live_risk(
                        app_state,
                        latitude,
                        longitude,
                        report_h3_cell=report_h3_cell,
                    )
                else:
                    logger.info("report_event_pending")

    except Exception:
        logger.exception("background_report_processing_failed")




@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.ready = False
    app.state.data_health = {"status": "initializing"}
    engine_type = getattr(settings, "routing_engine", "compact")
    print(f"Rotalama motoru başlatılıyor: {engine_type.upper()}...")

    engine_instance = get_routing_engine(engine_type)
    if engine_type == "compact":
        engine_instance.load_graph(settings.compact_graph_path)
    else:
        engine_instance.load_graph(settings.graph_path)

    print("Risk ağırlıkları veritabanından yükleniyor...")
    print(
        "Rota risk politikası: "
        f"alpha={settings.routing_risk_alpha:.2f}, "
        f"kırmızı eşik={settings.routing_red_risk_threshold:.2f}, "
        f"kırmızı ceza={settings.routing_red_risk_penalty:.2f}, "
        f"verisiz alan riski={settings.routing_unknown_risk:.2f}, "
        f"aday alpha={settings.routing_candidate_alphas}, "
        f"balanced bütçe=%{settings.routing_balanced_max_detour_pct:g}, "
        f"safer bütçe=%{settings.routing_safer_max_detour_pct:g}"
    )
    async with AsyncSessionLocal() as session:
        routing_resolution = validate_h3_resolution(
            getattr(settings, "routing_h3_resolution", LEGACY_H3_RESOLUTION)
        )
        parent_resolution = validate_h3_resolution(
            getattr(settings, "h3_parent_resolution", LEGACY_H3_RESOLUTION)
        )
        heatmap_points = await crud.get_all_heatmap_points(
            session,
            h3_resolution=routing_resolution,
        )
        if parent_resolution != routing_resolution:
            heatmap_points.extend(
                await crud.get_all_heatmap_points(
                    session,
                    h3_resolution=parent_resolution,
                )
            )
        risk_lookup = routing.build_risk_lookup(heatmap_points)
        engine_instance.apply_risk_weights(
            risk_lookup,
            alpha=settings.routing_risk_alpha,
        )

    app.state.engine = engine_instance
    app.state.graph = getattr(engine_instance, "graph", None)
    app.state.h3_to_edges = getattr(engine_instance, "h3_to_edges", None)
    app.state.ready = True
    app.state.data_health = {
        "status": "ok",
        "h3_resolution": routing_resolution,
        "risk_cell_count": len(risk_lookup),
    }

    print(
        f"Sistem hazır (Motor: {engine_type.upper()}, "
        f"H3 Res-{routing_resolution}). "
        f"LLM_MODE={settings.llm_mode}, LLM_PROVIDER={settings.llm_provider}. "
        "Rota istekleri kabul ediliyor."
    )
    try:
        yield
    finally:
        app.state.ready = False
        await engine.dispose()


app = FastAPI(
    title="SafeRoute API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None if settings.app_environment == "production" else "/docs",
    redoc_url=None if settings.app_environment == "production" else "/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def _error_body(request: Request, code: str, message: str) -> dict:
    return {
        "error": {
            "code": code,
            "message": message,
            "request_id": _request_id(request),
        },
        # Temporary compatibility field for existing mobile clients.
        "detail": message,
    }


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    started = time.perf_counter()
    incoming = request.headers.get("X-Request-ID", "").strip()
    request.state.request_id = incoming if 0 < len(incoming) <= 64 else str(uuid.uuid4())
    try:
        response = await call_next(request)
    except Exception:
        route = getattr(request.scope.get("route"), "path", "unmatched")
        HTTP_REQUESTS.labels(request.method, route, "500").inc()
        HTTP_LATENCY.labels(request.method, route).observe(time.perf_counter() - started)
        raise
    route = getattr(request.scope.get("route"), "path", "unmatched")
    HTTP_REQUESTS.labels(request.method, route, str(response.status_code)).inc()
    HTTP_LATENCY.labels(request.method, route).observe(time.perf_counter() - started)
    response.headers["X-Request-ID"] = request.state.request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    message = exc.detail if isinstance(exc.detail, str) else "İstek tamamlanamadı."
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_body(request, f"http_{exc.status_code}", message),
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    fields = [".".join(str(part) for part in item["loc"]) for item in exc.errors()]
    body = _error_body(request, "validation_error", "İstek alanları doğrulanamadı.")
    body["error"]["fields"] = fields
    return JSONResponse(status_code=422, content=body)


@app.exception_handler(PersistenceError)
async def persistence_exception_handler(request: Request, exc: PersistenceError):
    PERSISTENCE_FAILURES.inc()
    logger.exception("persistence_operation_failed", extra={"request_id": _request_id(request)})
    return JSONResponse(
        status_code=503,
        content=_error_body(
            request,
            exc.code,
            "Veri hizmeti şu anda kullanılamıyor. Lütfen daha sonra tekrar deneyin.",
        ),
    )


@app.exception_handler(ConfigurationError)
async def configuration_exception_handler(request: Request, exc: ConfigurationError):
    logger.error("runtime_configuration_missing", extra={"request_id": _request_id(request)})
    return JSONResponse(
        status_code=503,
        content=_error_body(request, exc.code, "Hizmet yapılandırması tamamlanmamış."),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("unhandled_request_error", extra={"request_id": _request_id(request)})
    return JSONResponse(
        status_code=500,
        content=_error_body(request, "internal_error", "Beklenmeyen bir hata oluştu."),
    )


# --- PYDANTIC MODELLERİ ---
class LineString(BaseModel):
    type: str = "LineString"
    coordinates: list[list[float]]


class RouteRequest(BaseModel):
    start: list[float] = Field(..., min_length=2, max_length=2, description="Başlangıç [lng, lat]")
    end: list[float] = Field(..., min_length=2, max_length=2, description="Bitiş [lng, lat]")
    hour: int | None = Field(default=None, ge=0, le=23)
    profile: Literal["shortest", "balanced", "safer"] = Field(
        default="balanced",
        description="Rota profili: shortest, balanced veya safer",
    )
    include_risk_explanation: bool = Field(
        default=False,
        description="Rota orta noktası için LLM destekli risk açıklaması ekle",
    )


class RouteDetailStats(BaseModel):
    route_id: str = ""
    geometry: LineString
    distance_m: float
    duration_s: float
    route_risk: float
    risk_score: float
    safety_score: float
    risk_coverage: float = Field(default=95.0, description="Dinamik risk verisiyle eşleşen kenar oranı (%)")
    edge_ids: list[str] = Field(default_factory=list)
    steps: list["NavigationStep"] = Field(default_factory=list)


class NavigationStep(BaseModel):
    step_id: str
    maneuver: Literal[
        "depart",
        "continue",
        "turn_left",
        "turn_right",
        "sharp_left",
        "sharp_right",
        "arrive",
    ]
    instruction: str
    street_name: str | None = None
    way_type: str | None = None
    distance_m: float
    duration_s: float
    bearing_before: float
    bearing_after: float
    location: list[float] = Field(min_length=2, max_length=2)
    edge_ids: list[str] = Field(default_factory=list)


class RouteComparisonStats(BaseModel):
    risk_reduction_pct: float
    extra_distance_m: float
    extra_distance_pct: float
    time_difference_s: float
    selected_profile: Literal["shortest", "balanced", "safer"] = "balanced"
    max_detour_pct: float = 15.0
    candidate_count: int = 1
    eligible_candidate_count: int = 1
    meaningful_safer_alternative: bool = False
    decision_reason: str = "no_meaningful_safer_alternative"
    distinct_from_balanced: bool = True


class RouteMetadata(BaseModel):
    schema_version: str = "1.0"
    graph_version: str
    risk_model_version: str = "crime65-light20-live15-v1"
    response_generated_at: str
    risk_snapshot_at: str
    crime_data_updated_at: str | None = None
    lighting_data_updated_at: str | None = None
    routing_engine: str = "compact"
    algorithm: str = "scipy_dijkstra"
    routing_profile: Literal["shortest", "balanced", "safer"] = "balanced"
    selection_method: str = "detour_budget_multi_candidate"
    candidate_alphas: list[float] = Field(default_factory=list)
    safety_disclaimer: str = "Güvenlik skoru kesin güvenlik garantisi değildir."


class StreetRiskRequest(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    hour: int | None = Field(default=None, ge=0, le=23)


class RiskChannels(BaseModel):
    crime: float
    lighting: float
    live: float
    total: float


class StreetRiskExplanationResponse(BaseModel):
    h3_index: str
    risk_level: str
    explanation: str
    factors: list[str]
    channels: RiskChannels
    total_risk: float | None = None
    crime_risk: float
    lighting_risk: float
    live_risk: float
    data_available: bool
    observed_risk_level: str
    risk_snapshot_at: str | None = None
    explanation_method: str = "deterministic_rules"
    disclaimer: str = "Güvenlik skoru kesin güvenlik garantisi değildir."


class RouteRiskExplanationResponse(BaseModel):
    """Rotanın tamamı için birleştirilmiş risk açıklaması.

    Tek noktalık ``StreetRiskExplanationResponse``'tan farkı, değerlerin rota
    geometrisi boyunca uzunluk ağırlıklı olarak toplanmasıdır; bu sayede
    açıklama gösterilen ``route_risk`` ile tutarlıdır.
    """

    risk_level: str
    explanation: str
    factors: list[str]
    channels: RiskChannels
    total_risk: float | None = None
    crime_risk: float = 0.0
    lighting_risk: float = 0.0
    live_risk: float = 0.0
    route_risk: float = 0.0
    high_risk_share_pct: float = 0.0
    data_coverage_pct: float = 0.0
    sampled_cell_count: int = 0
    data_available: bool
    observed_risk_level: str
    risk_snapshot_at: str | None = None
    explanation_method: str = "deterministic_rules"
    disclaimer: str = "Güvenlik skoru kesin güvenlik garantisi değildir."


class RouteResponse(BaseModel):
    schema_version: str = "1.0"
    route_id: str
    safe_route: RouteDetailStats
    shortest_route: RouteDetailStats
    comparison: RouteComparisonStats
    metadata: RouteMetadata
    risk_explanation: RouteRiskExplanationResponse | None = None

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


class HeatmapPoint(BaseModel):
    h3_index: str = ""
    h3_resolution: int = 9
    lat: float
    lng: float
    risk_crime: float = 0.0
    risk_lighting: float = 0.0
    risk_live: float = 0.0
    total_risk: float


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


STATUS_MESSAGES = {
    "pending": "Topluluk doğrulaması bekleniyor.",
    "processing": "İhbar analiz ediliyor.",
    "accepted": "İhbar bağımsız bildirimlerle doğrulandı.",
    "rejected": "İhbar doğrulama kriterlerini karşılamadı.",
    "expired": "İhbar doğrulanmadan zaman aşımına uğradı.",
}


class ReportCreate(BaseModel):
    text: str = Field(..., min_length=10, max_length=500, description="İhbar açıklaması (10-500 karakter)")
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    category: str = Field(default="general", description="Kategori: general, lighting, crime, harassment, obstacle")
    priority: Literal["normal", "urgent"] = Field(default="normal", description="İhbar önceliği: normal veya urgent")
    reporter_installation_id: str | None = Field(default=None, max_length=128, description="Kuruluma özel anonim UUID v4")


class ReportResponse(BaseModel):
    ok: bool
    id: str | None = None
    tracking_token: str | None = None
    status: str = "pending"
    message: str = "İhbarınız alındı ve topluluk doğrulaması bekleniyor."
    event_id: str | None = None
    event_status: str | None = None
    validation_score: float | None = None
    cluster_report_count: int | None = None
    live_risk_applied: bool = False


class ReportDetailResponse(BaseModel):
    id: str
    status: str = "pending"
    category: str = "general"
    created_at: str
    message: str = "Topluluk doğrulaması bekleniyor."
    description: str | None = None


class UserProfileResponse(BaseModel):
    user_id: str
    display_name: str | None = None
    role: Literal["user", "moderator", "admin"] = "user"
    deletion_requested_at: str | None = None


class MyReportsResponse(BaseModel):
    reports: list[ReportDetailResponse]


class AccountDeletionResponse(BaseModel):
    status: Literal["scheduled", "cancelled"]
    requested_at: str | None = None
    message: str


class HeatmapNearbyItem(BaseModel):
    h3_index: str
    lat: float
    lng: float
    distance_meters: float
    risk_crime: float
    risk_lighting: float
    risk_live: float
    total_risk: float


class HeatmapNearbyResponse(BaseModel):
    center: dict[str, float]
    radius_meters: float
    count: int
    items: list[HeatmapNearbyItem]




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



# Sınırlı Rotalama Semaphore ve Bekleme Kuyruğu Sayaçları
_route_semaphore = asyncio.Semaphore(settings.routing_max_concurrency)
_waiting_request_count = 0


# --- API ENDPOINT'LERİ ---
@app.get("/")
def read_root():
    return {"message": "Safe Route App Backend Çalışıyor!"}


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/health/ready")
async def readiness_check(request: Request):
    if not getattr(request.app.state, "ready", False):
        raise HTTPException(status_code=503, detail="Hizmet henüz hazır değil.")
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(select(1))
    except Exception as exc:
        raise PersistenceError("readiness database check failed") from exc
    return {
        "status": "ok",
        "routing_engine": getattr(settings, "routing_engine", "compact"),
        "h3_resolution": settings.routing_h3_resolution,
    }


@app.get("/health/data")
def data_health_check(request: Request):
    health = getattr(request.app.state, "data_health", {"status": "unavailable"})
    if health.get("status") != "ok":
        raise HTTPException(status_code=503, detail="Risk verisi hazır değil.")
    return health


@app.get("/api/v1/nlp/health")
@app.get("/health/nlp")
def nlp_health_check():
    return get_nlp_analyzer().get_health()


@app.get("/metrics", include_in_schema=False)
def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/api/v1/route", response_model=RouteResponse, response_model_exclude_none=True)
async def get_route(payload: RouteRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    global _waiting_request_count
    eng = request.app.state.engine

    start_lng, start_lat = payload.start[0], payload.start[1]
    end_lng, end_lat = payload.end[0], payload.end[1]

    _ensure_within_chicago(start_lat, start_lng, "Başlangıç")
    _ensure_within_chicago(end_lat, end_lng, "Bitiş")

    if _waiting_request_count >= settings.routing_queue_limit:
        ROUTE_REQUESTS.labels(payload.profile, "overloaded").inc()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sistem yüksek yük altında. Lütfen birkaç saniye sonra tekrar deneyin.",
            headers={"Retry-After": str(settings.retry_after_seconds)}
        )

    t_request_start = time.time()
    _waiting_request_count += 1
    ROUTING_QUEUE_DEPTH.set(_waiting_request_count)

    try:
        t_queue_start = time.time()
        async with _route_semaphore:
            t_compute_start = time.time()
            queue_wait_ms = (t_compute_start - t_queue_start) * 1000.0

            route_selection = await run_in_threadpool(
                eng.compute_profiled_route,
                start_lat=start_lat,
                start_lng=start_lng,
                end_lat=end_lat,
                end_lng=end_lng,
                profile=payload.profile,
            )
            selected_candidate = route_selection.selected
            shortest_candidate = route_selection.shortest
            (
                safe_coords,
                distance_m,
                safety_score,
                route_risk,
                safe_coverage,
            ) = selected_candidate.legacy_tuple()
            (
                shortest_coords,
                _shortest_distance,
                _shortest_safety,
                _shortest_risk,
                shortest_coverage,
            ) = shortest_candidate.legacy_tuple()
            t_compute_end = time.time()
            routing_compute_ms = (t_compute_end - t_compute_start) * 1000.0

    except Exception as exc:
        ROUTE_REQUESTS.labels(payload.profile, "error").inc()
        logger.exception(
            "route_compute_failed",
            extra={"request_id": _request_id(request)},
        )
        raise HTTPException(
            status_code=422,
            detail="Bu başlangıç ve varış için rota hesaplanamadı.",
        ) from exc
    finally:
        _waiting_request_count = max(0, _waiting_request_count - 1)
        ROUTING_QUEUE_DEPTH.set(_waiting_request_count)

    t_request_end = time.time()
    total_latency_ms = (t_request_end - t_request_start) * 1000.0

    duration_s = distance_m / routing.WALKING_SPEED_MPS
    shortest_duration_s = _shortest_distance / routing.WALKING_SPEED_MPS

    extra_dist_m = max(0.0, distance_m - _shortest_distance)
    extra_dist_pct = round((extra_dist_m / _shortest_distance * 100.0), 1) if _shortest_distance > 0 else 0.0
    risk_red_pct = round(((_shortest_risk - route_risk) / max(0.0001, _shortest_risk) * 100.0), 1) if _shortest_risk > route_risk else 0.0
    time_diff_s = max(0.0, duration_s - shortest_duration_s)

    etl_info = await crud.get_latest_etl_runs(db)

    response.headers["X-Queue-Wait-Ms"] = f"{queue_wait_ms:.2f}"
    response.headers["X-Routing-Compute-Ms"] = f"{routing_compute_ms:.2f}"
    response.headers["X-Total-Latency-Ms"] = f"{total_latency_ms:.2f}"
    response.headers["X-Route-Candidate-Count"] = str(
        route_selection.candidate_count
    )
    response.headers["X-Route-Decision"] = route_selection.decision_reason

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
        time_difference_s=round(time_diff_s, 1),
        selected_profile=route_selection.requested_profile,
        max_detour_pct=route_selection.max_detour_pct,
        candidate_count=route_selection.candidate_count,
        eligible_candidate_count=route_selection.eligible_candidate_count,
        meaningful_safer_alternative=route_selection.meaningful_safer_alternative,
        decision_reason=route_selection.decision_reason,
        distinct_from_balanced=route_selection.distinct_from_balanced,
    )

    metadata_stats = RouteMetadata(
        graph_version=getattr(eng, "graph_artifact_id", "unknown"),
        response_generated_at=datetime.now(timezone.utc).isoformat(),
        risk_snapshot_at=etl_info["risk_snapshot_at"],
        crime_data_updated_at=etl_info["crime_data_updated_at"],
        lighting_data_updated_at=etl_info["lighting_data_updated_at"],
        routing_engine=getattr(settings, "routing_engine", "compact"),
        algorithm="scipy_dijkstra",
        routing_profile=route_selection.requested_profile,
        selection_method="detour_budget_multi_candidate",
        candidate_alphas=list(
            parse_candidate_alphas(
                getattr(settings, "routing_candidate_alphas", None),
                required_alpha=float(
                    getattr(settings, "routing_risk_alpha", 2.0)
                ),
            )
        ),
    )

    graph_version = metadata_stats.graph_version
    safe_route_id, safe_edge_ids, safe_steps = build_navigation_contract(
        safe_coords,
        selected_candidate.path_signature,
        graph_version,
        route_selection.requested_profile,
        metadata_stats.risk_snapshot_at,
        selected_candidate.edge_signature,
        selected_candidate.street_names,
        selected_candidate.way_types,
    )
    shortest_route_id, shortest_edge_ids, shortest_steps = build_navigation_contract(
        shortest_coords,
        shortest_candidate.path_signature,
        graph_version,
        "shortest",
        metadata_stats.risk_snapshot_at,
        shortest_candidate.edge_signature,
        shortest_candidate.street_names,
        shortest_candidate.way_types,
    )

    safe_stats.route_id = safe_route_id
    safe_stats.edge_ids = safe_edge_ids
    safe_stats.steps = [NavigationStep(**step) for step in safe_steps]
    shortest_stats.route_id = shortest_route_id
    shortest_stats.edge_ids = shortest_edge_ids
    shortest_stats.steps = [NavigationStep(**step) for step in shortest_steps]

    risk_explanation: RouteRiskExplanationResponse | None = None
    if payload.include_risk_explanation and safe_coords:
        explanation_payload = await build_route_risk_explanation(
            db,
            coordinates=safe_coords,
            route_risk=route_risk,
            profile=route_selection.requested_profile,
            distance_m=distance_m,
            detour_pct=extra_dist_pct,
            risk_reduction_pct=risk_red_pct,
        )
        risk_explanation = RouteRiskExplanationResponse(**explanation_payload)

    ROUTE_REQUESTS.labels(payload.profile, "success").inc()
    return RouteResponse(
        route_id=safe_route_id,
        safe_route=safe_stats,
        shortest_route=shortest_stats,
        comparison=comparison_stats,
        metadata=metadata_stats,
        risk_explanation=risk_explanation,
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
    )


@app.get("/api/v1/heatmap/nearby", response_model=HeatmapNearbyResponse)
async def get_heatmap_nearby(
    lat: float = Query(..., ge=-90, le=90, description="Merkez Enlem"),
    lng: float = Query(..., ge=-180, le=180, description="Merkez Boylam"),
    radius: float | None = Query(
        default=None,
        ge=10.0,
        le=10000.0,
        description="Arama yarıçapı (metre, tercih edilen parametre)",
    ),
    radius_m: float | None = Query(
        default=None,
        ge=10.0,
        le=10000.0,
        description="Geriye dönük uyumlu arama yarıçapı (metre)",
    ),
    limit: int = Query(default=100, ge=1, le=500, description="Maksimum sonuç sayısı"),
    db: AsyncSession = Depends(get_db),
):
    """
    PostGIS ST_DWithin ile verilen koordinat etrafındaki H3 riski taşıyan noktaları veritabanı seviyesinde spatial index ile çeker.
    """
    _ensure_within_chicago(lat, lng, "Heatmap Nearby")
    selected_radius = (
        float(radius)
        if radius is not None
        else float(radius_m)
        if radius_m is not None
        else 1000.0
    )

    pts = await crud.get_nearby_heatmap_points(
        db,
        lat=lat,
        lng=lng,
        radius_meters=selected_radius,
        limit=limit,
        h3_resolution=getattr(
            settings,
            "routing_h3_resolution",
            LEGACY_H3_RESOLUTION,
        ),
    )
    items = []
    for p in pts:
        dy = (p.lat - lat) * 111000.0
        dx = (p.lng - lng) * 82900.0
        dist_m = math.sqrt(dx * dx + dy * dy)

        items.append(
            HeatmapNearbyItem(
                h3_index=p.h3_index,
                lat=p.lat,
                lng=p.lng,
                distance_meters=round(dist_m, 1),
                risk_crime=round(p.risk_crime or 0.0, 4),
                risk_lighting=round(p.risk_lighting or 0.0, 4),
                risk_live=round(p.risk_live or 0.0, 4),
                total_risk=round(p.total_risk or 0.0, 4),
            )
        )

    items.sort(key=lambda x: x.distance_meters)

    return HeatmapNearbyResponse(
        center={"lat": lat, "lng": lng},
        radius_meters=selected_radius,
        count=len(items),
        items=items,
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
    db: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(require_current_user),
):
    _ensure_within_chicago(payload.lat, payload.lng, "İhbar")

    category = payload.category.lower() if payload.category else "general"
    if category not in VALID_REPORT_CATEGORIES:
        REPORT_REQUESTS.labels("invalid", "rejected").inc()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Geçersiz kategori '{category}'. İzin verilen kategoriler: {list(VALID_REPORT_CATEGORIES)}"
        )

    client_ip = request.client.host if request.client else "127.0.0.1"
    _check_report_rate_limit(client_ip)

    profile = await crud.get_or_create_user_profile(db, user.user_id)
    if profile.deletion_requested_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Hesap silme isteği beklerken yeni bildirim gönderilemez.",
        )

    # İçerik analizi: siyaset/spam/anlamsız metin ihbar sayılmaz, bildirim gitmez.
    nlp_gate = get_nlp_analyzer().analyze(payload.text)
    if not nlp_gate.is_actionable:
        REPORT_REQUESTS.labels(category, "rejected").inc()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=nlp_gate.rejection_reason
            or "Bu metin güvenlik ihbarı olarak kabul edilmedi.",
        )

    # Mükerrer engeli: aynı hesabın aynı noktaya kısa sürede tekrar atması.
    is_duplicate = await crud.check_duplicate_report(
        db,
        payload.lat,
        payload.lng,
        reporter_hash=crud.generate_reporter_hash(payload.reporter_installation_id),
        user_id=user.user_id,
    )
    if is_duplicate:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Bu hesapla bu konumda son 10 dakika içinde zaten bir ihbar "
                "gönderildi. Spam korumasıdır (metin benzerliği değil). "
                "Farklı bir konum dene veya birkaç dakika bekle."
            ),
        )

    try:
        report = await crud.create_report(
            db,
            payload.lat,
            payload.lng,
            payload.text,
            category=category,
            priority=payload.priority,
            ip_address=None,
            reporter_installation_id=payload.reporter_installation_id,
            user_id=user.user_id,
        )


        report_id = getattr(report, "uuid_id", None) or str(getattr(report, "id", "1"))
        report_token = getattr(report, "tracking_token", None)

        event = await crud.process_report_and_event_clustering(db, report)
        event_status = getattr(event, "status", "pending") if event else "pending"
        validation_score = float(getattr(event, "validation_score", 0.0) or 0.0) if event else None
        cluster_count = int(getattr(event, "unique_reporter_count", 1) or 1) if event else 1
        live_risk_applied = False

        if event and event.status == "accepted":
            # Yalnızca REPORT_DEV_SOLO_ACCEPT veya önceki tanık onayı ile olur.
            background_tasks.add_task(
                apply_accepted_report_live_risk,
                app_state=request.app.state,
                latitude=payload.lat,
                longitude=payload.lng,
            )
            live_risk_applied = True
            status_msg = STATUS_MESSAGES.get("accepted", "İhbar doğrulandı.")
        elif event_status == "pending":
            status_msg = (
                "İhbar alındı ve analiz edildi. 1 km içindeki kullanıcılara "
                "tanık onayı (Gördüm / Görmedim / Emin değilim) soruluyor. "
                "Bir kişi 'Gördüm' derse haritada yayınlanır."
            )
        else:
            status_msg = STATUS_MESSAGES.get(event_status, "Durum güncelleniyor.")

        # Geçerli ihbar → 1 km tanık isteği (acil olmak zorunda değil).
        if event is not None and event_status == "pending":
            background_tasks.add_task(
                _run_witness_request_dispatch,
                event_id=int(event.id),
                report_id=int(report.id),
            )

        logger.info(
            "report_created",
            extra={
                "request_id": _request_id(request),
                "user_id": str(user.user_id),
                "report_uuid": str(report_id),
                "category": category,
                "event_status": event_status,
                "validation_score": validation_score,
                "priority": str(payload.priority),
            },
        )

        REPORT_REQUESTS.labels(category, "accepted").inc()
        # Olay kabul edildiyse bu ihbar da doğrulanmış sayılır; kümeye sonradan
        # katılan ihbarların 'pending' görünmesi kullanıcıyı yanıltıyordu.
        report_status = (
            "accepted"
            if event_status == "accepted"
            else (getattr(report, "status", None) or event_status)
        )
        return ReportResponse(
            ok=True,
            id=report_id,
            tracking_token=report_token,
            status=report_status,
            message=status_msg,
            event_id=getattr(event, "uuid_id", None) if event else None,
            event_status=event_status,
            validation_score=validation_score,
            cluster_report_count=cluster_count,
            live_risk_applied=live_risk_applied,
        )
    except HTTPException:
        raise
    except (ConfigurationError, PersistenceError):
        REPORT_REQUESTS.labels(category, "error").inc()
        raise
    except Exception as exc:
        REPORT_REQUESTS.labels(category, "error").inc()
        logger.exception(
            "report_create_failed",
            extra={"request_id": _request_id(request)},
        )
        raise HTTPException(
            status_code=500,
            detail="Bildirim kaydedilemedi.",
        ) from exc


@app.get("/api/v1/reports/map", response_model=PublicMapReportsResponse)
async def get_map_reports(
    minutes: int = Query(60, ge=5, le=60, description="Kaç dakika öncesine kadarki ihbarların getirileceği"),
    bbox: str | None = Query(None, description="west,south,east,north formatında coğrafi sınırlama"),
    category: str | None = Query(None, description="İhbar kategorisi filtresi"),
    limit: int = Query(500, ge=1, le=1000, description="Maksimum ihbar sayısı"),
    db: AsyncSession = Depends(get_db)
):
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
    report = await crud.get_report_by_uuid_and_token(db, uuid_id, token)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Erişim yetkiniz bulunmamaktadır veya geçersiz ihbar takip jetonu."
        )
    created_iso = report.created_at.isoformat() if report.created_at else datetime.now(timezone.utc).isoformat()
    status_val = report.status or "pending"
    msg = STATUS_MESSAGES.get(status_val, "Topluluk doğrulaması bekleniyor.")
    return ReportDetailResponse(
        id=report.uuid_id or str(report.id),
        status=status_val,
        category=report.category or "general",
        created_at=created_iso,
        message=msg
    )


class DeviceRegisterRequest(BaseModel):
    expo_push_token: str = Field(..., min_length=8, max_length=255)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)


class LocationUpdateRequest(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)


class AlertRespondRequest(BaseModel):
    response: Literal["confirm", "deny", "unsure"]


class PendingAlertItem(BaseModel):
    alert_id: str
    event_id: str | None = None
    phase: str = "witness_request"
    title: str
    body: str
    latitude: float
    longitude: float
    distance_m: float
    confirm_count: int = 0
    created_at: str | None = None
    llm_method: str | None = None


class AlertRespondResponse(BaseModel):
    ok: bool = True
    event_id: str
    alert_id: str
    response: str
    confirm_count: int
    deny_count: int
    broadcast_sent: bool = False
    broadcast_alert_id: str | None = None
    live_risk_applied: bool = False
    message: str


@app.post("/api/v1/me/device", status_code=status.HTTP_204_NO_CONTENT)
async def register_my_device(
    payload: DeviceRegisterRequest,
    db: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(require_current_user),
):
    """Expo push token + isteğe bağlı son konum kaydı (acil bildirim hedefleme)."""
    from services.emergency_alert_service import upsert_user_device

    await crud.get_or_create_user_profile(db, user.user_id)
    if payload.lat is not None and payload.lng is not None:
        _ensure_within_chicago(payload.lat, payload.lng, "Cihaz konumu")
    await upsert_user_device(
        db,
        user_id=user.user_id,
        expo_push_token=payload.expo_push_token,
        lat=payload.lat,
        lng=payload.lng,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/api/v1/me/location", status_code=status.HTTP_204_NO_CONTENT)
async def update_my_location(
    payload: LocationUpdateRequest,
    db: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(require_current_user),
):
    from services.emergency_alert_service import (
        ensure_user_device_for_location,
        update_user_location,
    )

    _ensure_within_chicago(payload.lat, payload.lng, "Konum")
    updated = await update_user_location(
        db, user_id=user.user_id, lat=payload.lat, lng=payload.lng
    )
    # Emülatörde Expo push token gelmeyebilir; konum yine de kaydedilsin ki
    # 1 km tanık / pending alert hedeflemesi çalışsın.
    if updated <= 0:
        await ensure_user_device_for_location(
            db,
            user_id=user.user_id,
            lat=payload.lat,
            lng=payload.lng,
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/api/v1/me/alerts/pending", response_model=list[PendingAlertItem])
async def list_my_pending_alerts(
    lat: float | None = Query(default=None, ge=-90, le=90),
    lng: float | None = Query(default=None, ge=-180, le=180),
    db: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(require_current_user),
):
    """Push gelmese bile yakındaki 'gördünüz mü?' isteklerini listeler."""
    from services.emergency_alert_service import list_nearby_pending_alerts_for_user

    if lat is not None and lng is not None:
        _ensure_within_chicago(lat, lng, "Konum")
    items = await list_nearby_pending_alerts_for_user(
        db, user_id=user.user_id, lat=lat, lng=lng
    )
    return [PendingAlertItem(**item) for item in items]


class JuryDemoRequest(BaseModel):
    """Konum artık opsiyonel; simülasyon sabit Magnificent Mile kullanır."""
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)


class JuryDemoResponse(BaseModel):
    ok: bool = True
    alert: PendingAlertItem
    message: str


@app.post("/api/v1/me/alerts/jury-demo", response_model=JuryDemoResponse)
async def start_jury_demo_alert(
    payload: JuryDemoRequest = JuryDemoRequest(),
    db: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(require_current_user),
):
    """Jüri videosu: Magnificent Mile ihbarı; her çağrıda sıfırdan başlar."""
    from services.emergency_alert_service import start_jury_demo_witness_alert

    _ = payload  # Konum sabit Mag Mile; istemci gövdesi geriye dönük uyumluluk.
    try:
        item = await start_jury_demo_witness_alert(db, user_id=user.user_id)
    except Exception:
        logger.exception("jury_demo_failed")
        raise HTTPException(
            status_code=500,
            detail="Jüri simülasyonu oluşturulamadı. Backend loguna bakın.",
        ) from None
    message = str(item.pop("message", "Jüri simülasyonu başlatıldı."))
    item.pop("viewer_lat", None)
    item.pop("viewer_lng", None)
    return JuryDemoResponse(ok=True, alert=PendingAlertItem(**item), message=message)


@app.post(
    "/api/v1/alerts/{event_id}/respond",
    response_model=AlertRespondResponse,
)
async def respond_to_emergency_alert(
    event_id: str,
    payload: AlertRespondRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(require_current_user),
):
    """Tanık yanıtı: confirm → eşik dolunca 1 km herkese yayın."""
    from services.emergency_alert_service import respond_to_alert

    try:
        result = await respond_to_alert(
            db,
            event_uuid=event_id,
            user_id=user.user_id,
            response=payload.response,
            app_state=request.app.state,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="Acil ihbar bulunamadı.") from None
    except PermissionError:
        raise HTTPException(
            status_code=403,
            detail="Kendi ihbarınızı tanık olarak onaylayamazsınız.",
        ) from None
    except ValueError:
        raise HTTPException(
            status_code=409,
            detail="Bu ihbara zaten yanıt verdiniz.",
        ) from None

    if result.get("live_risk_applied") or result.get("broadcast_sent"):
        # Yayın sonrası risk_live — rapor konumunu event'ten çek.
        event_res = await db.execute(
            select(ReportEventModel).where(ReportEventModel.uuid_id == event_id)
        )
        event = event_res.scalars().first()
        if event is not None:
            report_res = await db.execute(
                select(ReportModel)
                .where(ReportModel.event_id == event.id)
                .order_by(ReportModel.created_at.asc())
            )
            seed = report_res.scalars().first()
            if seed is not None:
                background_tasks.add_task(
                    apply_accepted_report_live_risk,
                    app_state=request.app.state,
                    latitude=float(seed.latitude),
                    longitude=float(seed.longitude),
                )
                result["live_risk_applied"] = True

    if result.get("broadcast_sent"):
        message = "Gördüm onayın kaydedildi. İhbar haritada yayınlandı."
    elif payload.response == "confirm":
        message = "Gördüm onayın kaydedildi."
    elif payload.response == "unsure":
        message = "Yanıtın kaydedildi (emin değilim)."
    else:
        message = "Görmedim yanıtın kaydedildi."

    return AlertRespondResponse(
        ok=True,
        event_id=result["event_id"],
        alert_id=result["alert_id"],
        response=result["response"],
        confirm_count=result["confirm_count"],
        deny_count=result["deny_count"],
        broadcast_sent=result["broadcast_sent"],
        broadcast_alert_id=result.get("broadcast_alert_id"),
        live_risk_applied=bool(result.get("live_risk_applied")),
        message=message,
    )


@app.get("/api/v1/me", response_model=UserProfileResponse)
async def get_my_profile(
    db: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(require_current_user),
):
    profile = await crud.get_or_create_user_profile(db, user.user_id)
    return UserProfileResponse(
        user_id=str(profile.user_id),
        display_name=profile.display_name,
        role=profile.role,
        deletion_requested_at=(
            profile.deletion_requested_at.isoformat()
            if profile.deletion_requested_at
            else None
        ),
    )


@app.get("/api/v1/me/reports", response_model=MyReportsResponse)
async def get_my_reports(
    limit: int = Query(default=100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(require_current_user),
):
    reports = await crud.list_user_reports(db, user.user_id, limit=limit)
    logger.info(
        "my_reports_listed",
        extra={
            "user_id": str(user.user_id),
            "count": len(reports),
        },
    )
    return MyReportsResponse(
        reports=[
            ReportDetailResponse(
                id=str(report.uuid_id or report.id),
                status=report.status or "pending",
                category=report.category or "general",
                created_at=(
                    report.created_at.isoformat()
                    if report.created_at
                    else datetime.now(timezone.utc).isoformat()
                ),
                message=STATUS_MESSAGES.get(
                    report.status or "pending", "Durum güncelleniyor."
                ),
                description=getattr(report, "description", None),
            )
            for report in reports
        ]
    )


@app.delete("/api/v1/me/reports/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_my_report(
    report_id: str,
    db: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(require_current_user),
):
    deleted = await crud.delete_user_report(db, user.user_id, report_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="İhbar bulunamadı.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.delete("/api/v1/me", response_model=AccountDeletionResponse, status_code=202)
async def request_account_deletion(
    db: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(require_current_user),
):
    profile = await crud.set_account_deletion_request(db, user.user_id, True)
    return AccountDeletionResponse(
        status="scheduled",
        requested_at=profile.deletion_requested_at.isoformat(),
        message="Hesap silme isteği alındı. İşlem tamamlanana kadar isteği iptal edebilirsiniz.",
    )


@app.post("/api/v1/me/deletion-cancel", response_model=AccountDeletionResponse)
async def cancel_account_deletion(
    db: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(require_current_user),
):
    await crud.set_account_deletion_request(db, user.user_id, False)
    return AccountDeletionResponse(
        status="cancelled",
        requested_at=None,
        message="Hesap silme isteği iptal edildi.",
    )



@app.get("/api/v1/heatmap", response_model=list[HeatmapPoint])
async def get_heatmap(db: AsyncSession = Depends(get_db)):
    selected_resolution = validate_h3_resolution(
        getattr(settings, "routing_h3_resolution", LEGACY_H3_RESOLUTION)
    )
    points = await crud.get_all_heatmap_points(
        db,
        h3_resolution=selected_resolution,
    )
    return [
        HeatmapPoint(
            h3_index=getattr(p, "h3_index", "") or "",
            h3_resolution=getattr(p, "h3_resolution", selected_resolution),
            lat=getattr(p, "lat", 0.0),
            lng=getattr(p, "lng", 0.0),
            risk_crime=round(getattr(p, "risk_crime", 0.0) or 0.0, 4),
            risk_lighting=round(getattr(p, "risk_lighting", 0.0) or 0.0, 4),
            risk_live=round(getattr(p, "risk_live", 0.0) or 0.0, 4),
            total_risk=round(getattr(p, "total_risk", 0.0) or 0.0, 4)
        )
        for p in points
    ]

@app.get("/api/v1/heatmap/map", response_model=HeatmapGeoJSONResponse)
async def get_heatmap_map(
    bbox: str | None = Query(None, description="west,south,east,north biçiminde opsiyonel coğrafi sınırlama"),
    channel: str = Query("total", description="Risk kanalı: total, crime, lighting, live"),
    include_no_data: bool = Query(True, description="Verisi bulunmayan H3 hücrelerinin dahil edilip edilmeyeceği"),
    format: str = Query("geojson", description="Çıktı formatı (varsayılan: geojson)"),
    h3_resolution: int | None = Query(
        default=None,
        ge=9,
        le=10,
        description="H3 çözünürlüğü (9 veya 10; varsayılan aktif routing çözünürlüğü)",
    ),
    db: AsyncSession = Depends(get_db)
):
    valid_channels = {"total", "crime", "lighting", "live"}
    clean_channel = channel.lower() if channel else "total"
    if clean_channel not in valid_channels:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Geçersiz risk kanalı '{channel}'. İzin verilen kanallar: {list(valid_channels)}"
        )

    selected_resolution = validate_h3_resolution(
        h3_resolution
        if h3_resolution is not None
        else getattr(settings, "routing_h3_resolution", LEGACY_H3_RESOLUTION)
    )
    data = await crud.get_heatmap_geojson_map(
        db,
        bbox=bbox,
        channel=clean_channel,
        include_no_data=include_no_data,
        h3_resolution=selected_resolution,
    )
    return data



@app.post("/api/v1/street-risk-explanation", response_model=StreetRiskExplanationResponse)
async def get_street_risk_explanation(payload: StreetRiskRequest, db: AsyncSession = Depends(get_db)):
    _ensure_within_chicago(payload.lat, payload.lng, "Konum")
    explanation_payload = await build_street_risk_explanation(
        db, lat=payload.lat, lng=payload.lng
    )
    return StreetRiskExplanationResponse(**explanation_payload)
