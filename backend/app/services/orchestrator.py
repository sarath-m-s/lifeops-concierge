"""Intent parsing and plan generation.

Mock mode (APP_ENV != production) answers from app.services.mock_mcp. Live mode routes
to app.services.live_planner, which talks to the real Swiggy MCP servers. The two paths
are kept separate on purpose — the real journeys have prerequisite stages (address and
lat/lng resolution) and different tool arguments than the mock ever had.
"""
from app.config import settings
from app.models.agent_response import AgentResponse, UIPayload, PendingAction
from app.services import live_planner
from app.services.mock_mcp import dineout, food, instamart


def parse_intent(user_message: str) -> dict:
    msg = user_message.lower()

    plan_evening = (
        ("evening" in msg or "dinner" in msg)
        and "dessert" in msg
        and any(w in msg for w in ["coffee", "restock", "grocery", "groceries", "instamart"])
    )
    if plan_evening:
        return {
            "intent": "plan_evening",
            "cuisine": "italian",
            "time": "8 PM",
            "party_size": 2,
            "extras": ["dessert", "coffee"],
        }

    if any(w in msg for w in ["order food", "delivery", "hungry", "food delivery"]):
        return {"intent": "food_order", "query": msg}

    if any(w in msg for w in ["book", "table", "reservation", "dine", "restaurant"]):
        return {"intent": "dineout", "query": msg}

    if any(w in msg for w in ["grocery", "restock", "instamart", "buy", "milk", "bread"]):
        return {"intent": "instamart", "query": msg}

    return {"intent": "general", "message": user_message}


async def generate_plan(intent: dict, session_id: str) -> AgentResponse:
    kind = intent["intent"]
    if kind == "general":
        return _general_response(intent)

    if settings.is_mock:
        if kind == "plan_evening":
            return _plan_evening(intent)
        if kind == "food_order":
            return _food_search(intent)
        if kind == "dineout":
            return _dineout_search(intent)
        return _instamart_search(intent)

    query = intent.get("query", "")
    if kind == "plan_evening":
        return await live_planner.plan_evening(session_id, intent)
    if kind == "food_order":
        return await live_planner.food_search(session_id, query)
    if kind == "dineout":
        return await live_planner.dineout_search(session_id, query)
    return await live_planner.instamart_search(session_id, query)


def _plan_evening(intent: dict) -> AgentResponse:
    # Query all three MCP services
    restaurants = dineout.search_restaurants_dineout(cuisine="Italian", party_size=2, date="Friday")["restaurants"]
    top_restaurant = restaurants[0]
    slots = dineout.get_available_slots(top_restaurant["restaurant_id"], date="Friday", party_size=2)["slots"]
    best_slot = next((s for s in slots if s["time"] >= "20:00"), slots[0])

    dessert_restaurants = food.search_restaurants(query="dessert")["restaurants"]
    top_dessert = dessert_restaurants[0]
    dessert_items = food.search_menu(top_dessert["restaurant_id"], query="dessert")["items"]

    coffee_products = instamart.search_products(query="coffee")["products"]
    breakfast_products = instamart.search_products(query="breakfast")["products"]
    grocery_items = coffee_products[:2] + breakfast_products[:2]

    timeline_items = [
        {
            "step": 1,
            "icon": "🍽️",
            "category": "dinner",
            "title": f"Dinner at {top_restaurant['name']}",
            "subtitle": f"{top_restaurant['locality']} · ₹{top_restaurant['price_for_two']} for two · {top_restaurant['rating']}★",
            "time": best_slot["time"],
            "details": {
                "restaurant": top_restaurant["name"],
                "address": top_restaurant["address"],
                "party_size": "2 people",
                "time_slot": best_slot["time"],
                "offer": top_restaurant["offers"][0] if top_restaurant["offers"] else "",
                "amenities": ", ".join(top_restaurant["amenities"][:2]),
            },
            "status": "ready",
            "source": "dineout",
            "powered_by": "Swiggy Dineout",
            "action": {
                "action_type": "book_table",
                "params": {
                    "restaurant_id": top_restaurant["restaurant_id"],
                    "slot_id": best_slot["slot_id"],
                    "party_size": 2,
                },
                "display_summary": f"Book table for 2 at {top_restaurant['name']}, {best_slot['time']} Friday",
            },
        },
        {
            "step": 2,
            "icon": "🍰",
            "category": "dessert",
            "title": f"Dessert from {top_dessert['name']}",
            "subtitle": f"Delivery ~10:30 PM · {top_dessert['delivery_time_min']} min",
            "details": {
                "restaurant": top_dessert["name"],
                "items": f"{dessert_items[0]['name']} (₹{dessert_items[0]['price']}), {dessert_items[1]['name']} (₹{dessert_items[1]['price']})" if len(dessert_items) > 1 else dessert_items[0]["name"],
                "delivery_time": f"{top_dessert['delivery_time_min']} minutes",
                "offer": top_dessert["offers"][0] if top_dessert["offers"] else "",
            },
            "status": "ready",
            "source": "food",
            "powered_by": "Swiggy Food",
            "action": {
                "action_type": "place_food_order",
                "params": {
                    "restaurant_id": top_dessert["restaurant_id"],
                    "items": [{"item_id": dessert_items[0]["item_id"], "quantity": 1}],
                    "cart_id": "cart_food_mock_001",
                    "address_id": "addr_mock_001",
                },
                "display_summary": f"Order {dessert_items[0]['name']} from {top_dessert['name']} — ₹{dessert_items[0]['price']}",
            },
        },
        {
            "step": 3,
            "icon": "🛒",
            "category": "grocery",
            "title": "Morning Restock",
            "subtitle": f"Coffee + Breakfast · {len(grocery_items)} items · Delivery tomorrow 6–9 AM",
            "details": {
                "items": ", ".join(f"{p['name']} ₹{p['price']}" for p in grocery_items),
                "total": f"₹{sum(p['price'] for p in grocery_items)}",
                "delivery_slot": "Tomorrow 6–9 AM",
            },
            "status": "ready",
            "source": "instamart",
            "powered_by": "Swiggy Instamart",
            "action": {
                "action_type": "checkout_instamart",
                "params": {
                    "cart_id": "cart_instamart_mock_001",
                    "items": [{"product_id": p["product_id"], "quantity": 1} for p in grocery_items],
                    "address_id": "addr_mock_001",
                },
                "display_summary": f"Checkout {len(grocery_items)} grocery items — ₹{sum(p['price'] for p in grocery_items)}",
            },
        },
    ]

    return AgentResponse(
        spoken_response=(
            f"I've planned your Friday evening! Dinner at {top_restaurant['name']} at {best_slot['time']}, "
            f"desserts from {top_dessert['name']}, and a morning coffee restock. Confirm each step when ready."
        ),
        ui_payload=UIPayload(
            type="timeline",
            title="Friday Evening Plan",
            items=timeline_items,
        ),
        requires_confirmation=False,
        pending_action=None,
    )


