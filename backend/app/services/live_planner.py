"""Plan assembly against the real Swiggy MCP servers.

Response field names come from the published tool reference. Where a payload
could plausibly use more than one spelling, reads go through `_get`, so a naming
surprise degrades to a missing field instead of a KeyError.
"""
import asyncio
import logging
from datetime import date, datetime
from typing import Any, Optional

from app.models.agent_response import AgentResponse, UIPayload
from app.services import live_mcp
from app.services.intent import ParsedIntent
from app.services.live_mcp import FOOD_CART_CAP_RUPEES
from app.services.swiggy_mcp import SwiggyToolError, client

log = logging.getLogger(__name__)

_ALL = ("dineout", "food", "instamart")


def _get(obj: Any, *names: str, default: Any = None) -> Any:
    if not isinstance(obj, dict):
        return default
    for name in names:
        if obj.get(name) is not None:
            return obj[name]
    return default


def _rows(payload: dict, *names: str) -> list[dict]:
    value = _get(payload, *names, default=[])
    if isinstance(value, dict):
        value = _get(value, *names, default=[])
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


# --- shared resolution -------------------------------------------------------

async def _home_address(sid: str) -> dict:
    """Food/Instamart delivery address. These two services share address endpoints."""
    payload = await live_mcp.get_addresses(sid)
    rows = _rows(payload, "addresses", "data") or ([payload] if _get(payload, "addressId", "id") else [])
    if not rows:
        raise SwiggyToolError(
            "No saved delivery address on your Swiggy account. Add one in the Swiggy app, then try again."
        )
    return next((a for a in rows if str(_get(a, "label", default="")).lower() == "home"), rows[0])


async def _saved_location(sid: str) -> dict:
    """Dineout search location. Returns index/id/addressLine — no coordinates."""
    payload = await live_mcp.get_saved_locations(sid)
    rows = _rows(payload, "locations", "data")
    if not rows:
        raise SwiggyToolError(
            "No saved location on your Swiggy account for restaurant search. Add an address in the Swiggy app."
        )
    return rows[0]


def _is_open(restaurant: dict) -> bool:
    status = str(_get(restaurant, "availabilityStatus", "availability", default="OPEN")).upper()
    return status in ("OPEN", "AVAILABLE")


def _free_deal(slot: dict) -> Optional[dict]:
    """Pick a free deal from a slot, returning the identifiers book_table needs.

    slotId and itemId live on the deal, not the slot — a slot can carry several
    deals at the same time with different prices. Paid prebook deals (isFree
    false, or bookingPrice above zero) need create_cart plus the UPI stage, which
    this app does not implement, so they are filtered out here rather than failing
    later at booking time.
    """
    for deal in _rows(slot, "deals"):
        if _get(deal, "isFree") is False:
            continue
        if (_get(deal, "bookingPrice", default=0) or 0) > 0:
            continue
        slot_id = _get(deal, "slotId") or _get(slot, "slotId")
        item_id = _get(deal, "itemId") or _get(slot, "itemId")
        if not slot_id or not item_id:
            continue
        return {
            "slotId": slot_id,
            "itemId": item_id,
            "reservationTime": _get(slot, "reservationTime", "time"),
            "displayTime": _get(slot, "displayTime", "time", default=""),
            "dateStr": _get(slot, "dateStr", default=""),
            "title": _get(deal, "title", default=""),
        }
    return None


def _pick_slot(slots: list[dict], booking_date: Optional[str], booking_time: Optional[str]) -> Optional[dict]:
    """Choose the first free deal at or after the requested time on the requested date.

    get_available_slots returns seven days in one response, so filter client-side
    rather than calling again for a different date.
    """
    candidates = [s for s in slots if not booking_date or _get(s, "dateStr", default=booking_date) == booking_date]
    candidates = candidates or slots
    wanted = booking_time or "00:00"

    def _minutes(slot: dict) -> int:
        raw = str(_get(slot, "displayTime", "time", default="")).strip()
        for fmt in ("%I:%M %p", "%H:%M"):
            try:
                parsed = datetime.strptime(raw.upper().replace(".", ""), fmt)
                return parsed.hour * 60 + parsed.minute
            except ValueError:
                continue
        return -1

    target = _minutes({"displayTime": wanted})
    at_or_after = [s for s in candidates if _minutes(s) >= target]
    for slot in (at_or_after or candidates):
        deal = _free_deal(slot)
        if deal is not None:
            return deal
    return None


# --- legs --------------------------------------------------------------------

