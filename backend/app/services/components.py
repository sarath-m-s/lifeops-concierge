"""Turn the model's render choices into components carrying real data.

The model names a cached tool result and the rows it wants shown. Everything the
user actually sees — names, prices, ids — is read out of that stored payload here.
The model contributes intent, never facts.

`digest` is the mirror image: a compact, id-free view of a tool result so the
model can reason about what it found without paying for the full payload or being
handed identifiers it might echo back incorrectly.
"""
import logging
import re
from typing import Any, Optional

from app.models.agent_response import AgentTurn, Component
from app.services.conversation import Conversation
from app.services.live_planner import _amount, _get, _rows

log = logging.getLogger(__name__)

# Near-misses a model actually produces (live-verified 2026-09-10: "menu" and
# "grocery_list" instead of "menu_list"/"product_list") — a plausible-sounding
# wrong name shouldn't cost the whole render, same reasoning as agent.py's
# _FINISH_ALIASES for tool-name slips.
_TYPE_ALIASES = {
    "menu": "menu_list", "menu_items": "menu_list",
    "grocery_list": "product_list", "groceries": "product_list", "products": "product_list",
    "restaurant": "restaurant_list", "restaurants": "restaurant_list",
    "coupon": "coupon_list", "coupons": "coupon_list",
    "slot": "slot_list", "slots": "slot_list",
    "address": "address_list", "addresses": "address_list",
    "order": "order_list", "orders": "order_list",
    "status": "order_status",
    "confirm": "confirm_action",
    "chip": "chips", "suggestions": "chips",
}

# Which tool result feeds which component, so a mismatched pair can be rejected.
_SOURCE_FOR = {
    "restaurant_list": ("search_food_restaurants", "search_tables"),
    "product_list": ("search_groceries", "list_usual_groceries"),
    "menu_list": ("get_menu", "search_menu"),
    "coupon_list": ("food_coupons", "grocery_coupons"),
    "slot_list": ("get_table_slots",),
    "address_list": ("list_addresses", "list_locations"),
    "order_list": ("my_food_orders", "my_grocery_orders"),
    "order_status": ("track_food", "track_groceries"),
}


# --- extraction --------------------------------------------------------------

def _restaurants(payload: Any) -> list[dict]:
    return _rows(payload or {}, "restaurants", "data")


_DINEOUT_LINE = re.compile(
    r"^\d+\.\s+(?P<name>.+?)\s+—\s+(?P<cuisines>[^|]+)\|\s*(?P<rating>[\d.]+)★\s*\|[^|]*\|"
    r"\s*(?P<area>[^(]*)\(ID:\s*(?P<id>[\w-]+)\)",
    re.MULTILINE,
)
_DINEOUT_COORDS = re.compile(r"latitude=(?P<lat>[-\d.]+),\s*longitude=(?P<lng>[-\d.]+)")


def _dineout_restaurants_from_message(payload: Any) -> list[dict]:
    """search_restaurants_dineout drops its `restaurants` array once it finds a
    match, replacing it with a prose `message` instead (live-verified
    2026-09-09, see docs/MCP_RESPONSE_SHAPES.md). Recover what we can from the
    text rather than rendering nothing on an actual hit.
    """
    message = _get(payload, "message", default="") if isinstance(payload, dict) else ""
    if not message:
        return []
    coords = _DINEOUT_COORDS.search(message)
    lat = float(coords["lat"]) if coords else None
    lng = float(coords["lng"]) if coords else None
    return [
        {
            "id": m["id"],
            "restaurantId": m["id"],
            "name": m["name"].strip(),
            "cuisines": [c.strip() for c in m["cuisines"].split(",") if c.strip()],
            "avgRating": float(m["rating"]),
            "area": m["area"].strip(),
            "latitude": lat,
            "longitude": lng,
        }
        for m in _DINEOUT_LINE.finditer(message)
    ]


