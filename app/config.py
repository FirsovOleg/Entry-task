import os

from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./data/payments.db")
    PROVIDER_URL: str = os.getenv("PROVIDER_URL", "http://provider-simulator:8081")
    CALLBACK_URL: str = os.getenv("CALLBACK_URL", "http://candidate-service:8080/receipts")
    MAX_ATTEMPTS: int = int(os.getenv("MAX_ATTEMPTS", "5"))
    RETRY_BACKOFF_SECONDS: int = int(os.getenv("RETRY_BACKOFF_SECONDS", "5"))


settings = Settings()
