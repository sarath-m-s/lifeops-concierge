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

import groq
from groq import AsyncGroq

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

TOOLS = [
    _tool("list_addresses", "The user's saved delivery addresses. Call before any food or grocery search.", {}, []),
    _tool("list_locations", "The user's saved locations for restaurant table search.", {}, []),
    _tool(
        "search_food_restaurants",
        "Search restaurants that deliver. `query` must be ONE term (a cuisine, dish type, or chain), never a sentence.",
        {"address_id": _STR, "query": _STR},
        ["address_id", "query"],
    ),
    _tool("get_menu", "Full menu for a delivery restaurant.", {"restaurant_id": _STR}, ["restaurant_id"]),
    _tool(
        "search_menu",
        "Search within one restaurant's menu.",
        {"restaurant_id": _STR, "query": _STR},
        ["restaurant_id", "query"],
    ),
    _tool(
        "search_groceries",
        "Search Instamart products. `query` is one item name.",
        {"address_id": _STR, "query": _STR},
        ["address_id", "query"],
    ),
    _tool(
        "list_usual_groceries",
        "The user's frequently-ordered groceries. Prefer this over searching for a reorder.",
        {"address_id": _STR},
        ["address_id"],
    ),
    _tool(
        "search_tables",
        "Search bookable restaurants. `query` is ONE term: a cuisine, area, chain, or vibe like 'rooftop'.",
        {"address_id": _STR, "query": _STR},
        ["address_id", "query"],
    ),
    _tool(
        "get_table_slots",
        "Available booking slots for a restaurant. Returns seven days at once — do not call again for another date.",
        {"restaurant_id": _STR, "date": _STR, "guests": {"type": "integer"}},
        ["restaurant_id", "date", "guests"],
    ),
    _tool("food_coupons", "Coupons available on food delivery right now.", {}, []),
    _tool("grocery_coupons", "Coupons available on Instamart right now.", {}, []),
    _tool("my_food_orders", "The user's recent food delivery orders.", {}, []),
    _tool("my_grocery_orders", "The user's recent Instamart orders.", {}, []),
    _tool("track_food", "Live delivery status for a food order.", {"order_id": _STR}, ["order_id"]),
    _tool("track_groceries", "Live delivery status for a grocery order.", {"order_id": _STR}, ["order_id"]),
    _tool(
        FINISH,
        (
            "Finish the turn. Say something brief and human, and choose which components to render. "
            "Always call this last. Never describe results in prose that a component already shows."
        ),
        {
            "say": {
                "type": "string",
                "description": "One or two natural sentences. No markdown, no lists — the components carry detail.",
            },
            "components": {
                "type": "array",
                "description": "Components to render, in order.",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {
                            "type": "string",
                            "enum": [
                                "restaurant_list",
                                "product_list",
                                "coupon_list",
                                "slot_list",
                                "address_list",
                                "order_list",
                                "order_status",
                                "confirm_action",
                                "chips",
                            ],
                        },
                        "source": {
                            "type": "string",
                            "description": "Handle of the tool result to render, e.g. 'search_food_restaurants#1'.",
                        },
                        "indexes": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "Which rows of that result to show. Omit for all.",
                        },
                        "action": {
                            "type": "string",
                            "enum": ["place_food_order", "checkout_instamart", "book_table"],
                            "description": "confirm_action only: which order to propose.",
                        },
                        "options": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "chips only: short follow-up suggestions.",
                        },
                    },
                    "required": ["type"],
                    "additionalProperties": False,
                },
            },
        },
        ["say", "components"],
    ),
]

_MUTATING = {"place_food_order", "checkout", "book_table", "update_food_cart", "update_cart"}
assert not (_MUTATING & {t["function"]["name"] for t in TOOLS}), "no mutating tool may reach the model"
assert FINISH in {t["function"]["name"] for t in TOOLS}


def _calendar(today: date, days: int = 8) -> str:
    return "\n".join(
        f"{(today + timedelta(days=o)).isoformat()} is {(today + timedelta(days=o)).strftime('%A')}"
        + (" (today)" if o == 0 else " (tomorrow)" if o == 1 else "")
        for o in range(days)
    )


