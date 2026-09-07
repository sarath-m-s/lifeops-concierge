"""The voice agent's brain: read-only Swiggy tools plus the safety invariants
carried over unchanged from the old text agent (app/services/agent.py):

1. No mutating tool (place_food_order, checkout, book_table, update_food_cart,
   update_cart) is ever registered here. Asserted at class-definition time below,
   same shape as the old assertion — mutations only happen via /confirm, after an
   explicit user tap on a confirm_action component.

2. The model never supplies data or identifiers. It refers to a cached tool
   result by index; `_resolve` reads the real value out of that cached payload.
   A restaurant name, price, or item id can never be something the model made up.

Unlike the old agent.py, there is no hand-rolled malformed-tool-envelope recovery
code here — that existed only because Groq's gpt-oss-20b produced broken tool-call
JSON. LiveKit Agents drives the tool loop itself against a model with reliable
native function calling, so that whole class of problem doesn't apply.
"""
import logging
from datetime import date, timedelta
from typing import Any

from livekit.agents import Agent, function_tool
from livekit.agents.llm.tool_context import FunctionTool

from app.services import components as comp
from app.services import live_mcp
from app.services.conversation import Conversation
from app.services.swiggy_mcp import SwiggyToolError

log = logging.getLogger(__name__)

_IDX_HELP = "Row number from the list you were shown (0 is the first)."


def _calendar(today: date, days: int = 8) -> str:
    return "\n".join(
        f"{(today + timedelta(days=o)).isoformat()} is {(today + timedelta(days=o)).strftime('%A')}"
        + (" (today)" if o == 0 else " (tomorrow)" if o == 1 else "")
        for o in range(days)
    )


SYSTEM = """You are a Swiggy concierge. You help with food delivery, groceries, and restaurant table bookings in India, over voice or text.

How to work:
- You never see raw ids. Every list you get back is numbered from 0, and you refer to a
  row by its number — address_index, restaurant_index, order_index. Pass the number, not a name.
- If the user names something you already listed ("Popeyes", "the second one"), that is a
  selection, not a new search. Use its number with get_menu or get_table_slots.
- Never re-fetch something the context block above already gives you.
- For a greeting or a vague opener, just say hello and offer a few suggestions. Do not call any tool.
- Resolve an address first. Food and groceries need an addressId; table search needs a saved location.
- The user has several saved addresses. If which one matters and you cannot tell, show an address_list and ask.
- Search queries take ONE term, never a sentence. "somewhere Italian in Indiranagar" is query "Italian".
  For a dish, search the cuisine that serves it: "dosa" becomes "South Indian".
- If a search returns nothing, say so plainly and suggest a different term or area. Do not invent results.
- When the user is ready to order, call show_components with a confirm_action. You cannot place orders yourself.
- Offer to check coupons before an order when it would save money.
- Whenever you find something worth showing (a restaurant list, a menu, slots, coupons, a
  confirm_action, follow-up suggestions), call show_components with the right entries — this
  renders on the user's screen. Call it whenever it's useful; it doesn't interrupt your speech.

How to talk:
- Brief and natural. One or two sentences, meant to be heard, not read.
- Never read out restaurant names, prices, or item lists aloud — the screen shows them. Say what
  you found and why it's worth their attention, e.g. "Found a few good Italian spots nearby."
- Do not mention tools, ids, or internal steps."""


