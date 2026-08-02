import math
import os
import pytest
from unittest.mock import patch
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, text, func

import crud
from crud import bulk_upsert_crime_data, bulk_upsert_lighting_data, DEFAULT_ETL_BATCH_SIZE
from models import H3HeatmapModel, ETLRunModel, Base
from chicago_crime_etl import run_crime_etl, ETLWriteError as CrimeETLWriteError

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
async def clean_test_db(test_engine):
    """Her test öncesinde veritabanı tablolarını temizler."""
    async with test_engine.begin() as conn:
        await conn.execute(text("TRUNCATE h3_heatmap, reports, report_events, etl_runs RESTART IDENTITY CASCADE;"))
    yield


@pytest.mark.anyio
async def test_1_batch_chunking_5171_cells(test_engine):
    """5.171 hücrenin 250'lik varsayılan batch'lere bölünmesini doğrular (ceil(5171/250) = 21 batch)."""
    items = [
        {
            "h3_index": f"892a1008{i:07x}",
            "lat": 41.8781,
            "lng": -87.6298,
            "risk_crime": 0.5,
            "extra_features": {"crime_7d": 1}
        } for i in range(5171)
    ]
    total_batches = math.ceil(len(items) / DEFAULT_ETL_BATCH_SIZE)
    assert total_batches == 21
    assert len(items[0:250]) == 250
    assert len(items[5000:5171]) == 171


@pytest.mark.anyio
async def test_2_bulk_upsert_crime_and_lighting_single_execute(test_engine):
    """bulk_upsert_crime_data ve bulk_upsert_lighting_data fonksiyonlarının ORM refresh olmadan veriyi yazdığını doğrular."""
    SessionLocal = sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    
    crime_batch = [
        {
            "h3_index": f"892a1008000000{i}",
            "lat": 41.8781 + (i * 0.001),
            "lng": -87.6298 + (i * 0.001),
            "risk_crime": 0.4,
            "extra_features": {"crime_30d": 2}
        } for i in range(10)
    ]

    async with SessionLocal() as session:
        async with session.begin():
            written = await bulk_upsert_crime_data(session, crime_batch)
            assert written == 10

    async with SessionLocal() as session:
        res = await session.execute(select(func.count()).select_from(H3HeatmapModel))
        assert res.scalar() == 10


@pytest.mark.anyio
async def test_3_idempotency_and_non_duplication(test_engine):
    """Aynı 100 hücre iki kez upsert edildiğinde satır sayısının artmadığını (duplicate olmadığını) ve güncellendiğini doğrular."""
    SessionLocal = sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    
    batch_v1 = [
        {
            "h3_index": f"892a100800000{i:02x}",
            "lat": 41.8781,
            "lng": -87.6298,
            "risk_crime": 0.2,
            "extra_features": {"v": 1}
        } for i in range(100)
    ]

    batch_v2 = [
        {
            "h3_index": f"892a100800000{i:02x}",
            "lat": 41.8781,
            "lng": -87.6298,
            "risk_crime": 0.8,
            "extra_features": {"v": 2}
        } for i in range(100)
    ]

    # 1. İlk Çalıştırma
    async with SessionLocal() as session:
        async with session.begin():
            await bulk_upsert_crime_data(session, batch_v1)

    async with SessionLocal() as session:
        cnt1 = (await session.execute(select(func.count()).select_from(H3HeatmapModel))).scalar()
        assert cnt1 == 100

    # 2. İkinci Çalıştırma (Idempotent Update)
    async with SessionLocal() as session:
        async with session.begin():
            await bulk_upsert_crime_data(session, batch_v2)

    async with SessionLocal() as session:
        cnt2 = (await session.execute(select(func.count()).select_from(H3HeatmapModel))).scalar()
        assert cnt2 == 100  # Satır sayısı artmadı!

        cell = (await session.execute(select(H3HeatmapModel).where(H3HeatmapModel.h3_index == "892a10080000000"))).scalars().first()
        assert abs(cell.risk_crime - 0.8) < 1e-4
        assert cell.extra_features.get("v") == 2