SYSTEM = """You are a Swiggy concierge. You help with food delivery, groceries, and restaurant table bookings in India.

How to work:
- For a greeting or a vague opener, just say hello and offer a few chips. Do not call any tool.
- Resolve an address first. Food and groceries need an addressId; table search needs a saved location.
- The user has several saved addresses. If which one matters and you cannot tell, show an address_list and ask.
- Search queries take ONE term, never a sentence. "somewhere Italian in Indiranagar" is query "Italian".
  For a dish, search the cuisine that serves it: "dosa" becomes "South Indian".
- If a search returns nothing, say so plainly and suggest a different term or area. Do not invent results.
- When the user is ready to order, render a confirm_action. You cannot place orders yourself.
- Offer to check coupons before an order when it would save money.

How to talk:
- Brief and natural. One or two sentences.
- Never list restaurants, prices, or items in your text — the components display them. Say what you found and why it is worth their attention.
- Do not mention tools, ids, or internal steps.

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


def _salvage(exc: Exception) -> Optional[dict]:
    """Recover the intended answer from a rejected tool call.

    A wrong tool name fails validation *after* the model has already produced a
    perfectly good say/components payload. Groq returns it as `failed_generation`,
    so read it back rather than discarding the turn.
    """
    body = getattr(exc, "body", None) or {}
    raw = (body.get("error") or {}).get("failed_generation") if isinstance(body, dict) else None
    # Fall back to the stringified exception — the payload is in there either way.
    return _answer_from(raw or str(exc))


class Agent:
    def __init__(self, session_id: str, convo: Conversation):
        self.sid = session_id
        self.convo = convo
        self._client = AsyncGroq(api_key=settings.LLM_API_KEY.strip())

    async def _dispatch(self, name: str, args: dict) -> Any:
        sid = self.sid
        if name == "list_addresses":
            return await live_mcp.get_addresses(sid)
        if name == "list_locations":
            return await live_mcp.get_saved_locations(sid)
        if name == "search_food_restaurants":
            return await live_mcp.search_restaurants(sid, args["address_id"], args["query"])
        if name == "get_menu":
            return await live_mcp.get_restaurant_menu(sid, args["restaurant_id"])
        if name == "search_menu":
            return await live_mcp.search_menu(sid, args["restaurant_id"], args["query"])
        if name == "search_groceries":
            return await live_mcp.search_products(sid, args["address_id"], args["query"])
        if name == "list_usual_groceries":
            return await live_mcp.your_go_to_items(sid, args["address_id"])
        if name == "search_tables":
            return await live_mcp.search_restaurants_dineout(sid, query=args["query"], address_id=args["address_id"])
        if name == "get_table_slots":
            return await live_mcp.get_available_slots(sid, args["restaurant_id"], args["date"], int(args["guests"]))
        if name == "food_coupons":
            return await live_mcp.fetch_food_coupons(sid)
        if name == "grocery_coupons":
            return await live_mcp.list_grocery_coupons(sid)
        if name == "my_food_orders":
            return await live_mcp.get_food_orders(sid)
        if name == "my_grocery_orders":
            return await live_mcp.get_orders(sid)
        if name == "track_food":
            return await live_mcp.track_food_order(sid, args["order_id"])
        if name == "track_groceries":
            return await live_mcp.track_grocery_order(sid, args["order_id"])
        raise ValueError(f"unknown tool {name}")

    async def run(self, message: str) -> AgentTurn:
        from app.services import components as comp

        started = time.perf_counter()
        tool_calls = 0
        log.info('\u25b8 turn: "%s"', message[:120])
        self.convo.add("user", message)
        prompt = [
            {"role": "system", "content": f"{SYSTEM}\n\nCalendar:\n{_calendar(date.today())}"},
            *self.convo.messages,
        ]

        try:
            for _ in range(MAX_STEPS):
                response = await asyncio.wait_for(
                    self._client.chat.completions.create(
                        model=settings.LLM_MODEL,
                        messages=prompt,
                        tools=TOOLS,
                        tool_choice="auto",
                        temperature=0,
                        max_completion_tokens=1400,
                    ),
                    timeout=_TURN_TIMEOUT,
                )
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

                    log.info('  plain reply: "%s"', text[:100])
                    log.info(
                        "\u25aa turn done in %.1fs, %d tool call(s)",
                        time.perf_counter() - started, tool_calls,
                    )
                    self.convo.add("assistant", text)
                    return AgentTurn(say=text, components=[])

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

                    tool_calls += 1
                    log.info("  \u2192 %s(%s)", name, _fmt_args(args))
                    t0 = time.perf_counter()
                    try:
                        payload = await self._dispatch(name, args)
                        handle = self.convo.remember(name, payload)
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
                        log.warning("  \u2717 %s refused: %s", name, exc.message)
                        content = json.dumps({"error": exc.message})
                    except Exception as exc:  # noqa: BLE001 — the model should see and route around failures
                        log.warning("  \u2717 %s failed: %s", name, exc)
                        content = json.dumps({"error": str(exc)[:300]})

                    prompt.append({"role": "tool", "tool_call_id": call.id, "name": name, "content": content})
        except asyncio.TimeoutError:
            log.warning("agent turn timed out")
            return AgentTurn(say="That took too long. Try asking again?", components=[])
        except groq.BadRequestError as exc:
            salvaged = _salvage(exc)
            if salvaged is not None:
                log.warning("  \u26a0 tool-name slip recovered from failed_generation")
                turn = comp.build(self.convo, salvaged)
                self.convo.add("assistant", turn.say)
                return turn
            log.warning("agent rejected by the model API: %s", exc)
            return AgentTurn(say="I got confused there. Try rephrasing?", components=[])
        except groq.APIError as exc:
            log.warning("agent LLM call failed: %s", exc)
            return AgentTurn(say="I couldn't reach Swiggy's brain just then. Try again?", components=[])
        finally:
            await self._client.close()

        return AgentTurn(say="I couldn't work that one out. Could you rephrase?", components=[])
