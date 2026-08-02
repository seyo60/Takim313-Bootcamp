import pytest
import os
from unittest.mock import patch, MagicMock
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, text, func

from models import Base, H3HeatmapModel, ETLRunModel
from chicago_311_lighting_etl import (
    fetch_chicago_311_lighting,
    run_lighting_etl,
    build_date_windows,
    ETLCheckpointManager,
    ETLFetchError,
)

TEST_DB_URL = os.getenv("SAFEROUTE_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(
    not TEST_DB_URL,
    reason="SAFEROUTE_TEST_DATABASE_URL isolated PostGIS target is not configured",
)


@pytest.fixture(scope="module")
async def test_engine():
    assert TEST_DB_URL
    engine = create_async_engine(TEST_DB_URL, echo=False, pool_pre_ping=True, pool_recycle=300)
    yield engine
    await engine.dispose()


@pytest.fixture(scope="module", autouse=True)
async def init_test_db(test_engine):
    """Module başında bir kez tabloları silip yeniden oluşturur."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_h3_heatmap_resolution_index ON h3_heatmap (h3_resolution, h3_index);"))


@pytest.fixture(autouse=True)
async def clean_test_db(test_engine, tmp_path):
    """Her test öncesinde veritabanı tablolarını ve geçici checkpoint'leri temizler."""
    async with test_engine.begin() as conn:
        await conn.execute(text("TRUNCATE h3_heatmap, reports, report_events, etl_runs RESTART IDENTITY CASCADE;"))
    yield


@pytest.fixture
def tmp_checkpoint_mgr(tmp_path):
    cp_file = tmp_path / "test_lighting_checkpoint.json"
    cache_file = tmp_path / "test_lighting_cache.json"
    return ETLCheckpointManager(checkpoint_file=cp_file, cache_file=cache_file)


def _generate_mock_records(count: int, start_idx: int = 0, date_str: str = "2026-07-28T12:00:00.000", same_date: bool = False):
    records = []
    for i in range(count):
        idx = start_idx + i
        dt_str = date_str
        sr_num = f"SR26-{idx:08d}"
        lat = 41.8781 if same_date else 41.8781 + (idx * 0.0001)
        lng = -87.6298 if same_date else -87.6298 + (idx * 0.0001)
        records.append({
            "sr_number": sr_num,
            "created_date": dt_str,
            "sr_type": "Street Light Out Complaint",
            "status": "OPEN",
            "latitude": f"{lat:.5f}",
            "longitude": f"{lng:.5f}",
        })
    return records


@pytest.mark.anyio
async def test_1_date_windows_boundary_continuity():
    """Tarih pencerelerinin sınır çakışması veya boşluğu olmadan bölündüğünü doğrular."""
    windows = build_date_windows(start_date_str="2026-07-01T00:00:00.000", window_days=7)
    assert len(windows) > 0

    for i in range(len(windows) - 1):
        w_current_start = windows[i][0]
        w_next_end = windows[i + 1][1]
        assert w_current_start == w_next_end, f"Pencere sınır uyumsuzluğu: {w_current_start} != {w_next_end}"


@pytest.mark.anyio
@patch("chicago_311_lighting_etl._make_api_request_with_retry")
async def test_2_no_duplicates_between_windows(mock_api, tmp_checkpoint_mgr):
    """Farklı tarih pencereleri arasında mükerrer kayıt oluşmadığını doğrular."""
    page_win0 = _generate_mock_records(5, start_idx=0, date_str="2026-07-25T12:00:00.000")
    page_win1 = _generate_mock_records(5, start_idx=5, date_str="2026-07-15T12:00:00.000")

    mock_api.side_effect = [page_win0, [], page_win1, []]

    results = fetch_chicago_311_lighting(
        start_date="2026-07-10T00:00:00.000",
        window_days=7,
        checkpoint_mgr=tmp_checkpoint_mgr,
    )

    assert len(results) == 10
    sr_set = set(r["sr_number"] for r in results)
    assert len(sr_set) == 10


