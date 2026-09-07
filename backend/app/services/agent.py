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
_TURN_TIMEOUT = 45.0


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
        "respond",
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


def _calendar(today: date, days: int = 8) -> str:
    return "\n".join(
        f"{(today + timedelta(days=o)).isoformat()} is {(today + timedelta(days=o)).strftime('%A')}"
        + (" (today)" if o == 0 else " (tomorrow)" if o == 1 else "")
        for o in range(days)
    )


SYSTEM = """You are a Swiggy concierge. You help with food delivery, groceries, and restaurant table bookings in India.

How to work:
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

Always finish by calling respond."""


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

                if not calls:
                    # The model answered in prose without finishing properly.
                    text = (choice.content or "").strip()
                    if text:
                        self.convo.add("assistant", text)
                        return AgentTurn(say=text, components=[])
                    break

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

                    if name == "respond":
                        turn = comp.build(self.convo, args)
                        self.convo.add("assistant", turn.say)
                        return turn

                    try:
                        payload = await self._dispatch(name, args)
                        handle = self.convo.remember(name, payload)
                        # The model sees a compact digest plus the handle; the full
                        # payload stays server-side for component materialisation.
                        content = json.dumps({"handle": handle, "result": comp.digest(name, payload)})[:4000]
                    except SwiggyToolError as exc:
                        content = json.dumps({"error": exc.message})
                    except Exception as exc:  # noqa: BLE001 — the model should see and route around failures
                        log.warning("tool %s failed: %s", name, exc)
                        content = json.dumps({"error": str(exc)[:300]})

                    prompt.append({"role": "tool", "tool_call_id": call.id, "name": name, "content": content})
        except asyncio.TimeoutError:
            log.warning("agent turn timed out")
            return AgentTurn(say="That took too long. Try asking again?", components=[])
        except groq.APIError as exc:
            log.warning("agent LLM call failed: %s", exc)
            return AgentTurn(say="I couldn't reach my brain just then. Try again?", components=[])
        finally:
            await self._client.close()

        return AgentTurn(say="I couldn't work that one out. Could you rephrase?", components=[])
