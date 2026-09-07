"""Runnable self-check: python test_backend.py

Covers the logic that would silently do the wrong thing if it broke — PKCE, error
classification, the Swiggy error envelope, the non-idempotency guards, and the
1000-rupee cart cap. No framework, no fixtures.
"""
import asyncio
import base64
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("APP_ENV", "development")

from app.config import settings  # noqa: E402
from app.services import live_mcp, live_planner, swiggy_auth  # noqa: E402
from app.services.intent import ParsedIntent, _calendar, _keyword_intent, _schema_param  # noqa: E402
from app.services.swiggy_mcp import SwiggyToolError, _unwrap, classify  # noqa: E402
from app.utils.id_sanitizer import strip_ids  # noqa: E402


class _Err(Exception):
    def __init__(self, msg="", status=None, code=None):
        super().__init__(msg)
        if status is not None:
            self.status_code = status
        if code is not None:
            self.error = type("E", (), {"code": code})()


class _Result:
    def __init__(self, payload=None, text=None, is_error=False):
        self.structuredContent = payload
        self.isError = is_error
        self.content = [type("T", (), {"type": "text", "text": text})()] if text else []


def test_pkce_is_s256_of_verifier():
    verifier, challenge = swiggy_auth.make_pkce_pair()
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).decode().rstrip("=")
    assert challenge == expected, "challenge must be base64url(sha256(verifier)) with no padding"
    assert "=" not in challenge and "+" not in challenge and "/" not in challenge
    assert swiggy_auth.make_pkce_pair()[0] != verifier, "verifier must not repeat"


def test_server_urls_match_swiggy_paths():
    settings.SWIGGY_MCP_BASE = "https://mcp.swiggy.com"
    assert settings.server_url("food") == "https://mcp.swiggy.com/food"
    # Instamart is /im, not /instamart - getting this wrong is a silent 404.
    assert settings.server_url("instamart") == "https://mcp.swiggy.com/im"
    assert settings.server_url("dineout") == "https://mcp.swiggy.com/dineout"


def test_error_classification_buckets():
    assert classify(_Err(status=401)) == "auth"
    assert classify(_Err(status=419)) == "auth"
    assert classify(_Err(code=-32001)) == "auth", "JSON-RPC -32001 is Swiggy's auth signal"
    assert classify(_Err("invalid_token")) == "auth"
    assert classify(_Err(status=429)) == "rate_limit", "429 must never be retried as a 5xx"
    assert classify(_Err(status=503)) == "retryable"
    assert classify(_Err(status=504)) == "retryable"
    assert classify(_Err("upstream timeout")) == "retryable"
    assert classify(_Err(status=400)) == "fatal", "bad input must not be retried"
    assert classify(_Err(status=404)) == "fatal"

    # anyio task groups wrap the real error; the wrapper must not hide a 401.
    grouped = BaseExceptionGroup("task group", [_Err(status=401)])
    assert classify(grouped) == "auth", "a 401 inside an exception group is still auth"
    assert classify(BaseExceptionGroup("g", [_Err(status=503)])) == "retryable"

    chained = _Err("wrapper")
    chained.__cause__ = _Err(status=429)
    assert classify(chained) == "rate_limit", "a chained 429 must not be retried as generic"


def test_unwrap_raises_on_swiggy_error_envelope():
    ok = _unwrap(_Result({"success": True, "data": {"orders": [1]}}))
    assert ok == {"orders": [1]}, "the data envelope should be unwrapped for callers"

    try:
        _unwrap(_Result({"success": False, "error": {"message": "Slot no longer available"}}))
    except SwiggyToolError as exc:
        assert "Slot no longer available" in str(exc)
    else:
        raise AssertionError("success:false on HTTP 200 must raise, not return")

    # Tools that answer in plain prose must not blow up JSON parsing.
    assert _unwrap(_Result(text="all good")) == {"message": "all good"}


def test_ids_are_stripped_from_display_but_kept_in_params():
    payload = {
        "spoken_response": "ok",
        "ui_payload": {
            "type": "timeline",
            "items": [
                {
                    "title": "Dinner",
                    "restaurant_id": "din_001",
                    "action": {
                        "action_type": "book_table",
                        "params": {"restaurantId": "din_001", "slotId": "s1"},
                    },
                }
            ],
        },
    }
    cleaned = strip_ids(payload)
    item = cleaned["ui_payload"]["items"][0]
    assert "restaurant_id" not in item, "internal ids must not reach the UI"
    assert item["action"]["params"]["restaurantId"] == "din_001", "params must survive for the mutation"


