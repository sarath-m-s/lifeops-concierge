from fastapi import APIRouter
from app.models.agent_response import ChatRequest, AgentResponse
from app.services.orchestrator import parse_intent, generate_plan
from app.utils.id_sanitizer import strip_ids

router = APIRouter()


@router.post("/chat", response_model=AgentResponse)
def chat(request: ChatRequest):
    intent = parse_intent(request.message)
    response = generate_plan(intent)
    cleaned = strip_ids(response.model_dump())
    return cleaned