def _products(payload: Any) -> list[dict]:
    return _rows(payload or {}, "products", "items", "data")


def _coupons(payload: Any) -> list[dict]:
    return _rows(payload or {}, "coupons", "availableCoupons", "data")


def _coupon_code(payload: Any, index: Optional[int]) -> Optional[str]:
    """Resolve a coupon by row index, never by a code the model typed itself."""
    if index is None:
        return None
    rows = _coupons(payload)
    if not rows or not (0 <= index < len(rows)):
        return None
    return _get(rows[index], "code", "couponCode") or None


def _slots(payload: Any) -> list[dict]:
    return _rows(payload or {}, "slots", "data")


def _addresses(payload: Any) -> list[dict]:
    return _rows(payload or {}, "addresses", "locations", "data")


def _orders(payload: Any) -> list[dict]:
    return _rows(payload or {}, "orders", "data")


def _menu_items(payload: Any) -> list[dict]:
    flat = _rows(payload or {}, "items", "menuItems", "data")
    if flat:
        return flat
    # get_restaurant_menu nests items under categories[] (search_menu doesn't) —
    # flatten so the model still sees one list, live-verified 2026-09-09, see
    # docs/MCP_RESPONSE_SHAPES.md.
    return [item for cat in _rows(payload or {}, "categories") for item in _rows(cat, "items")]


def _rows_for(tool: str, payload: Any) -> list[dict]:
    if tool in ("get_menu", "search_menu"):
        return _menu_items(payload)
    if tool == "search_food_restaurants":
        return _restaurants(payload)
    if tool == "search_tables":
        rows = _restaurants(payload)
        return rows if rows else _dineout_restaurants_from_message(payload)
    if tool in ("search_groceries", "list_usual_groceries"):
        return _products(payload)
    if tool in ("food_coupons", "grocery_coupons"):
        return _coupons(payload)
    if tool == "get_table_slots":
        return _slots(payload)
    if tool in ("list_addresses", "list_locations"):
        return _addresses(payload)
    if tool in ("my_food_orders", "my_grocery_orders"):
        return _orders(payload)
    return _rows(payload or {}, "items", "data")


def _first_variation(product: dict) -> dict:
    return (_rows(product, "variations", "variants") or [{}])[0]


# --- digests (what the model sees) -------------------------------------------

