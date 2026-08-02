"""LLM yanıt normalizasyonu testleri.

Biçim aşımları (uzun açıklama, fazla faktör) kırpılarak kabul edilir; güvenlik
kısıtları (yasaklı kesinlik ifadeleri, geçersiz risk seviyesi) reddedilir.
"""

import json

import pytest
from pydantic import ValidationError

from llm_service import MAX_EXPLANATION_CHARS, MAX_FACTORS, parse_llm_explanation


def test_over_limit_explanation_is_truncated_not_rejected():
    long_text = (
        "Rota boyunca düşük-orta risk gözlemlenmiştir. " * 8
    )  # 320 karakterin üzerinde
    raw = json.dumps(
        {
            "risk_level": "low_medium",
            "explanation": long_text,
            "factors": ["a", "b"],
        }
    )
    result = parse_llm_explanation(raw)
    assert len(result.explanation) <= MAX_EXPLANATION_CHARS
    assert result.risk_level == "low_medium"


def test_extra_factors_are_trimmed_to_limit():
    raw = json.dumps(
        {
            "risk_level": "medium",
            "explanation": "Rota boyunca orta seviyede risk kaydedilmiştir.",
            "factors": ["bir", "iki", "üç", "dört", "beş"],
        }
    )
    result = parse_llm_explanation(raw)
    assert len(result.factors) == MAX_FACTORS
    assert result.factors == ["bir", "iki", "üç"]


def test_single_string_factor_is_accepted_as_list():
    raw = json.dumps(
        {
            "risk_level": "low",
            "explanation": "Rota boyunca düşük risk gözlemlenmiştir.",
            "factors": "suç oranı düşük",
        }
    )
    result = parse_llm_explanation(raw)
    assert result.factors == ["suç oranı düşük"]


def test_certainty_language_is_still_rejected():
    raw = json.dumps(
        {
            "risk_level": "low",
            "explanation": "Bu rota tamamen güvenli, hiç endişelenmeyin.",
            "factors": ["düşük risk"],
        }
    )
    with pytest.raises(ValidationError):
        parse_llm_explanation(raw)


def test_invalid_risk_level_is_rejected():
    raw = json.dumps(
        {
            "risk_level": "catastrophic",
            "explanation": "Rota boyunca orta seviyede risk kaydedilmiştir.",
            "factors": ["orta risk"],
        }
    )
    with pytest.raises(ValidationError):
        parse_llm_explanation(raw)


def test_non_object_response_is_rejected():
    with pytest.raises(ValueError):
        parse_llm_explanation(json.dumps(["not", "an", "object"]))


def test_truncation_prefers_sentence_boundary():
    sentences = (
        "Rota boyunca orta seviyede risk kaydedilmiştir. "
        "Aydınlatma yetersizliği sinyali vardır. "
        "Bu koşullar değişebilir ve kullanıcı çevresini izlemelidir. "
        "Ek olarak çok uzun bir cümle daha ekleyerek sınırı aşıyoruz ve "
        "kırpmanın cümle sonunda gerçekleşmesini bekliyoruz burada."
    )
    raw = json.dumps(
        {
            "risk_level": "medium",
            "explanation": sentences,
            "factors": ["orta risk"],
        }
    )
    result = parse_llm_explanation(raw)
    assert len(result.explanation) <= MAX_EXPLANATION_CHARS
    assert result.explanation.endswith(".")
