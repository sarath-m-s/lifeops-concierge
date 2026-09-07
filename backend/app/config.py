from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_ENV: str = "development"
    CORS_ORIGINS: str = "http://localhost:19006,exp://localhost:8081,http://localhost:8081"

    # Swiggy MCP is an OAuth 2.1 public client (PKCE S256). There is no client secret —
    # the metadata document advertises token_endpoint_auth_method "none". The client_id
    # comes back from Dynamic Client Registration; we cache it here so a restart does not
    # re-register (every registration counts as an auth event against the rate limit).
    SWIGGY_MCP_BASE: str = "https://mcp.swiggy.com"
    SWIGGY_REDIRECT_URI: str = "http://localhost:8000/auth/callback"
    SWIGGY_CLIENT_ID: str = ""

    MOBILE_SUCCESS_DEEPLINK: str = "lifeops://"

    LLM_API_KEY: str = "mock_llm_key"

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def is_mock(self) -> bool:
        return self.APP_ENV != "production"

    def server_url(self, server: str) -> str:
        """Map a logical server name onto its Swiggy MCP endpoint."""
        path = {"food": "food", "instamart": "im", "dineout": "dineout"}[server]
        return f"{self.SWIGGY_MCP_BASE.rstrip('/')}/{path}"


settings = Settings()
