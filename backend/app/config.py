from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_ENV: str = "development"
    CORS_ORIGINS: str = "http://localhost:19006,exp://localhost:8081,http://localhost:8081"
    SWIGGY_CLIENT_ID: str = "mock_client_id"
    SWIGGY_CLIENT_SECRET: str = "mock_client_secret"
    SWIGGY_REDIRECT_URI: str = "http://localhost:8000/auth/callback"
    LLM_API_KEY: str = "mock_llm_key"

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",")]

    @property
    def is_mock(self) -> bool:
        return self.APP_ENV != "production"


settings = Settings()
