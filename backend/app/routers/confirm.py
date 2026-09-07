import asyncio
import hashlib
import json
import logging

from fastapi import APIRouter, Depends
from livekit import api
from livekit.protocol.models import DataPacket

from app import deps, errors
from app.config import settings
from app.models.agent_response import ConfirmRequest, ConfirmResult
from app.services.live_planner import execute

log = logging.getLogger(__name__)
router = APIRouter()

# Topic the voice worker listens on (see app/voice/worker.py). /confirm is a plain
# REST call in the *web* process — it is never itself a room participant — so this
# goes over the LiveKit server API (a raw data packet) rather than the room's
# participant-to-participant text-stream API.
_CONFIRM_RESULT_TOPIC = "lifeops.confirm_result"


async def _tell_room(session_id: str, say: str) -> None:
    """Best-effort: let the voice agent speak+render a confirmation result.

    Never raises — the order/booking already succeeded and was already reported
    to the caller synchronously below; a dropped or unconfigured LiveKit room
    just means the spoken confirmation is skipped, not that the action failed.
    """
    if not (settings.LIVEKIT_URL and settings.LIVEKIT_API_KEY and settings.LIVEKIT_API_SECRET):
        return
    lkapi = api.LiveKitAPI(
        url=settings.LIVEKIT_URL, api_key=settings.LIVEKIT_API_KEY, api_secret=settings.LIVEKIT_API_SECRET
    )
    try:
        await lkapi.room.send_data(
            api.SendDataRequest(
                room=f"lifeops-{session_id}",
                data=json.dumps({"say": say}).encode(),
                kind=DataPacket.Kind.RELIABLE,
                topic=_CONFIRM_RESULT_TOPIC,
            )
        )
    except Exception as exc:  # noqa: BLE001 — signaling the room is best-effort
        log.warning("could not signal room for session %s: %s", session_id[:8], exc)
    finally:
        await lkapi.aclose()

# place_food_order / checkout / book_table are non-idempotent. Two separate hazards:
#
#   1. The user double-taps Confirm. Handled here: one lock per action, and the result
#      of a completed action is replayed instead of placing a second order.
#   2. The call itself 5xxs mid-flight. Handled in swiggy_mcp.place_with_verification,
#      which checks get_food_orders / get_orders / get_booking_status before re-placing,
#      per docs/build/ship-to-production. A blanket 409 would have been wrong: it also
#      blocks the legitimate retry of an order that never landed.
#
# ponytail: process-local, so it guards one worker. Move to Redis with a short TTL if
# this ever runs multiple workers or needs to survive a restart.
_locks: dict[str, asyncio.Lock] = {}
_completed: dict[str, dict] = {}


def _action_key(session_id: str, request: ConfirmRequest) -> str:
    payload = json.dumps(
        [request.action.action_type, request.action.params, request.action.display_summary],
        sort_keys=True,
        default=str,
    )
    return f"{session_id}:{hashlib.sha256(payload.encode()).hexdigest()[:16]}"


@router.post("/confirm", response_model=ConfirmResult)
async def confirm(request: ConfirmRequest, session_id: str = Depends(deps.require_session)):
    key = _action_key(session_id, request)
    lock = _locks.setdefault(key, asyncio.Lock())

    async with lock:
        if key in _completed:
            return ConfirmResult(**_completed[key])

        try:
            result = await execute(
                session_id,
                request.action.action_type,
                request.action.params,
            )
        except Exception as exc:
            raise errors.as_http(exc) from exc

        message = result.get("confirmation_message", "Action confirmed successfully.")
        payload = {
            "success": True,
            "message": message,
            # Internal identifiers stay server-side; only human-readable detail goes out.
            "details": {
                k: v
                for k, v in result.items()
                if k not in ("order_id", "orderId", "booking_id", "bookingId", "cart_id", "cartId", "paasId", "confirmation_message")
            },
        }
        _completed[key] = payload
        await _tell_room(session_id, message)
        return ConfirmResult(**payload)