@pytest.mark.anyio
@patch("chicago_311_lighting_etl._make_api_request_with_retry")
async def test_3_adaptive_page_size_reduction_on_timeout(mock_api, tmp_checkpoint_mgr):
    """Zaman aşımı / API hatası alındığında sayfa boyutunun 1000 -> 500 -> 250 seviyelerine düştüğünü doğrular."""
    mock_api.side_effect = [
        ETLFetchError("504 Gateway Timeout"),
        _generate_mock_records(5),
        [],
    ]

    results = fetch_chicago_311_lighting(
        start_date="2026-07-28T00:00:00.000",
        end_date="2026-07-29T00:00:00.000",
        window_days=1,
        page_size=1000,
        checkpoint_mgr=tmp_checkpoint_mgr,
    )

    assert len(results) == 5
    limit_used = mock_api.call_args_list[1][1]["params"]["$limit"]
    assert limit_used == 500


@pytest.mark.anyio
@patch("requests.get")
async def test_4_retry_preserves_same_cursor(mock_requests, tmp_checkpoint_mgr):
    """Ağ retry sırasında cursor ve $where sorgusunun değişmeden kaldığını doğrular."""
    mock_resp_500 = MagicMock()
    mock_resp_500.status_code = 500
    mock_resp_500.headers = {}

    mock_resp_200 = MagicMock()
    mock_resp_200.status_code = 200
    mock_resp_200.json.return_value = _generate_mock_records(3)

    mock_requests.side_effect = [mock_resp_500, mock_resp_200]

    with patch("time.sleep"):
        results = fetch_chicago_311_lighting(
            start_date="2026-07-28T00:00:00.000",
            end_date="2026-07-29T00:00:00.000",
            window_days=1,
            checkpoint_mgr=tmp_checkpoint_mgr,
        )

    assert len(results) == 3
    params1 = mock_requests.call_args_list[0][1]["params"]
    params2 = mock_requests.call_args_list[1][1]["params"]
    assert params1["$where"] == params2["$where"]


@pytest.mark.anyio
@patch("chicago_311_lighting_etl._make_api_request_with_retry")
async def test_5_checkpoint_creation_and_resume(mock_api, tmp_checkpoint_mgr):
    """Yarıda kesilen bir çekimin checkpoint'ten resume edilerek kaldığı yerden tamamlandığını doğrular."""
    rec_page1 = _generate_mock_records(5, start_idx=0, date_str="2026-07-28T12:00:00.000")
    rec_page2 = _generate_mock_records(5, start_idx=5, date_str="2026-07-28T10:00:00.000")

    # 1. Çalıştırma: 1. sayfadan sonra kesilsin
    mock_api.side_effect = [rec_page1, ETLFetchError("İşlem kesildi")]

    with pytest.raises(ETLFetchError):
        fetch_chicago_311_lighting(
            start_date="2026-07-28T00:00:00.000",
            end_date="2026-07-29T00:00:00.000",
            window_days=1,
            page_size=5,
            checkpoint_mgr=tmp_checkpoint_mgr,
        )

    # Checkpoint'in kaydedildiğini doğrula
    assert tmp_checkpoint_mgr.checkpoint_file.exists()
    cp_data = tmp_checkpoint_mgr.load()
    assert cp_data["status"] == "in_progress"
    assert cp_data["records_count"] == 5

    # 2. Çalıştırma (Resume): 2. sayfadan devam etsin
    mock_api.side_effect = [rec_page2, []]

    results_resumed = fetch_chicago_311_lighting(
        start_date="2026-07-28T00:00:00.000",
        end_date="2026-07-29T00:00:00.000",
        window_days=1,
        page_size=5,
        resume=True,
        checkpoint_mgr=tmp_checkpoint_mgr,
    )

    assert len(results_resumed) == 10
    final_cp = tmp_checkpoint_mgr.load()
    assert final_cp["status"] == "completed"


