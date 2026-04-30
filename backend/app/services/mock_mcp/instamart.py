"""Mock Swiggy Instamart MCP — realistic grocery data for coffee/breakfast."""
import uuid
from typing import List

_PRODUCTS = {
    "coffee": [
        {"product_id": "prd_sleepyowl_cold_001", "name": "Sleepy Owl Cold Brew", "brand": "Sleepy Owl", "price": 299, "unit": "250ml", "category": "Coffee", "in_stock": True, "image_url": "https://placeholder.pics/svg/100/FC8019/FFFFFF/SleepyOwl"},
        {"product_id": "prd_cothas_filter_002", "name": "Cothas Filter Coffee", "brand": "Cothas", "price": 185, "unit": "500g", "category": "Coffee", "in_stock": True, "image_url": "https://placeholder.pics/svg/100/FC8019/FFFFFF/Cothas"},
        {"product_id": "prd_bru_instant_003", "name": "Bru Instant Coffee", "brand": "Bru", "price": 245, "unit": "200g", "category": "Coffee", "in_stock": True, "image_url": "https://placeholder.pics/svg/100/FC8019/FFFFFF/Bru"},
    ],
    "breakfast": [
        {"product_id": "prd_amul_milk_001", "name": "Amul Milk", "brand": "Amul", "price": 68, "unit": "1L", "category": "Dairy", "in_stock": True, "image_url": "https://placeholder.pics/svg/100/FC8019/FFFFFF/AmulMilk"},
        {"product_id": "prd_britannia_bread_002", "name": "Britannia Bread", "brand": "Britannia", "price": 45, "unit": "400g", "category": "Bakery", "in_stock": True, "image_url": "https://placeholder.pics/svg/100/FC8019/FFFFFF/Britannia"},
        {"product_id": "prd_quaker_oats_003", "name": "Quaker Oats", "brand": "Quaker", "price": 149, "unit": "500g", "category": "Breakfast", "in_stock": True, "image_url": "https://placeholder.pics/svg/100/FC8019/FFFFFF/Oats"},
    ],
}

_cart: dict = {"cart_id": "cart_instamart_mock_001", "items": [], "total": 0, "delivery_slot": "Tomorrow 6–9 AM"}


def search_products(query: str = "coffee", category: str = "") -> dict:
    key = "breakfast" if category == "breakfast" or "breakfast" in query.lower() else "coffee"
    results = _PRODUCTS.get(key, _PRODUCTS["coffee"])
    if "milk" in query.lower() or "bread" in query.lower():
        results = _PRODUCTS["breakfast"]
    return {
        "products": results,
        "total": len(results),
        "query": query,
        "powered_by": "Swiggy Instamart",
    }


def get_cart() -> dict:
    return {**_cart, "powered_by": "Swiggy Instamart"}


def update_cart(items: List[dict]) -> dict:
    _cart["items"] = items
    _cart["total"] = sum(i.get("price", 0) * i.get("quantity", 1) for i in items)
    return {**_cart, "powered_by": "Swiggy Instamart"}


def checkout(cart_id: str, address_id: str = "addr_mock_001") -> dict:
    order_id = f"im_ord_{uuid.uuid4().hex[:10]}"
    total = _cart["total"] or (299 + 185 + 68 + 45)
    return {
        "order_id": order_id,
        "status": "confirmed",
        "delivery_slot": "Tomorrow 6–9 AM",
        "total_amount": total,
        "confirmation_message": "Your grocery order is confirmed! Delivery tomorrow between 6–9 AM.",
        "powered_by": "Swiggy Instamart",
    }


def track_order(order_id: str) -> dict:
    return {
        "order_id": order_id,
        "status": "scheduled",
        "delivery_slot": "Tomorrow 6–9 AM",
        "message": "Your groceries are scheduled for delivery tomorrow morning.",
        "powered_by": "Swiggy Instamart",
    }


def get_orders() -> dict:
    return {"orders": [], "powered_by": "Swiggy Instamart"}
