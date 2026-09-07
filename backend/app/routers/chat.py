from fastapi import APIRouter, Depends

from app import deps, errors
from app.models.agent_response import ChatRequest, AgentResponse
from app.services.orchestrator import parse_intent, generate_plan
from app.utils.id_sanitizer import strip_ids

router = APIRouter()


@router.post("/chat", response_model=AgentResponse)
async def chat(request: ChatRequest, session_id: str = Depends(deps.require_session)):
    intent = parse_intent(request.message)
    try:
        response = await generate_plan(intent, session_id)
    except Exception as exc:
        raise errors.as_http(exc) from exc
    return strip_ids(response.model_dump())