class ConciergeAgent(Agent):
    def __init__(self, session_id: str, convo: Conversation):
        super().__init__(instructions=f"{SYSTEM}\n\nCalendar:\n{_calendar(date.today())}")
        self.sid = session_id
        self.convo = convo
        self._pending_components: list[dict] = []

    def pop_pending_components(self):
        """Drain and return whatever show_components staged this turn."""
        out, self._pending_components = self._pending_components, []
        return out

    # --- safety: index -> real id, unchanged from the old agent -------------

    async def _resolve(self, kind: str, index: Any) -> str:
        """Turn a row number into the real identifier.

        The model is never given raw ids — the digest strips them — so it refers
        to rows positionally and the lookup happens here against the cached
        payload. If the underlying list has not been fetched yet, fetch it, so a
        skipped step degrades into an extra call rather than a dead end.
        """
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
            log.info("  ↳ auto-fetched %s to resolve %s #%s", tool, kind, index)

        rows = comp._rows_for(tool, payload) if payload is not None else []
        if not rows:
            raise SwiggyToolError(
                "I don't have a list to pick that from yet — search first, then choose a row."
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

    def _record(self, tool: str, payload: Any) -> dict:
        """Remember a tool result and return the compact, id-free view the model sees."""
        handle = self.convo.remember(tool, payload)
        log.info("  ← %s  %s", handle, comp.summarise(tool, payload))
        return {"handle": handle, "result": comp.digest(tool, payload)}

    # --- read-only Swiggy tools ----------------------------------------------

    @function_tool
    async def list_addresses(self) -> dict:
        """The user's saved delivery addresses. Call before any food or grocery search."""
        return self._record("list_addresses", await live_mcp.get_addresses(self.sid))

    @function_tool
    async def list_locations(self) -> dict:
        """The user's saved locations for restaurant table search."""
        return self._record("list_locations", await live_mcp.get_saved_locations(self.sid))

    @function_tool
    async def search_food_restaurants(self, address_index: int, query: str) -> dict:
        """Search restaurants that deliver.

        Args:
            address_index: Row number from the address list you were shown.
            query: ONE term — a cuisine, dish type, or chain, never a sentence.
        """
        addr = await self._resolve("address", address_index)
        return self._record("search_food_restaurants", await live_mcp.search_restaurants(self.sid, addr, query))

    @function_tool
    async def get_menu(self, restaurant_index: int) -> dict:
        """Full menu for a delivery restaurant you searched for.

        Args:
            restaurant_index: Row number from the restaurant list you were shown.
        """
        rid = await self._resolve("food_restaurant", restaurant_index)
        return self._record("get_menu", await live_mcp.get_restaurant_menu(self.sid, rid))

    @function_tool
    async def search_menu(self, restaurant_index: int, query: str) -> dict:
        """Search within one restaurant's menu.

        Args:
            restaurant_index: Row number from the restaurant list you were shown.
            query: The dish or item to look for.
        """
        rid = await self._resolve("food_restaurant", restaurant_index)
        return self._record("search_menu", await live_mcp.search_menu(self.sid, rid, query))

    @function_tool
    async def search_groceries(self, address_index: int, query: str) -> dict:
        """Search Instamart products.

        Args:
            address_index: Row number from the address list you were shown.
            query: One item name.
        """
        addr = await self._resolve("address", address_index)
        return self._record("search_groceries", await live_mcp.search_products(self.sid, addr, query))

    @function_tool
    async def list_usual_groceries(self, address_index: int) -> dict:
        """The user's frequently-ordered groceries. Prefer this over searching for a reorder.

        Args:
            address_index: Row number from the address list you were shown.
        """
        addr = await self._resolve("address", address_index)
        return self._record("list_usual_groceries", await live_mcp.your_go_to_items(self.sid, addr))

    @function_tool
    async def search_tables(self, address_index: int, query: str) -> dict:
        """Search bookable restaurants.

        Args:
            address_index: Row number from the address/location list you were shown.
            query: ONE term — a cuisine, area, chain, or vibe like "rooftop".
        """
        addr = await self._resolve("address", address_index)
        return self._record(
            "search_tables", await live_mcp.search_restaurants_dineout(self.sid, query=query, address_id=addr)
        )

    @function_tool
    async def get_table_slots(self, restaurant_index: int, date: str, guests: int) -> dict:
        """Available booking slots for a restaurant. Returns seven days at once — do not
        call again for another date.

        Args:
            restaurant_index: Row number from the restaurant list you were shown.
            date: Date to check, YYYY-MM-DD.
            guests: Party size.
        """
        rid = await self._resolve("table_restaurant", restaurant_index)
        return self._record("get_table_slots", await live_mcp.get_available_slots(self.sid, rid, date, int(guests)))

    @function_tool
    async def food_coupons(self) -> dict:
        """Coupons available on food delivery right now."""
        return self._record("food_coupons", await live_mcp.fetch_food_coupons(self.sid))

    @function_tool
    async def grocery_coupons(self) -> dict:
        """Coupons available on Instamart right now."""
        return self._record("grocery_coupons", await live_mcp.list_grocery_coupons(self.sid))

    @function_tool
    async def my_food_orders(self) -> dict:
        """The user's recent food delivery orders."""
        return self._record("my_food_orders", await live_mcp.get_food_orders(self.sid))

    @function_tool
    async def my_grocery_orders(self) -> dict:
        """The user's recent Instamart orders."""
        return self._record("my_grocery_orders", await live_mcp.get_orders(self.sid))

    @function_tool
    async def track_food(self, order_index: int) -> dict:
        """Live delivery status for a food order.

        Args:
            order_index: Row number from the food order list you were shown.
        """
        oid = await self._resolve("food_order", order_index)
        return self._record("track_food", await live_mcp.track_food_order(self.sid, oid))

    @function_tool
    async def track_groceries(self, order_index: int) -> dict:
        """Live delivery status for a grocery order.

        Args:
            order_index: Row number from the grocery order list you were shown.
        """
        oid = await self._resolve("grocery_order", order_index)
        return self._record("track_groceries", await live_mcp.track_grocery_order(self.sid, oid))

    # --- rendering: the voice-agent equivalent of the old final_answer's
    # `components` array. Spoken text comes from the LLM's normal reply and is
    # handled outside this class (see worker.py's conversation_item_added hook,
    # which bundles it with whatever this tool staged into one lifeops.turn
    # message) — this tool only stages what should render on screen. -----------

    @function_tool
    async def show_components(self, components: list[dict]) -> str:
        """Render one or more components on the user's screen — restaurant lists,
        menus, slots, coupons, a confirm_action, or follow-up suggestion chips.
        Call this whenever you have something worth showing; it does not
        interrupt your spoken reply.

        Args:
            components: Render instructions, e.g.
                [{"type": "restaurant_list", "source": "search_food_restaurants#1"}]
                or [{"type": "confirm_action", "source": "get_menu#1", "indexes": [0,2], "action": "place_food_order"}]
                or [{"type": "chips", "options": ["Check coupons", "Something cheaper"]}].
        """
        resolved = comp.build_components(self.convo, components)
        self._pending_components.extend(c.model_dump() for c in resolved)
        return f"staged {len(resolved)} component(s)"


# Hard invariant: no mutating tool may ever be reachable from the model. Checked
# at class-definition time (no instance needed — @function_tool-decorated methods
# are FunctionTool instances directly on the class), same intent as the old
# agent.py:184 assertion, just against the new tool-registration shape.
_MUTATING = {"place_food_order", "checkout", "checkout_instamart", "book_table", "update_food_cart", "update_cart"}
_registered = {v.info.name for v in vars(ConciergeAgent).values() if isinstance(v, FunctionTool)}
assert not (_MUTATING & _registered), f"mutating tool leaked into the model's toolset: {_MUTATING & _registered}"
assert "show_components" in _registered
