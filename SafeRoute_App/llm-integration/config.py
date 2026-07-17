# llm-integration/config.py
from pydantic_settings import BaseSettings


class LLMSettings(BaseSettings):
    """
    LLM modülü ayarları.
    .env dosyası llm-integration/ klasöründe olmalı.
    """
    # mock = sahte cevaplar (API key gerekmez), live = gerçek LLM API
    llm_mode: str = "mock"

    # Hangi sağlayıcı: deepseek | openai | gemini
    llm_provider: str = "deepseek"

    # DeepSeek (varsayılan sağlayıcı — OpenAI uyumlu API)
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com"

    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # Gemini
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    # LLM parametreleri
    llm_temperature: float = 0.2
    llm_max_tokens: int = 1024

    # Yakın kullanıcı arama yarıçapı (metre)
    alert_radius_meters: int = 500

    # Mock veri dosyalarının yolu
    mocks_dir: str = "mocks"

    class Config:
        env_file = ".env"


settings = LLMSettings()