def test_confirm_replays_instead_of_placing_twice():
    """A double-tapped Confirm must return the first result, not place a second order."""
    from app.models.agent_response import ConfirmRequest, PendingAction
    from app.routers import confirm as confirm_router

    calls = {"n": 0}

    async def fake_execute(session_id, action_type, params):
        calls["n"] += 1
        return {"confirmation_message": "Booked.", "bookingId": "bk_1"}

    confirm_router.execute = fake_execute
    confirm_router._locks.clear()
    confirm_router._completed.clear()

    request = ConfirmRequest(
        action=PendingAction(
            action_type="book_table",
            params={"restaurantId": "r1", "slotId": "s1"},
            display_summary="Book table for 2",
        )
    )

    async def run():
        first = await confirm_router.confirm(request, session_id="sess")
        second = await confirm_router.confirm(request, session_id="sess")
        return first, second

    first, second = asyncio.run(run())
    assert calls["n"] == 1, f"non-idempotent action ran {calls['n']} times; must run once"
    assert first.message == second.message == "Booked."
    assert "bookingId" not in (first.details or {}), "internal booking id must not be returned"


def test_food_cart_cap_blocks_place_order():
    """The 1000-rupee Builders Club cap must stop the order before it reaches Swiggy."""
    placed = {"n": 0}

    async def fake_update_food_cart(sid, restaurant_id, items):
        return {}

    async def fake_get_food_cart(sid):
        return {"total": 1450}

    async def fake_place(sid, address_id, payment_method=None):
        placed["n"] += 1
        return {}

    live_planner.live_mcp.update_food_cart = fake_update_food_cart
    live_planner.live_mcp.get_food_cart = fake_get_food_cart
    live_planner.live_mcp.place_food_order = fake_place

    try:
        asyncio.run(
            live_planner.execute(
                "sess",
                "place_food_order",
                {"addressId": "a1", "restaurantId": "r1", "items": [{"itemId": "i1", "quantity": 1}]},
            )
        )
    except SwiggyToolError as exc:
        assert str(live_mcp.FOOD_CART_CAP_RUPEES) in str(exc)
    else:
        raise AssertionError("a 1450-rupee cart must be rejected before placing")
    assert placed["n"] == 0, "place_food_order must not be called once the cap is exceeded"


def test_pending_payment_is_never_reported_as_placed():
    async def noop(*args, **kwargs):
        return {}

    async def fake_get_food_cart(sid):
        return {"total": 300}

    async def fake_place(sid, address_id, payment_method=None):
        return {"status": "PENDING_PAYMENT", "orderId": "o1"}

    live_planner.live_mcp.update_food_cart = noop
    live_planner.live_mcp.get_food_cart = fake_get_food_cart
    live_planner.live_mcp.place_food_order = fake_place

    try:
        asyncio.run(
            live_planner.execute(
                "sess", "place_food_order", {"addressId": "a1", "restaurantId": "r1", "items": []}
            )
        )
    except SwiggyToolError as exc:
        assert "payment" in str(exc).lower()
    else:
        raise AssertionError("PENDING_PAYMENT must not be announced as a placed order")


def test_free_deal_reads_identifiers_from_the_deal_not_the_slot():
    """slotId and itemId live on slot.deals[]; a paid deal must be skipped."""
    slot = {
        "displayTime": "08:00 PM",
        "dateStr": "2026-09-11",
        "reservationTime": 1789200000,
        "deals": [
            {"title": "Prebook 20% off", "isFree": False, "bookingPrice": 500,
             "slotId": "paid_slot", "itemId": "rest-paid"},
            {"title": "Free reservation", "isFree": True, "bookingPrice": 0,
             "slotId": "free_slot", "itemId": "rest-free"},
        ],
    }
    deal = live_planner._free_deal(slot)
    assert deal is not None
    assert deal["slotId"] == "free_slot", "must skip the paid deal and take the free one"
    assert deal["itemId"] == "rest-free"
    assert deal["reservationTime"] == 1789200000

    # A slot whose only deal is paid has no bookable option for this app.
    paid_only = {"displayTime": "09:00 PM", "deals": [slot["deals"][0]]}
    assert live_planner._free_deal(paid_only) is None

    # A slot with no deals at all must not crash.
    assert live_planner._free_deal({"displayTime": "10:00 PM"}) is None


