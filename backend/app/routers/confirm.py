from fastapi import APIRouter, HTTPException
from app.models.agent_response import ConfirmRequest, ConfirmResult
from app.services.orchestrator import execute_confirmed_action

router = APIRouter()

# Per Swiggy MCP docs: order placement (place_food_order, checkout, book_table) is
# non-idempotent. Track confirmed action_ids so we never blind-retry a mutation.
_confirmed_actions: set[str] = set()


def _action_key(request: ConfirmRequest) -> str:
    return f"{request.session_id}:{request.action.action_type}:{request.action.display_summary}"


@router.post("/confirm", response_model=ConfirmResult)
def confirm(request: ConfirmRequest):
    key = _action_key(request)

    # Guard: non-idempotent actions must not be replayed within the same session
    if key in _confirmed_actions:
        raise HTTPException(
            status_code=409,
            detail={
                "success": False,
                "error": {
                    "message": "This action has already been confirmed. Check status before retrying.",
                    "reportHint": "Use track_food_order / get_booking_status to verify the current state.",
                },
            },
        )

    try:
        result = execute_confirmed_action(
            action_type=request.action.action_type,
            params=request.action.params,
        )
        _confirmed_actions.add(key)
        return ConfirmResult(
            success=True,
            message=result.get("confirmation_message", "Action confirmed successfully."),
            # Strip internal IDs from user-facing details
            details={
                k: v for k, v in result.items()
                if k not in ("order_id", "booking_id", "cart_id", "confirmation_message")
            },
        )
    except Exception as e:
        # Match Swiggy MCP uniform error envelope
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": {
                    "message": str(e),
                    "reportHint": "If this persists, contact builders@swiggy.in",
                },
            },
        )
