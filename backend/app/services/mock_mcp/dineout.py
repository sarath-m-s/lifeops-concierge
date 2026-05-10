"""Mock Swiggy Dineout MCP — realistic Bangalore restaurant data."""
import uuid
from datetime import datetime, timedelta
from typing import Optional

# Per Swiggy Dineout MCP docs: only isFree=True / bookingPrice=0 reservations are
# supported in v1.0. Paid deals are rejected at the MCP layer.
_RESTAURANTS = [
    {
        "restaurant_id": "din_toscano_indnr_001",
        "isFree": True,
        "bookingPrice": 0,
        "name": "Toscano",
        "cuisine": ["Italian", "Continental"],
        "rating": 4.3,
        "price_for_two": 1200,
        "locality": "Indiranagar",
        "address": "100 Feet Road, Indiranagar, Bengaluru - 560038",
        "distance_km": 2.1,
        "offers": ["20% off on drinks", "Complimentary bread basket"],
        "amenities": ["Valet parking", "Live music on weekends", "Outdoor seating"],
        "image_url": "https://placeholder.pics/svg/400x200/FC8019/FFFFFF/Toscano",
    },
    {
        "restaurant_id": "din_olive_ashoknagar_002",
        "isFree": True,
        "bookingPrice": 0,
        "name": "Olive Beach",
        "cuisine": ["Italian", "Mediterranean"],
        "rating": 4.5,
        "price_for_two": 1800,
        "locality": "Ashok Nagar",
        "address": "Wood Street, Ashok Nagar, Bengaluru - 560025",
        "distance_km": 3.4,
        "offers": ["Free dessert with dinner for two", "10% off on pre-booking"],
        "amenities": ["Rooftop seating", "Wine cellar", "Private dining room"],
        "image_url": "https://placeholder.pics/svg/400x200/FC8019/FFFFFF/OliveBeach",
    },
    {
        "restaurant_id": "din_ciclo_koramangala_003",
        "isFree": True,
        "bookingPrice": 0,
        "name": "Ciclo Café",
        "cuisine": ["Italian", "Café"],
        "rating": 4.1,
        "price_for_two": 900,
        "locality": "Koramangala",
        "address": "80 Feet Road, Koramangala 4th Block, Bengaluru - 560034",
        "distance_km": 1.8,
        "offers": ["15% off on weekdays", "Free dessert on birthdays"],
        "amenities": ["Bicycle theme décor", "Outdoor seating", "Pet friendly"],
        "image_url": "https://placeholder.pics/svg/400x200/FC8019/FFFFFF/CicloCafe",
    },
]

_SLOTS = {
    "din_toscano_indnr_001": ["19:30", "20:00", "20:15", "20:30", "21:00"],
    "din_olive_ashoknagar_002": ["19:45", "20:00", "20:30", "21:15"],
    "din_ciclo_koramangala_003": ["19:00", "19:30", "20:00", "20:45"],
}


def search_restaurants_dineout(
    location: str = "Bengaluru",
    cuisine: str = "Italian",
    party_size: int = 2,
    date: str = "Friday",
) -> dict:
    return {
        "restaurants": _RESTAURANTS,
        "total": len(_RESTAURANTS),
        "location": location,
        "date": date,
        "party_size": party_size,
        "powered_by": "Swiggy Dineout",
    }


def get_restaurant_details(restaurant_id: str) -> dict:
    match = next((r for r in _RESTAURANTS if r["restaurant_id"] == restaurant_id), _RESTAURANTS[0])
    return {**match, "powered_by": "Swiggy Dineout"}


def get_available_slots(restaurant_id: str, date: str = "Friday", party_size: int = 2) -> dict:
    slots_raw = _SLOTS.get(restaurant_id, _SLOTS["din_toscano_indnr_001"])
    slots = [
        {"slot_id": f"slot_{restaurant_id}_{t.replace(':', '')}_{uuid.uuid4().hex[:6]}", "time": t, "available": True}
        for t in slots_raw
    ]
    return {
        "restaurant_id": restaurant_id,
        "date": date,
        "party_size": party_size,
        "slots": slots,
        "powered_by": "Swiggy Dineout",
    }


def book_table(restaurant_id: str, slot_id: str, party_size: int = 2) -> dict:
    restaurant = next((r for r in _RESTAURANTS if r["restaurant_id"] == restaurant_id), _RESTAURANTS[0])
    parts = slot_id.split("_")
    # slot_id format: slot_{restaurant_id}_{HHMM}_{hex} — time is second-to-last part
    slot_time = parts[-2] if len(parts) >= 3 and parts[-2].isdigit() else "2000"
    formatted_time = f"{slot_time[:2]}:{slot_time[2:]}"
    booking_id = f"bkg_{uuid.uuid4().hex[:10]}"
    return {
        "booking_id": booking_id,
        "status": "confirmed",
        "restaurant_name": restaurant["name"],
        "address": restaurant["address"],
        "time": formatted_time,
        "party_size": party_size,
        "confirmation_message": f"Table confirmed at {restaurant['name']} for {party_size} at {formatted_time} on Friday.",
        "powered_by": "Swiggy Dineout",
    }


def get_booking_status(booking_id: str) -> dict:
    return {
        "booking_id": booking_id,
        "status": "confirmed",
        "powered_by": "Swiggy Dineout",
    }