def test_pick_slot_honours_requested_date_and_time():
    def slot(time, dateStr):
        return {"displayTime": time, "dateStr": dateStr,
                "deals": [{"isFree": True, "bookingPrice": 0,
                           "slotId": f"s_{dateStr}_{time}", "itemId": "i"}]}

    slots = [
        slot("07:00 PM", "2026-09-11"),
        slot("08:30 PM", "2026-09-11"),
        slot("08:00 PM", "2026-09-12"),
    ]
    picked = live_planner._pick_slot(slots, "2026-09-11", "20:00")
    assert picked["slotId"] == "s_2026-09-11_08:30 PM", "must not cross to another date"

    # No slot at or after the requested time falls back within the same date.
    late = live_planner._pick_slot(slots, "2026-09-11", "23:00")
    assert late is not None and late["slotId"].startswith("s_2026-09-11")


def test_dineout_search_requires_a_location():
    """Location is a required argument; sending neither form is a caller bug."""
    async def run():
        await live_mcp.search_restaurants_dineout("sess", query="Italian")

    try:
        asyncio.run(run())
    except ValueError as exc:
        assert "address_id or lat/lng" in str(exc)
    else:
        raise AssertionError("a search with no location must raise, not send an empty request")


def test_keyword_intent_fallback_classifies_without_the_llm():
    """The fallback keeps the app usable when the model is unreachable."""
    combined = _keyword_intent(
        "Plan Friday evening for two. Italian dinner around 8 PM, dessert later at home, "
        "and restock coffee for tomorrow."
    )
    assert combined.intent == "plan_evening"
    assert combined.search_term == "Italian", "search must be a term, never the sentence"
    assert combined.booking_date is not None and len(combined.booking_date) == 10

    assert _keyword_intent("book a table").intent == "dineout"
    assert _keyword_intent("hello there").intent == "general"
    assert isinstance(_keyword_intent("anything"), ParsedIntent)


def test_intent_schema_satisfies_groq_strict_mode():
    """Strict structured outputs reject a schema that isn't fully closed.

    Groq requires additionalProperties:false and every property listed in
    `required`. A field gaining a default would silently drop it from `required`
    and turn every intent call into a 400 at runtime — caught here instead.
    """
    schema = ParsedIntent.model_json_schema()
    assert schema.get("additionalProperties") is False, "extra=forbid must emit additionalProperties:false"
    assert sorted(schema["properties"]) == sorted(schema["required"]), (
        "strict mode needs every property in `required`; a field with a default breaks this"
    )

    # Optional fields must stay expressible as null rather than be omitted.
    assert {"type": "null"} in schema["properties"]["booking_date"]["anyOf"]

    param = _schema_param(strict=True)
    assert param["type"] == "json_schema"
    assert param["json_schema"]["strict"] is True
    assert param["json_schema"]["name"] == "parsed_intent"
    assert _schema_param(strict=False)["json_schema"]["strict"] is False


def test_calendar_spells_out_weekdays_for_the_model():
    """The model must look weekdays up, not compute them.

    Asked to resolve "Friday" from Monday 2026-09-07, the model returned
    2026-09-09 — a Wednesday. Supplying a named calendar removed the error, so
    this asserts the calendar itself is right; a wrong calendar would reintroduce
    the bug while looking like it was fixed.
    """
    from datetime import date as _date

    cal = _calendar(_date(2026, 9, 7))
    assert "2026-09-07 is Monday (today)" in cal
    assert "2026-09-08 is Tuesday (tomorrow)" in cal
    assert "2026-09-11 is Friday" in cal, "the date that was previously resolved wrong"
    assert len(cal.splitlines()) == 8, "a full week plus today, so any weekday is present"

    # Every line must agree with the real calendar, not just the spot checks.
    for line in cal.splitlines():
        iso, _, rest = line.partition(" is ")
        y, m, d = map(int, iso.split("-"))
        assert _date(y, m, d).strftime("%A") == rest.split(" (")[0]


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"  ok  {test.__name__}")
    print(f"\n{len(tests)} checks passed")