@pytest.mark.anyio
async def test_6_corrupt_checkpoint_rejection(tmp_checkpoint_mgr):
    """Bozuk / uyumsuz JSON checkpoint dosyasının açık bir ETLFetchError ile reddedildiğini doğrular."""
    tmp_checkpoint_mgr.ensure_dir()

    # Bozuk metin yaz
    with open(tmp_checkpoint_mgr.checkpoint_file, "w", encoding="utf-8") as f:
        f.write("{ INVALID JSON DATA ...")

    with pytest.raises(ETLFetchError) as exc_info:
        tmp_checkpoint_mgr.load(resume=True)
    assert "Bozuk/okunamayan checkpoint" in str(exc_info.value)


@pytest.mark.anyio
@patch("chicago_311_lighting_etl.fetch_chicago_311_lighting")
async def test_7_failed_fetch_prevents_db_and_etl_runs_write(mock_fetch, test_engine, tmp_checkpoint_mgr):
    """Başarısız API çekiminde veritabanına ve etl_runs'a hiçbir yazma yapılmadığını doğrular."""
    SessionLocal = sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    mock_fetch.side_effect = ETLFetchError("API Bağlantı Hatası")

    with patch("main.AsyncSessionLocal", side_effect=lambda: SessionLocal()):
        with pytest.raises(ETLFetchError):
            await run_lighting_etl(max_records=100, dry_run=False, checkpoint_mgr=tmp_checkpoint_mgr)

    async with SessionLocal() as session:
        h3_cnt = (await session.execute(select(func.count()).select_from(H3HeatmapModel))).scalar()
        etl_cnt = (await session.execute(select(func.count()).select_from(ETLRunModel))).scalar()
        assert h3_cnt == 0
        assert etl_cnt == 0


@pytest.mark.anyio
@patch("chicago_311_lighting_etl._make_api_request_with_retry")
async def test_8_full_success_marks_checkpoint_completed(mock_api, tmp_checkpoint_mgr):
    """Tam API çekimi sonrasında checkpoint durumunun completed olarak işaretlendiğini doğrular."""
    mock_api.side_effect = [_generate_mock_records(5), []]

    fetch_chicago_311_lighting(
        start_date="2026-07-28T00:00:00.000",
        end_date="2026-07-29T00:00:00.000",
        window_days=1,
        checkpoint_mgr=tmp_checkpoint_mgr,
    )

    cp_data = tmp_checkpoint_mgr.load()
    assert cp_data["status"] == "completed"


@pytest.mark.anyio
@patch("chicago_311_lighting_etl.fetch_chicago_311_lighting")
async def test_9_dry_run_prevents_db_writes(mock_fetch, test_engine, tmp_checkpoint_mgr):
    """dry_run=True ile çalıştırıldığında veritabanına hiçbir kayıt atılmadığını doğrular."""
    SessionLocal = sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    mock_fetch.return_value = _generate_mock_records(10)

    with patch("main.AsyncSessionLocal", side_effect=lambda: SessionLocal()):
        heatmap_data = await run_lighting_etl(max_records=10, dry_run=True, checkpoint_mgr=tmp_checkpoint_mgr)

    assert len(heatmap_data) > 0

    async with SessionLocal() as session:
        h3_cnt = (await session.execute(select(func.count()).select_from(H3HeatmapModel))).scalar()
        etl_cnt = (await session.execute(select(func.count()).select_from(ETLRunModel))).scalar()
        assert h3_cnt == 0
        assert etl_cnt == 0


@pytest.mark.anyio
@patch("chicago_311_lighting_etl.fetch_chicago_311_lighting")
async def test_10_risk_lighting_bounded_zero_to_one(mock_fetch, test_engine, tmp_checkpoint_mgr):
    """Aşırı sayıda arıza içeren durumlarda risk_lighting değerlerinin 0 ile 1 aralığında kaldığını doğrular."""
    SessionLocal = sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    # 100 adet aynı noktada açık arıza
    heavy_records = _generate_mock_records(100, same_date=True)
    mock_fetch.return_value = heavy_records

    with patch("main.AsyncSessionLocal", side_effect=lambda: SessionLocal()):
        heatmap_data = await run_lighting_etl(max_records=100, dry_run=True, checkpoint_mgr=tmp_checkpoint_mgr)

    for cell_data in heatmap_data.values():
        risk = cell_data["risk_lighting"]
        assert 0.0 <= risk <= 1.0, f"Out of bounds risk: {risk}"