def digest(tool: str, payload: Any) -> Any:
    """Compact, identifier-free summary. Keeps prompts small and ids out of reach."""
    rows = _rows_for(tool, payload)

    if tool in ("search_food_restaurants", "search_tables"):
        if not rows:
            return {"count": 0, "message": _get(payload, "message", default="No results.")}
        return {
            "count": len(rows),
            "rows": [
                {
                    "i": i,
                    "name": _get(r, "name", default=""),
                    "area": _get(r, "areaName", "locality", default=""),
                    "rating": _get(r, "avgRating", "rating", default=""),
                    "cost": _get(r, "costForTwo", default=""),
                    "eta_min": _get(r, "deliveryTimeMinutes", default=""),
                    "cuisines": (_get(r, "cuisines", default=[]) or [])[:3],
                    "open": _get(r, "availabilityStatus", "availability", default=""),
                }
                for i, r in enumerate(rows[:6])
            ],
        }

    if tool in ("search_groceries", "list_usual_groceries"):
        out = []
        for i, p in enumerate(rows[:6]):
            v = _first_variation(p)
            out.append(
                {
                    "i": i,
                    "name": _get(p, "displayName", "name", default=""),
                    "unit": _get(v, "quantityDescription", default=""),
                    "price": _amount(_get(v, "price", "finalPrice")),
                    "in_stock": _get(v, "isInStockAndAvailable", default=_get(p, "inStock", default=True)),
                }
            )
        return {"count": len(rows), "rows": out}

    if tool == "get_table_slots":
        out = []
        for i, s in enumerate(rows[:40]):
            free = [d for d in _rows(s, "deals") if _get(d, "isFree") is not False and not (_get(d, "bookingPrice", default=0) or 0)]
            out.append(
                {
                    "i": i,
                    "date": _get(s, "dateStr", default=""),
                    "time": _get(s, "displayTime", "time", default=""),
                    "band": _get(s, "slotGroupName", default=""),
                    "free": bool(free),
                }
            )
        return {"count": len(rows), "rows": out}

    if tool in ("list_addresses", "list_locations"):
        return {
            "count": len(rows),
            "rows": [
                {"i": i, "label": _get(a, "addressTag", "addressCategory", default=""), "address": _get(a, "addressLine", default="")}
                for i, a in enumerate(rows)
            ],
        }

    if tool in ("food_coupons", "grocery_coupons"):
        return {
            "count": len(rows),
            "rows": [
                {
                    "i": i,
                    "code": _get(c, "code", "couponCode", default=""),
                    "description": _get(c, "description", "title", "message", default=""),
                    "needs_online_payment": bool(_get(c, "requiresOnlinePayment", default=False)),
                }
                for i, c in enumerate(rows[:6])
            ],
        }

    if tool in ("my_food_orders", "my_grocery_orders"):
        return {
            "count": len(rows),
            "rows": [
                {
                    "i": i,
                    "restaurant": _get(o, "restaurantName", "storeName", "name", default=""),
                    "status": _get(o, "status", "orderStatus", default=""),
                    "total": _amount(_get(o, "total", "grandTotal", "orderTotal")),
                }
                for i, o in enumerate(rows[:8])
            ],
        }

    if tool == "get_menu" or tool == "search_menu":
        items = _menu_items(payload)
        return {
            "count": len(items),
            "rows": [
                {
                    "i": i,
                    "name": _get(it, "name", "displayName", default=""),
                    "price": _amount(_get(it, "price", "finalPrice", "defaultPrice")),
                    "veg": _get(it, "isVeg", default=None),
                }
                for i, it in enumerate(items[:12])
            ],
        }

    if isinstance(payload, dict):
        return {k: v for k, v in payload.items() if k not in ("imageUrl", "widgets")}
    return payload


def summarise(tool: str, payload: Any) -> str:
    """One-line description of a tool result, for the log."""
    rows = _rows_for(tool, payload)
    if rows:
        first = _get(rows[0], "name", "displayName", "addressTag", "code", "displayTime", default="")
        return f"{len(rows)} row(s)" + (f', first="{str(first)[:40]}"' if first else "")
    message = _get(payload, "message")
    if isinstance(message, str) and message.strip():
        return f'empty — "{message[:80]}"'
    return "empty"


# --- components (what the app renders) ---------------------------------------

def _pick(rows: list[dict], indexes: Optional[list[int]]) -> list[dict]:
    if not indexes:
        return rows[:8]
    return [rows[i] for i in indexes if isinstance(i, int) and 0 <= i < len(rows)]


def _restaurant_props(rows: list[dict]) -> dict:
    return {
        "items": [
            {
                "name": _get(r, "name", default=""),
                "area": _get(r, "areaName", "locality", default=""),
                "rating": str(_get(r, "avgRating", "rating", default="") or ""),
                "cost": _get(r, "costForTwo", default=""),
                "eta": (f"{_get(r, 'deliveryTimeMinutes')} min" if _get(r, "deliveryTimeMinutes") else ""),
                "cuisines": ", ".join((_get(r, "cuisines", default=[]) or [])[:3]),
                "offer": _get(r, "offer", default=""),
                "image": _get(r, "imageUrl", default=""),
                "open": str(_get(r, "availabilityStatus", "availability", default="OPEN")).upper() in ("OPEN", "AVAILABLE"),
            }
            for r in rows
        ]
    }


