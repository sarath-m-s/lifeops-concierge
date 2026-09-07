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
from app.services import swiggy_auth  # noqa: E402
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

    async def fake_execute(action_type, params, session_id):
        calls["n"] += 1
        return {"confirmation_message": "Booked.", "bookingId": "bk_1"}

    confirm_router.execute_confirmed_action = fake_execute
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
    from app.services import live_mcp, live_planner

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
    from app.services import live_planner

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


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"  ok  {test.__name__}")
    print(f"\n{len(tests)} checks passed")
