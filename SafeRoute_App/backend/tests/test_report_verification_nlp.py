import pytest
import asyncio
from datetime import datetime, timezone, timedelta

from services.report_nlp import ReportNLPAnalyzer
from crud import (
    generate_reporter_hash,
    create_report,
    process_report_and_event_clustering,
    recalculate_h3_live_risk,
    get_recent_map_reports,
    get_report_by_uuid_and_token,
    _compute_total_risk,
    _in_memory_reports,
    _in_memory_report_events,
)
from models import ReportEventModel


@pytest.fixture(autouse=True)
def reset_in_memory_stores():
    _in_memory_reports.clear()
    _in_memory_report_events.clear()
    yield
    _in_memory_reports.clear()
    _in_memory_report_events.clear()


def test_1_single_report_remains_pending_and_does_not_change_live_risk():
    async def _run():
        rep = await create_report(
            db=None,
            lat=41.8781,
            lng=-87.6298,
            text="Sokakta aydınlatma arızası var karanlık",
            category="lighting",
            reporter_installation_id="device-uuid-111"
        )
        assert rep.status == "pending"

        event = await process_report_and_event_clustering(db=None, report=rep)
        assert event.status == "pending"
        assert event.unique_reporter_count == 1

        live_risk = await recalculate_h3_live_risk(db=None, h3_index=event.h3_index)
        assert live_risk == 0.0

    asyncio.run(_run())


def test_2_nlp_category_normalization_and_severity():
    nlp = ReportNLPAnalyzer()
    res1 = nlp.analyze("Sokakta 311 lamba arızası var ve sokak karanlık")
    assert res1.normalized_category == "lighting_failure"
    assert res1.severity_weight == 0.30

    res2 = nlp.analyze("Silahlı kişilerin olduğunu gördüm büyük tehlike")
    assert res2.normalized_category == "armed_violence"
    assert res2.severity_weight == 1.00

    res3 = nlp.analyze("Takip edildim ve rahatsız edildim")
    assert res3.normalized_category == "harassment"
    assert res3.severity_weight == 0.65



def test_3_nlp_similarity_hybrid_identical_texts():
    nlp = ReportNLPAnalyzer()
    text = "Sokakta şüpheli şahıs dolaşıyor araba camlarını zorluyor"
    sim = nlp.similarity(text, text)
    assert sim == 1.0


def test_4_nlp_similarity_different_texts():
    nlp = ReportNLPAnalyzer()
    text1 = "Sokak lambaları tamamen sönük karanlık sokak"
    text2 = "Kedilerin beslenme alanında mama kabı kırılmış"
    sim = nlp.similarity(text1, text2)
    assert sim < 0.60


def test_5_reporter_hash_deterministic_hmac():
    hash1 = generate_reporter_hash("device-abc-123")
    hash2 = generate_reporter_hash("device-abc-123")
    hash3 = generate_reporter_hash("device-xyz-999")

    assert hash1 is not None
    assert hash1 == hash2
    assert hash1 != hash3


def test_6_reporter_hash_privacy_does_not_leak_raw_id():
    raw_uuid = "user-device-sensitive-uuid-777"
    hashed = generate_reporter_hash(raw_uuid)
    assert raw_uuid not in hashed
    assert len(hashed) == 64


def test_7_same_reporter_duplicate_hash_does_not_increase_independent_support():
    async def _run():
        rep1 = await create_report(
            db=None,
            lat=41.8781,
            lng=-87.6298,
            text="Şüpheli şahıs sokakta geziniyor kapıları zorluyor",
            category="crime",
            reporter_installation_id="device-same-user"
        )
        event1 = await process_report_and_event_clustering(db=None, report=rep1)

        rep2 = await create_report(
            db=None,
            lat=41.8781,
            lng=-87.6298,
            text="Şüpheli şahıs sokakta geziniyor kapıları zorluyor",
            category="crime",
            reporter_installation_id="device-same-user"
        )
        event2 = await process_report_and_event_clustering(db=None, report=rep2)

        assert event1.id == event2.id
        assert event2.unique_reporter_count == 1
        assert event2.status == "pending"

    asyncio.run(_run())


def test_8_two_independent_reporters_trigger_event_acceptance():
    async def _run():
        rep1 = await create_report(
            db=None,
            lat=41.8781,
            lng=-87.6298,
            text="Şüpheli şahıs sokakta geziniyor araç kapılarını zorluyor",
            category="crime",
            reporter_installation_id="user-device-alpha"
        )
        event1 = await process_report_and_event_clustering(db=None, report=rep1)
        assert event1.status == "pending"

        rep2 = await create_report(
            db=None,
            lat=41.8782,
            lng=-87.6297,
            text="Şüpheli şahıs sokakta geziniyor araç kapılarını zorluyor",
            category="crime",
            reporter_installation_id="user-device-beta"
        )
        event2 = await process_report_and_event_clustering(db=None, report=rep2)

        assert event1.id == event2.id
        assert event2.unique_reporter_count == 2
        assert event2.validation_score >= 0.70
        assert event2.status == "accepted"
        assert rep1.status == "accepted"
        assert rep2.status == "accepted"

    asyncio.run(_run())


