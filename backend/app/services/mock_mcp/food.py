"""Mock Swiggy Food MCP — realistic Bangalore dessert delivery data."""
import uuid
from typing import List

_RESTAURANTS = [
    {
        "restaurant_id": "food_theobroma_indnr_001",
        "name": "Theobroma",
        "cuisine": ["Desserts", "Bakery"],
        "rating": 4.6,
        "delivery_time_min": 35,
        "price_for_two": 600,
        "locality": "Indiranagar",
        "offers": ["Buy 2 get 1 free on pastries after 9 PM"],
    },
    {
        "restaurant_id": "food_aubree_koramangala_002",
        "name": "Aubree",
        "cuisine": ["Desserts", "Patisserie"],
        "rating": 4.4,
        "delivery_time_min": 40,
        "price_for_two": 500,
        "locality": "Koramangala",
        "offers": ["20% off on orders above ₹499"],
    },
    {
        "restaurant_id": "food_cornerhouse_mgroad_003",
        "name": "Corner House",
        "cuisine": ["Ice Cream", "Desserts"],
        "rating": 4.2,
        "delivery_time_min": 30,
        "price_for_two": 350,
        "locality": "MG Road",
        "offers": ["Free delivery above ₹300"],
    },
]

_MENUS = {
    "food_theobroma_indnr_001": [
        {"item_id": "itm_theo_choc_001", "name": "Chocolate Truffle Cake", "price": 450, "description": "Rich dark chocolate layers with truffle cream", "category": "Cakes"},
        {"item_id": "itm_theo_rv_002", "name": "Red Velvet Pastry", "price": 180, "description": "Classic red velvet with cream cheese frosting", "category": "Pastries"},
        {"item_id": "itm_theo_brownie_003", "name": "Walnut Brownie", "price": 120, "description": "Dense fudgy brownie with walnuts", "category": "Brownies"},
    ],
    "food_aubree_koramangala_002": [
        {"item_id": "itm_aub_tira_001", "name": "Tiramisu", "price": 350, "description": "Classic Italian tiramisu with mascarpone and espresso", "category": "Italian Desserts"},
        {"item_id": "itm_aub_cheese_002", "name": "New York Cheesecake", "price": 280, "description": "Creamy baked cheesecake on graham cracker crust", "category": "Cheesecake"},
        {"item_id": "itm_aub_eclair_003", "name": "Chocolate Éclair", "price": 160, "description": "Choux pastry filled with custard, topped with chocolate", "category": "Pastries"},
    ],
    "food_cornerhouse_mgroad_003": [
        {"item_id": "itm_ch_dbc_001", "name": "Death by Chocolate", "price": 220, "description": "Signature chocolate ice cream sundae with fudge and brownies", "category": "Sundaes"},
        {"item_id": "itm_ch_hcf_002", "name": "Hot Chocolate Fudge", "price": 190, "description": "Vanilla ice cream with warm chocolate fudge sauce", "category": "Sundaes"},
        {"item_id": "itm_ch_mango_003", "name": "Mango Mania", "price": 160, "description": "Mango ice cream with fresh mango pieces", "category": "Sundaes"},
    ],
}

_cart: dict = {"cart_id": "cart_food_mock_001", "items": [], "total": 0}


def search_restaurants(location: str = "Bengaluru", query: str = "dessert") -> dict:
    return {
        "restaurants": _RESTAURANTS,
        "total": len(_RESTAURANTS),
        "query": query,
        "powered_by": "Swiggy Food",
    }


def search_menu(restaurant_id: str, query: str = "dessert") -> dict:
    items = _MENUS.get(restaurant_id, _MENUS["food_theobroma_indnr_001"])
    return {"restaurant_id": restaurant_id, "items": items, "powered_by": "Swiggy Food"}


def get_restaurant_menu(restaurant_id: str) -> dict:
    return search_menu(restaurant_id)


def get_food_cart() -> dict:
    return {**_cart, "powered_by": "Swiggy Food"}


def update_food_cart(items: List[dict]) -> dict:
    _cart["items"] = items
    _cart["total"] = sum(i.get("price", 0) * i.get("quantity", 1) for i in items)
    return {**_cart, "powered_by": "Swiggy Food"}


def place_food_order(cart_id: str, address_id: str = "addr_mock_001") -> dict:
    order_id = f"ord_{uuid.uuid4().hex[:10]}"
    total = _cart["total"] or 450
    return {
        "order_id": order_id,
        "status": "confirmed",
        "estimated_delivery_min": 35,
        "total_amount": total,
        "confirmation_message": f"Your dessert order is confirmed! Estimated delivery in 35 minutes.",
        "powered_by": "Swiggy Food",
    }


def track_food_order(order_id: str) -> dict:
    return {
        "order_id": order_id,
        "status": "out_for_delivery",
        "eta_minutes": 20,
        "message": "Your order is on its way!",
        "powered_by": "Swiggy Food",
    }
