"""Confirmed-action execution and shared payload helpers.

The search and planning that used to live here is gone — the agent loop does that
now. What remains is the part the model is deliberately kept away from: actually
placing an order, reached only from /confirm after an explicit tap.

The readers below are shared with components.py. They stay tolerant because
Swiggy's payloads vary by tool, and a missing field should render as a gap rather
than take the turn down.
"""
import logging
from typing import Any

from app.services import live_mcp
from app.services.live_mcp import FOOD_CART_CAP_RUPEES
from app.services.swiggy_mcp import SwiggyToolError

log = logging.getLogger(__name__)


def _get(obj: Any, *names: str, default: Any = None) -> Any:
    if not isinstance(obj, dict):
        return default
    for name in names:
        if obj.get(name) is not None:
            return obj[name]
    return default


def _rows(payload: Any, *names: str) -> list[dict]:
    value = _get(payload, *names, default=[])
    if isinstance(value, dict):
        value = _get(value, *names, default=[])
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _amount(value: Any) -> int:
    """Money arrives either as a number or as an object.

    Instamart returns {"mrp": 280, "offerPrice": 260, "unitLevelPrice": "260/100 g"}.
    Summing that dict is what produced `unsupported operand type(s) for +`.
    """
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, dict):
        for key in ("offerPrice", "finalPrice", "price", "mrp", "amount", "value"):
            inner = value.get(key)
            if isinstance(inner, (int, float)):
                return int(inner)
    return 0


def _reject_pending_payment(result: dict) -> None:
    """PENDING_PAYMENT means the UPI leg is still open — never call that placed."""
    if str(_get(result, "status", default="")).upper() == "PENDING_PAYMENT":
        raise SwiggyToolError(
            "This order needs an online payment, which this app doesn't handle yet. "
            "Complete it in the Swiggy app."
        )


async def execute(sid: str, action_type: str, params: dict) -> dict:
    """Run a user-confirmed mutation. Every branch reads server state before writing."""
    if action_type == "book_table":
        result = await live_mcp.book_table(
            sid,
            restaurant_id=params["restaurantId"],
            slot_id=params["slotId"],
            item_id=params.get("itemId"),
            reservation_time=params.get("reservationTime"),
            latitude=params.get("latitude"),
            longitude=params.get("longitude"),
            guest_count=int(params.get("guestCount", 2)),
        )
        result.setdefault("confirmation_message", "Your table is booked.")
        return result

    if action_type == "place_food_order":
        # Flush first: update_food_cart's add-vs-replace semantics aren't documented,
        # so a stale item from an earlier abandoned attempt must not ride along into
        # an order that actually charges the user.
        await live_mcp.flush_food_cart(sid)
        await live_mcp.update_food_cart(sid, params["restaurantId"], params["items"])
        if params.get("couponCode"):
            await live_mcp.apply_food_coupon(sid, params["couponCode"], params["addressId"])
        # Read the cart back before placing: the user may have edited it in the
        # Swiggy app between turns, and the cap applies to the real total.
        cart = await live_mcp.get_food_cart(sid, params["addressId"])
        total = _get(cart, "total", "grandTotal", "billTotal", default=0) or 0
        if total > FOOD_CART_CAP_RUPEES:
            raise SwiggyToolError(
                f"Cart total ₹{total} exceeds the ₹{FOOD_CART_CAP_RUPEES} Swiggy Builders Club cap. "
                "Remove an item and try again."
            )
        result = await live_mcp.place_food_order(sid, params["addressId"])
        _reject_pending_payment(result)
        result.setdefault("confirmation_message", "Your food order is placed.")
        return result

    if action_type == "checkout_instamart":
        await live_mcp.clear_grocery_cart(sid)
        await live_mcp.update_cart(sid, params["items"])
        if params.get("couponCode"):
            await live_mcp.apply_grocery_coupon(sid, params["couponCode"])
        await live_mcp.get_cart(sid)
        result = await live_mcp.checkout(sid, params["addressId"])
        _reject_pending_payment(result)
        result.setdefault("confirmation_message", "Your grocery order is placed.")
        return result

    if action_type == "delete_address":
        result = await live_mcp.delete_address(sid, params["addressId"])
        result.setdefault("confirmation_message", "That address has been removed.")
        return result

    raise ValueError(f"Unknown action_type: {action_type}")
