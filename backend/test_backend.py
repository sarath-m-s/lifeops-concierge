"""Runnable self-check: python test_backend.py

Covers the logic that would silently do the wrong thing if it broke — PKCE, error
classification, the Swiggy error envelope, the non-idempotency guards, and the
1000-rupee cart cap. No framework, no fixtures.
"""
import asyncio
import base64
import json
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("APP_ENV", "development")

from app.config import settings  # noqa: E402
from app.services import live_mcp, live_planner, swiggy_auth  # noqa: E402
from app.services import components as comp  # noqa: E402
from app.services.agent import FINISH, TOOLS, _FINISH_ALIASES, _answer_from, _as_final_answer, _salvage  # noqa: E402
from app.services.conversation import Conversation  # noqa: E402
from app.services.live_planner import _amount  # noqa: E402
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


def test_empty_structured_content_does_not_shadow_text():
    """An empty structuredContent must fall through to the text block.

    `{}` is not None, so preferring structuredContent on a None-check alone threw
    away the real payload — and, on failures, the real error message. That is what
    turned every Food error into the literal string "{}".
    """
    payload = _unwrap(_Result({}, text='{"restaurants": [{"id": "1"}]}'))
    assert payload["restaurants"][0]["id"] == "1", "text content must be used when structured is empty"

    # A populated structuredContent still wins.
    assert _unwrap(_Result({"data": {"a": 1}}, text="ignored")) == {"a": 1}

    try:
        _unwrap(_Result({}, text='{"success": false, "error": {"message": "Restaurant is closed"}}'))
    except SwiggyToolError as exc:
        assert exc.message == "Restaurant is closed", "the server's message must survive"
    else:
        raise AssertionError("an error envelope in text content must still raise")


def test_money_survives_being_an_object():
    """Instamart returns price as an object; summing it raised a TypeError."""
    assert _amount({"mrp": 280, "offerPrice": 260, "unitLevelPrice": "260/100 g"}) == 260, (
        "offerPrice is what the user pays and must win over mrp"
    )
    assert _amount({"mrp": 140}) == 140
    assert _amount(450) == 450
    assert _amount(None) == 0 and _amount({}) == 0
    # The original crash was sum() over these.
    assert sum(_amount(p) for p in [{"offerPrice": 260}, 130, None]) == 390


def test_model_cannot_reach_a_mutating_tool():
    """The agent's toolset must be read-only.

    place_food_order / checkout / book_table spend real money. They are reachable
    only from /confirm after an explicit tap; if one ever appears in TOOLS the
    model could place an order on its own, which is the single thing this design
    exists to prevent.
    """
    names = {t["function"]["name"] for t in TOOLS}
    forbidden = {
        "place_food_order", "checkout", "checkout_instamart", "book_table",
        "update_food_cart", "update_cart", "clear_cart", "flush_food_cart",
        "create_address", "delete_address", "cancel_booking", "confirm_order",
    }
    assert not (names & forbidden), f"mutating tools exposed to the model: {names & forbidden}"
    assert FINISH in names, "the model needs a way to finish a turn"

    for t in TOOLS:  # strict function-calling needs closed parameter schemas
        assert t["function"]["parameters"]["additionalProperties"] is False


def test_confirm_card_uses_cached_data_not_model_claims():
    """Identifiers and prices come from the stored payload, never from the model.

    A model that hallucinates a price or an item id would otherwise put a wrong
    order behind a Confirm button. Here the model only picks an index.
    """
    convo = Conversation(session_id="s")
    convo.remember("list_addresses", {"addresses": [{"id": "addr_real", "addressLine": "Home"}]})
    convo.remember("search_food_restaurants", {"restaurants": [{"id": "rest_real", "name": "Sweet Truth"}]})
    convo.remember("get_menu", {"items": [
        {"id": "item_real", "name": "Chocolate Cake", "price": 450},
        {"id": "item_other", "name": "Brownie", "price": 120},
    ]})

    # The model asks for row 0 — and separately tries to smuggle in its own values.
    turn = comp.build(convo, {
        "say": "Here you go.",
        "components": [{
            "type": "confirm_action", "action": "place_food_order",
            "source": "get_menu#1", "indexes": [0],
            "items": [{"itemId": "hacked", "price": 1}], "total": "₹1",
        }],
    })

    card = turn.components[0]
    params = card.props["action"]["params"]
    assert params["addressId"] == "addr_real"
    assert params["restaurantId"] == "rest_real"
    assert params["items"] == [{"itemId": "item_real", "quantity": 1}], "ids must come from the cache"
    assert card.props["total"] == "₹450", "price is read from the payload, not the model"
    assert "hacked" not in json.dumps(card.model_dump())


def test_unresolvable_component_is_dropped_not_faked():
    """A stale or wrong handle must yield nothing rather than an empty shell."""
    convo = Conversation(session_id="s")
    turn = comp.build(convo, {"say": "hi", "components": [
        {"type": "confirm_action", "action": "place_food_order", "source": "get_menu#9"},
        {"type": "restaurant_list", "source": "nonexistent#1"},
        {"type": "made_up_component", "source": "whatever#1"},
        {"type": "chips", "options": ["Show coupons", "Something else"]},
    ]})
    assert [c.type for c in turn.components] == ["chips"], "only the resolvable component survives"
    assert turn.say == "hi"


