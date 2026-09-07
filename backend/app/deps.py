"""App-level session handling.

The app session id is ours, not Swiggy's. The mobile client gets one from /auth/login
and sends it back as X-Session-Id; the Swiggy access token stays server-side and is
never handed to the client.
"""
import secrets

from fastapi import Header, HTTPException

from app.config import settings
from app.services import swiggy_auth

# ponytail: process-local, same ceiling as the token store — a restart logs everyone
# out. Move both to Redis/Postgres together when that matters.
_mock_authenticated: set[str] = set()


def new_session() -> str:
    return secrets.token_urlsafe(24)


def mark_mock_authenticated(session_id: str) -> None:
    _mock_authenticated.add(session_id)


def is_authenticated(session_id: str) -> bool:
    if settings.is_mock:
        return session_id in _mock_authenticated
    return swiggy_auth.has_token(session_id)


def forget(session_id: str) -> None:
    _mock_authenticated.discard(session_id)


def require_session(x_session_id: str = Header(default="")) -> str:
    """FastAPI dependency: reject anything without a session we actually issued."""
    if not x_session_id or not is_authenticated(x_session_id):
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
