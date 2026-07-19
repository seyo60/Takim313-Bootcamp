# backend/config.py
"""
TEK yapilandirma kaynagi (backend + LLM entegrasyonu birlesik).

- Butun sirlar (API anahtarlari vb.) .env dosyasindan okunur.
  Kod icinde HICBIR hardcoded secret bulunmaz. Ornek icin: .env.example
- Eski `webhook_secret` sabiti kaldirildi: sosyal medya / n8n webhook
  entegrasyonu MVP kapsami disina alindi (bkz. BACKEND_IMPLEMENTATION_
  MASTER_PLAN.md, Bolum 2.4).
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- Veritabani ---
    # Ornek: postgresql+asyncpg://saferoute:saferoute@localhost:5432/saferoute
    database_url: str = "postgresql+asyncpg://saferoute:saferoute@localhost:5432/saferoute"

    # --- Graf dosyasi ---
    graph_path: str = "../data-science/chicago.graphml"

    # --- LLM modu / saglayici ---
    # llm_mode: "mock" -> API anahtari gerekmez, kural tabanli cevaplar
    #           "live" -> gercek LLM API cagrisi (hata halinde mock'a fallback)
    llm_mode: str = "mock"
    # llm_provider: gemini | deepseek | openai  (birincil tercih: gemini)
    llm_provider: str = "gemini"

    # --- Gemini (birincil saglayici) ---
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    # --- DeepSeek (alternatif, OpenAI uyumlu API) ---
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com"

    # --- OpenAI (alternatif) ---
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # --- LLM parametreleri ---
    llm_temperature: float = 0.2
    llm_max_tokens: int = 1024

    # --- Bildirim / mock ayarlari (alert_dispatcher icin) ---
    alert_radius_meters: int = 500
    mocks_dir: str = "mocks"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
