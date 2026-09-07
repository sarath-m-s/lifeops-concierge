from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_ENV: str = "development"
    CORS_ORIGINS: str = "http://localhost:19006,http://localhost:8081"

    # Swiggy MCP is an OAuth 2.1 public client (PKCE S256). There is no client secret —
    # the metadata document advertises token_endpoint_auth_method "none". The client_id
    # comes back from Dynamic Client Registration; caching it here stops a restart from
    # re-registering, since every registration counts as an auth event against the limit.
    SWIGGY_MCP_BASE: str = "https://mcp.swiggy.com"
    SWIGGY_REDIRECT_URI: str = "http://localhost:8000/auth/callback"
    SWIGGY_CLIENT_ID: str = ""

    MOBILE_SUCCESS_DEEPLINK: str = "lifeops://"

    # INFO narrates every turn and tool call. DEBUG additionally dumps full tool
    # payloads — verbose, and they contain the user's addresses, so keep it off
    # unless you are actively diagnosing a field-name mismatch.
    LOG_LEVEL: str = "INFO"

    # Groq API key for intent extraction. Without it the backend falls back to
    # keyword matching — degraded, but the app still runs.
    LLM_API_KEY: str = ""
    # Must be a model that supports structured outputs in strict mode.
    LLM_MODEL: str = "openai/gpt-oss-120b"

    # Placeholder values that ship in .env.example must not read as "configured".
    _LLM_PLACEHOLDERS = ("", "mock_llm_key", "your_llm_api_key", "your_groq_api_key")

    @property
    def llm_enabled(self) -> bool:
        return self.LLM_API_KEY.strip() not in self._LLM_PLACEHOLDERS

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    def server_url(self, server: str) -> str:
        """Map a logical server name onto its Swiggy MCP endpoint."""
        path = {"food": "food", "instamart": "im", "dineout": "dineout"}[server]
        return f"{self.SWIGGY_MCP_BASE.rstrip('/')}/{path}"


settings = Settings()
