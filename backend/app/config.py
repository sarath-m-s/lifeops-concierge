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

    # Backs the Swiggy token store (app/services/token_store.py) so the web process
    # (issues tokens via OAuth) and the voice worker process (reads them to call
    # Swiggy MCP) see the same session — an in-memory dict is invisible across
    # processes. Falls back to in-process memory when unset (fine for local dev,
    # not for a two-process deployment).
    DATABASE_URL: str = ""

    # LiveKit Cloud project for the voice agent worker. STT/LLM/TTS all route
    # through LiveKit Inference (app/voice/session.py) using these same
    # credentials — no separate Deepgram/Cartesia/OpenAI key, billed through
    # LiveKit Cloud instead (free trial credits apply).
    LIVEKIT_URL: str = ""
    LIVEKIT_API_KEY: str = ""
    LIVEKIT_API_SECRET: str = ""
    # The voice agent's LLM (function-calling brain) — a LiveKit Inference model
    # id (see livekit.agents.inference.LLMModels for the catalog).
    VOICE_LLM_MODEL: str = "openai/gpt-4o-mini"

    # INFO narrates every turn and tool call. DEBUG additionally dumps full tool
    # payloads — verbose, and they contain the user's addresses, so keep it off
    # unless you are actively diagnosing a field-name mismatch.
    LOG_LEVEL: str = "INFO"

    # Groq API key for intent extraction. Without it the backend falls back to
    # keyword matching — degraded, but the app still runs.
    LLM_API_KEY: str = ""
    # Must handle tool calling reliably. Measured across 12 turns each on Groq:
    # gpt-oss-20b 12/12 clean, gpt-oss-120b 9/12, qwen3.8-27b 8/12 — the larger
    # models mangle the tool-call envelope often enough to break real turns, so
    # the small one wins on reliability despite being ~1s slower.
    LLM_MODEL: str = "openai/gpt-oss-20b"

    # Fallback when Groq itself is down/rate-limited (litellm.APIError — not a
    # BadRequestError, which is a content problem no provider switch fixes).
    # Measured 2026-09-09 against this app's real TOOLS schema: 9/9 clean
    # tool-calling turns on NVIDIA NIM's free tier, ~2x faster than the other
    # reliable NIM candidates tried (gpt-oss-20b-on-NIM, nemotron-3-super).
    # Still ~10x slower than Groq — fallback only, never the primary.
    NVIDIA_API_KEY: str = ""
    FALLBACK_LLM_MODEL: str = "nvidia_nim/meta/muse-glimmer-30b"

    # Placeholder values that ship in .env.example must not read as "configured".
    _LLM_PLACEHOLDERS = ("", "mock_llm_key", "your_llm_api_key", "your_groq_api_key", "your_nvidia_api_key")

    @property
    def llm_enabled(self) -> bool:
        return self.LLM_API_KEY.strip() not in self._LLM_PLACEHOLDERS

    @property
    def nvidia_fallback_enabled(self) -> bool:
        return self.NVIDIA_API_KEY.strip() not in self._LLM_PLACEHOLDERS

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    def server_url(self, server: str) -> str:
        """Map a logical server name onto its Swiggy MCP endpoint."""
        path = {"food": "food", "instamart": "im", "dineout": "dineout"}[server]
        return f"{self.SWIGGY_MCP_BASE.rstrip('/')}/{path}"


settings = Settings()
