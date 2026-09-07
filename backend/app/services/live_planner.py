"""Live plan assembly against the real Swiggy MCP servers.

Deliberately separate from the mock planner: the real journeys have prerequisite
stages the mock never had (address resolution for Food/Instamart, lat/lng resolution
for Dineout) and the tool arguments are genuinely different, so one shared function
body would only be a shared lie.

Response field names come from the published recipes. Where a payload could plausibly
use more than one spelling we read through `_get`, so a naming surprise on first
contact degrades to a missing field instead of a KeyError. Tighten these once a real
response has been captured.
"""
import asyncio
import logging
from datetime import date, datetime, timedelta
from typing import Any, Optional

from app.models.agent_response import AgentResponse, UIPayload
from app.services import live_mcp
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


def _next_weekday(name: str = "friday") -> str:
    weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    try:
        target = weekdays.index(name.lower())
    except ValueError:
        return date.today().isoformat()
    today = date.today()
    ahead = (target - today.weekday()) % 7 or 7
    return (today + timedelta(days=ahead)).isoformat()


async def _home_address(sid: str) -> dict:
    payload = await live_mcp.get_addresses(sid)
    rows = _rows(payload, "addresses", "data") or ([payload] if _get(payload, "addressId", "id") else [])
    if not rows:
        raise SwiggyToolError(
            "No saved delivery address on your Swiggy account. Add one in the Swiggy app, then try again."
        )
    return next((a for a in rows if str(_get(a, "label", default="")).lower() == "home"), rows[0])


async def _home_location(sid: str) -> dict:
    payload = await live_mcp.get_saved_locations(sid)
    rows = _rows(payload, "locations", "data")
    if not rows:
        raise SwiggyToolError("No saved location on your Swiggy account for Dineout search.")
    return rows[0]


def _is_bookable_free(restaurant: dict) -> bool:
    """Free-deal filter. Paid prebook deals need the UPI stage we do not implement yet."""
    availability = str(_get(restaurant, "availability", "availabilityStatus", default="")).upper()
    if availability and availability not in ("AVAILABLE", "OPEN"):
        return False
    is_free = _get(restaurant, "isFree")
    price = _get(restaurant, "bookingPrice")
    if is_free is False:
        return False
    return price in (None, 0, 0.0)


def _is_open(restaurant: dict) -> bool:
    status = str(_get(restaurant, "availabilityStatus", "availability", default="OPEN")).upper()
    return status in ("OPEN", "AVAILABLE")


