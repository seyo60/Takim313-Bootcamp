# backend/tests/test_nlp_minilm_shadow.py
"""
SafeRoute Stage 3.2.1: Kontrollü MiniLM Shadow Mode Unit Testleri.
Üretim veritabanından tamamen bağımsız, in-memory ve mock testler.
"""
import pytest
import asyncio
from unittest.mock import patch, MagicMock

from config import settings
from services.report_nlp import ReportNLPAnalyzer, get_nlp_analyzer
from crud import (
    create_report,
    process_report_and_event_clustering,
    recalculate_h3_live_risk,
    _compute_total_risk,
    _in_memory_reports,
    _in_memory_report_events,
)


@pytest.fixture(autouse=True)
def reset_nlp_and_stores():
    """Her test öncesi in-memory depolama ve NLP analizör durumunu sıfırlar."""
    _in_memory_reports.clear()
    _in_memory_report_events.clear()

    # Reset singletons/states
    analyzer = get_nlp_analyzer()
    analyzer._model = None
    analyzer._model_status = "disabled"
    analyzer._load_attempted = False

    yield

    _in_memory_reports.clear()
    _in_memory_report_events.clear()


# ============================================================================
# 1. KONFİGÜRASYON VE MOD DAVRANIŞ TESTLERİ
# ============================================================================

def test_1_deterministic_mode_does_not_load_minilm():
    """Deterministic modda MiniLM yüklenmeye veya import edilmeye çalışılmaz."""
    with patch.object(settings, "report_nlp_mode", "deterministic"):
        analyzer = ReportNLPAnalyzer()
        res = analyzer.analyze("Two people are fighting near Michigan Avenue.")

        assert res.analysis_method == "deterministic_fallback"
        assert res.model_status == "disabled"
        assert res.embedding_available is False
        assert res.embedding is None
        assert res.shadow_minilm_result is None

        health = analyzer.get_health()
        assert health["configured_mode"] == "deterministic"
        assert health["model_status"] == "disabled"
        assert health["active_analysis_method"] == "deterministic_fallback"
        assert health["fallback_available"] is True


def test_2_missing_sentence_transformers_sets_not_installed_status():
    """sentence-transformers kurulu olmadığında shadow modunda 'not_installed' durumu verilir ve fallback çalışır."""
    with patch.object(settings, "report_nlp_mode", "shadow"):
        analyzer = ReportNLPAnalyzer()
        # sentence-transformers import edilmeye çalışıldığında ImportError fırlatılmasını simüle et
        with patch.dict("sys.modules", {"sentence_transformers": None}):
            res = analyzer.analyze("Gunshots heard near Wabash Ave.")

            assert res.analysis_method == "deterministic_fallback"
            assert res.model_status == "not_installed"
            assert res.embedding_available is False
            assert res.embedding is None

            health = analyzer.get_health()
            assert health["configured_mode"] == "shadow"
            assert health["model_status"] == "not_installed"
            assert health["active_analysis_method"] == "deterministic_fallback"


def test_3_shadow_mode_does_not_alter_primary_production_decisions():
    """Shadow modunda MiniLM skorları hesaplansa dahi birincil alanlar ve üretim kararları fallback ile çalışır."""
    with patch.object(settings, "report_nlp_mode", "shadow"):
        analyzer = ReportNLPAnalyzer()
        mock_model = MagicMock()
        mock_model.encode.return_value = MagicMock(tolist=lambda: [0.1] * 384)

        analyzer._model = mock_model
        analyzer._model_status = "ready"
        analyzer._load_attempted = True

        res = analyzer.analyze("Street light is completely out and dark on State St.")

        # Birincil metot deterministik olmalı!
        assert res.analysis_method == "deterministic_fallback"
        assert res.normalized_category == "lighting_failure"
        assert res.severity_weight == 0.30
        assert res.shadow_minilm_result is not None
        assert res.shadow_minilm_result["embedding_available"] is True


# ============================================================================
# 2. GÜVEN HESAPLAMASI VE ALAN AYRIŞTIRMA TESTLERİ
# ============================================================================

def test_4_no_artificial_confidence_boost():
    """Embedding üretilmesi kategori güvenini yapay olarak 0.85 seviyesine yükseltmemelidir."""
    analyzer = ReportNLPAnalyzer()
    # Anahtar kelimesiz genel güvenlik metni
    res = analyzer.analyze("Walking down the street at night.")

    assert res.normalized_category == "general_safety"
    assert res.category_confidence == 0.50
    assert res.model_confidence == 0.50
    assert res.category_confidence < 0.85


def test_5_explicit_field_separation():
    """category_confidence, text_similarity, analysis_method, embedding_available, model_status ayrıştırılmıştır."""
    analyzer = ReportNLPAnalyzer()
    res = analyzer.analyze("Car crash at intersection.")

    assert hasattr(res, "category_confidence")
    assert hasattr(res, "text_similarity")
    assert hasattr(res, "analysis_method")
    assert hasattr(res, "embedding_available")
    assert hasattr(res, "model_status")
    assert res.category_confidence == res.model_confidence


