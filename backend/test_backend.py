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
from app.services.agent import FINISH, TOOLS, _FINISH_ALIASES, _answer_from, _as_final_answer, _prose_from, _salvage  # noqa: E402
from app.services.conversation import Conversation  # noqa: E402
from app.services.live_planner import _amount  # noqa: E402
from app.services.swiggy_mcp import SwiggyToolError, _unwrap, classify  # noqa: E402
from app.utils.id_sanitizer import strip_ids  # noqa: E402
from app.voice.tools import ConciergeAgent  # noqa: E402
from livekit.agents.llm.tool_context import FunctionTool  # noqa: E402


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

    async def noop(*args, **kwargs):
        return {}

    async def fake_update_food_cart(sid, restaurant_id, items):
        return {}

    async def fake_get_food_cart(sid, address_id):
        return {"total": 1450}

    async def fake_place(sid, address_id, payment_method=None):
        placed["n"] += 1
        return {}

    live_planner.live_mcp.flush_food_cart = noop
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

    async def fake_get_food_cart(sid, address_id):
        return {"total": 300}

    async def fake_place(sid, address_id, payment_method=None):
        return {"status": "PENDING_PAYMENT", "orderId": "o1"}

    live_planner.live_mcp.flush_food_cart = noop
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
    """The legacy /chat agent's toolset must be read-only.

    place_food_order / checkout / book_table spend real money. They are reachable
    only from /confirm after an explicit tap; if one ever appears in TOOLS the
    model could place an order on its own, which is the single thing this design
    exists to prevent.

    Remove this test alongside app/services/agent.py at cutover (see the
    superpowers plan); until then both the legacy and voice agents guard the
    same invariant independently — see test_voice_agent_cannot_reach_a_mutating_tool.
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


def test_voice_agent_tracks_turn_handles_for_the_auto_render_fallback():
    """worker.py's conversation_item_added handler needs to know which tool
    results this turn produced, to auto-render one if the model fetched
    something but never called show_components (live-verified 2026-09-10:
    happens reliably on the Dineout flow). pop_turn_handles() is that signal.
    """
    convo = Conversation(session_id="s")
    agent = ConciergeAgent("s", convo)
    assert agent.pop_turn_handles() == []

    live_mcp.get_saved_locations = lambda sid: _async_result({"locations": [{"id": "loc_1"}]})
    asyncio.run(agent.list_locations())
    handles = agent.pop_turn_handles()
    assert handles == ["list_locations#1"]
    # Draining resets it — a second pop before anything new happened is empty.
    assert agent.pop_turn_handles() == []


async def _async_result(value):
    return value


def test_voice_agent_cannot_reach_a_mutating_tool():
    """Same invariant as test_model_cannot_reach_a_mutating_tool, checked against
    the new LiveKit ConciergeAgent's @function_tool-registered toolset instead of
    the legacy TOOLS list. tools.py itself also asserts this at class-definition
    time (import-time) — this test exists so `python test_backend.py` catches a
    regression too, not just `import app.voice.tools`."""
    names = {v.info.name for v in vars(ConciergeAgent).values() if isinstance(v, FunctionTool)}
    forbidden = {
        "place_food_order", "checkout", "checkout_instamart", "book_table",
        "update_food_cart", "update_cart", "clear_cart", "flush_food_cart",
        "create_address", "delete_address", "cancel_booking", "confirm_order",
    }
    assert not (names & forbidden), f"mutating tools exposed to the voice agent: {names & forbidden}"
    assert "show_components" in names, "the voice agent needs a way to render components"


def test_ensure_dispatched_treats_a_new_room_as_no_existing_dispatch():
    """live-verified 2026-09-10 on Render: list_dispatch 404s ("requested room
    does not exist") for a room nobody has joined yet, instead of returning an
    empty list. Left unhandled, that crashed the whole /livekit/token request
    — the client saw it as a hang, not an error. A brand-new room means no
    existing dispatch either; must fall through to create_dispatch, not raise.
    """
    from livekit import api as lk_api
    from app.routers.livekit_token import _ensure_dispatched

    created = {}

    class FakeDispatchService:
        async def list_dispatch(self, room_name):
            raise lk_api.ServerError("not_found", "requested room does not exist", status=404)

        async def create_dispatch(self, request):
            created["room"] = request.room

    class FakeLkApi:
        agent_dispatch = FakeDispatchService()

    asyncio.run(_ensure_dispatched(FakeLkApi(), "lifeops-sess_123"))
    assert created["room"] == "lifeops-sess_123"

    # A genuinely different server error must still surface, not be swallowed.
    class FakeDispatchServiceOtherError:
        async def list_dispatch(self, room_name):
            raise lk_api.ServerError("internal", "something else broke", status=500)

    class FakeLkApiOtherError:
        agent_dispatch = FakeDispatchServiceOtherError()

    try:
        asyncio.run(_ensure_dispatched(FakeLkApiOtherError(), "lifeops-sess_456"))
    except lk_api.ServerError as exc:
        assert exc.code == "internal"
    else:
        raise AssertionError("a non-404 ServerError must not be swallowed")


def test_livekit_token_mints_a_room_scoped_token():
    """/livekit/token must scope the join token to exactly one session's room.

    identity == session_id is load-bearing: the voice worker's entrypoint reads
    the session id straight off participant.identity (see app/voice/worker.py),
    so a wrong identity here means the worker can never find the right
    Conversation or Swiggy session.
    """
    import asyncio as _asyncio
    import base64 as _b64
    import json as _json

    from app.routers import livekit_token

    settings.LIVEKIT_URL = "wss://test.example.com"
    settings.LIVEKIT_API_KEY = "test_key"
    settings.LIVEKIT_API_SECRET = "test_secret_at_least_32_bytes_long"

    result = _asyncio.run(livekit_token.mint_token(session_id="sess_123"))
    assert result["room_name"] == "lifeops-sess_123"
    assert result["url"] == settings.LIVEKIT_URL

    payload_b64 = result["token"].split(".")[1]
    payload_b64 += "=" * (-len(payload_b64) % 4)
    claims = _json.loads(_b64.urlsafe_b64decode(payload_b64))
    assert claims["sub"] == "sess_123", "identity must be the session id"
    grants = claims["video"]
    assert grants["room"] == "lifeops-sess_123"
    assert grants["roomJoin"] is True
    assert grants["canPublish"] is True and grants["canSubscribe"] is True and grants["canPublishData"] is True


def test_recall_tolerates_a_zero_indexed_handle():
    """Handles are 1-indexed ("tool#1") but row "indexes" inside a component are
    0-indexed ("indexes": [0]) — live-verified 2026-09-10: a model conflated the
    two and asked for "get_menu#0", which never exists, and the confirm_action
    silently failed to materialise. recall() must fall back to that tool's
    latest real result — still real cached data, never fabricated — rather
    than dropping a render over one wrong digit.
    """
    convo = Conversation(session_id="s")
    convo.remember("get_menu", {"items": [{"id": "item_1", "name": "Cake"}]})
    assert convo.recall("get_menu#0") == convo.recall("get_menu#1")
    assert convo.recall("get_menu#1")["items"][0]["id"] == "item_1"
    # A genuinely unknown tool must still miss, not return something unrelated.
    assert convo.recall("nonexistent_tool#0") is None


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


def test_coupon_index_resolves_to_the_real_code_not_a_typed_one():
    """The model picks a coupon by row, never by typing the code itself.

    Mirrors test_confirm_card_uses_cached_data_not_model_claims: a coupon code
    is exactly the kind of fact that must come from a cached tool result.
    """
    convo = Conversation(session_id="s")
    convo.remember("list_addresses", {"addresses": [{"id": "addr_real", "addressLine": "Home"}]})
    convo.remember("search_food_restaurants", {"restaurants": [{"id": "rest_real", "name": "Sweet Truth"}]})
    convo.remember("get_menu", {"items": [{"id": "item_real", "name": "Cake", "price": 450}]})
    convo.remember("food_coupons", {"coupons": [{"code": "WELCOME50"}, {"code": "SAVE20"}]})

    turn = comp.build(convo, {
        "say": "Here you go.",
        "components": [{
            "type": "confirm_action", "action": "place_food_order",
            "source": "get_menu#1", "indexes": [0], "coupon_index": 1,
        }],
    })
    params = turn.components[0].props["action"]["params"]
    assert params["couponCode"] == "SAVE20"

    # An out-of-range index must not crash the turn or fabricate a code.
    turn2 = comp.build(convo, {
        "say": "Here you go.",
        "components": [{
            "type": "confirm_action", "action": "place_food_order",
            "source": "get_menu#1", "indexes": [0], "coupon_index": 99,
        }],
    })
    assert "couponCode" not in turn2.components[0].props["action"]["params"]


def test_delete_address_confirm_reads_the_real_id():
    """delete_address must resolve addressId from the cached list, same pattern
    as every other confirm_action — never from anything the model supplies."""
    convo = Conversation(session_id="s")
    convo.remember("list_addresses", {"addresses": [
        {"id": "addr_home", "addressTag": "Home", "addressLine": "12 MG Road"},
        {"id": "addr_work", "addressTag": "Work", "addressLine": "1 Tech Park"},
    ]})
    turn = comp.build(convo, {
        "say": "Sure.",
        "components": [{
            "type": "confirm_action", "action": "delete_address",
            "source": "list_addresses#1", "indexes": [1],
        }],
    })
    card = turn.components[0]
    assert card.props["action"]["action_type"] == "delete_address"
    assert card.props["action"]["params"] == {"addressId": "addr_work"}


def test_get_restaurant_menu_items_are_flattened_from_categories():
    """get_restaurant_menu nests items under categories[] instead of a flat
    items array, despite the docs promising flat — live-verified 2026-09-09
    (docs/MCP_RESPONSE_SHAPES.md). search_menu stays flat; both must resolve
    to the same row shape so menu_list/confirm_action keep working either way.
    """
    nested = {
        "restaurant": {"id": "r1", "name": "KFC"},
        "categories": [
            {"title": "Burgers", "items": [{"id": "i1", "name": "Zinger", "price": 199}]},
            {"title": "Sides", "items": [{"id": "i2", "name": "Fries", "price": 99}]},
        ],
    }
    rows = comp._rows_for("get_menu", nested)
    assert [r["id"] for r in rows] == ["i1", "i2"]

    flat = {"items": [{"id": "i3", "name": "Wrap", "price": 149}]}
    assert [r["id"] for r in comp._rows_for("search_menu", flat)] == ["i3"]


def test_component_type_near_misses_still_render():
    """A plausible-but-wrong component type must not cost the render — live-
    verified 2026-09-10: the voice agent asked for "menu" and "grocery_list",
    neither of which exist, instead of "menu_list"/"product_list". Same
    reasoning as agent.py's _FINISH_ALIASES for a tool-name slip.
    """
    convo = Conversation(session_id="s")
    convo.remember("get_menu", {"items": [{"id": "i1", "name": "Cake", "price": 450}]})
    convo.remember("search_groceries", {"products": [{"productId": "p1", "displayName": "Milk",
                                                        "variations": [{"price": 28}]}]})

    out = comp.build_components(convo, [{"type": "menu", "source": "get_menu#1"}])
    assert len(out) == 1 and out[0].type == "menu_list"

    out2 = comp.build_components(convo, [{"type": "grocery_list", "source": "search_groceries#1"}])
    assert len(out2) == 1 and out2[0].type == "product_list"


def test_dineout_search_recovers_restaurants_from_prose_message():
    """search_restaurants_dineout drops its restaurants array and returns a
    prose message instead once it finds a match — live-verified 2026-09-09.
    Recovering id/name/coords from the text is the only way book_table's
    confirm_action can still resolve real identifiers for it.
    """
    payload = {
        "message": (
            'Found 2 restaurant(s) matching "family", showing 2.\n'
            "1. CK's Bakery — Middle Eastern, Desserts | 4.8★ | ₹400 for two | Tennur (ID: 650957)\n"
            "2. Amaya — North Indian, Chinese | 4.1★ | ₹800 for two | Cantonment (ID: 700111)\n"
            "Search coordinates: latitude=10.81091071040457, longitude=78.672757409513 "
            "(use these for get_restaurant_details and downstream calls).\n"
        )
    }
    rows = comp._rows_for("search_tables", payload)
    assert [r["id"] for r in rows] == ["650957", "700111"]
    assert rows[0]["name"] == "CK's Bakery"
    assert rows[0]["cuisines"] == ["Middle Eastern", "Desserts"]
    assert rows[0]["latitude"] == 10.81091071040457
    assert rows[0]["longitude"] == 78.672757409513

    # A genuine zero-result response still carries a real (empty) array — must
    # not be re-parsed as prose.
    assert comp._rows_for("search_tables", {"restaurants": [], "message": "No restaurants found."}) == []
    # search_food_restaurants must never take this fallback — Food's search
    # always returns a real array; message-parsing there would be a silent
    # data-fabrication risk, not a recovery.
    assert comp._rows_for("search_food_restaurants", payload) == []


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


def test_tool_name_slip_is_recovered_through_litellm_shaped_error():
    """Same recovery, but against how litellm actually surfaces a Groq 400.

    Verified live: litellm's BadRequestError carries `body=None` and a
    synthetic empty `.response` for Groq's error path — the raw JSON only
    survives in the exception's own message, as `"...: GroqException - {json}"`.
    `_salvage` must still find `failed_generation` there, not just on `.body`.
    """
    payload = json.dumps({
        "name": "response",
        "arguments": {"say": "Hey there!", "components": []},
    })

    class LiteLLMShaped(Exception):
        body = None
        response = None

        def __str__(self):
            return (
                "litellm.BadRequestError: GroqException - "
                + json.dumps({"error": {"failed_generation": payload}})
            )

    salvaged = _salvage(LiteLLMShaped())
    assert salvaged is not None and salvaged["say"] == "Hey there!"


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


def test_no_tool_asks_the_model_for_a_raw_id():
    """The digest strips ids, so a tool requiring one is unanswerable.

    That contradiction made the model pass a row number where an address id was
    expected, and Swiggy replied "Address with ID 3 not found". Rows are now
    referenced positionally and resolved server-side.
    """
    for t in TOOLS:
        params = t["function"]["parameters"]["properties"]
        offenders = [p for p in params if p.endswith("_id")]
        assert not offenders, f"{t['function']['name']} asks the model for {offenders}"


def test_index_resolves_to_the_real_identifier():
    from app.services.agent import Agent
    from app.services.swiggy_mcp import SwiggyToolError as ToolErr

    convo = Conversation(session_id="s")
    convo.remember("list_addresses", {"addresses": [
        {"id": "addr_trichy", "addressTag": "Air BNB"},
        {"id": "addr_kochi_home", "addressTag": "Kochi Home"},
        {"id": "addr_work", "addressTag": "Work"},
        {"id": "addr_kochi3", "addressTag": "Kochi 3"},
    ]})
    agent = Agent("sess", convo)

    assert asyncio.run(agent._resolve("address", 3)) == "addr_kochi3"
    assert asyncio.run(agent._resolve("address", 0)) == "addr_trichy"
    # Models sometimes hand back the index as a string.
    assert asyncio.run(agent._resolve("address", "1")) == "addr_kochi_home"

    for bad in (99, -1 if False else 7, "abc"):
        try:
            asyncio.run(agent._resolve("address", bad))
        except ToolErr as exc:
            assert "row" in str(exc).lower(), exc
        else:
            raise AssertionError(f"index {bad!r} should not resolve")


def test_resolving_without_a_list_explains_itself():
    """A restaurant index with no prior search must say so, not crash."""
    from app.services.agent import Agent
    from app.services.swiggy_mcp import SwiggyToolError as ToolErr

    agent = Agent("sess", Conversation(session_id="s"))
    try:
        asyncio.run(agent._resolve("food_restaurant", 0))
    except ToolErr as exc:
        assert "search first" in str(exc).lower()
    else:
        raise AssertionError("resolving with no cached search should raise a readable error")


def test_prose_reply_still_renders_what_the_turn_found():
    """A turn that fetched results must not render an empty screen.

    The model often describes what it found without asking for a component, which
    left the user reading "here's a place that serves biryani" with nothing to
    look at. The freshest renderable result is shown instead of discarded.
    """
    convo = Conversation(session_id="s")
    h1 = convo.remember("list_addresses", {"addresses": [{"id": "a", "addressTag": "Home"}]})
    h2 = convo.remember("search_food_restaurants", {"restaurants": [
        {"id": "r1", "name": "Kayees Rahmathulla", "areaName": "Kochi", "availabilityStatus": "OPEN"},
    ]})

    auto = comp.auto_components(convo, [h1, h2])
    assert [c.type for c in auto] == ["restaurant_list"], "the newest renderable result wins"
    assert auto[0].props["items"][0]["name"] == "Kayees Rahmathulla"

    # An empty search has nothing worth drawing.
    h3 = convo.remember("search_food_restaurants", {"restaurants": [], "message": "none nearby"})
    assert comp.auto_components(convo, [h3]) == []

    # A menu renders too — asking for one and getting prose was the gap.
    h4 = convo.remember("get_menu", {"items": [{"id": "i", "name": "Chicken Sandwich", "price": 229}]})
    menu = comp.auto_components(convo, [h4])
    assert [c.type for c in menu] == ["menu_list"]
    assert menu[0].props["items"][0]["price"] == 229

    # A tool with no natural component still contributes nothing.
    h5 = convo.remember("track_food", {"status": "on the way"})
    assert comp.auto_components(convo, [h5]) == []
    assert comp.auto_components(convo, []) == []


def test_finished_prose_is_kept_but_chain_of_thought_is_not():
    """Groq returns whatever the model produced when it rejects a generation.

    Sometimes that is a finished reply worth showing; sometimes it is the model
    reasoning aloud, which must never reach the user. Length, JSON, and
    deliberative markers separate the two.
    """
    class Rejected(Exception):
        def __init__(self, gen):
            self.body = {"error": {"code": "output_parse_failed", "failed_generation": gen}}

    good = "Here are some South-Indian options near your work address. They're all open."
    assert _prose_from(Rejected(good)) == good

    thinking = (
        'We need to list addresses first. The user says "Use my Kochi 3 address". '
        "We should call list_addresses to resolve it."
    )
    assert _prose_from(Rejected(thinking)) is None, "chain-of-thought must not be shown"

    assert _prose_from(Rejected('{"say": "hi", "components": []}')) is None, "JSON goes to the parser"
    assert _prose_from(Rejected("x" * 500)) is None, "an essay is not a reply"
    assert _prose_from(Rejected("")) is None
    assert _prose_from(Exception("no body")) is None


def test_groq_outage_falls_back_to_nvidia():
    """Groq unavailable must retry against the configured NVIDIA fallback —
    for a transient APIError (down/rate-limited/timed out) *and* for a
    BadRequestError, because that's what an invalid Groq key actually looks
    like live (verified 2026-09-09: "Invalid API Key" comes back as
    litellm.BadRequestError, not AuthenticationError — litellm has no
    dedicated Groq error-mapping branch). The one BadRequestError that must
    NOT fall back is output_parse_failed — `_complete_once` already owns
    full recovery for that itself.
    """
    import litellm

    import app.services.agent as agent_mod
    from app.services.agent import Agent, FINISH

    class _FakeBadRequest(litellm.BadRequestError):
        def __init__(self, message):
            self.message = message
            self.num_retries = None
            self.max_retries = None

    class _FakeOutage(litellm.APIError):
        def __init__(self):
            self.message = "down"

    class _FakeMessage:
        content = ""
        tool_calls = [type("C", (), {
            "id": "call_1",
            "function": type("F", (), {
                "name": FINISH, "arguments": json.dumps({"say": "hi", "components": []}),
            })(),
        })()]

    class _FakeResponse:
        choices = [type("Ch", (), {"message": _FakeMessage(), "finish_reason": "tool_calls"})()]
        usage = None

    original_key, original_model = settings.NVIDIA_API_KEY, settings.FALLBACK_LLM_MODEL
    settings.NVIDIA_API_KEY = "real_nvidia_key"
    settings.FALLBACK_LLM_MODEL = "nvidia_nim/meta/muse-glimmer-30b"
    try:
        for label, groq_exc in [
            ("transient outage", _FakeOutage()),
            ("invalid API key (live-verified shape)", _FakeBadRequest("GroqException - Invalid API Key")),
        ]:
            calls = []

            async def fake_acompletion(**kwargs):
                calls.append(kwargs["model"])
                if kwargs["model"].startswith("groq/"):
                    raise groq_exc
                return _FakeResponse()

            agent_mod.litellm.acompletion = fake_acompletion
            turn = asyncio.run(Agent("s", Conversation(session_id="s")).run("hi"))
            assert turn.say == "hi", f"{label}: fallback did not recover the turn"
            assert calls == ["groq/openai/gpt-oss-20b", "nvidia_nim/meta/muse-glimmer-30b"], label

        # output_parse_failed is `_complete_once`'s own case — must not also fall back.
        calls = []

        async def fake_parse_failed(**kwargs):
            calls.append(kwargs["model"])
            raise _FakeBadRequest("GroqException - output_parse_failed: model produced prose")

        agent_mod.litellm.acompletion = fake_parse_failed
        turn = asyncio.run(Agent("s3", Conversation(session_id="s3")).run("hi"))
        assert all(c.startswith("groq/") for c in calls), "output_parse_failed must never reach the NVIDIA fallback"

        # No fallback configured: an outage must surface as a failure, not hang or crash.
        settings.NVIDIA_API_KEY = ""
        calls = []

        async def fake_outage_no_fallback(**kwargs):
            calls.append(kwargs["model"])
            raise _FakeOutage()

        agent_mod.litellm.acompletion = fake_outage_no_fallback
        turn = asyncio.run(Agent("s2", Conversation(session_id="s2")).run("hi"))
        assert "reach Swiggy" in turn.say
        assert calls == ["groq/openai/gpt-oss-20b"]
    finally:
        settings.NVIDIA_API_KEY, settings.FALLBACK_LLM_MODEL = original_key, original_model


def test_menu_tools_send_the_address_swiggy_demands():
    """get_restaurant_menu is refused without an addressId.

    The reference example shows restaurantId alone, but the live tool answers
    "addressId is required" — so the wrapper must accept and forward one, and the
    agent must know which address is in play.
    """
    import inspect

    from app.services import live_mcp as lm
    from app.services.agent import Agent

    assert "address_id" in inspect.signature(lm.get_restaurant_menu).parameters
    assert "address_id" in inspect.signature(lm.search_menu).parameters

    # A chosen address is reused rather than re-derived.
    convo = Conversation(session_id="s")
    convo.state["address"] = {"index": 2, "label": "Work", "id": "addr_work"}
    assert asyncio.run(Agent("s", convo)._active_address()) == "addr_work"

    # With nothing chosen, fall back to the first saved address.
    other = Conversation(session_id="s2")
    other.remember("list_addresses", {"addresses": [{"id": "addr_first", "addressTag": "Home"}]})
    assert asyncio.run(Agent("s2", other)._active_address()) == "addr_first"

    assert "address_id" in inspect.signature(lm.get_food_cart).parameters
    assert {"latitude", "longitude"} <= set(inspect.signature(lm.get_restaurant_details).parameters)
    assert {"latitude", "longitude"} <= set(inspect.signature(lm.get_available_slots).parameters)


def test_table_details_uses_the_restaurants_own_coordinates():
    """table_details must pass the searched restaurant's lat/lng, not the user's.

    get_restaurant_details 400s without them (docs: both required) — same
    coordinate source book_table already relies on (see live_mcp.book_table).
    """
    from app.services import live_mcp as lm
    from app.services.agent import Agent

    convo = Conversation(session_id="s")
    convo.remember("search_tables", {"restaurants": [
        {"id": "rest_1", "name": "Rooftop Bistro", "latitude": 12.9, "longitude": 77.6},
    ]})

    captured = {}

    async def fake_get_restaurant_details(sid, restaurant_id, latitude, longitude):
        captured.update(sid=sid, restaurant_id=restaurant_id, latitude=latitude, longitude=longitude)
        return {"restaurant": {"name": "Rooftop Bistro"}}

    lm.get_restaurant_details = fake_get_restaurant_details

    asyncio.run(Agent("s", convo)._dispatch("table_details", {"restaurant_index": 0}))
    assert captured == {"sid": "s", "restaurant_id": "rest_1", "latitude": 12.9, "longitude": 77.6}


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"  ok  {test.__name__}")
    print(f"\n{len(tests)} checks passed")