def test_digest_keeps_identifiers_away_from_the_model():
    """The model reasons over names and indexes; ids stay server-side."""
    payload = {"restaurants": [
        {"id": "secret_rest_id", "name": "Sweet Truth", "areaName": "Thillai Nagar", "avgRating": 4.3},
    ]}
    d = comp.digest("search_food_restaurants", payload)
    assert d["rows"][0]["name"] == "Sweet Truth"
    assert d["rows"][0]["i"] == 0, "the index is how the model refers back to a row"
    assert "secret_rest_id" not in json.dumps(d), "raw ids must not enter the prompt"


def test_price_object_survives_the_component_path():
    convo = Conversation(session_id="s")
    convo.remember("search_groceries", {"products": [
        {"displayName": "Bru Instant Coffee", "variations": [
            {"spinId": "SPIN1", "quantityDescription": "50 g", "price": {"mrp": 140, "offerPrice": 130}},
        ]},
    ]})
    turn = comp.build(convo, {"say": "found it", "components": [
        {"type": "product_list", "source": "search_groceries#1"},
    ]})
    item = turn.components[0].props["items"][0]
    assert item["price"] == 130, "offerPrice is what the user pays"
    assert item["name"] == "Bru Instant Coffee" and item["unit"] == "50 g"


def test_tool_name_slip_is_recovered_not_discarded():
    """A wrong finish-tool name must not cost the whole turn.

    The model produced a valid say/components payload and then called it
    `response` instead of `final_answer`. Groq rejects the call after generating
    it, handing the payload back in `failed_generation` — so read it rather than
    throwing away a good answer over one word.
    """
    class Rejected(Exception):
        body = {
            "error": {
                "code": "tool_use_failed",
                "failed_generation": json.dumps({
                    "name": "response",
                    "arguments": {"say": "Hey there!", "components": [{"type": "chips", "options": ["Order food"]}]},
                }),
            }
        }

    salvaged = _salvage(Rejected())
    assert salvaged is not None and salvaged["say"] == "Hey there!"

    # Arguments sometimes arrive as a JSON string rather than an object.
    class StringArgs(Exception):
        body = {"error": {"failed_generation": json.dumps({
            "name": "respond", "arguments": json.dumps({"say": "hi", "components": []}),
        })}}
    assert _salvage(StringArgs())["say"] == "hi"

    # A rejected *data* tool must not be mistaken for a finish call.
    class WrongTool(Exception):
        body = {"error": {"failed_generation": json.dumps({
            "name": "search_groceries", "arguments": {"query": "x"},
        })}}
    assert _salvage(WrongTool()) is None
    assert _salvage(Exception("no body at all")) is None

    assert "respond" in _FINISH_ALIASES and "response" in _FINISH_ALIASES


def test_final_answer_written_as_text_is_parsed_not_shown():
    """The model sometimes writes the finish payload instead of calling the tool.

    When that happened the raw JSON was rendered to the user as the assistant's
    reply. Parse it back into a turn; only genuine prose should pass through
    untouched.
    """
    bare = _as_final_answer('{"say": "Which address?", "components": [{"type": "chips", "options": ["a"]}]}')
    assert bare is not None and bare["say"] == "Which address?"

    assert _as_final_answer('```json\n{"say": "hi", "components": []}\n```')["say"] == "hi"
    assert _as_final_answer('{"name": "response", "arguments": {"say": "hey", "components": []}}')["say"] == "hey"
    assert _as_final_answer('Sure thing. {"say": "ok", "components": []}')["say"] == "ok"

    # Real prose must be left alone, not coerced into a component payload.
    assert _as_final_answer("Which address would you like to order from?") is None
    assert _as_final_answer('{"components": []}') is None, "a payload with no say is not an answer"
    assert _as_final_answer("") is None


def test_malformed_tool_envelope_is_still_recoverable():
    """Three separate malformed shapes have shown up in real traffic.

    The worst put prose inside `arguments` before the object, so the envelope is
    not JSON at all. Slicing first-brace-to-last-brace spans the broken wrapper,
    so the parser walks brace depth instead — while tracking string state, or a
    brace inside a value would throw the count off.
    """
    observed = (
        '{"name": "answer", "arguments": Sure! What cuisine are you in the mood for? \n\n'
        '{\n  "components": [\n    {\n      "type": "chips",\n'
        '      "options": ["South Indian", "Chinese"]\n    }\n  ],\n'
        '  "say": "Pick a cuisine."\n}"}'
    )
    got = _answer_from(observed)
    assert got is not None, "prose inside arguments must not cost the turn"
    assert got["say"] == "Pick a cuisine."
    assert got["components"][0]["type"] == "chips"

    # A brace inside a string value must not confuse the depth scan.
    assert _answer_from('{"say": "use {this} literally", "components": []}')["say"] == "use {this} literally"

    # Real prose is still left alone.
    assert _answer_from("Which address would you like?") is None
    assert _answer_from('{"components": []}') is None
    assert _answer_from("") is None


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"  ok  {test.__name__}")
    print(f"\n{len(tests)} checks passed")
