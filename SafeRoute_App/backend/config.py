# backend/config.py
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str

    # n8n gibi dis otomasyon araclarinin webhook'a erisebilmesi icin
    # paylasilan gizli anahtar. .env dosyasinda tanimlanmali:
    # WEBHOOK_SECRET=uzun-rastgele-bir-anahtar
    webhook_secret: str = "WEBHOOK_SECRET=saferoute-n8n-gizli-anahtar-2026-3bIWKCfNF6fCMu9e"

    class Config:
        env_file = ".env"


settings = Settings()