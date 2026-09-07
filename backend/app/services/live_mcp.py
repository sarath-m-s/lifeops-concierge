"""Thin wrappers over the real Swiggy MCP tools.

This file is the tool contract in one place: exact tool names, exact argument
spelling. The API is camelCase throughout (`addressId`, `restaurantId`, `spinId`,
`guestCount`) — every mismatch we shipped before lived in an ad-hoc dict at a call
site, so all of them are funnelled through here now.
"""
from typing import Any, Optional

from app.services.swiggy_mcp import client

# Swiggy caps Builders Club food carts at ₹1000. Checked before place_food_order.
FOOD_CART_CAP_RUPEES = 1000


def _clean(args: dict) -> dict:
    return {k: v for k, v in args.items() if v is not None}


# --- Food (POST /food) -------------------------------------------------------

async def get_addresses(sid: str) -> dict:
    return await client.call(sid, "food", "get_addresses", {})


async def search_restaurants(sid: str, address_id: str, query: str) -> dict:
    return await client.call(sid, "food", "search_restaurants", {"addressId": address_id, "query": query})


async def get_restaurant_menu(sid: str, restaurant_id: str) -> dict:
    return await client.call(sid, "food", "get_restaurant_menu", {"restaurantId": restaurant_id})


async def update_food_cart(sid: str, restaurant_id: str, items: list[dict]) -> dict:
    # items: [{"itemId": ..., "quantity": n}]
    return await client.call(
        sid, "food", "update_food_cart", {"restaurantId": restaurant_id, "items": items}
    )


async def get_food_cart(sid: str) -> dict:
    return await client.call(sid, "food", "get_food_cart", {})


async def get_food_orders(sid: str) -> dict:
    return await client.call(sid, "food", "get_food_orders", {})


async def track_food_order(sid: str, order_id: str) -> dict:
    return await client.call(sid, "food", "track_food_order", {"orderId": order_id})


async def place_food_order(sid: str, address_id: str, payment_method: Optional[str] = None) -> dict:
    """Place the order. Non-idempotent: verifies against get_food_orders on failure.

    paymentMethod is omitted unless given — the tool reference places COD orders with
    addressId alone, and the recipe only passes a method explicitly when the user has
    picked one from get_payment_options.
    """

    async def verify() -> Optional[dict]:
        orders = await get_food_orders(sid)
        found = (orders.get("orders") or [])[:1]
        return found[0] if found else None

    return await client.place_with_verification(
        sid,
        "food",
        "place_food_order",
        _clean({"addressId": address_id, "paymentMethod": payment_method}),
        verify,
    )


# --- Instamart (POST /im) ----------------------------------------------------

async def search_products(sid: str, address_id: str, query: str) -> dict:
    return await client.call(sid, "instamart", "search_products", {"addressId": address_id, "query": query})


async def update_cart(sid: str, items: list[dict]) -> dict:
    # items: [{"spinId": ..., "quantity": n}] — spinId is the SKU-level id from
    # product.variations[], NOT the parent product id.
    return await client.call(sid, "instamart", "update_cart", {"items": items})


async def get_cart(sid: str) -> dict:
    return await client.call(sid, "instamart", "get_cart", {})


async def get_orders(sid: str) -> dict:
    return await client.call(sid, "instamart", "get_orders", {})


async def checkout(sid: str, address_id: str, payment_method: Optional[str] = None) -> dict:
    """Place the grocery order. Non-idempotent: verifies against get_orders on failure."""

    async def verify() -> Optional[dict]:
        orders = await get_orders(sid)
        found = (orders.get("orders") or [])[:1]
        return found[0] if found else None

    return await client.place_with_verification(
        sid,
        "instamart",
        "checkout",
        _clean({"addressId": address_id, "paymentMethod": payment_method}),
        verify,
    )


# --- Dineout (POST /dineout) -------------------------------------------------
# Location is REQUIRED on search and is one of two things: the `id` of a saved
# location passed as `addressId`, or an explicit lat/lng for a named area.
#
# The book-a-table recipe claims get_saved_locations returns lat/lng. It does not
# — the tool reference (generated from the live schema) says it returns index, id
# and addressLine, and to pass that id as addressId. The reference wins. Reading
# lat/lng off that payload yields None and the search fails before booking is ever
# reached, which is exactly how the Dineout leg broke.

