"""The agent loop.

The model drives: it calls read-only Swiggy tools, reads the results, and decides
what to do next. It finishes by calling `respond`, which carries the spoken line
plus the components the app should render.

Two invariants, both deliberate:

1. **No mutating tool is in the model's toolset.** place_food_order, checkout and
   book_table are unreachable from here. The model can only *propose* one via a
   confirm_action component; /confirm remains the single place an order is
   placed, behind an explicit tap.

2. **The model never supplies data or identifiers.** It references a cached tool
   result by handle and index; the server reads the real values out of that cached
   payload. So a restaurant name, a price, or an item id cannot be something the
   model made up — which matters a great deal when the next tap spends money.
"""
import asyncio
import json
import logging
import time
from datetime import date, timedelta
from typing import Any, Optional

import litellm

from app.config import settings
from app.models.agent_response import AgentTurn, Component
from app.services import live_mcp
from app.services.conversation import Conversation
from app.services.swiggy_mcp import SwiggyToolError

log = logging.getLogger(__name__)

MAX_STEPS = 8

# The name the model must call to end a turn, plus the near-misses it actually
# produces. Groq rejects an unknown tool name outright, so an accepted synonym is
# cheaper than losing the turn to a one-word slip.
FINISH = "final_answer"
_FINISH_ALIASES = {FINISH, "respond", "response", "answer", "reply", "finish"}
_TURN_TIMEOUT = 45.0


def _fmt_args(args: dict) -> str:
    """Compact call signature for the log. Long ids are elided, not printed whole."""
    parts = []
    for k, v in (args or {}).items():
        text = str(v)
        parts.append(f"{k}={text[:18] + '\u2026' if len(text) > 18 else text}")
    return ", ".join(parts)


def _tool(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        },
    }


_STR = {"type": "string"}
_IDX = {"type": "integer", "description": "Row number from the list shown (0-based)."}

TOOLS = [
    _tool("list_addresses", "Saved delivery addresses.", {}, []),
    _tool("list_locations", "Saved locations for table search.", {}, []),
    _tool(
        "search_food_restaurants",
        "Search delivery restaurants. query = ONE term (cuisine/dish/chain), not a sentence.",
        {"address_index": _IDX, "query": _STR},
        ["address_index", "query"],
    ),
    _tool("get_menu", "Menu of a restaurant you searched.",
          {"restaurant_index": _IDX}, ["restaurant_index"]),
    _tool(
        "search_menu",
        "Search one restaurant's menu.",
        {"restaurant_index": _IDX, "query": _STR},
        ["restaurant_index", "query"],
    ),
    _tool(
        "search_groceries",
        "Search groceries. query = one item name.",
        {"address_index": _IDX, "query": _STR},
        ["address_index", "query"],
    ),
    _tool(
        "list_usual_groceries",
        "Usual groceries. Prefer for reorders.",
        {"address_index": _IDX},
        ["address_index"],
    ),
    _tool(
        "search_tables",
        "Search bookable restaurants. query = ONE term (cuisine/area/chain/vibe).",
        {"address_index": _IDX, "query": _STR},
        ["address_index", "query"],
    ),
    _tool(
        "get_table_slots",
        "Booking slots. Returns 7 days at once; do not re-call for another date.",
        {"restaurant_index": _IDX, "date": _STR, "guests": {"type": "integer"}},
        ["restaurant_index", "date", "guests"],
    ),
    _tool("food_coupons", "Food delivery coupons.", {}, []),
    _tool("grocery_coupons", "Grocery coupons.", {}, []),
    _tool("my_food_orders", "Recent food orders.", {}, []),
    _tool("my_grocery_orders", "Recent grocery orders.", {}, []),
    _tool("track_food", "Food order status.", {"order_index": _IDX}, ["order_index"]),
    _tool("track_groceries", "Grocery order status.", {"order_index": _IDX}, ["order_index"]),
    _tool("food_order_details", "Itemised receipt for a past food order.", {"order_index": _IDX}, ["order_index"]),
    _tool("grocery_order_details", "Itemised receipt for a past grocery order.", {"order_index": _IDX}, ["order_index"]),
    _tool("table_details", "Amenities, deals and photos for a restaurant you searched for a table.",
          {"restaurant_index": _IDX}, ["restaurant_index"]),
    _tool("food_payment_options", "Payment methods available for a food order.", {}, []),
    _tool("grocery_payment_options", "Payment methods available for a grocery order.", {}, []),
    _tool("table_payment_options", "Payment methods available for a table booking.", {}, []),
    _tool(
        FINISH,
        (
            "Finish the turn: a brief human sentence plus the components to render. Always call this last."
        ),
        {
            "say": {"type": "string", "description": "One or two sentences. No lists; components carry detail."},
            "components": {
                "type": "array",
                "description": "Components to render.",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {
                            "type": "string",
                            "enum": [
                                "restaurant_list",
                                "product_list",
                                "menu_list",
                                "coupon_list",
                                "slot_list",
                                "address_list",
                                "order_list",
                                "order_status",
                                "confirm_action",
                                "chips",
                            ],
                        },
                        "source": {"type": "string", "description": "Tool result handle, e.g. search_food_restaurants#1."},
                        "indexes": {"type": "array", "items": {"type": "integer"}, "description": "Rows to show; omit for all."},
                        "action": {"type": "string",
                                   "enum": ["place_food_order", "checkout_instamart", "book_table", "delete_address"],
                                   "description": "confirm_action only. delete_address: source/indexes pick the address."},
                        "coupon_index": {"type": "integer",
                                          "description": "confirm_action place_food_order/checkout_instamart only: "
                                                          "row from food_coupons/grocery_coupons to apply. Omit for none."},
                        "options": {"type": "array", "items": {"type": "string"}, "description": "chips only."},
                    },
                    "required": ["type"],
                    "additionalProperties": False,
                },
            },
        },
        ["say", "components"],
    ),
]