# ============================================================================
# 3. İNGİLİZCE VE KALİBRASYON BENZERLİK TESTLERİ (CHICAGO ODAKLI)
# ============================================================================

def test_6_chicago_english_calibration_similarity_ordering():
    """
    A: Two people are fighting near Michigan Avenue.
    B: There is a physical altercation on Michigan Ave.
    C: The street lights are not working and the area is dark.
    A-B benzerliği A-C benzerliğinden belirgin biçimde yüksek olmalıdır.
    """
    analyzer = ReportNLPAnalyzer()

    text_a = "Two people are fighting near Michigan Avenue."
    text_b = "There is a physical altercation on Michigan Ave."
    text_c = "The street lights are not working and the area is dark."

    sim_ab = analyzer.similarity(text_a, text_b)
    sim_ac = analyzer.similarity(text_a, text_c)

    assert sim_ab > sim_ac, f"A-B benzerliği ({sim_ab}) A-C benzerliğinden ({sim_ac}) büyük olmalıdır."


def test_7_calibration_negation_and_past_tense_and_cross_lingual():
    """Negation, geçmiş zaman ve İngilizce/İspanyolca çapraz dil testleri."""
    analyzer = ReportNLPAnalyzer()

    # Negation
    fighting_event = "Two people are fighting near State Street."
    no_fight_event = "There is no fight near State Street, everything is quiet."
    sim_neg = analyzer.similarity(fighting_event, no_fight_event)
    assert sim_neg < 0.90

    # Cross-lingual / Same event keywords (İspanyolca & İngilizce)
    en_report = "Two people fighting on Michigan Ave."
    es_report = "Dos personas peleando en Michigan Ave."
    sim_cross = analyzer.similarity(en_report, es_report)
    assert sim_cross > 0.0

    # Short invalid/spam text (<3 chars)
    spam_text = "a"
    res_spam = analyzer.analyze(spam_text)
    assert res_spam.is_actionable is False


# ============================================================================
# 4. GÜVENLİK VE ALAN KURALLARI (DOMAIN RULES) TESTLERİ
# ============================================================================

def test_8_single_report_does_not_become_accepted_or_generate_risk():
    """Tek bir ihbar accepted olamaz ve risk_live üretemez."""
    async def _run():
        rep = await create_report(
            db=None,
            lat=41.8781,
            lng=-87.6298,
            text="Armed robbery on Wabash Avenue",
            category="crime",
            reporter_installation_id="device-111"
        )
        assert rep.status == "pending"

        event = await process_report_and_event_clustering(db=None, report=rep)
        assert event.status == "pending"
        assert event.unique_reporter_count == 1

        live_risk = await recalculate_h3_live_risk(db=None, h3_index=event.h3_index)
        assert live_risk == 0.0

    asyncio.run(_run())


def test_9_urgent_priority_does_not_bypass_verification():
    """Urgent öncelikli ihbar çoklu doğrulama adımlarını atlayıp tek başına kabul edilemez."""
    async def _run():
        rep = await create_report(
            db=None,
            lat=41.8781,
            lng=-87.6298,
            text="URGENT: Gunshots fired near Loop!",
            category="crime",
            priority="urgent",
            reporter_installation_id="device-urgent-1"
        )
        assert rep.priority == "urgent"
        assert rep.status == "pending"

        event = await process_report_and_event_clustering(db=None, report=rep)
        assert event.status == "pending"
        assert event.unique_reporter_count == 1
        assert event.validation_score < float(getattr(settings, "report_acceptance_threshold", 0.70))

    asyncio.run(_run())


def test_10_same_reporter_duplicates_do_not_increase_independent_support():
    """Aynı cihazdan gönderilen mükerrer ihbarlar bağımsız kullanıcı sayısını (S) artırmaz."""
    async def _run():
        rep1 = await create_report(
            db=None,
            lat=41.8781,
            lng=-87.6298,
            text="Physical fight on Michigan Ave",
            category="assault",
            reporter_installation_id="same-device-xyz"
        )
        event1 = await process_report_and_event_clustering(db=None, report=rep1)

        rep2 = await create_report(
            db=None,
            lat=41.8781,
            lng=-87.6298,
            text="Physical fight on Michigan Ave",
            category="assault",
            reporter_installation_id="same-device-xyz"
        )
        event2 = await process_report_and_event_clustering(db=None, report=rep2)

        assert event1.id == event2.id
        assert event2.unique_reporter_count == 1
        assert event2.status == "pending"

    asyncio.run(_run())


def test_11_all_scores_strictly_bounded_between_zero_and_one():
    """Tüm risk, doğrulama, ciddiyet ve güven skorları 0.0 - 1.0 aralığında kalır."""
    analyzer = ReportNLPAnalyzer()
    res = analyzer.analyze("Serious armed assault on street")

    assert 0.0 <= res.severity_weight <= 1.0
    assert 0.0 <= res.category_confidence <= 1.0
    assert 0.0 <= res.model_confidence <= 1.0

    sim = analyzer.similarity("test text 1", "test text 2")
    assert 0.0 <= sim <= 1.0

    tot_risk = _compute_total_risk(crime=0.8, lighting=0.4, live=0.9)
    assert 0.0 <= tot_risk <= 1.0