def _food_search(intent: dict) -> AgentResponse:
    restaurants = food.search_restaurants(query=intent.get("query", "food"))["restaurants"]
    top = restaurants[:3]
    items = [
        {
            "title": r["name"],
            "subtitle": f"{r['locality']} · {r['delivery_time_min']} min · ₹{r['price_for_two']} for two",
            "details": {"rating": f"{r['rating']}★", "offer": r["offers"][0] if r["offers"] else ""},
            "status": "ready",
            "source": "food",
            "powered_by": "Swiggy Food",
        }
        for r in top
    ]
    return AgentResponse(
        spoken_response=f"Found {len(top)} options. Top pick is {top[0]['name']} delivering in {top[0]['delivery_time_min']} minutes.",
        ui_payload=UIPayload(type="cards", title="Food Delivery", items=items),
        requires_confirmation=False,
    )


def _dineout_search(intent: dict) -> AgentResponse:
    restaurants = dineout.search_restaurants_dineout()["restaurants"]
    top = restaurants[:3]
    items = [
        {
            "title": r["name"],
            "subtitle": f"{r['locality']} · ₹{r['price_for_two']} for two · {r['rating']}★",
            "details": {"offer": r["offers"][0] if r["offers"] else "", "distance": f"{r['distance_km']} km"},
            "status": "ready",
            "source": "dineout",
            "powered_by": "Swiggy Dineout",
        }
        for r in top
    ]
    return AgentResponse(
        spoken_response=f"Found {len(top)} restaurants. Top pick is {top[0]['name']} in {top[0]['locality']} at ₹{top[0]['price_for_two']} for two.",
        ui_payload=UIPayload(type="cards", title="Dine Out", items=items),
        requires_confirmation=False,
    )


def _instamart_search(intent: dict) -> AgentResponse:
    results = instamart.search_products(query=intent.get("query", "grocery"))
    products = results["products"][:4]
    items = [
        {
            "title": p["name"],
            "subtitle": f"₹{p['price']} · {p['unit']} · {p['brand']}",
            "details": {"category": p["category"], "in_stock": "Yes" if p["in_stock"] else "No"},
            "status": "ready",
            "source": "instamart",
            "powered_by": "Swiggy Instamart",
        }
        for p in products
    ]
    return AgentResponse(
        spoken_response=f"Found {len(products)} items. Showing top picks for your restock.",
        ui_payload=UIPayload(type="cards", title="Grocery Restock", items=items),
        requires_confirmation=False,
    )


def _general_response(intent: dict) -> AgentResponse:
    return AgentResponse(
        spoken_response="I can help you plan dinner, order food, book a restaurant, or restock groceries. What would you like to do?",
        ui_payload=UIPayload(
            type="cards",
            title="What can I help with?",
            items=[
                {"title": "Plan My Evening", "subtitle": "Dinner + dessert + grocery in one go", "status": "ready", "source": "dineout", "details": {}},
                {"title": "Order Food", "subtitle": "Delivery to your door", "status": "ready", "source": "food", "details": {}},
                {"title": "Book a Table", "subtitle": "Reserve a restaurant", "status": "ready", "source": "dineout", "details": {}},
                {"title": "Restock Groceries", "subtitle": "Instamart delivery", "status": "ready", "source": "instamart", "details": {}},
            ],
        ),
        requires_confirmation=False,
    )


async def execute_confirmed_action(action_type: str, params: dict, session_id: str) -> dict:
    """Execute a user-confirmed mutating action."""
    if not settings.is_mock:
        return await live_planner.execute(session_id, action_type, params)
    return _execute_mock(action_type, params)


def _execute_mock(action_type: str, params: dict) -> dict:
    if action_type == "book_table":
        return dineout.book_table(
            restaurant_id=params.get("restaurant_id", "din_toscano_indnr_001"),
            slot_id=params.get("slot_id", "slot_mock"),
            party_size=params.get("party_size", 2),
        )
    if action_type == "place_food_order":
        food.update_food_cart(params.get("items", []))
        return food.place_food_order(
            cart_id=params.get("cart_id", "cart_food_mock_001"),
            address_id=params.get("address_id", "addr_mock_001"),
        )
    if action_type == "checkout_instamart":
        instamart.update_cart(params.get("items", []))
        return instamart.checkout(
            cart_id=params.get("cart_id", "cart_instamart_mock_001"),
            address_id=params.get("address_id", "addr_mock_001"),
        )
    raise ValueError(f"Unknown action_type: {action_type}")
