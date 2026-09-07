from fastapi import APIRouter

from app.config import settings

router = APIRouter()


@router.get("/health")
def health():
    return {
        "status": "ok",
        "version": "0.2.0",
        "mock_mode": settings.is_mock,
        "env": settings.APP_ENV,
        "mcp_base": settings.SWIGGY_MCP_BASE,
    }
