"""Mint a LiveKit room-join token for an already-authenticated app session.

One room per app session (`lifeops-<session_id>`), matching the one-Conversation-
per-session model the voice worker also uses. `identity` is set to the session_id
itself, so the worker's job entrypoint can recover it straight from
`participant.identity` — no separate room-name parsing needed on that side.
"""
import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from livekit import api

from app import deps
from app.config import settings

log = logging.getLogger(__name__)
router = APIRouter()

# Short-lived: minted fresh on every connect rather than cached client-side, same
# posture as not handing the Swiggy access token to the device.
_TOKEN_TTL = timedelta(minutes=10)


@router.post("/livekit/token")
async def mint_token(session_id: str = Depends(deps.require_session)):
    if not (settings.LIVEKIT_URL and settings.LIVEKIT_API_KEY and settings.LIVEKIT_API_SECRET):
        raise HTTPException(
            status_code=503,
            detail={"success": False, "error": {"message": "LiveKit is not configured on this server."}},
        )

    room_name = f"lifeops-{session_id}"
    token = (
        api.AccessToken(settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)
        .with_identity(session_id)
        .with_ttl(_TOKEN_TTL)
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
            )
        )
    )
    return {"room_name": room_name, "token": token.to_jwt(), "url": settings.LIVEKIT_URL}
