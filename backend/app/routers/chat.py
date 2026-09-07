from fastapi import APIRouter, Depends

from app import deps, errors
from app.models.agent_response import ChatRequest, AgentResponse, UIPayload
from app.services import live_planner
from app.services.intent import parse_intent
from app.utils.id_sanitizer import strip_ids

router = APIRouter()

_GREETING = (
    "I can book a table, order food, or restock groceries — or plan all three at once. "
    "What would you like?"
)


@router.post("/chat", response_model=AgentResponse)
async def chat(request: ChatRequest, session_id: str = Depends(deps.require_session)):
    intent = await parse_intent(request.message)

    if intent.intent == "general":
        return AgentResponse(
            spoken_response=_GREETING,
            ui_payload=UIPayload(type="cards", title="What can I help with?", items=[]),
        )

    try:
        if intent.intent == "plan_evening":
            response = await live_planner.plan_evening(session_id, intent)
        else:
            response = await live_planner.single_service(session_id, intent)
    except Exception as exc:
        raise errors.as_http(exc) from exc
    return strip_ids(response.model_dump())
