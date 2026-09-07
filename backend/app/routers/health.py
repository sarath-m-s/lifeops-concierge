from fastapi import APIRouter

from app.config import settings

router = APIRouter()


@router.get("/health")
def health():
    return {
        "status": "ok",
        "version": "0.4.0",
        "env": settings.APP_ENV,
        "mcp_base": settings.SWIGGY_MCP_BASE,
        "llm": settings.llm_enabled,
    }
