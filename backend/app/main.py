from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.logging_setup import capture_uvicorn, setup as setup_logging
from app.routers import health, chat, confirm, auth, debug, livekit_token
from app.services.swiggy_mcp import client
from app.services.token_store import store as token_store

setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # uvicorn installs its handlers after import, so re-capture once it is up.
    capture_uvicorn()
    # Opens the Postgres pool (or falls back to in-process memory) so Swiggy
    # tokens survive a restart and are visible to the voice worker process.
    await token_store.start()
    yield
    # MCP sessions are long-lived by design; close them so Swiggy doesn't see
    # abandoned connections when this process goes away.
    await client.close_all()
    await token_store.close()


app = FastAPI(
    title="LifeOps Concierge API",
    description="Voice-first AI concierge for Swiggy Food, Instamart, and Dineout",
    version="0.4.0",
    lifespan=lifespan,
)

# Explicit origin allowlist, always. Every data endpoint is additionally gated on a
# server-issued X-Session-Id, so a browser origin alone grants nothing.
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
app.include_router(debug.router)
app.include_router(livekit_token.router)
