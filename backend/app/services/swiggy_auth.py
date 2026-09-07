"""Swiggy MCP OAuth 2.1 + PKCE.

No client secret exists. https://mcp.swiggy.com/.well-known/oauth-authorization-server
advertises token_endpoint_auth_methods_supported: ["none", ...] and a
registration_endpoint — i.e. a public client that registers itself via Dynamic
Client Registration (RFC 7591) and proves itself with PKCE S256.

Token lifetime is 5 days and refresh_token issuance is NOT wired in Swiggy v1.0
(the metadata advertises the grant, /auth/token only implements authorization_code).
So a 401 means "re-run the whole authorization flow", never "refresh".
"""
import asyncio
import base64
import hashlib
import logging
import secrets
import time
from dataclasses import dataclass
from typing import Optional

import httpx

from app.config import settings

log = logging.getLogger(__name__)

SCOPES = "mcp:tools mcp:resources mcp:prompts"

# Authorization codes are single-use and live 120s; anything older is junk.
_PENDING_TTL_SECONDS = 300


class SwiggyAuthError(RuntimeError):
    """Authorization failed or the session is gone. Caller must re-authorize."""


@dataclass
class Token:
    access_token: str
    expires_at: float

    @property
    def expired(self) -> bool:
        # Proactively treat the last 60s as expired, per the docs' guidance.
        return time.time() >= self.expires_at - 60


@dataclass
class _Pending:
    verifier: str
    session_id: str
    created_at: float


# ponytail: process-local stores. A Render restart (free tier spins down) drops every
# token and forces users to re-authorize. Move to Redis/Postgres when that stops being
# acceptable — the interface below is already keyed by session_id.
_tokens: dict[str, Token] = {}
_pending: dict[str, _Pending] = {}

_metadata: Optional[dict] = None
_client_id: Optional[str] = None
_registration_lock = asyncio.Lock()


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def make_pkce_pair() -> tuple[str, str]:
    """Return (verifier, S256 challenge)."""
    verifier = _b64url(secrets.token_bytes(32))
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


async def get_metadata(client: Optional[httpx.AsyncClient] = None) -> dict:
    """Fetch and cache RFC 8414 authorization-server metadata."""
    global _metadata
    if _metadata is not None:
        return _metadata
    url = f"{settings.SWIGGY_MCP_BASE.rstrip('/')}/.well-known/oauth-authorization-server"
    owns = client is None
    client = client or httpx.AsyncClient(timeout=15)
    try:
        resp = await client.get(url)
        resp.raise_for_status()
        _metadata = resp.json()
    finally:
        if owns:
            await client.aclose()
    return _metadata


async def get_client_id() -> str:
    """Return the registered client_id, registering once via DCR if we have none."""
    global _client_id
    if _client_id:
        return _client_id
    if settings.SWIGGY_CLIENT_ID:
        _client_id = settings.SWIGGY_CLIENT_ID
        return _client_id

    async with _registration_lock:
        if _client_id:  # another request registered while we waited
            return _client_id
        meta = await get_metadata()
        endpoint = meta.get("registration_endpoint")
        if not endpoint:
            raise SwiggyAuthError("Swiggy metadata has no registration_endpoint")
        body = {
            "client_name": "LifeOps Concierge",
            "redirect_uris": [settings.SWIGGY_REDIRECT_URI],
            "grant_types": ["authorization_code"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
            "scope": SCOPES,
        }
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(endpoint, json=body)
        if resp.status_code >= 400:
            raise SwiggyAuthError(f"Dynamic client registration failed ({resp.status_code}): {resp.text}")
        _client_id = resp.json()["client_id"]
        # Surfaced so it can be pinned into SWIGGY_CLIENT_ID and survive a restart.
        log.warning("Registered Swiggy MCP client. Set SWIGGY_CLIENT_ID=%s to reuse it.", _client_id)
        return _client_id


def _prune_pending() -> None:
    cutoff = time.time() - _PENDING_TTL_SECONDS
    for state in [s for s, p in _pending.items() if p.created_at < cutoff]:
        _pending.pop(state, None)


async def build_authorize_url(session_id: str) -> str:
    """Start a flow for session_id and return the URL the user must open."""
    _prune_pending()
    meta = await get_metadata()
    client_id = await get_client_id()
    verifier, challenge = make_pkce_pair()
    state = _b64url(secrets.token_bytes(24))
    _pending[state] = _Pending(verifier=verifier, session_id=session_id, created_at=time.time())

    params = httpx.QueryParams(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": settings.SWIGGY_REDIRECT_URI,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
            "scope": SCOPES,
        }
    )
    return f"{meta['authorization_endpoint']}?{params}"


async def exchange_code(code: str, state: str) -> str:
    """Exchange an authorization code for a token. Returns the owning session_id."""
    pending = _pending.pop(state, None)
    if pending is None:
        # Unknown state = CSRF, replay, or an expired flow. All are refusals.
        raise SwiggyAuthError("Unknown or expired OAuth state. Start the login again.")
    if time.time() - pending.created_at > _PENDING_TTL_SECONDS:
        raise SwiggyAuthError("OAuth state expired. Start the login again.")

    meta = await get_metadata()
    body = {
        "grant_type": "authorization_code",
        "code": code,
        "code_verifier": pending.verifier,
        "redirect_uri": settings.SWIGGY_REDIRECT_URI,
        "client_id": await get_client_id(),
    }
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(meta["token_endpoint"], json=body)
    if resp.status_code >= 400:
        raise SwiggyAuthError(f"Token exchange failed ({resp.status_code}): {resp.text}")

    payload = resp.json()
    if "access_token" not in payload:
        raise SwiggyAuthError("Token response had no access_token")
    _tokens[pending.session_id] = Token(
        access_token=payload["access_token"],
        expires_at=time.time() + float(payload.get("expires_in", 432000)),
    )
    return pending.session_id


def get_token(session_id: str) -> str:
    token = _tokens.get(session_id)
    if token is None:
        raise SwiggyAuthError("Not connected to Swiggy. Start the login flow.")
    if token.expired:
        _tokens.pop(session_id, None)
        raise SwiggyAuthError("Swiggy session expired. Re-run the login flow.")
    return token.access_token


def has_token(session_id: str) -> bool:
    token = _tokens.get(session_id)
    return token is not None and not token.expired


def expires_at(session_id: str) -> Optional[float]:
    token = _tokens.get(session_id)
    return token.expires_at if token else None


def drop_token(session_id: str) -> None:
    _tokens.pop(session_id, None)


async def logout(session_id: str) -> None:
    """Revoke the Swiggy session, then forget it locally regardless of the outcome."""
    token = _tokens.get(session_id)
    if token is not None:
        url = f"{settings.SWIGGY_MCP_BASE.rstrip('/')}/auth/logout"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                await client.post(url, headers={"Authorization": f"Bearer {token.access_token}"})
        except httpx.HTTPError as exc:
            log.warning("Swiggy logout call failed, dropping token locally anyway: %s", exc)
    drop_token(session_id)
