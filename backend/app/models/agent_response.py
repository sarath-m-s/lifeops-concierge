from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Dict, Any


class PendingAction(BaseModel):
    action_type: Literal["book_table", "place_food_order", "checkout_instamart"]
    params: Dict[str, Any]
    display_summary: str


class UIPayload(BaseModel):
    type: Literal["timeline", "cards", "cart", "status", "confirmation"]
    items: List[Dict[str, Any]] = []
    title: Optional[str] = None


class AgentResponse(BaseModel):
    spoken_response: str = Field(max_length=200)
    ui_payload: UIPayload
    requires_confirmation: bool = False
    pending_action: Optional[PendingAction] = None


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class ConfirmRequest(BaseModel):
    action: PendingAction
    session_id: str


class ConfirmResult(BaseModel):
    success: bool
    message: str
    details: Optional[Dict[str, Any]] = None
