from fastapi import APIRouter, HTTPException
from app.models.agent_response import ConfirmRequest, ConfirmResult
from app.services.orchestrator import execute_confirmed_action

router = APIRouter()


@router.post("/confirm", response_model=ConfirmResult)
def confirm(request: ConfirmRequest):
    try:
        result = execute_confirmed_action(
            action_type=request.action.action_type,
            params=request.action.params,
        )
        return ConfirmResult(
            success=True,
            message=result.get("confirmation_message", "Action confirmed successfully."),
            details={k: v for k, v in result.items() if k not in ("order_id", "booking_id", "cart_id")},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