def _product_props(rows: list[dict]) -> dict:
    items = []
    for p in rows:
        v = _first_variation(p)
        items.append(
            {
                "name": _get(p, "displayName", "name", default=""),
                "unit": _get(v, "quantityDescription", default=""),
                "price": _amount(_get(v, "price", "finalPrice")),
                "mrp": _amount({"mrp": _get(_get(v, "price", default={}) or {}, "mrp")}) if isinstance(_get(v, "price"), dict) else 0,
                "image": _get(v, "imageUrl", default=_get(p, "imageUrl", default="")),
                "in_stock": bool(_get(v, "isInStockAndAvailable", default=_get(p, "inStock", default=True))),
            }
        )
    return {"items": items}


def _menu_props(rows: list[dict]) -> dict:
    return {
        "items": [
            {
                "name": _get(it, "name", "displayName", default=""),
                "description": _get(it, "description", default=""),
                "price": _amount(_get(it, "price", "finalPrice", "defaultPrice")),
                "veg": _get(it, "isVeg", "veg"),
                "image": _get(it, "imageUrl", "image", default=""),
            }
            for it in rows
        ]
    }


def _coupon_props(rows: list[dict]) -> dict:
    return {
        "items": [
            {
                "code": _get(c, "code", "couponCode", default=""),
                "description": _get(c, "description", "title", "message", default=""),
                "online_only": bool(_get(c, "requiresOnlinePayment", default=False)),
            }
            for c in rows
        ]
    }


def _slot_props(rows: list[dict]) -> dict:
    out = []
    for s in rows:
        free = [d for d in _rows(s, "deals") if _get(d, "isFree") is not False and not (_get(d, "bookingPrice", default=0) or 0)]
        out.append(
            {
                "date": _get(s, "dateStr", default=""),
                "time": _get(s, "displayTime", "time", default=""),
                "band": _get(s, "slotGroupName", default=""),
                "free": bool(free),
                "deal": _get(free[0], "title", default="") if free else "",
            }
        )
    return {"items": out}


def _address_props(rows: list[dict]) -> dict:
    return {
        "items": [
            {
                "label": _get(a, "addressTag", "addressCategory", default="Address"),
                "address": _get(a, "addressLine", default=""),
                "category": _get(a, "addressCategory", default=""),
            }
            for a in rows
        ]
    }


def _order_props(rows: list[dict]) -> dict:
    return {
        "items": [
            {
                "name": _get(o, "restaurantName", "storeName", "name", default="Order"),
                "status": _get(o, "status", "orderStatus", default=""),
                "total": _amount(_get(o, "total", "grandTotal", "orderTotal")),
                "eta": _get(o, "eta", "estimatedDeliveryTime", default=""),
            }
            for o in rows
        ]
    }