async def _dineout_leg(sid: str, intent: ParsedIntent, step: int) -> Optional[dict]:
    location = await _saved_location(sid)
    results = await live_mcp.search_restaurants_dineout(
        sid, query=intent.search_term or "dinner", address_id=_get(location, "id", "addressId")
    )
    bookable = [r for r in _rows(results, "restaurants", "data") if _is_open(r)]
    if not bookable:
        return None

    top = bookable[0]
    restaurant_id = _get(top, "restaurantId", "id")
    # book_table wants the RESTAURANT's coordinates, not the user's location.
    lat = _get(top, "latitude", "lat")
    lng = _get(top, "longitude", "lng")

    booking_date = intent.booking_date or date.today().isoformat()
    slots_payload = await live_mcp.get_available_slots(sid, restaurant_id, booking_date, intent.party_size)
    deal = _pick_slot(_rows(slots_payload, "slots", "data"), booking_date, intent.booking_time)
    if deal is None:
        return None

    name = _get(top, "name", default="your pick")
    return {
        "step": step,
        "category": "dinner",
        "title": f"Dinner at {name}",
        "subtitle": f"{_get(top, 'locality', 'area', default='')} · table for {intent.party_size}",
        "time": deal["displayTime"],
        "details": {
            "restaurant": name,
            "address": _get(top, "address", default=""),
            "party size": f"{intent.party_size} people",
            "date": deal["dateStr"] or booking_date,
            "deal": deal["title"],
        },
        "status": "ready",
        "source": "dineout",
        "action": {
            "action_type": "book_table",
            "params": {
                "restaurantId": restaurant_id,
                "slotId": deal["slotId"],
                "itemId": deal["itemId"],
                "reservationTime": deal["reservationTime"],
                "latitude": lat,
                "longitude": lng,
                "guestCount": intent.party_size,
            },
            "display_summary": (
                f"Book a table for {intent.party_size} at {name}, "
                f"{deal['displayTime']} on {deal['dateStr'] or booking_date}"
            ),
        },
    }


async def _food_leg(sid: str, address_id: str, term: str, step: int) -> Optional[dict]:
    results = await live_mcp.search_restaurants(sid, address_id, term)
    open_now = [r for r in _rows(results, "restaurants", "data") if _is_open(r)]
    if not open_now:
        return None

    shop = open_now[0]
    shop_id = _get(shop, "restaurantId", "id")
    menu = await live_mcp.get_restaurant_menu(sid, shop_id)
    items = _rows(menu, "items", "menuItems")
    if not items:
        return None

    pick = items[0]
    price = _get(pick, "price", "finalPrice", default=0)
    shop_name = _get(shop, "name", default="")
    item_name = _get(pick, "name", default=term)
    return {
        "step": step,
        "category": "delivery",
        "title": f"{item_name} from {shop_name}",
        "subtitle": f"₹{price} · {_get(shop, 'deliveryTime', 'slaMinutes', default='~')} min",
        "details": {
            "restaurant": shop_name,
            "item": f"{item_name} (₹{price})",
            "delivery": f"{_get(shop, 'deliveryTime', 'slaMinutes', default='~')} minutes",
        },
        "status": "ready",
        "source": "food",
        # The cart is deliberately NOT built here. Mutating it before the user has
        # confirmed would be a silent state change; /confirm builds and places.
        "action": {
            "action_type": "place_food_order",
            "params": {
                "addressId": address_id,
                "restaurantId": shop_id,
                "items": [{"itemId": _get(pick, "itemId", "id"), "quantity": 1}],
            },
            "display_summary": f"Order {item_name} from {shop_name} — ₹{price}",
        },
    }


async def _instamart_leg(sid: str, address_id: str, terms: list[str], step: int) -> Optional[dict]:
    picks: list[dict] = []
    for term in terms[:3]:
        results = await live_mcp.search_products(sid, address_id, term)
        for product in _rows(results, "products", "data")[:1]:
            # Carts are keyed on spinId from variations[] — the SKU, not the parent product.
            variations = _rows(product, "variations", "variants")
            if not variations:
                continue
            variation = variations[0]
            picks.append(
                {
                    "name": _get(product, "name", default=term),
                    "spinId": _get(variation, "spinId", "id"),
                    "price": _get(variation, "price", "finalPrice", default=0) or 0,
                }
            )
    if not picks:
        return None

    total = sum(p["price"] for p in picks)
    return {
        "step": step,
        "category": "grocery",
        "title": "Grocery restock",
        "subtitle": f"{len(picks)} items · ₹{total}",
        "details": {
            "items": ", ".join(f"{p['name']} ₹{p['price']}" for p in picks),
            "total": f"₹{total}",
        },
        "status": "ready",
        "source": "instamart",
        "action": {
            "action_type": "checkout_instamart",
            "params": {
                "addressId": address_id,
                "items": [{"spinId": p["spinId"], "quantity": 1} for p in picks],
            },
            "display_summary": f"Check out {len(picks)} grocery items — ₹{total}",
        },
    }