async def plan_evening(sid: str, intent: dict) -> AgentResponse:
    cuisine = intent.get("cuisine", "italian")
    guests = int(intent.get("party_size", 2))
    booking_date = _next_weekday("friday")

    # Connect all three servers first, sequentially — the pool enforces the ordering.
    # Only after the sessions exist do the read queries fan out concurrently; the
    # rate-limit doc forbids parallel *initialization*, not parallel tool calls.
    await client.ensure(sid, _ALL)
    address, location = await asyncio.gather(_home_address(sid), _home_location(sid))
    address_id = _get(address, "addressId", "id")
    lat = _get(location, "lat", "latitude")
    lng = _get(location, "lng", "longitude")

    dine_task = live_mcp.search_restaurants_dineout(sid, lat=lat, lng=lng, query=cuisine)
    dessert_task = live_mcp.search_restaurants(sid, address_id, "dessert")
    coffee_task = live_mcp.search_products(sid, address_id, "coffee")
    dine_res, dessert_res, coffee_res = await asyncio.gather(dine_task, dessert_task, coffee_task)

    items: list[dict] = []

    # --- Dineout leg
    candidates = [r for r in _rows(dine_res, "restaurants", "data") if _is_bookable_free(r)]
    if candidates:
        top = candidates[0]
        restaurant_id = _get(top, "restaurantId", "id")
        slots_res = await live_mcp.get_available_slots(sid, restaurant_id, booking_date, guests)
        slots = _rows(slots_res, "slots", "data")
        slot = next(
            (s for s in slots if str(_get(s, "displayTime", "time", default="")) >= "20:00"),
            slots[0] if slots else None,
        )
        if slot is not None:
            items.append(
                {
                    "step": len(items) + 1,
                    "icon": "🍽️",
                    "category": "dinner",
                    "title": f"Dinner at {_get(top, 'name', default='your pick')}",
                    "subtitle": f"{_get(top, 'locality', 'area', default='')} · table for {guests}",
                    "time": _get(slot, "displayTime", "time", default=""),
                    "details": {
                        "restaurant": _get(top, "name", default=""),
                        "address": _get(top, "address", default=""),
                        "party_size": f"{guests} people",
                        "time_slot": _get(slot, "displayTime", "time", default=""),
                    },
                    "status": "ready",
                    "source": "dineout",
                    "powered_by": "Swiggy Dineout",
                    "action": {
                        "action_type": "book_table",
                        "params": {
                            "restaurantId": restaurant_id,
                            "slotId": _get(slot, "slotId", "id"),
                            "itemId": _get(slot, "itemId"),
                            "reservationTime": _get(slot, "reservationTime", "time"),
                            "latitude": lat,
                            "longitude": lng,
                            "guestCount": guests,
                        },
                        "display_summary": (
                            f"Book table for {guests} at {_get(top, 'name', default='restaurant')}, "
                            f"{_get(slot, 'displayTime', 'time', default='')} on {booking_date}"
                        ),
                    },
                }
            )

    # --- Food leg. The cart is deliberately NOT built here: mutating it before the
    # user has confirmed would be a silent mutation. /confirm builds and places.
    dessert_shops = [r for r in _rows(dessert_res, "restaurants", "data") if _is_open(r)]
    if dessert_shops:
        shop = dessert_shops[0]
        shop_id = _get(shop, "restaurantId", "id")
        menu = await live_mcp.get_restaurant_menu(sid, shop_id)
        menu_items = _rows(menu, "items", "menuItems")
        if menu_items:
            pick = menu_items[0]
            price = _get(pick, "price", "finalPrice", default=0)
            items.append(
                {
                    "step": len(items) + 1,
                    "icon": "🍰",
                    "category": "dessert",
                    "title": f"Dessert from {_get(shop, 'name', default='')}",
                    "subtitle": f"{_get(pick, 'name', default='')} · ₹{price}",
                    "details": {
                        "restaurant": _get(shop, "name", default=""),
                        "items": f"{_get(pick, 'name', default='')} (₹{price})",
                        "delivery_time": f"{_get(shop, 'deliveryTime', 'slaMinutes', default='~')} minutes",
                    },
                    "status": "ready",
                    "source": "food",
                    "powered_by": "Swiggy Food",
                    "action": {
                        "action_type": "place_food_order",
                        "params": {
                            "addressId": address_id,
                            "restaurantId": shop_id,
                            "items": [{"itemId": _get(pick, "itemId", "id"), "quantity": 1}],
                        },
                        "display_summary": (
                            f"Order {_get(pick, 'name', default='dessert')} from "
                            f"{_get(shop, 'name', default='')} — ₹{price}"
                        ),
                    },
                }
            )

    # --- Instamart leg. Cart entries are keyed on spinId from variations[].
    products = _rows(coffee_res, "products", "data")
    picks: list[dict] = []
    for product in products[:2]:
        variations = _rows(product, "variations", "variants")
        if not variations:
            continue
        variation = variations[0]
        picks.append(
            {
                "name": _get(product, "name", default=""),
                "spinId": _get(variation, "spinId", "id"),
                "price": _get(variation, "price", "finalPrice", default=0),
            }
        )
    if picks:
        total = sum(p["price"] or 0 for p in picks)
        items.append(
            {
                "step": len(items) + 1,
                "icon": "🛒",
                "category": "grocery",
                "title": "Morning Restock",
                "subtitle": f"{len(picks)} items · ₹{total}",
                "details": {
                    "items": ", ".join(f"{p['name']} ₹{p['price']}" for p in picks),
                    "total": f"₹{total}",
                },
                "status": "ready",
                "source": "instamart",
                "powered_by": "Swiggy Instamart",
                "action": {
                    "action_type": "checkout_instamart",
                    "params": {
                        "addressId": address_id,
                        "items": [{"spinId": p["spinId"], "quantity": 1} for p in picks],
                    },
                    "display_summary": f"Checkout {len(picks)} grocery items — ₹{total}",
                },
            }
        )

    if not items:
        return AgentResponse(
            spoken_response="I couldn't find options for all three parts of that. Want to try a different area or time?",
            ui_payload=UIPayload(type="cards", title="Nothing available", items=[]),
        )

    return AgentResponse(
        spoken_response=(
            f"Planned your evening across {len(items)} steps. Confirm each one when you're ready."
        ),
        ui_payload=UIPayload(type="timeline", title="Evening Plan", items=items),
        requires_confirmation=False,
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
        # Swiggy app between turns, and the ₹1000 cap is enforced on the real total.
        cart = await live_mcp.get_food_cart(sid)
        total = _get(cart, "total", "grandTotal", "billTotal", default=0) or 0
        if total > FOOD_CART_CAP_RUPEES:
            raise SwiggyToolError(
                f"Cart total ₹{total} exceeds the ₹{FOOD_CART_CAP_RUPEES} Swiggy Builders Club cap. "
                "Remove an item and try again."
            )
        result = await live_mcp.place_food_order(sid, params["addressId"])
        if str(_get(result, "status", default="")).upper() == "PENDING_PAYMENT":
            # UPI leg is not implemented; never report a pending order as placed.
            raise SwiggyToolError(
                "This order needs an online payment, which this app doesn't handle yet. "
                "Complete it in the Swiggy app."
            )
        result.setdefault("confirmation_message", "Your food order is placed.")
        return result

    if action_type == "checkout_instamart":
        await live_mcp.update_cart(sid, params["items"])
        cart = await live_mcp.get_cart(sid)
        log.info("Instamart cart before checkout: %s items", len(_rows(cart, "items")))
        result = await live_mcp.checkout(sid, params["addressId"])
        if str(_get(result, "status", default="")).upper() == "PENDING_PAYMENT":
            raise SwiggyToolError(
                "This order needs an online payment, which this app doesn't handle yet. "
                "Complete it in the Swiggy app."
            )
        result.setdefault("confirmation_message", "Your grocery order is placed.")
        return result

    raise ValueError(f"Unknown action_type: {action_type}")


async def _cards(title: str, spoken: str, rows: list[dict]) -> AgentResponse:
    return AgentResponse(
        spoken_response=spoken,
        ui_payload=UIPayload(type="cards", title=title, items=rows),
        requires_confirmation=False,
    )


async def food_search(sid: str, query: str) -> AgentResponse:
    await client.ensure(sid, ("food",))
    address = await _home_address(sid)
    payload = await live_mcp.search_restaurants(sid, _get(address, "addressId", "id"), query)
    top = [r for r in _rows(payload, "restaurants", "data") if _is_open(r)][:3]
    rows = [
        {
            "title": _get(r, "name", default=""),
            "subtitle": f"{_get(r, 'locality', 'area', default='')} · {_get(r, 'deliveryTime', 'slaMinutes', default='~')} min",
            "details": {"rating": str(_get(r, "rating", default=""))},
            "status": "ready",
            "source": "food",
            "powered_by": "Swiggy Food",
        }
        for r in top
    ]
    if not rows:
        return await _cards("Food Delivery", "Nothing open near you for that right now.", [])
    return await _cards("Food Delivery", f"Found {len(rows)} options. Top pick is {rows[0]['title']}.", rows)


async def dineout_search(sid: str, query: str) -> AgentResponse:
    await client.ensure(sid, ("dineout",))
    location = await _home_location(sid)
    payload = await live_mcp.search_restaurants_dineout(
        sid, lat=_get(location, "lat", "latitude"), lng=_get(location, "lng", "longitude"), query=query
    )
    top = [r for r in _rows(payload, "restaurants", "data") if _is_bookable_free(r)][:3]
    rows = [
        {
            "title": _get(r, "name", default=""),
            "subtitle": f"{_get(r, 'locality', 'area', default='')} · {_get(r, 'rating', default='')}★",
            "details": {"cuisines": ", ".join(_get(r, "cuisines", default=[]) or [])},
            "status": "ready",
            "source": "dineout",
            "powered_by": "Swiggy Dineout",
        }
        for r in top
    ]
    if not rows:
        return await _cards("Dine Out", "No free-reservation tables matched that nearby.", [])
    return await _cards("Dine Out", f"Found {len(rows)} restaurants. Top pick is {rows[0]['title']}.", rows)


async def instamart_search(sid: str, query: str) -> AgentResponse:
    await client.ensure(sid, ("instamart",))
    address = await _home_address(sid)
    payload = await live_mcp.search_products(sid, _get(address, "addressId", "id"), query)
    rows = []
    for product in _rows(payload, "products", "data")[:4]:
        variation = (_rows(product, "variations", "variants") or [{}])[0]
        rows.append(
            {
                "title": _get(product, "name", default=""),
                "subtitle": f"₹{_get(variation, 'price', 'finalPrice', default=0)} · {_get(variation, 'unit', 'quantity', default='')}",
                "details": {"brand": _get(product, "brand", default="")},
                "status": "ready",
                "source": "instamart",
                "powered_by": "Swiggy Instamart",
            }
        )
    if not rows:
        return await _cards("Grocery Restock", "Nothing matched that at your address.", [])
    return await _cards("Grocery Restock", f"Found {len(rows)} items for your restock.", rows)