def _confirm(convo: Conversation, spec: dict) -> Optional[Component]:
    """Build a confirmation card. Every identifier comes from a cached payload."""
    action = spec.get("action")
    source = spec.get("source") or ""
    indexes = spec.get("indexes") or [0]
    rows = _rows_for(source.rsplit("#", 1)[0], convo.recall(source)) if source else []
    chosen = _pick(rows, indexes)

    if action == "place_food_order":
        addresses = _addresses(convo.latest("list_addresses"))
        # `chosen` (computed above via _rows_for) already handles get_restaurant_menu's
        # categories[]-nested shape — recomputing it here via a flat _rows() call is
        # exactly the bug that made get_menu-sourced orders silently fail to materialise.
        chosen_items = chosen
        restaurants = _restaurants(convo.latest("search_food_restaurants"))
        if not (addresses and chosen_items and restaurants):
            return None
        total = sum(_amount(_get(i, "price", "finalPrice", "defaultPrice")) for i in chosen_items)
        coupon_code = _coupon_code(convo.latest("food_coupons"), spec.get("coupon_index"))
        return Component(
            type="confirm_action",
            props={
                "title": f"Order from {_get(restaurants[0], 'name', default='')}",
                "lines": [
                    {"label": _get(i, "name", "displayName", default=""), "value": f"₹{_amount(_get(i, 'price', 'finalPrice', 'defaultPrice'))}"}
                    for i in chosen_items
                ],
                "total": f"₹{total}",
                "note": "Placing this charges your Swiggy account.",
                "action": {
                    "action_type": "place_food_order",
                    "params": {
                        "addressId": _get(addresses[0], "id", "addressId"),
                        "restaurantId": _get(restaurants[0], "id", "restaurantId"),
                        "items": [{"itemId": _get(i, "id", "itemId"), "quantity": 1} for i in chosen_items],
                        **({"couponCode": coupon_code} if coupon_code else {}),
                    },
                    "display_summary": f"Order {len(chosen_items)} item(s) from {_get(restaurants[0], 'name', default='')} — ₹{total}",
                },
            },
        )

    if action == "checkout_instamart":
        addresses = _addresses(convo.latest("list_addresses"))
        if not (addresses and chosen):
            return None
        picks = [(p, _first_variation(p)) for p in chosen]
        total = sum(_amount(_get(v, "price", "finalPrice")) for _, v in picks)
        coupon_code = _coupon_code(convo.latest("grocery_coupons"), spec.get("coupon_index"))
        return Component(
            type="confirm_action",
            props={
                "title": "Grocery order",
                "lines": [
                    {"label": _get(p, "displayName", "name", default=""), "value": f"₹{_amount(_get(v, 'price', 'finalPrice'))}"}
                    for p, v in picks
                ],
                "total": f"₹{total}",
                "note": "Placing this charges your Swiggy account.",
                "action": {
                    "action_type": "checkout_instamart",
                    "params": {
                        "addressId": _get(addresses[0], "id", "addressId"),
                        "items": [{"spinId": _get(v, "spinId", "id"), "quantity": 1} for _, v in picks],
                        **({"couponCode": coupon_code} if coupon_code else {}),
                    },
                    "display_summary": f"Check out {len(picks)} grocery item(s) — ₹{total}",
                },
            },
        )

    if action == "delete_address":
        if not chosen:
            return None
        addr = chosen[0]
        address_id = _get(addr, "id", "addressId")
        if not address_id:
            return None
        label = _get(addr, "addressTag", "addressCategory", default="that address")
        return Component(
            type="confirm_action",
            props={
                "title": f"Delete {label}?",
                "lines": [{"label": "Address", "value": _get(addr, "addressLine", default="")}],
                "total": "",
                "note": "This permanently removes the address from your Swiggy account.",
                "action": {
                    "action_type": "delete_address",
                    "params": {"addressId": address_id},
                    "display_summary": f"Delete saved address: {label}",
                },
            },
        )

    if action == "book_table":
        slots = _slots(convo.latest("get_table_slots"))
        chosen_slots = _pick(slots, indexes)
        restaurants = _restaurants(convo.latest("search_tables"))
        if not (chosen_slots and restaurants):
            return None
        slot = chosen_slots[0]
        deals = [d for d in _rows(slot, "deals") if _get(d, "isFree") is not False and not (_get(d, "bookingPrice", default=0) or 0)]
        if not deals:
            return None
        deal, top = deals[0], restaurants[0]
        name = _get(top, "name", default="")
        when = f"{_get(slot, 'displayTime', default='')} on {_get(slot, 'dateStr', default='')}"
        return Component(
            type="confirm_action",
            props={
                "title": f"Table at {name}",
                "lines": [
                    {"label": "When", "value": when},
                    {"label": "Deal", "value": _get(deal, "title", default="Free reservation")},
                ],
                "total": "Free",
                "note": "This books a real table on your Swiggy account.",
                "action": {
                    "action_type": "book_table",
                    "params": {
                        "restaurantId": _get(top, "id", "restaurantId"),
                        "slotId": _get(deal, "slotId") or _get(slot, "slotId"),
                        "itemId": _get(deal, "itemId") or _get(slot, "itemId"),
                        "reservationTime": _get(slot, "reservationTime", "time"),
                        "latitude": _get(top, "latitude", "lat"),
                        "longitude": _get(top, "longitude", "lng"),
                        "guestCount": 2,
                    },
                    "display_summary": f"Book a table at {name}, {when}",
                },
            },
        )
    return None


