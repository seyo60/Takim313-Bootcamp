# backend/tests/test_nlp_minilm_real_model.py
"""
SafeRoute Stage 3.2.2: Gerçek MiniLM Shadow Smoke Testi.
Bu test dosyası gerçek 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
modelini yükler ve shadow modunu gerçek ağırlıklarla sınar.

Normal hızlı testleri yavaşlatmaması için `@pytest.mark.real_model` ve `@pytest.mark.calibration`
ile işaretlenmiştir.
"""
import pytest
import math
import warnings
import logging
from unittest.mock import patch

pytestmark = [
    pytest.mark.real_model,
    pytest.mark.calibration,
    pytest.mark.filterwarnings(
        "ignore:(?s).*Some weights of the model checkpoint.*embeddings.position_ids.*:UserWarning"
    ),
]

# Disable logger output noise during tests if needed
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
logging.getLogger("transformers").setLevel(logging.ERROR)

from config import settings  # noqa: E402
from services.report_nlp import get_nlp_analyzer  # noqa: E402


@pytest.fixture
def real_shadow_analyzer():
    """Gerçek MiniLM modelini shadow modunda izole olarak yükleyen fixture."""
    analyzer = get_nlp_analyzer()
    analyzer._model = None
    analyzer._model_status = "disabled"
    analyzer._load_attempted = False

    with patch.object(settings, "report_nlp_mode", "shadow"):
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="(?s).*embeddings.position_ids.*",
                category=UserWarning,
            )
            loaded = analyzer._lazy_load_model("shadow")
            assert loaded is True, "Gerçek MiniLM modeli yüklenemedi."
        yield analyzer

    # Cleanup
    analyzer._model = None
    analyzer._model_status = "disabled"
    analyzer._load_attempted = False


@pytest.mark.real_model
@pytest.mark.calibration
def test_1_real_minilm_shadow_smoke_and_field_integrity(real_shadow_analyzer):
    """
    Gerçek MiniLM modelinin shadow modundaki davranışını doğrular:
    - model_status == 'ready'
    - shadow_minilm_result.embedding_available == True
    - Birincil alanlar deterministik fallback alanları ile BİREBİR EŞİT olmalı
    """
    analyzer = real_shadow_analyzer

    text = "Two people are fighting near Michigan Avenue."
    with patch.object(settings, "report_nlp_mode", "deterministic"):
        fallback_res = analyzer.analyze(text)

    with patch.object(settings, "report_nlp_mode", "shadow"):
        res = analyzer.analyze(text)

        assert res.model_status == "ready"
        assert res.analysis_method == "deterministic_fallback"  # Production kararı korundu!
        assert res.normalized_category == fallback_res.normalized_category
        assert res.severity_weight == fallback_res.severity_weight
        assert res.category_confidence == fallback_res.category_confidence
        assert res.is_actionable == fallback_res.is_actionable
        assert res.rejection_reason == fallback_res.rejection_reason
        assert res.embedding_available is False  # Birincil nesnede false (shadow'da var)

        shadow_data = res.shadow_minilm_result
        assert shadow_data is not None
        assert shadow_data["embedding_available"] is True
        assert shadow_data["analysis_method"] == "multilingual_embedding"
        assert shadow_data["embedding_dim"] == 384


@pytest.mark.real_model
@pytest.mark.calibration
def test_2_real_minilm_similarity_vs_fallback_comparison(real_shadow_analyzer):
    """
    Aynı olay ve farklı olay metinlerinin gerçek MiniLM ve Fallback skorlarını karşılaştırır.
    A: Two people are fighting near Michigan Avenue.
    B: There is a physical altercation on Michigan Ave.
    C: The street lights are not working and the area is dark.
    """
    analyzer = real_shadow_analyzer

    text_a = "Two people are fighting near Michigan Avenue."
    text_b = "There is a physical altercation on Michigan Ave."
    text_c = "The street lights are not working and the area is dark."

    with patch.object(settings, "report_nlp_mode", "shadow"):
        # 1. Primary return (Deterministic Fallback)
        sim_ab_fallback = analyzer.similarity(text_a, text_b)
        sim_ac_fallback = analyzer.similarity(text_a, text_c)

        # 2. Real MiniLM Cosine Similarity doğrudan model üzerinden hesaplanır
        embeddings = analyzer._model.encode([text_a, text_b, text_c], convert_to_numpy=True)
        vec_a, vec_b, vec_c = embeddings[0], embeddings[1], embeddings[2]

        def cosine_sim(v1, v2):
            dot = sum(x * y for x, y in zip(v1, v2))
            n1 = math.sqrt(sum(x * x for x in v1))
            n2 = math.sqrt(sum(x * x for x in v2))
            return dot / (n1 * n2)

        sim_ab_minilm = float(cosine_sim(vec_a, vec_b))
        sim_ac_minilm = float(cosine_sim(vec_a, vec_c))

        # Doğrulamalar:
        # - Hem fallback hem MiniLM için aynı olay (A-B) benzerliği farklı olaydan (A-C) daha yüksek olmalı
        assert sim_ab_minilm > sim_ac_minilm
        assert sim_ab_fallback > sim_ac_fallback

        # - Production kararlarında kullanılan primary return değeri fallback skoru kalmalıdır
        assert 0.0 <= sim_ab_fallback <= 1.0
        assert 0.0 <= sim_ab_minilm <= 1.0


@pytest.mark.real_model
@pytest.mark.calibration
def test_3_health_endpoint_reports_ready_status_in_shadow_mode(real_shadow_analyzer):
    """Gerçek model yüklendiğinde shadow modunda get_health() model_status='ready' döndürür."""
    analyzer = real_shadow_analyzer
    with patch.object(settings, "report_nlp_mode", "shadow"):
        health = analyzer.get_health()
        assert health["configured_mode"] == "shadow"
        assert health["model_status"] == "ready"
        assert health["model_name"] == "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
        assert health["active_analysis_method"] == "deterministic_fallback"
