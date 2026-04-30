from fastapi import APIRouter
from fastapi.responses import RedirectResponse
from app.config import settings

router = APIRouter()

_mock_session = {"authenticated": True, "user_id": "mock_user_001", "is_mock": True}


@router.get("/auth/callback")
def auth_callback(code: str = None, error: str = None):
    if error:
        return {"error": error, "message": "OAuth authorization failed."}
    # In mock mode, accept any code and return success
    _mock_session["code"] = code
    # In a real app, redirect to the mobile deep link: lifeops://auth/success
    return {"status": "authenticated", "mock_mode": settings.is_mock, "message": "Auth successful. Return to the app."}


@router.get("/auth/status")
def auth_status():
    return _mock_session
