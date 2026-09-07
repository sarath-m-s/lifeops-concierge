"""Read-only inspection of raw Swiggy tool responses.

Field names in the Swiggy docs are incomplete, so the planner reads defensively
and a naming surprise shows up as a blank section rather than a crash. That makes
it safe but opaque — this endpoint is how you see what actually came back.

Only tools on READ_ONLY are callable. That allowlist is the security boundary: a
general "call any tool" endpoint would let any authenticated session place an
order and bypass the confirmation gate entirely, which is the one invariant this
app has.
"""
import logging

from fastapi import APIRouter, Depends

from app import deps, errors
from app.services.swiggy_mcp import client

log = logging.getLogger(__name__)
router = APIRouter()

READ_ONLY: dict[str, set[str]] = {
    "food": {
        "get_addresses",
        "search_restaurants",
        "get_restaurant_menu",
        "search_menu",
        "get_food_cart",
        "get_food_orders",
    },
    "instamart": {"get_addresses", "search_products", "get_cart", "get_orders", "your_go_to_items"},
    "dineout": {
        "get_saved_locations",
        "search_restaurants_dineout",
        "get_restaurant_details",
        "get_available_slots",
        "get_booking_status",
    },
}


@router.post("/debug/tool")
async def debug_tool(body: dict, session_id: str = Depends(deps.require_session)):
    server = str(body.get("server", ""))
    tool = str(body.get("tool", ""))
    args = body.get("args") or {}

    if tool not in READ_ONLY.get(server, set()):
        allowed = sorted(READ_ONLY.get(server, set()))
        return {
            "error": f"{server}/{tool} is not an allowlisted read-only tool",
            "allowed": allowed,
        }

    try:
        return {"server": server, "tool": tool, "data": await client.call(session_id, server, tool, args)}
    except Exception as exc:
        raise errors.as_http(exc) from exc