_MUTATING = {
    "place_food_order", "checkout", "book_table", "update_food_cart", "update_cart",
    "delete_address", "apply_food_coupon", "apply_grocery_coupon", "flush_food_cart", "clear_grocery_cart",
}
assert not (_MUTATING & {t["function"]["name"] for t in TOOLS}), "no mutating tool may reach the model"
assert FINISH in {t["function"]["name"] for t in TOOLS}


def _calendar(today: date, days: int = 8) -> str:
    return "\n".join(
        f"{(today + timedelta(days=o)).isoformat()} is {(today + timedelta(days=o)).strftime('%A')}"
        + (" (today)" if o == 0 else " (tomorrow)" if o == 1 else "")
        for o in range(days)
    )


SYSTEM = """You are a Swiggy concierge: food delivery, groceries, and restaurant table bookings in India.

Rules:
- You never see raw ids. Lists are numbered from 0; refer to rows by number (address_index, restaurant_index, order_index).
- Two different numbers, don't mix them up: a result's handle (e.g. "get_menu#1") is
  1-indexed — the first call to a tool is always #1, never #0. The "indexes" you pass
  in a component (which rows of that list to show) are 0-indexed, first row is 0.
- If the user names something already listed ("Popeyes", "the second one"), that is a selection — use its number, do not search again.
- Never re-fetch anything the context block already gives you.
- Greetings need no tools: say hello and offer chips.
- Resolve an address before searching food or groceries. If it matters and you cannot tell which, show address_list and ask.
- Queries take ONE term, never a sentence. For a dish, search its cuisine ("dosa" -> "South Indian").
- Empty results: say so and suggest another term or area. Never invent results.
- To order, render a confirm_action. You cannot place orders yourself.
- Offer coupons before an order when they would save money. To apply one, set coupon_index
  on the order's confirm_action to its row in food_coupons/grocery_coupons.
- To remove a saved address, confirm the user means it, then use confirm_action with
  action=delete_address, source=list_addresses#N, indexes=[the row].

Voice: brief, natural, one or two sentences. Never list restaurants, prices, or items in text — components show them. Never mention tools or ids.

Always finish by CALLING the final_answer tool. Never write its JSON as a message —
emit it as a tool call, or the user sees raw JSON instead of an answer."""


