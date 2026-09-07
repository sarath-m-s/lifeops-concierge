from pydantic import BaseModel, Field
from typing import Any, Dict, List, Literal, Optional


class PendingAction(BaseModel):
    action_type: Literal["book_table", "place_food_order", "checkout_instamart"]
    params: Dict[str, Any]
    display_summary: str


ComponentType = Literal[
    "restaurant_list",
    "product_list",
    "menu_list",
    "coupon_list",
    "slot_list",
    "address_list",
    "order_list",
    "order_status",
    "confirm_action",
    "chips",
]


class Component(BaseModel):
    """A render instruction. The client maps `type` to a view and passes `props`.

    Unknown types are dropped by the client rather than erroring, so the backend
    can ship a new component ahead of an app release.
    """

    type: ComponentType
    props: Dict[str, Any] = Field(default_factory=dict)


class AgentTurn(BaseModel):
    """One assistant turn: something to say, plus what to render alongside it."""

    say: str
    components: List[Component] = Field(default_factory=list)


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class ConfirmRequest(BaseModel):
    action: PendingAction
    # Advisory only. The authoritative session comes from the X-Session-Id header,
    # so a client cannot act as another session by editing the body.
    session_id: Optional[str] = None


class ConfirmResult(BaseModel):
    success: bool
    message: str
    details: Optional[Dict[str, Any]] = None
