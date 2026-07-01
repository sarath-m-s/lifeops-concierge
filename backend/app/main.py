from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.routers import health, chat, confirm, auth

app = FastAPI(
    title="LifeOps Concierge API",
    description="Voice-first AI concierge for Swiggy Food, Instamart, and Dineout",
    version="0.1.0",
)

# In dev/mock mode, allow any origin so the app works regardless of which port
# Expo picks (web, simulator, LAN device). Production uses the explicit allowlist.
# Note: browsers reject wildcard origin + credentials, so credentials are off in dev.
if settings.is_mock:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(health.router)
app.include_router(chat.router)
app.include_router(confirm.router)
app.include_router(auth.router)