def _json_objects(text: str):
    """Yield every balanced {...} in `text`, parsed, outermost-first per position.

    The model has produced malformed envelopes in three different ways now, most
    recently prose sitting inside `arguments` before the real object. Slicing from
    the first brace to the last spans the broken wrapper, so walk the string
    tracking depth — and track string state, since braces inside a value must not
    move the depth counter.
    """
    for start, ch in enumerate(text):
        if ch != "{":
            continue
        depth, in_string, escaped = 0, False, False
        for end in range(start, len(text)):
            c = text[end]
            if escaped:
                escaped = False
                continue
            if c == "\\":
                escaped = True
                continue
            if c == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    try:
                        parsed = json.loads(text[start : end + 1])
                    except (json.JSONDecodeError, ValueError):
                        break
                    if isinstance(parsed, dict):
                        yield parsed
                    break


def _answer_from(text: str) -> Optional[dict]:
    """Find a final_answer payload anywhere in `text`.

    Accepts the bare arguments object, or a {name, arguments} envelope where the
    arguments are themselves an object or a JSON string.
    """
    if not text:
        return None
    for candidate in _json_objects(text):
        if candidate.get("name") in _FINISH_ALIASES:
            args = candidate.get("arguments")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = None
            if isinstance(args, dict) and "say" in args:
                return args
        if "say" in candidate:
            return candidate
    return None


def _as_final_answer(text: str) -> Optional[dict]:
    """Read a final_answer payload the model wrote as text instead of calling it.

    gpt-oss will sometimes emit the finish payload as message content — occasionally
    fenced, occasionally wrapped in {"name": ..., "arguments": {...}}. Without this
    the user is shown raw JSON, which is what happened in testing.
    """
    return _answer_from(text)


_REASONING = ("we need to", "we should", "the user says", "let's call", "i'd ask", "but we")


def _error_body(exc: BaseException) -> dict:
    """The provider's raw error JSON, however the client surfaced it.

    The Groq SDK put this straight on `exc.body`. Verified against a live
    Groq 400 through litellm: `.body` comes back None and `.response` is a
    synthetic empty httpx.Response (litellm only forwards it when the
    original has `._request` set, which Groq's path doesn't). The one place
    the JSON does survive is the exception's own message — litellm renders it
    as `"litellm.<Type>: GroqException - {raw json}"` — so that is the real
    fallback, not `.response`.
    """
    body = getattr(exc, "body", None)
    if isinstance(body, dict) and body:
        return body
    response = getattr(exc, "response", None)
    if response is not None:
        try:
            parsed = response.json()
        except Exception:
            parsed = None
        if isinstance(parsed, dict) and parsed:
            return parsed
    for candidate in _json_objects(str(exc)):
        if isinstance(candidate.get("error"), dict):
            return candidate
    return {}


def _prose_from(exc: Exception) -> Optional[str]:
    """A user-facing sentence out of a rejected generation, if there is one.

    Groq returns whatever the model produced. Sometimes that is a finished reply
    ("Here are some South-Indian options near your work address"); sometimes it is
    raw chain-of-thought talking itself in circles. Only the former is worth
    showing, so reject anything long or visibly deliberative.
    """
    body = _error_body(exc)
    raw = (body.get("error") or {}).get("failed_generation") if isinstance(body, dict) else None
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text or "{" in text or len(text) > 400:
        return None
    lowered = text.lower()
    if any(marker in lowered for marker in _REASONING):
        return None
    return text


def _salvage(exc: Exception) -> Optional[dict]:
    """Recover the intended answer from a rejected tool call.

    A wrong tool name fails validation *after* the model has already produced a
    perfectly good say/components payload. Groq returns it as `failed_generation`,
    so read it back rather than discarding the turn.
    """
    body = _error_body(exc)
    raw = (body.get("error") or {}).get("failed_generation") if isinstance(body, dict) else None
    # Fall back to the stringified exception — the payload is in there either way.
    return _answer_from(raw or str(exc))