_PROPS = {
    "restaurant_list": _restaurant_props,
    "product_list": _product_props,
    "menu_list": _menu_props,
    "coupon_list": _coupon_props,
    "slot_list": _slot_props,
    "address_list": _address_props,
    "order_list": _order_props,
    "order_status": _order_props,
}


# Which component naturally displays each tool's result, for the fallback below.
_NATURAL = {
    "search_food_restaurants": "restaurant_list",
    "search_tables": "restaurant_list",
    "search_groceries": "product_list",
    "get_menu": "menu_list",
    "search_menu": "menu_list",
    "list_usual_groceries": "product_list",
    "food_coupons": "coupon_list",
    "grocery_coupons": "coupon_list",
    "get_table_slots": "slot_list",
    "list_addresses": "address_list",
    "list_locations": "address_list",
    "my_food_orders": "order_list",
    "my_grocery_orders": "order_list",
}


def auto_components(convo: Conversation, handles: list[str]) -> list[Component]:
    """Render the freshest result when the model answered in prose.

    The model regularly describes what it found without asking for a component,
    which left the user reading "here's a place that serves biryani" with no card
    to look at. If a turn produced something renderable, show it rather than
    discarding the work the tool call already paid for.
    """
    for handle in reversed(handles):
        tool = handle.rsplit("#", 1)[0]
        kind = _NATURAL.get(tool)
        if kind is None:
            continue
        payload = convo.recall(handle)
        rows = _pick(_rows_for(tool, payload), None)
        if not rows:
            continue
        builder = _PROPS.get(kind)
        if builder is None:
            continue
        return [Component(type=kind, props=builder(rows))]
    return []


def build_components(convo: Conversation, components: list[dict]) -> list[Component]:
    """Resolve the model's render choices against cached tool results.

    Shared by the text-turn path (`build`, below) and the voice agent's
    `show_components` tool — both hand it the same `components` array shape.
    """
    out: list[Component] = []

    for spec in components or []:
        if not isinstance(spec, dict):
            continue
        kind = _TYPE_ALIASES.get(spec.get("type"), spec.get("type"))

        if kind == "chips":
            options = [str(o) for o in (spec.get("options") or []) if str(o).strip()][:4]
            if options:
                out.append(Component(type="chips", props={"options": options}))
            continue

        if kind == "confirm_action":
            card = _confirm(convo, spec)
            if card is not None:
                out.append(card)
            else:
                log.warning("confirm_action could not be materialised: %s", spec)
            continue

        builder = _PROPS.get(kind)
        if builder is None:
            continue
        source = spec.get("source") or ""
        tool = source.rsplit("#", 1)[0]
        expected = _SOURCE_FOR.get(kind, ())
        payload = convo.recall(source)
        if payload is None and expected:
            # The model named a stale or wrong handle; fall back to the newest
            # result of a tool that legitimately feeds this component.
            for candidate in expected:
                payload = convo.latest(candidate)
                if payload is not None:
                    tool = candidate
                    break
        if payload is None:
            continue
        rows = _pick(_rows_for(tool, payload), spec.get("indexes"))
        if not rows:
            continue
        out.append(Component(type=kind, props=builder(rows)))

    return out


def build(convo: Conversation, args: dict) -> AgentTurn:
    say = str(args.get("say") or "").strip() or "Here you go."
    out = build_components(convo, args.get("components") or [])
    return AgentTurn(say=say, components=out)