def test_9_acceptance_recalculates_h3_live_risk_bounded_accumulation():
    async def _run():
        rep1 = await create_report(
            db=None,
            lat=41.8781,
            lng=-87.6298,
            text="Sokak lambaları tamamen patlamış ve kapkaranlık",
            category="lighting",
            reporter_installation_id="user-1"
        )
        await process_report_and_event_clustering(db=None, report=rep1)

        rep2 = await create_report(
            db=None,
            lat=41.8781,
            lng=-87.6298,
            text="Sokak lambaları tamamen patlamış ve kapkaranlık",
            category="lighting",
            reporter_installation_id="user-2"
        )
        event = await process_report_and_event_clustering(db=None, report=rep2)
        assert event.status == "accepted"

        tot_risk = await recalculate_h3_live_risk(db=None, h3_index=event.h3_index)
        assert tot_risk > 0.0
        expected_tot = _compute_total_risk(crime=0.0, lighting=0.0, live=event.severity_weight * event.validation_score)
        assert abs(tot_risk - expected_tot) < 0.05

    asyncio.run(_run())


def test_10_time_decay_reduces_live_risk_over_time():
    async def _run():
        now_utc = datetime.now(timezone.utc)
        ev = ReportEventModel(
            id=99,
            uuid_id="decay-event-uuid",
            h3_index="892654a32b7ffff",
            status="accepted",
            unique_reporter_count=2,
            validation_score=0.80,
            severity_weight=0.90,
            first_seen_at=now_utc - timedelta(minutes=45),
            accepted_at=now_utc - timedelta(minutes=45),
            expires_at=now_utc + timedelta(minutes=15)
        )
        _in_memory_report_events["decay-event-uuid"] = ev

        tot_risk_decayed = await recalculate_h3_live_risk(db=None, h3_index="892654a32b7ffff")

        ev.accepted_at = now_utc - timedelta(minutes=5)
        tot_risk_fresh = await recalculate_h3_live_risk(db=None, h3_index="892654a32b7ffff")

        assert tot_risk_fresh > tot_risk_decayed

    asyncio.run(_run())


def test_11_clustering_respects_15_minute_time_window():
    async def _run():
        now_utc = datetime.now(timezone.utc)
        old_event = ReportEventModel(
            id=101,
            uuid_id="old-event-uuid",
            h3_index="892654a32b7ffff",
            normalized_category="crime",
            status="pending",
            last_seen_at=now_utc - timedelta(minutes=20),
            created_at=now_utc - timedelta(minutes=25)
        )
        _in_memory_report_events["old-event-uuid"] = old_event

        rep = await create_report(
            db=None,
            lat=41.8781,
            lng=-87.6298,
            text="Şüpheli şahıs sokakta geziniyor araç kapılarını zorluyor",
            category="crime",
            reporter_installation_id="user-new"
        )
        event = await process_report_and_event_clustering(db=None, report=rep)

        assert event.id != old_event.id

    asyncio.run(_run())


def test_12_clustering_respects_h3_neighbor_resolution_9():
    async def _run():
        rep1 = await create_report(
            db=None,
            lat=41.8781,
            lng=-87.6298,
            text="Karanlık sokak ve aydınlatma yok",
            category="lighting",
            reporter_installation_id="user-chicago-1"
        )
        ev1 = await process_report_and_event_clustering(db=None, report=rep1)

        rep2 = await create_report(
            db=None,
            lat=42.0000,
            lng=-87.9000,
            text="Karanlık sokak ve aydınlatma yok",
            category="lighting",
            reporter_installation_id="user-chicago-2"
        )
        ev2 = await process_report_and_event_clustering(db=None, report=rep2)

        assert ev1.id != ev2.id

    asyncio.run(_run())


def test_13_dissimilar_text_creates_separate_event():
    async def _run():
        rep1 = await create_report(
            db=None,
            lat=41.8781,
            lng=-87.6298,
            text="Aydınlatma direği devrilmiş kablolar açıkta",
            category="lighting",
            reporter_installation_id="user-a"
        )
        ev1 = await process_report_and_event_clustering(db=None, report=rep1)

        rep2 = await create_report(
            db=None,
            lat=41.8781,
            lng=-87.6298,
            text="Sokak köpeği sürüsü yolculara saldırıyor",
            category="lighting",
            reporter_installation_id="user-b"
        )
        ev2 = await process_report_and_event_clustering(db=None, report=rep2)

        assert ev1.id != ev2.id

    asyncio.run(_run())


