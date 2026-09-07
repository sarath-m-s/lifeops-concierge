"""App-level session handling.

The app session id is ours, not Swiggy's. The mobile client gets one from /auth/login
and sends it back as X-Session-Id; the Swiggy access token stays server-side and is
never handed to the client.
"""
import secrets

from fastapi import Header, HTTPException

from app.services import swiggy_auth

def new_session() -> str:
    return secrets.token_urlsafe(24)


async def is_authenticated(session_id: str) -> bool:
    return await swiggy_auth.has_token(session_id)


async def require_session(x_session_id: str = Header(default="")) -> str:
    """FastAPI dependency: reject anything without a session we actually issued."""
    if not x_session_id or not await is_authenticated(x_session_id):
        raise HTTPException(
            status_code=401,
            detail={
                "success": False,
                "error": {
                    "message": "Not connected to Swiggy. Start the login flow.",
                    "reportHint": "POST /auth/login, open the returned authorize_url, then retry.",
                },
            },
        )
    return x_session_id
