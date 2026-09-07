import asyncio
import hashlib
import json

from fastapi import APIRouter, Depends

from app import deps, errors
from app.models.agent_response import ConfirmRequest, ConfirmResult
from app.services.orchestrator import execute_confirmed_action

router = APIRouter()

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
            result = await execute_confirmed_action(
                action_type=request.action.action_type,
                params=request.action.params,
                session_id=session_id,
            )
        except Exception as exc:
            raise errors.as_http(exc) from exc

        payload = {
            "success": True,
            "message": result.get("confirmation_message", "Action confirmed successfully."),
            # Internal identifiers stay server-side; only human-readable detail goes out.
            "details": {
                k: v
                for k, v in result.items()
                if k not in ("order_id", "orderId", "booking_id", "bookingId", "cart_id", "cartId", "paasId", "confirmation_message")
            },
        }
        _completed[key] = payload
        return ConfirmResult(**payload)
