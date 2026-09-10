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
from livekit.protocol.agent import JobStatus

from app import deps
from app.config import settings
from app.voice import AGENT_NAME

# A dispatch that's still pending/running already has (or will have) an agent
# in the room. SUCCESS/FAILED are terminal — the job ended, the agent is gone —
# so a dispatch record in either state must not block a fresh one.
_LIVE_JOB_STATES = {JobStatus.JS_PENDING, JobStatus.JS_RUNNING}

log = logging.getLogger(__name__)
router = APIRouter()

# Short-lived: minted fresh on every connect rather than cached client-side, same
# posture as not handing the Swiggy access token to the device.
_TOKEN_TTL = timedelta(minutes=10)


async def _ensure_dispatched(lkapi: api.LiveKitAPI, room_name: str) -> None:
    """Make sure an agent job is (or will be) running in this room.

    The worker only accepts explicit dispatch (see WorkerOptions in worker.py)
    — automatic dispatch fires once per room's *lifetime*, and this app reuses
    the same room name across reconnects (`lifeops-<session_id>`), so a
    returning participant would otherwise never get a fresh agent.

    `list_dispatch` returns every dispatch ever made for this room, including
    ones whose job already finished (success) or died (failed) — a stale
    FAILED record must not be mistaken for "already served" and block a retry.
    Only a dispatch with a job still pending/running for *this* agent counts.

    Live-verified 2026-09-10: a room nobody has ever joined doesn't exist yet
    as far as LiveKit's server is concerned, and list_dispatch 404s instead of
    returning an empty list — an unhandled 404 here crashed the whole request
    (client saw it as a hang, not an error). No existing room means no
    existing dispatch either, so treat it exactly the same as an empty list.
    """
    try:
        existing = await lkapi.agent_dispatch.list_dispatch(room_name=room_name)
    except api.ServerError as exc:
        if exc.code != "not_found":
            raise
        existing = []
    for dispatch in existing:
        if dispatch.agent_name != AGENT_NAME:
            continue
        if any(job.state.status in _LIVE_JOB_STATES for job in dispatch.state.jobs):
            return
    await lkapi.agent_dispatch.create_dispatch(
        api.CreateAgentDispatchRequest(agent_name=AGENT_NAME, room=room_name)
    )


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

    lkapi = api.LiveKitAPI(
        url=settings.LIVEKIT_URL, api_key=settings.LIVEKIT_API_KEY, api_secret=settings.LIVEKIT_API_SECRET
    )
    try:
        await _ensure_dispatched(lkapi, room_name)
    finally:
        await lkapi.aclose()

    return {"room_name": room_name, "token": token.to_jwt(), "url": settings.LIVEKIT_URL}