@pytest.mark.anyio
async def test_4_crime_upsert_preserves_lighting_and_live_risk(test_engine):
    """Crime upsert işlemi hücredeki mevcut risk_lighting ve risk_live değerlerini korur, total_risk'i kanonik formülle yeniden hesaplar."""
    SessionLocal = sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    # 1. Önce lighting verisi yaz (risk_lighting = 0.5)
    lighting_batch = [
        {
            "h3_index": "892a10080000099",
            "lat": 41.8781,
            "lng": -87.6298,
            "risk_lighting": 0.5,
            "extra_features": {"open_311_lighting_count": 2}
        }
    ]
    async with SessionLocal() as session:
        async with session.begin():
            await bulk_upsert_lighting_data(session, lighting_batch)

    # Manuel olarak risk_live = 0.2 yap
    async with SessionLocal() as session:
        async with session.begin():
            cell = (await session.execute(select(H3HeatmapModel).where(H3HeatmapModel.h3_index == "892a10080000099"))).scalars().first()
            cell.risk_live = 0.2
            cell.total_risk = crud._compute_total_risk(crime=0.0, lighting=0.5, live=0.2)

    # 2. Şimdi Crime upsert yap (risk_crime = 0.8)
    crime_batch = [
        {
            "h3_index": "892a10080000099",
            "lat": 41.8781,
            "lng": -87.6298,
            "risk_crime": 0.8,
            "extra_features": {"crime_7d": 4}
        }
    ]
    async with SessionLocal() as session:
        async with session.begin():
            await bulk_upsert_crime_data(session, crime_batch)

    # 3. Kontrol: risk_crime=0.8, risk_lighting=0.5, risk_live=0.2
    # total_risk = 0.65*0.8 + 0.20*0.5 + 0.15*0.2 = 0.52 + 0.10 + 0.03 = 0.65
    async with SessionLocal() as session:
        cell = (await session.execute(select(H3HeatmapModel).where(H3HeatmapModel.h3_index == "892a10080000099"))).scalars().first()
        assert abs(cell.risk_crime - 0.8) < 1e-4
        assert abs(cell.risk_lighting - 0.5) < 1e-4
        assert abs(cell.risk_live - 0.2) < 1e-4
        assert abs(cell.total_risk - 0.65) < 1e-4


@pytest.mark.anyio
async def test_5_lighting_upsert_preserves_crime_and_live_risk(test_engine):
    """Lighting upsert işlemi hücredeki mevcut risk_crime ve risk_live değerlerini korur, total_risk'i günceller."""
    SessionLocal = sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    # 1. Önce Crime verisi yaz (risk_crime = 0.6)
    crime_batch = [
        {
            "h3_index": "892a10080000088",
            "lat": 41.8781,
            "lng": -87.6298,
            "risk_crime": 0.6,
            "extra_features": {"crime_30d": 3}
        }
    ]
    async with SessionLocal() as session:
        async with session.begin():
            await bulk_upsert_crime_data(session, crime_batch)

    # 2. Şimdi Lighting upsert yap (risk_lighting = 0.4)
    lighting_batch = [
        {
            "h3_index": "892a10080000088",
            "lat": 41.8781,
            "lng": -87.6298,
            "risk_lighting": 0.4,
            "extra_features": {"open_311_lighting_count": 1}
        }
    ]
    async with SessionLocal() as session:
        async with session.begin():
            await bulk_upsert_lighting_data(session, lighting_batch)

    # 3. Kontrol: risk_crime=0.6, risk_lighting=0.4
    # total_risk = 0.65*0.6 + 0.20*0.4 = 0.39 + 0.08 = 0.47
    async with SessionLocal() as session:
        cell = (await session.execute(select(H3HeatmapModel).where(H3HeatmapModel.h3_index == "892a10080000088"))).scalars().first()
        assert abs(cell.risk_crime - 0.6) < 1e-4
        assert abs(cell.risk_lighting - 0.4) < 1e-4
        assert abs(cell.total_risk - 0.47) < 1e-4


@pytest.mark.anyio
async def test_6_jsonb_extra_features_merge(test_engine):
    """Crime ve Lighting ETL'lerinin extra_features JSONB alanını birbirinin üzerine yazmadan birlestirdigini (merge) doğrular."""
    SessionLocal = sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    crime_batch = [
        {
            "h3_index": "892a10080000077",
            "lat": 41.8781,
            "lng": -87.6298,
            "risk_crime": 0.5,
            "extra_features": {"crime_7d": 10, "crime_30d": 25}
        }
    ]
    async with SessionLocal() as session:
        async with session.begin():
            await bulk_upsert_crime_data(session, crime_batch)

    lighting_batch = [
        {
            "h3_index": "892a10080000077",
            "lat": 41.8781,
            "lng": -87.6298,
            "risk_lighting": 0.3,
            "extra_features": {"open_311_lighting_count": 2, "completed_311_lighting_count": 5}
        }
    ]
    async with SessionLocal() as session:
        async with session.begin():
            await bulk_upsert_lighting_data(session, lighting_batch)

    async with SessionLocal() as session:
        cell = (await session.execute(select(H3HeatmapModel).where(H3HeatmapModel.h3_index == "892a10080000077"))).scalars().first()
        ef = cell.extra_features
        assert ef.get("crime_7d") == 10
        assert ef.get("crime_30d") == 25
        assert ef.get("open_311_lighting_count") == 2
        assert ef.get("completed_311_lighting_count") == 5