class Agent:
    def __init__(self, session_id: str, convo: Conversation):
        self.sid = session_id
        self.convo = convo

    async def _resolve(self, kind: str, index: Any) -> str:
        """Turn a row number into the real identifier.

        The model is never given raw ids — the digest strips them — so it refers
        to rows positionally and the lookup happens here against the cached
        payload. If the underlying list has not been fetched yet, fetch it, so a
        skipped step degrades into an extra call rather than a dead end.
        """
        from app.services import components as comp

        loaders = {
            "address": ("list_addresses", live_mcp.get_addresses, ("id", "addressId")),
            "food_restaurant": ("search_food_restaurants", None, ("id", "restaurantId")),
            "table_restaurant": ("search_tables", None, ("id", "restaurantId")),
            "food_order": ("my_food_orders", live_mcp.get_food_orders, ("orderId", "id")),
            "grocery_order": ("my_grocery_orders", live_mcp.get_orders, ("orderId", "id")),
        }
        tool, loader, keys = loaders[kind]

        payload = self.convo.latest(tool)
        if payload is None and loader is not None:
            payload = await loader(self.sid)
            self.convo.remember(tool, payload)
            log.info("  \u21b3 auto-fetched %s to resolve %s #%s", tool, kind, index)

        rows = comp._rows_for(tool, payload) if payload is not None else []
        if not rows:
            raise SwiggyToolError(
                f"I don't have a list to pick that from yet — search first, then choose a row."
            )
        try:
            row = rows[int(index)]
        except (TypeError, ValueError, IndexError):
            raise SwiggyToolError(
                f"There is no row {index} in that list; it has {len(rows)} item(s), numbered from 0."
            ) from None

        value = next((row[k] for k in keys if row.get(k) is not None), None)
        if value is None:
            raise SwiggyToolError("That row is missing the identifier I need.")

        if kind == "address":
            # Sticky for the rest of the conversation, so later turns stop
            # re-fetching the list just to arrive at the same answer.
            label = comp._get(row, "addressTag", "addressCategory", default="that address")
            self.convo.state["address"] = {"index": int(index), "label": label, "id": str(value)}
        return str(value)

    async def _complete(self, prompt: list[dict]):
        """One model call against Groq, falling back to NIM if Groq itself is
        unavailable.

        Only one case is excluded: `output_parse_failed`, where the *model*
        produced content Groq's own schema validator rejected. `_complete_once`
        already has bespoke recovery for exactly that (forced retry pinned to
        `final_answer`), so it isn't a "provider is unavailable" situation and
        doesn't need a fallback on top.

        Everything else does — including litellm.BadRequestError. Verified
        live 2026-09-09: an invalid/expired Groq key surfaces as a
        BadRequestError ("Invalid API Key"), not AuthenticationError — litellm
        has no dedicated Groq error-mapping branch, so it falls through the
        generic 4xx path. Treating BadRequestError as always-safe-to-skip
        would silently defeat the fallback for exactly the case it exists for.
        """
        kwargs = dict(
            model=f"groq/{settings.LLM_MODEL}",
            api_key=settings.LLM_API_KEY.strip(),
            messages=prompt,
            tools=TOOLS,
            temperature=0,
            max_completion_tokens=1400,
        )
        try:
            return await self._complete_once(prompt, kwargs)
        except litellm.BadRequestError as exc:
            if "output_parse_failed" in str(exc):
                raise
            return await self._fallback_or_raise(prompt, kwargs, exc)
        except litellm.APIError as exc:
            return await self._fallback_or_raise(prompt, kwargs, exc)

    async def _fallback_or_raise(self, prompt: list[dict], kwargs: dict, exc: Exception):
        if not settings.nvidia_fallback_enabled:
            raise exc
        log.warning(
            "  ⚠ %s unavailable (%s); falling back to %s",
            settings.LLM_MODEL, type(exc).__name__, settings.FALLBACK_LLM_MODEL,
        )
        fallback = dict(kwargs, model=settings.FALLBACK_LLM_MODEL, api_key=settings.NVIDIA_API_KEY.strip())
        return await self._complete_once(prompt, fallback)

    async def _complete_once(self, prompt: list[dict], kwargs: dict):
        """One model call, forcing the finish tool if free-form output won't parse.

        gpt-oss sometimes answers in prose while tools are attached, which Groq
        rejects as output_parse_failed. Re-asking with tool_choice pinned to
        final_answer removes the free-form path entirely, and keeps the tool
        results already gathered rather than re-running the whole turn.
        """
        try:
            return await asyncio.wait_for(
                litellm.acompletion(tool_choice="auto", **kwargs),
                timeout=_TURN_TIMEOUT,
            )
        except litellm.BadRequestError as exc:
            if "output_parse_failed" not in str(exc):
                raise
            prose = _prose_from(exc)
            log.warning("  \u26a0 unparseable output; forcing final_answer")
            forced = dict(kwargs)
            if prose:
                # Hand back what it tried to say so the retry keeps the wording.
                forced["messages"] = prompt + [{
                    "role": "system",
                    "content": (
                        "Your previous reply was not a tool call and was rejected. "
                        f'Call final_answer now. You were saying: "{prose[:300]}"'
                    ),
                }]
            return await asyncio.wait_for(
                litellm.acompletion(
                    tool_choice={"type": "function", "function": {"name": FINISH}}, **forced
                ),
                timeout=_TURN_TIMEOUT,
            )

    async def _active_address(self) -> str:
        """The delivery address in play, resolving or fetching one if needed.

        Several Food tools require an addressId beyond the obvious one, so this is
        the single place that answers "which address are we ordering to".
        """
        chosen = self.convo.state.get("address")
        if chosen and chosen.get("id"):
            return str(chosen["id"])
        return await self._resolve("address", 0)

    async def _table_coords(self, restaurant_index: Any) -> tuple[Any, Any]:
        """The searched restaurant's own lat/lng — required by get_restaurant_details
        and get_available_slots, neither documented nor optional in practice."""
        from app.services import components as comp

        rows = comp._rows_for("search_tables", self.convo.latest("search_tables"))
        row = rows[int(restaurant_index)] if rows else {}
        return comp._get(row, "latitude", "lat"), comp._get(row, "longitude", "lng")

    async def _dispatch(self, name: str, args: dict) -> Any:
        sid = self.sid
        if name == "list_addresses":
            return await live_mcp.get_addresses(sid)
        if name == "list_locations":
            return await live_mcp.get_saved_locations(sid)
        if name == "search_food_restaurants":
            addr = await self._resolve("address", args["address_index"])
            return await live_mcp.search_restaurants(sid, addr, args["query"])
        if name == "get_menu":
            rid = await self._resolve("food_restaurant", args["restaurant_index"])
            return await live_mcp.get_restaurant_menu(sid, rid, await self._active_address())
        if name == "search_menu":
            rid = await self._resolve("food_restaurant", args["restaurant_index"])
            return await live_mcp.search_menu(sid, rid, args["query"], await self._active_address())
        if name == "search_groceries":
            addr = await self._resolve("address", args["address_index"])
            return await live_mcp.search_products(sid, addr, args["query"])
        if name == "list_usual_groceries":
            addr = await self._resolve("address", args["address_index"])
            return await live_mcp.your_go_to_items(sid, addr)
        if name == "search_tables":
            addr = await self._resolve("address", args["address_index"])
            return await live_mcp.search_restaurants_dineout(sid, query=args["query"], address_id=addr)
        if name == "get_table_slots":
            rid = await self._resolve("table_restaurant", args["restaurant_index"])
            lat, lng = await self._table_coords(args["restaurant_index"])
            return await live_mcp.get_available_slots(sid, rid, args["date"], int(args["guests"]), lat, lng)
        if name == "food_coupons":
            return await live_mcp.fetch_food_coupons(sid)
        if name == "grocery_coupons":
            return await live_mcp.list_grocery_coupons(sid)
        if name == "my_food_orders":
            return await live_mcp.get_food_orders(sid)
        if name == "my_grocery_orders":
            return await live_mcp.get_orders(sid)
        if name == "track_food":
            oid = await self._resolve("food_order", args["order_index"])
            return await live_mcp.track_food_order(sid, oid)
        if name == "track_groceries":
            oid = await self._resolve("grocery_order", args["order_index"])
            return await live_mcp.track_grocery_order(sid, oid)
        if name == "food_order_details":
            oid = await self._resolve("food_order", args["order_index"])
            return await live_mcp.get_food_order_details(sid, oid)
        if name == "grocery_order_details":
            oid = await self._resolve("grocery_order", args["order_index"])
            return await live_mcp.get_grocery_order_details(sid, oid)
        if name == "table_details":
            rid = await self._resolve("table_restaurant", args["restaurant_index"])
            lat, lng = await self._table_coords(args["restaurant_index"])
            return await live_mcp.get_restaurant_details(sid, rid, lat, lng)
        if name == "food_payment_options":
            return await live_mcp.get_food_payment_options(sid, await self._active_address())
        if name == "grocery_payment_options":
            return await live_mcp.get_grocery_payment_options(sid)
        if name == "table_payment_options":
            return await live_mcp.get_table_payment_options(sid)
        raise ValueError(f"unknown tool {name}")

    async def run(self, message: str, retried: bool = False) -> AgentTurn:
        from app.services import components as comp

        started = time.perf_counter()
        tool_calls = 0
        handles: list[str] = []
        # Same call, same failure, twice in a turn means retrying is not going to
        # help. One turn spent 66s re-issuing a call Swiggy had already refused.
        failed: dict[str, int] = {}
        log.info('\u25b8 turn: "%s"%s', message[:120], " (retry)" if retried else "")
        if not retried:
            self.convo.add("user", message)
        header = f"{SYSTEM}\n\nCalendar:\n{_calendar(date.today())}"
        note = self.convo.context_note()
        if note:
            header += f"\n\n{note}"
        prompt = [{"role": "system", "content": header}, *self.convo.messages]

        try:
            for _ in range(MAX_STEPS):
                response = await self._complete(prompt)
                choice = response.choices[0].message
                calls = choice.tool_calls or []
                usage = getattr(response, "usage", None)
                if usage is not None:
                    log.debug(
                        "  model: %s in / %s out tokens",
                        getattr(usage, "prompt_tokens", "?"),
                        getattr(usage, "completion_tokens", "?"),
                    )

                if not calls:
                    text = (choice.content or "").strip()
                    if not text:
                        log.warning(
                            "  \u26a0 empty response (finish_reason=%s); ending turn",
                            getattr(response.choices[0], "finish_reason", "?"),
                        )
                        break

                    # The model sometimes writes the final_answer payload as plain
                    # text rather than calling the tool. Parse it rather than
                    # showing the user raw JSON.
                    payload = _as_final_answer(text)
                    if payload is not None:
                        log.warning("  \u26a0 final_answer arrived as text, not a tool call")
                        turn = comp.build(self.convo, payload)
                        log.info('  respond say="%s"', turn.say[:100])
                        log.info(
                            "\u25aa turn done in %.1fs, %d tool call(s)",
                            time.perf_counter() - started, tool_calls,
                        )
                        self.convo.add("assistant", turn.say)
                        return turn

                    auto = comp.auto_components(self.convo, handles)
                    log.info('  plain reply: "%s"%s', text[:100],
                             f"  (auto-rendered {auto[0].type})" if auto else "")
                    log.info(
                        "\u25aa turn done in %.1fs, %d tool call(s)",
                        time.perf_counter() - started, tool_calls,
                    )
                    self.convo.add("assistant", text)
                    return AgentTurn(say=text, components=auto)

                prompt.append(
                    {
                        "role": "assistant",
                        "content": choice.content or "",
                        "tool_calls": [
                            {
                                "id": c.id,
                                "type": "function",
                                "function": {"name": c.function.name, "arguments": c.function.arguments},
                            }
                            for c in calls
                        ],
                    }
                )

                for call in calls:
                    name = call.function.name
                    try:
                        args = json.loads(call.function.arguments or "{}")
                    except json.JSONDecodeError:
                        args = {}

                    if name in _FINISH_ALIASES:
                        turn = comp.build(self.convo, args)
                        asked = [c.get("type") for c in (args.get("components") or []) if isinstance(c, dict)]
                        rendered = [c.type for c in turn.components]
                        log.info('  respond say="%s"', turn.say[:100])
                        log.info(
                            "  components asked=%s rendered=%s%s",
                            asked or "[]",
                            rendered or "[]",
                            "  (some dropped: unresolvable source)" if len(rendered) < len(asked) else "",
                        )
                        log.info(
                            "\u25aa turn done in %.1fs, %d tool call(s)",
                            time.perf_counter() - started,
                            tool_calls,
                        )
                        self.convo.add("assistant", turn.say)
                        return turn

                    signature = f"{name}:{json.dumps(args, sort_keys=True, default=str)}"
                    if failed.get(signature, 0) >= 1:
                        log.warning("  \u21ba %s already failed with these arguments; refusing to repeat", name)
                        prompt.append({
                            "role": "tool", "tool_call_id": call.id, "name": name,
                            "content": json.dumps({
                                "error": "This exact call already failed. Do not repeat it — "
                                         "try different arguments or tell the user what went wrong."
                            }),
                        })
                        continue

                    tool_calls += 1
                    log.info("  \u2192 %s(%s)", name, _fmt_args(args))
                    t0 = time.perf_counter()
                    try:
                        payload = await self._dispatch(name, args)
                        handle = self.convo.remember(name, payload)
                        handles.append(handle)
                        log.info(
                            "  \u2190 %s  %s  %.0fms",
                            handle,
                            comp.summarise(name, payload),
                            (time.perf_counter() - t0) * 1000,
                        )
                        log.debug("    raw %s: %s", handle, json.dumps(payload, default=str)[:1500])
                        # The model sees a compact digest plus the handle; the full
                        # payload stays server-side for component materialisation.
                        content = json.dumps({"handle": handle, "result": comp.digest(name, payload)})[:4000]
                    except SwiggyToolError as exc:
                        failed[signature] = failed.get(signature, 0) + 1
                        log.warning("  \u2717 %s refused: %s", name, exc.message.split("\n")[0])
                        content = json.dumps({"error": exc.message})
                    except Exception as exc:  # noqa: BLE001 — the model should see and route around failures
                        failed[signature] = failed.get(signature, 0) + 1
                        log.warning("  \u2717 %s failed: %s", name, str(exc).split("\n")[0])
                        content = json.dumps({"error": str(exc)[:300]})

                    prompt.append({"role": "tool", "tool_call_id": call.id, "name": name, "content": content})
        except asyncio.TimeoutError:
            log.warning("agent turn timed out")
            return AgentTurn(say="That took too long. Try asking again?", components=[])
        except litellm.BadRequestError as exc:
            salvaged = _salvage(exc)
            if salvaged is None:
                # Last resort: the model wrote a usable sentence, it just wasn't a
                # tool call. Keep the sentence and render what the turn found.
                prose = _prose_from(exc)
                if prose:
                    log.warning("  \u26a0 kept the plain sentence the model was rejected for")
                    auto = comp.auto_components(self.convo, handles)
                    self.convo.add("assistant", prose)
                    return AgentTurn(say=prose, components=auto)
            if salvaged is not None:
                log.warning("  \u26a0 tool-name slip recovered from failed_generation")
                turn = comp.build(self.convo, salvaged)
                self.convo.add("assistant", turn.say)
                return turn
            log.warning("agent rejected by the model API: %s", exc)
            return AgentTurn(say="I got confused there. Try rephrasing?", components=[])
        except litellm.APIError as exc:
            log.warning("agent LLM call failed: %s", exc)
            return AgentTurn(say="I couldn't reach Swiggy's brain just then. Try again?", components=[])

        log.warning("  \u26a0 loop ended without a final answer after %d tool call(s)", tool_calls)
        auto = comp.auto_components(self.convo, handles)
        if auto:
            # Steps ran out but the turn did fetch something; show it rather than
            # discarding the work and asking the user to start over.
            return AgentTurn(say="Here's what I found.", components=auto)
        return AgentTurn(say="I couldn't work that one out. Could you rephrase?", components=[])