# --- entry points ------------------------------------------------------------

async def plan_evening(sid: str, intent: ParsedIntent) -> AgentResponse:
    # Sessions open sequentially — the pool enforces the ordering, because parallel
    # multi-domain initialization is a named rate-limit trigger. Only the reads that
    # follow fan out concurrently.
    await client.ensure(sid, _ALL)
    address = await _home_address(sid)
    address_id = _get(address, "addressId", "id")

    legs = await asyncio.gather(
        _dineout_leg(sid, intent, 1),
        _food_leg(sid, address_id, intent.dessert_term or "dessert", 2),
        _instamart_leg(sid, address_id, intent.grocery_terms or ["coffee"], 3),
        return_exceptions=True,
    )

    items: list[dict] = []
    failures: list[str] = []
    for leg in legs:
        if isinstance(leg, SwiggyToolError):
            failures.append(leg.message)
        elif isinstance(leg, BaseException):
            log.warning("Plan leg failed: %s", leg)
            failures.append("One part of the plan could not be loaded.")
        elif leg is not None:
            leg["step"] = len(items) + 1
            items.append(leg)

    if not items:
        return AgentResponse(
            spoken_response=failures[0] if failures else "I couldn't find options for that. Try a different area or time?",
            ui_payload=UIPayload(type="cards", title="Nothing available", items=[]),
        )

    spoken = f"Planned {len(items)} step{'s' if len(items) != 1 else ''}. Confirm each one when you're ready."
    if failures:
        spoken += " Some parts weren't available."
    return AgentResponse(
        spoken_response=spoken,
        ui_payload=UIPayload(type="timeline", title="Your plan", items=items),
        requires_confirmation=False,
    )


async def single_service(sid: str, intent: ParsedIntent) -> AgentResponse:
    """Run one service end to end and return its leg as a one-item timeline."""
    if intent.intent == "dineout":
        await client.ensure(sid, ("dineout",))
        leg = await _dineout_leg(sid, intent, 1)
        title, empty = "Dine out", "No bookable tables matched that nearby."
    elif intent.intent == "food_order":
        await client.ensure(sid, ("food",))
        address = await _home_address(sid)
        leg = await _food_leg(sid, _get(address, "addressId", "id"), intent.search_term or "food", 1)
        title, empty = "Food delivery", "Nothing open near you for that right now."
    else:
        await client.ensure(sid, ("instamart",))
        address = await _home_address(sid)
        terms = intent.grocery_terms or [intent.search_term or "groceries"]
        leg = await _instamart_leg(sid, _get(address, "addressId", "id"), terms, 1)
        title, empty = "Grocery restock", "Nothing matched that at your address."

    if leg is None:
        return AgentResponse(
            spoken_response=empty,
            ui_payload=UIPayload(type="cards", title=title, items=[]),
        )
    return AgentResponse(
        spoken_response=f"{leg['title']}. Confirm when you're ready.",
        ui_payload=UIPayload(type="timeline", title=title, items=[leg]),
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
        await live_mcp.update_food_cart(sid, params["restaurantId"], params["items"])
        # Read the cart back before placing: the user may have edited it in the
        # Swiggy app between turns, and the cap applies to the real total.
        cart = await live_mcp.get_food_cart(sid)
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
        await live_mcp.update_cart(sid, params["items"])
        await live_mcp.get_cart(sid)
        result = await live_mcp.checkout(sid, params["addressId"])
        _reject_pending_payment(result)
        result.setdefault("confirmation_message", "Your grocery order is placed.")
        return result

    raise ValueError(f"Unknown action_type: {action_type}")


def _reject_pending_payment(result: dict) -> None:
    """PENDING_PAYMENT means the UPI leg is still open — never call that placed."""
    if str(_get(result, "status", default="")).upper() == "PENDING_PAYMENT":
        raise SwiggyToolError(
            "This order needs an online payment, which this app doesn't handle yet. "
            "Complete it in the Swiggy app."
        )
