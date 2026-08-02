"""Validated runtime configuration for SafeRoute."""

from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_environment: Literal["development", "test", "staging", "production"] = "development"
    database_url: str = "postgresql+asyncpg://saferoute:saferoute@localhost:5432/saferoute"
    webhook_secret: str = ""
    reporter_hash_secret: str = ""
    cors_origins: str = "http://localhost:8081,http://127.0.0.1:8081"
    log_level: str = "INFO"
    auth_required: bool = False
    supabase_url: str = ""
    supabase_publishable_key: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_audience: str = "authenticated"
    account_deletion_grace_days: int = 7
    account_deletion_execution_enabled: bool = False

    routing_engine: str = "compact"
    routing_search_algorithm: Literal[
        "scipy_dijkstra", "bidirectional_a_star"
    ] = "scipy_dijkstra"
    compact_graph_path: str = "../data-science/compact_graph_res10.npz"
    navigation_sidecar_path: str = (
        "../data-science/navigation_sidecar_res10.npz"
    )
    navigation_sidecar_required: bool = False
    web_concurrency: int = 1
    routing_max_concurrency: int = 2
    routing_semaphore_limit: int = 2
    routing_queue_limit: int = 20
    retry_after_seconds: int = 10
    routing_risk_alpha: float = 2.0
    routing_red_risk_threshold: float = 0.60
    routing_red_risk_penalty: float = 6.0
    routing_unknown_risk: float = 0.25

    # Res-10 primary; res-9 is an explicit parent/report fallback.
    routing_h3_resolution: int = 10
    etl_h3_resolution: int = 10
    report_h3_resolution: int = 9
    h3_parent_resolution: int = 9
    routing_edge_sample_spacing_m: float = 30.0
    routing_edge_max_risk_weight: float = 0.65
    routing_candidate_alphas: str = "1,2,4,8,16"
    routing_balanced_max_detour_pct: float = 15.0
    routing_safer_max_detour_pct: float = 25.0
    routing_min_meaningful_risk_reduction_pct: float = 5.0
    # Dengeli profilde azalan getiri eşiği: her ek %1 sapmanın en az bu kadar
    # (en kısa rotanın riskine göre yüzde) risk düşüşü getirmesi beklenir.
    # Asıl orta-yol seçimi routing_balanced_detour_penalty ile yapılır; bu değer
    # yalnızca ceza=0 iken yedek olarak kullanılır. 0 = kapalı.
    routing_balanced_marginal_gain_floor: float = 0.0
    # Dengeli profil skor cezası: skor = risk_düşüşü_% − ceza × sapma_%.
    # Yüksek ceza → daha kısa/orta yol; düşük ceza → daha güvenli ama uzun.
    # 0 verilirse (ve floor da 0 ise) eski davranış: bütçe içinde en düşük risk.
    routing_balanced_detour_penalty: float = 2.0
    routing_diversify_iterations: int = 10
    routing_diversify_risk_iterations: int = 4
    routing_diversify_penalty_factor: float = 3.0
    routing_budget_bracket_enabled: bool = True
    routing_budget_bracket_steps: int = 6
    # İkili aramanın örnekleme noktaları üst sınıra bağlı olduğu için bu değer
    # kanıtlanmış aralıkta tutulur; daha yüksek ağırlıklar
    # routing_extra_safer_alphas üzerinden ayrı aday olarak eklenir.
    routing_budget_bracket_alpha_hi: float = 16.0
    # Alpha ızgarasının üst sınırında sıkışan güzergâhlar için ek risk ağırlıkları.
    routing_extra_safer_alphas: str = "32,64,128"
    # Bütçe elipsi ile alt graf kırpma (kayıpsız gecikme optimizasyonu).
    routing_subgraph_enabled: bool = True
    routing_subgraph_margin: float = 1.10
    routing_subgraph_max_node_ratio: float = 0.70
    crime_h3_shrinkage_strength: float = 2.0
    lighting_h3_shrinkage_strength: float = 1.0

    graph_path: str = "../data-science/chicago_walk.graphml"

    llm_mode: str = "mock"
    llm_provider: Literal["deepseek"] = "deepseek"
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-v4-flash"
    deepseek_base_url: str = "https://api.deepseek.com"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.2
    llm_max_tokens: int = 1024

    # Acil ihbar tanık/yayın bildirimi yarıçapı (metre).
    alert_radius_meters: int = 1000
    # Tanık onayı eşiği: ihbarı yapan hariç kaç bağımsız "gördüm" gerekir.
    alert_min_confirmations: int = 1
    expo_push_enabled: bool = True
    expo_push_url: str = "https://exp.host/--/api/v2/push/send"
    mocks_dir: str = "mocks"
    chicago_data_app_token: str = ""
    chicago_crime_api_url: str = "https://data.cityofchicago.org/resource/ijzp-q8t2.json"
    chicago_311_api_url: str = "https://data.cityofchicago.org/resource/v6vf-nfxy.json"

    report_cluster_window_minutes: int = 15
    report_similarity_threshold: float = 0.80
    # Metin benzerliği eşiği tutmadığında, aynı kategori/hücre/zaman penceresindeki
    # bağımsız muhabirin ihbarını yine de aynı olaya bağlar.
    report_cluster_category_match_enabled: bool = True
    # Tüm ihbarlar aynı kategoriye düştüğünde uygulanan taban benzerlik değeri.
    report_category_similarity_floor: float = 0.75
    report_min_independent_support: int = 2
    report_acceptance_threshold: float = 0.70
    report_event_expiry_minutes: int = 60
    report_live_risk_tau_minutes: float = 60.0
    report_nlp_mode: str = "deterministic"
    report_dev_solo_accept: bool = False

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @model_validator(mode="after")
    def validate_runtime_contract(self) -> "Settings":
        for name, value in (
            ("ROUTING_H3_RESOLUTION", self.routing_h3_resolution),
            ("ETL_H3_RESOLUTION", self.etl_h3_resolution),
            ("REPORT_H3_RESOLUTION", self.report_h3_resolution),
            ("H3_PARENT_RESOLUTION", self.h3_parent_resolution),
        ):
            if value not in (9, 10):
                raise ValueError(f"{name} must be 9 or 10")
        if self.h3_parent_resolution > self.routing_h3_resolution:
            raise ValueError("H3_PARENT_RESOLUTION cannot exceed ROUTING_H3_RESOLUTION")
        if self.report_nlp_mode not in {"deterministic", "shadow", "minilm"}:
            raise ValueError("REPORT_NLP_MODE must be deterministic, shadow, or minilm")
        if self.llm_mode not in {"disabled", "mock", "live"}:
            raise ValueError("LLM_MODE must be disabled, mock, or live")

        if self.app_environment in {"staging", "production"}:
            if len(self.reporter_hash_secret) < 32:
                raise ValueError("REPORTER_HASH_SECRET must contain at least 32 characters")
            if self.webhook_secret and len(self.webhook_secret) < 32:
                raise ValueError("WEBHOOK_SECRET must contain at least 32 characters when enabled")
            if not self.cors_origin_list or "*" in self.cors_origin_list:
                raise ValueError("CORS_ORIGINS must be a non-wildcard allowlist")
            if "localhost" in self.database_url or "saferoute:saferoute" in self.database_url:
                raise ValueError("Production-like environments require an explicit database URL")
            if self.llm_mode == "live" and not self.deepseek_api_key:
                raise ValueError("DEEPSEEK_API_KEY is required for live DeepSeek mode")
            if self.llm_mode == "live" and not self.deepseek_base_url.startswith("https://"):
                raise ValueError("DEEPSEEK_BASE_URL must be an HTTPS origin")
            if not self.auth_required:
                raise ValueError("AUTH_REQUIRED must be true in production-like environments")
            if not self.supabase_url.startswith("https://"):
                raise ValueError("SUPABASE_URL must be an HTTPS origin")
            if not self.supabase_publishable_key:
                raise ValueError("SUPABASE_PUBLISHABLE_KEY is required")
        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        case_sensitive=False,
    )


settings = Settings()
