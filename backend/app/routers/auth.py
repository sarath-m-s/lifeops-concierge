import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

from app import deps
from app.config import settings
from app.services import swiggy_auth, swiggy_mcp
from app.services.swiggy_auth import SwiggyAuthError

log = logging.getLogger(__name__)
router = APIRouter()


@router.post("/auth/login")
async def login():
    """Start a login. Returns the session id to send back as X-Session-Id.

    In mock mode no Swiggy call happens — the session is marked authenticated locally
    so the demo runs, but an unknown session id is still rejected everywhere else.
    """
    session_id = deps.new_session()
    if settings.is_mock:
        deps.mark_mock_authenticated(session_id)
        return {"session_id": session_id, "authorize_url": None, "mock_mode": True}
    try:
        url = await swiggy_auth.build_authorize_url(session_id)
    except SwiggyAuthError as exc:
        raise HTTPException(status_code=502, detail={"success": False, "error": {"message": str(exc)}}) from exc
    return {"session_id": session_id, "authorize_url": url, "mock_mode": False}


@router.get("/auth/callback")
async def auth_callback(code: str = "", state: str = "", error: str = ""):
    """OAuth redirect target. Exchanges the code, then bounces back into the app."""
    if error:
        return HTMLResponse(f"<h3>Swiggy authorization failed</h3><p>{error}</p>", status_code=400)
    if not code or not state:
        return HTMLResponse("<h3>Missing authorization code</h3>", status_code=400)
    try:
        await swiggy_auth.exchange_code(code, state)
    except SwiggyAuthError as exc:
        log.warning("Token exchange failed: %s", exc)
        return HTMLResponse(f"<h3>Could not complete sign-in</h3><p>{exc}</p>", status_code=400)
    return RedirectResponse(settings.MOBILE_SUCCESS_DEEPLINK, status_code=302)


@router.get("/auth/status")
def auth_status(session_id: str = ""):
    """Report whether a specific session is connected. No session id, no answer."""
    if not session_id:
        return {"authenticated": False, "mock_mode": settings.is_mock}
    return {
        "authenticated": deps.is_authenticated(session_id),
        "mock_mode": settings.is_mock,
        "expires_at": swiggy_auth.expires_at(session_id),
    }


@router.post("/auth/logout")
async def logout(session_id: str = Depends(deps.require_session)):
    await swiggy_mcp.client.close_session(session_id)
    await swiggy_auth.logout(session_id)
    deps.forget(session_id)
    return {"status": "logged_out"}
