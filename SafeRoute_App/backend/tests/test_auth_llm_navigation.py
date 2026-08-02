import asyncio
import json
from unittest.mock import AsyncMock, patch
from uuid import UUID

import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

import auth
import account_deletion
from config import Settings, settings
from llm_service import DeepSeekRiskExplainer, RiskExplanation
from navigation import build_navigation_contract


USER_ID = UUID("8d836c8a-f668-4e2e-b72d-7f2fb6f4bd61")


def staging_settings(**overrides) -> dict:
    values = {
        "app_environment": "staging",
        "database_url": "postgresql+asyncpg://user:password@db.example.com/saferoute",
        "reporter_hash_secret": "test-only-reporter-hash-secret-0001",
        "cors_origins": "https://staging.example.com",
        "auth_required": True,
        "supabase_url": "https://project.supabase.co",
        "supabase_publishable_key": "test-publishable-key",
    }
    values.update(overrides)
    return values


def bearer(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def test_anonymous_access_policy_is_explicitly_configurable():
    with patch.object(settings, "auth_required", False):
        assert asyncio.run(auth.get_current_user(None)) is None
    with patch.object(settings, "auth_required", True):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(auth.get_current_user(None))
        assert exc.value.status_code == 401


def test_hs256_is_verified_remotely_without_a_shared_secret():
    token = jwt.encode({"sub": str(USER_ID)}, "test-only-key", algorithm="HS256")
    verifier = auth.SupabaseTokenVerifier("https://project.supabase.co")
    verifier.verify_legacy = AsyncMock(
        return_value={"sub": str(USER_ID), "role": "authenticated", "email": "person@example.com"}
    )
    with patch.object(settings, "supabase_url", "https://project.supabase.co"), patch.object(
        auth, "_verifier", return_value=verifier
    ):
        user = asyncio.run(auth.get_current_user(bearer(token)))
    assert user and user.user_id == USER_ID
    verifier.verify_legacy.assert_awaited_once_with(token)


def test_unknown_or_anonymous_token_role_is_denied():
    token = jwt.encode({"sub": str(USER_ID)}, "test-only-key", algorithm="HS256")
    verifier = auth.SupabaseTokenVerifier("https://project.supabase.co")
    verifier.verify_legacy = AsyncMock(return_value={"sub": str(USER_ID), "role": "anon"})
    with patch.object(settings, "supabase_url", "https://project.supabase.co"), patch.object(
        auth, "_verifier", return_value=verifier
    ):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(auth.get_current_user(bearer(token)))
    assert exc.value.status_code == 401


def deterministic(level: str = "high") -> RiskExplanation:
    return RiskExplanation(
        risk_level=level,
        explanation="Gözlemlenen birleşik risk sinyali yüksek düzeydedir.",
        factors=["Toplu risk sinyali"],
    )


def test_live_deepseek_requires_server_side_key_in_staging():
    with pytest.raises(ValueError, match="DEEPSEEK_API_KEY"):
        Settings(
            _env_file=None,
            **staging_settings(llm_mode="live", deepseek_api_key=""),
        )

    configured = Settings(
        _env_file=None,
        **staging_settings(llm_mode="live", deepseek_api_key="test-key"),
    )
    assert configured.llm_provider == "deepseek"
    assert configured.deepseek_model == "deepseek-v4-flash"


def test_deepseek_structured_output_cannot_change_canonical_level():
    explainer = DeepSeekRiskExplainer()
    response = {
        "choices": [{
            "finish_reason": "stop",
            "message": {"content": json.dumps({
                "risk_level": "low",
                "explanation": "Gözlemlenen sinyaller düşük düzeyde raporlanmıştır.",
                "factors": ["Toplu risk sinyali"],
            })},
        }]
    }
    explainer._request_with_retry = AsyncMock(return_value=response)
    with patch.object(settings, "llm_mode", "live"), patch.object(
        settings, "llm_provider", "deepseek"
    ), patch.object(settings, "deepseek_api_key", "test-key"):
        result, method = asyncio.run(
            explainer.explain(crime=0.8, lighting=0.4, live=0.1, total=0.615, deterministic=deterministic())
        )
    assert result == deterministic()
    assert method == "deterministic_fallback_provider_error"


def test_deepseek_request_uses_json_mode_and_preserves_canonical_level():
    explainer = DeepSeekRiskExplainer()
    response = {
        "choices": [{
            "finish_reason": "stop",
            "message": {"content": json.dumps({
                "risk_level": "high",
                "explanation": "Gözlemlenen birleşik risk sinyali yüksek düzeydedir.",
                "factors": ["Suç sinyali", "Aydınlatma sinyali"],
            })},
        }]
    }
    explainer._request_with_retry = AsyncMock(return_value=response)
    with patch.object(settings, "llm_mode", "live"), patch.object(
        settings, "llm_provider", "deepseek"
    ), patch.object(settings, "deepseek_api_key", "test-key"):
        result, method = asyncio.run(
            explainer.explain(
                crime=0.8,
                lighting=0.4,
                live=0.1,
                total=0.615,
                deterministic=deterministic(),
            )
        )

    assert result.risk_level == "high"
    assert method == "deepseek_structured_output"
    url, body = explainer._request_with_retry.await_args.args
    assert url == "https://api.deepseek.com/chat/completions"
    assert body["model"] == "deepseek-v4-flash"
    assert body["response_format"] == {"type": "json_object"}
    assert body["thinking"] == {"type": "disabled"}
    assert "JSON" in body["messages"][0]["content"]


def test_certainty_language_validation_uses_whole_words():
    RiskExplanation(
        risk_level="low",
        explanation="Gözlemlenen risk düşük; genel güvenlik önlemleri sürdürülmelidir.",
        factors=["Sınırlı sinyal"],
    )
    with pytest.raises(ValueError):
        RiskExplanation(
            risk_level="low",
            explanation="Bu alan kesinlikle güvenli olarak değerlendirilmiştir.",
            factors=["Sınırlı sinyal"],
        )


def test_navigation_contract_is_stable_versioned_and_geometry_based():
    coordinates = [[-87.63, 41.88], [-87.63, 41.881], [-87.629, 41.881]]
    nodes = ["10", "11", "12"]
    first = build_navigation_contract(coordinates, nodes, "graph-v1", "balanced", "snapshot-v1")
    second = build_navigation_contract(coordinates, nodes, "graph-v1", "balanced", "snapshot-v1")
    assert first == second
    route_id, edge_ids, steps = first
    assert len(route_id) == 32
    assert len(edge_ids) == 2
    assert steps[0]["maneuver"] == "depart"
    assert steps[-1]["maneuver"] == "arrive"
    assert all(step["street_name"] is None for step in steps)


def test_navigation_contract_rejects_unaligned_path_identity():
    with pytest.raises(ValueError):
        build_navigation_contract(
            [[-87.63, 41.88], [-87.62, 41.88]],
            ["only-one-node"],
            "graph-v1",
            "balanced",
            "snapshot-v1",
        )


def test_navigation_contract_uses_sidecar_edge_identity_and_street_names():
    route_id, edge_ids, steps = build_navigation_contract(
        [[-87.63, 41.88], [-87.63, 41.881], [-87.629, 41.881]],
        ["10", "11", "12"],
        "graph-v1",
        "balanced",
        "snapshot-v1",
        ["osm:10:11:0", "osm:11:12:0"],
        ["State Street", "Lake Street"],
    )
    assert len(route_id) == 32
    assert len(edge_ids) == 2
    assert steps[0]["street_name"] == "State Street"
    assert "State Street" in steps[0]["instruction"]
    assert steps[1]["street_name"] == "Lake Street"


def test_navigation_contract_uses_honest_way_type_fallback():
    _route_id, _edge_ids, steps = build_navigation_contract(
        [[-87.63, 41.88], [-87.63, 41.881]],
        ["10", "11"],
        "graph-v1",
        "balanced",
        "snapshot-v1",
        ["osm:10:11:0"],
        [None],
        ["footway"],
    )
    assert steps[0]["street_name"] is None
    assert steps[0]["way_type"] == "footway"
    assert steps[0]["instruction"] == "Yaya yolunda rotaya başlayın."


def test_account_deletion_requires_a_separate_execution_gate():
    with patch.object(settings, "account_deletion_execution_enabled", False):
        with pytest.raises(account_deletion.ConfigurationError):
            asyncio.run(account_deletion.process_due_account_deletions(execute=True))
