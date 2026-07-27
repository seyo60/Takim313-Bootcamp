# backend/config.py
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str

<<<<<<< Updated upstream
    # n8n gibi dis otomasyon araclarinin webhook'a erisebilmesi icin
    # paylasilan gizli anahtar. .env dosyasinda tanimlanmali:
    # WEBHOOK_SECRET=uzun-rastgele-bir-anahtar
    webhook_secret: str = "WEBHOOK_SECRET=saferoute-n8n-gizli-anahtar-2026-3bIWKCfNF6fCMu9e"

    class Config:
        env_file = ".env"
=======
    # --- Rotalama Motoru & Performans Ayarları ---
    routing_engine: str = "compact"
    compact_graph_path: str = "../data-science/compact_graph.npz"
    web_concurrency: int = 1
    routing_max_concurrency: int = 2
    routing_semaphore_limit: int = 2
    routing_queue_limit: int = 20
    retry_after_seconds: int = 10

    # --- Graf dosyasi ---
    graph_path: str = "../data-science/chicago_walk.graphml"

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

    # --- Chicago Data Portal Socrata API Settings ---
    chicago_data_app_token: str = ""
    chicago_crime_api_url: str = "https://data.cityofchicago.org/resource/ijzp-q8t2.json"
    chicago_311_api_url: str = "https://data.cityofchicago.org/resource/v6vf-nfxy.json"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
>>>>>>> Stashed changes


settings = Settings()