async def get_saved_locations(sid: str) -> dict:
    return await client.call(sid, "dineout", "get_saved_locations", {})


async def search_restaurants_dineout(
    sid: str,
    query: str,
    address_id: Optional[str] = None,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
) -> dict:
    """Search bookable restaurants. Pass either address_id or lat/lng, not both.

    `query` must be the single thing being looked for — a cuisine, area, chain or
    vibe — never the user's whole sentence.
    """
    if address_id is None and (lat is None or lng is None):
        raise ValueError("search_restaurants_dineout needs address_id or lat/lng")
    return await client.call(
        sid,
        "dineout",
        "search_restaurants_dineout",
        _clean({"query": query, "addressId": address_id, "lat": lat, "lng": lng}),
    )


async def get_restaurant_details(sid: str, restaurant_id: str) -> dict:
    return await client.call(sid, "dineout", "get_restaurant_details", {"restaurantId": restaurant_id})


async def get_available_slots(sid: str, restaurant_id: str, date: str, guest_count: int) -> dict:
    return await client.call(
        sid,
        "dineout",
        "get_available_slots",
        {"restaurantId": restaurant_id, "date": date, "guestCount": guest_count},
    )


async def get_booking_status(sid: str, booking_id: Optional[str] = None, **extra: Any) -> dict:
    return await client.call(sid, "dineout", "get_booking_status", _clean({"bookingId": booking_id, **extra}))


async def book_table(
    sid: str,
    restaurant_id: str,
    slot_id: str,
    item_id: str,
    reservation_time: str,
    latitude: float,
    longitude: float,
    guest_count: int,
) -> dict:
    """Book a FREE reservation. Non-idempotent: verifies before any retry.

    slot_id and item_id both come from `slot.deals[]`, not from the slot itself;
    reservation_time is the slot's epoch timestamp. latitude/longitude are the
    RESTAURANT's coordinates from the search or details response — not the user's
    location. See live_planner._free_deal for the extraction.

    A free deal (isFree=true) books in one step. Paid prebook deals need create_cart
    with cartType="DEAL_TICKET_PURCHASE" plus the UPI payment stage, which this app
    does not offer yet — the planner filters to free deals upstream.
    """

    async def verify() -> Optional[dict]:
        status = await get_booking_status(sid, restaurantId=restaurant_id, slotId=slot_id)
        return status if status.get("bookingId") or status.get("status") else None

    return await client.place_with_verification(
        sid,
        "dineout",
        "book_table",
        {
            "restaurantId": restaurant_id,
            "slotId": slot_id,
            "itemId": item_id,
            "reservationTime": reservation_time,
            "latitude": latitude,
            "longitude": longitude,
            "guestCount": guest_count,
        },
        verify,
    )


# --- Additional read-only tools exposed to the agent -------------------------
# Everything below is safe for the model to call directly: none of it mutates
# server state or spends money. Mutating tools stay out of the agent's reach and
# are reachable only through the confirmation gate.

async def get_restaurant_details(sid: str, restaurant_id: str) -> dict:
    return await client.call(sid, "dineout", "get_restaurant_details", {"restaurantId": restaurant_id})


async def search_menu(sid: str, restaurant_id: str, query: str) -> dict:
    return await client.call(sid, "food", "search_menu", {"restaurantId": restaurant_id, "query": query})


async def fetch_food_coupons(sid: str) -> dict:
    return await client.call(sid, "food", "fetch_food_coupons", {})


async def list_grocery_coupons(sid: str) -> dict:
    return await client.call(sid, "instamart", "list_coupons", {})


async def your_go_to_items(sid: str, address_id: str) -> dict:
    """Frequently-ordered SKUs. One call replaces several searches for a reorder."""
    return await client.call(sid, "instamart", "your_go_to_items", {"addressId": address_id})


async def track_food_order(sid: str, order_id: str) -> dict:
    return await client.call(sid, "food", "track_food_order", {"orderId": order_id})


async def track_grocery_order(sid: str, order_id: str) -> dict:
    return await client.call(sid, "instamart", "track_order", {"orderId": order_id})


async def get_food_delivery_status(sid: str, order_id: str) -> dict:
    return await client.call(sid, "food", "get_food_delivery_status", {"orderId": order_id})


async def get_food_order_details(sid: str, order_id: str) -> dict:
    return await client.call(sid, "food", "get_food_order_details", {"orderId": order_id})