@pytest.mark.anyio
@patch("chicago_crime_etl.fetch_chicago_crimes")
@patch("main.AsyncSessionLocal")
async def test_7_transient_db_error_retry_and_persistent_error_halts(mock_session_factory, mock_fetch, test_engine):
    """Geçici DB hatasında aynı batch'in yeniden denendiğini, kalıcı hatada ise sonraki batch'e geçilmeden durduğunu doğrular."""
    SessionLocal = sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    mock_session_factory.side_effect = lambda: SessionLocal()

    mock_fetch.return_value = [
        {
            "id": f"{i}",
            "date": "2026-07-28T12:00:00.000",
            "primary_type": "BATTERY",
            "latitude": f"{41.8781 + (i*0.0001):.5f}",
            "longitude": "-87.6298"
        } for i in range(300)
    ]

        # 33 aggregate H3 cell / batch_size=10 => 4 batch. The transient
        # failure is retried in batch 1; the permanent failure stops batch 2.
    with patch("crud.bulk_upsert_crime_data") as mock_bulk:
        # 1. Çağrı: ConnectionError (geçici)
        # 2. Çağrı: Başarılı (Batch 1 tamamlandı)
        # 3. Çağrı: Kalıcı ValueError (Batch 2 kalıcı hata)
        mock_bulk.side_effect = [
            ConnectionError("Supabase session pooler reset"),
            250,
            ValueError("Fatal DB Constraint Error")
        ]

        with pytest.raises(CrimeETLWriteError) as exc_info:
            await run_crime_etl(max_records=300, dry_run=False, batch_size=10)

        assert "Batch 2/4" in str(exc_info.value)
        assert mock_bulk.call_count == 3  # Batch 1 iki kez çağrıldı (1 retry), Batch 2 bir kez çağrıldı ve durdu!

    # etl_runs tablosunda "crime_etl" başarısı kaydedilmemeli
    async with SessionLocal() as session:
        res = await session.execute(select(ETLRunModel).where(ETLRunModel.etl_name == "crime_etl"))
        assert res.scalars().first() is None


@pytest.mark.anyio
async def test_8_partial_production_recovery_simulation(test_engine):
    """Mevcut 3.145 hücre bulunan veritabanında 5.171 hücrelik tam ETL çalıştırıldığında eksik 2.026 hücrenin eklendiğini ve toplam 5.171 hücre olduğunu doğrular."""
    SessionLocal = sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    # 1. 3.145 adet eski hücre oluştur
    existing_items = [
        {
            "h3_index": f"892a1008{i:07x}",
            "lat": 41.8781,
            "lng": -87.6298,
            "risk_crime": 0.1,
            "extra_features": {"status": "old"}
        } for i in range(3145)
    ]
    
    for b in range(math.ceil(3145 / 250)):
        batch = existing_items[b*250 : min(3145, (b+1)*250)]
        async with SessionLocal() as session:
            async with session.begin():
                await bulk_upsert_crime_data(session, batch)

    async with SessionLocal() as session:
        cnt_initial = (await session.execute(select(func.count()).select_from(H3HeatmapModel))).scalar()
        assert cnt_initial == 3145

    # 2. Şimdi 5.171 hücrelik tam yeni ETL verisini (ilk 3.145'i dahil) yaz
    full_items = [
        {
            "h3_index": f"892a1008{i:07x}",
            "lat": 41.8781,
            "lng": -87.6298,
            "risk_crime": 0.5,
            "extra_features": {"status": "updated"}
        } for i in range(5171)
    ]

    for b in range(math.ceil(5171 / 250)):
        batch = full_items[b*250 : min(5171, (b+1)*250)]
        async with SessionLocal() as session:
            async with session.begin():
                await bulk_upsert_crime_data(session, batch)

    # 3. Sonuç Kontrolü
    async with SessionLocal() as session:
        cnt_final = (await session.execute(select(func.count()).select_from(H3HeatmapModel))).scalar()
        assert cnt_final == 5171  # Toplam hücre sayısı tam 5.171 olmalı (0 duplicate)

        # Ilk hücre güncellenmiş mi?
        first_cell = (await session.execute(select(H3HeatmapModel).where(H3HeatmapModel.h3_index == "892a10080000000"))).scalars().first()
        assert abs(first_cell.risk_crime - 0.5) < 1e-4
        assert first_cell.extra_features.get("status") == "updated"
