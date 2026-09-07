import logging

from fastapi import APIRouter, Depends

from app import deps, errors
from app.config import settings
from app.models.agent_response import AgentTurn, ChatRequest
from app.services import conversation
from app.services.agent import Agent

log = logging.getLogger(__name__)
router = APIRouter()

_NO_LLM = (
    "I need an AI key to understand free-form requests. "
    "Set LLM_API_KEY on the server and I'll be able to help properly."
)


@router.post("/chat", response_model=AgentTurn)
async def chat(request: ChatRequest, session_id: str = Depends(deps.require_session)):
    message = (request.message or "").strip()
    if not message:
        return AgentTurn(say="Say that again?", components=[])

    if not settings.llm_enabled:
        # There is no keyword fallback for an agent — a tool-calling loop has no
        # degraded mode. Say so plainly rather than pretending to work.
        return AgentTurn(say=_NO_LLM, components=[])

    convo = conversation.store.get(session_id)
    try:
        return await Agent(session_id, convo).run(message)
    except Exception as exc:
        raise errors.as_http(exc) from exc


@router.post("/chat/reset")
async def reset(session_id: str = Depends(deps.require_session)):
    """Start a fresh conversation without disconnecting Swiggy."""
    conversation.store.reset(session_id)
    return {"status": "reset"}