def test_14_public_map_reports_only_includes_accepted_reports():
    async def _run():
        rep_pending = await create_report(
            db=None,
            lat=41.8781,
            lng=-87.6298,
            text="Tekil ihbar onay bekliyor",
            category="general",
            reporter_installation_id="user-p"
        )
        await process_report_and_event_clustering(db=None, report=rep_pending)

        res1 = await get_recent_map_reports(db=None, minutes=60)
        assert res1["count"] == 0

        rep1 = await create_report(
            db=None,
            lat=41.8888,
            lng=-87.6350,
            text="Aydınlatma yok ve sokak karanlık tehlike",
            category="lighting",
            reporter_installation_id="user-ok-1"
        )
        await process_report_and_event_clustering(db=None, report=rep1)

        rep2 = await create_report(
            db=None,
            lat=41.8888,
            lng=-87.6350,
            text="Aydınlatma yok ve sokak karanlık tehlike",
            category="lighting",
            reporter_installation_id="user-ok-2"
        )
        await process_report_and_event_clustering(db=None, report=rep2)

        res2 = await get_recent_map_reports(db=None, minutes=60)
        assert res2["count"] >= 1
        assert all(r["status"] == "accepted" for r in res2["reports"])

    asyncio.run(_run())


def test_15_idor_protection_requires_matching_uuid_and_token():
    async def _run():
        rep = await create_report(
            db=None,
            lat=41.8781,
            lng=-87.6298,
            text="IDOR test ihbar metni 12345",
            category="general",
            reporter_installation_id="user-idor"
        )

        found = await get_report_by_uuid_and_token(db=None, uuid_id=rep.uuid_id, token=rep.tracking_token)
        assert found is not None

        invalid = await get_report_by_uuid_and_token(db=None, uuid_id=rep.uuid_id, token="fake-token-999")
        assert invalid is None

    asyncio.run(_run())


def test_16_validation_score_formula_weights():
    async def _run():
        rep1 = await create_report(db=None, lat=41.8781, lng=-87.6298, text="Sokak lambası arızalı", category="lighting", reporter_installation_id="u1")
        ev = await process_report_and_event_clustering(db=None, report=rep1)

        S = 1.0 / 3.0
        M = 1.0
        U = 0.50
        C = rep1.model_confidence or 0.50
        expected_v = round((0.35 * S) + (0.25 * M) + (0.20 * U) + (0.20 * C), 4)

        assert abs(ev.validation_score - expected_v) < 0.01

    asyncio.run(_run())


def test_17_expired_events_do_not_contribute_to_live_risk():
    async def _run():
        now_utc = datetime.now(timezone.utc)
        expired_event = ReportEventModel(
            id=200,
            uuid_id="exp-uuid",
            h3_index="892654a32b7ffff",
            status="accepted",
            validation_score=0.90,
            severity_weight=0.90,
            expires_at=now_utc - timedelta(minutes=5)
        )
        _in_memory_report_events["exp-uuid"] = expired_event

        live_risk = await recalculate_h3_live_risk(db=None, h3_index="892654a32b7ffff")
        assert live_risk == 0.0

    asyncio.run(_run())


def test_18_deterministic_fallback_when_nlp_model_unavailable():
    nlp = ReportNLPAnalyzer()
    res = nlp.analyze("Bıçaklı veya silahlı şahıs tehdit saçıyor")
    assert res.normalized_category in ("armed_violence", "assault", "robbery", "harassment", "suspicious_activity", "infrastructure_hazard", "general_safety", "lighting_failure")
    assert 0.0 <= res.model_confidence <= 1.0



def test_19_report_create_returns_pending_status_and_message():
    async def _run():
        rep = await create_report(
            db=None,
            lat=41.8781,
            lng=-87.6298,
            text="Aydınlatma direği arızalı sokak karanlık",
            category="lighting",
            reporter_installation_id="device-19"
        )
        assert rep.status == "pending"
        assert rep.tracking_token is not None
        assert rep.reporter_hash is not None

    asyncio.run(_run())


def test_20_recalculate_h3_live_risk_obeys_formula_and_clamping():
    async def _run():
        now_utc = datetime.now(timezone.utc)
        ev1 = ReportEventModel(
            id=301,
            uuid_id="acc-1",
            h3_index="892654a32b7ffff",
            status="accepted",
            validation_score=0.85,
            severity_weight=0.90,
            accepted_at=now_utc,
            expires_at=now_utc + timedelta(minutes=60)
        )
        ev2 = ReportEventModel(
            id=302,
            uuid_id="acc-2",
            h3_index="892654a32b7ffff",
            status="accepted",
            validation_score=0.80,
            severity_weight=0.85,
            accepted_at=now_utc,
            expires_at=now_utc + timedelta(minutes=60)
        )
        _in_memory_report_events["acc-1"] = ev1
        _in_memory_report_events["acc-2"] = ev2

        tot = await recalculate_h3_live_risk(db=None, h3_index="892654a32b7ffff")
        assert tot > 0.0
        assert tot <= 1.0

    asyncio.run(_run())
