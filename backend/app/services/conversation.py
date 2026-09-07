"""Per-session conversation state.

The old design classified each message independently, so "any coupons for that?"
had no "that". The agent needs the transcript plus the raw tool results from
earlier turns, because a later turn routinely refers to something found earlier.

Tool results are kept verbatim and referenced by handle. The model picks *what*
to show by naming a handle and an index; the server materialises the actual
values. That way a restaurant name, a price, or an item id can never be something
the model invented — which matters when the next step spends money.
"""
import time
from dataclasses import dataclass, field
from typing import Any, Optional

# Keep the prompt bounded. Older turns fall out; the tool-result cache below is
# what carries forward the facts that matter.
MAX_TURNS = 24
MAX_RESULTS = 40
IDLE_TTL_SECONDS = 60 * 60


@dataclass
class Conversation:
    session_id: str
    messages: list[dict] = field(default_factory=list)
    # handle -> raw tool payload, e.g. "search_food_restaurants#1"
    results: dict[str, Any] = field(default_factory=dict)
    order: list[str] = field(default_factory=list)
    # Sticky facts for the whole conversation, e.g. the chosen delivery address.
    state: dict[str, Any] = field(default_factory=dict)
    touched_at: float = field(default_factory=time.time)

    def add(self, role: str, content: Any, **extra: Any) -> None:
        message = {"role": role, "content": content}
        message.update(extra)
        self.messages.append(message)
        if len(self.messages) > MAX_TURNS:
            self.messages = self.messages[-MAX_TURNS:]
        self.touched_at = time.time()

    def remember(self, tool: str, payload: Any) -> str:
        """Store a tool result and return the handle the model can refer to."""
        index = sum(1 for h in self.order if h.rsplit("#", 1)[0] == tool) + 1
        handle = f"{tool}#{index}"
        self.results[handle] = payload
        self.order.append(handle)
        while len(self.order) > MAX_RESULTS:
            self.results.pop(self.order.pop(0), None)
        return handle

    def recall(self, handle: str) -> Any:
        return self.results.get(handle)

    def latest(self, tool: str) -> Optional[Any]:
        for handle in reversed(self.order):
            if handle.rsplit("#", 1)[0] == tool:
                return self.results[handle]
        return None

    def context_note(self) -> str:
        """A running summary of what is already known.

        Without this the model re-derives everything each turn: it re-fetched the
        address list five turns running, and when the user typed "Popeyes" — a
        name already on screen — it ran a fresh search instead of selecting row 0.
        Restating the current address and the last list it was shown makes both
        the obvious move.
        """
        from app.services import components as comp

        lines: list[str] = []

        address = self.state.get("address")
        if address:
            lines.append(f'Delivery address already chosen: "{address["label"]}" (address_index={address["index"]}).')

        for tool, label in (
            ("search_food_restaurants", "Delivery restaurants"),
            ("search_tables", "Bookable restaurants"),
            ("search_groceries", "Grocery products"),
            ("list_usual_groceries", "Usual groceries"),
            ("get_table_slots", "Table slots"),
        ):
            payload = self.latest(tool)
            if payload is None:
                continue
            rows = comp._rows_for(tool, payload)[:6]
            if not rows:
                continue
            named = ", ".join(
                f"[{i}] {comp._get(r, 'name', 'displayName', 'displayTime', default='?')}"
                for i, r in enumerate(rows)
            )
            lines.append(f"{label} you already showed: {named}")

        if not lines:
            return ""
        return (
            "Context so far — reuse this instead of fetching it again:\n"
            + "\n".join(lines)
            + "\nIf the user names one of these, use its number. Do not search again for something already listed."
        )


class ConversationStore:
    """ponytail: process-local, same ceiling as the token store. Both move to
    Postgres together — until then a restart loses history, not correctness."""

    def __init__(self) -> None:
        self._items: dict[str, Conversation] = {}

    def get(self, session_id: str) -> Conversation:
        self._prune()
        convo = self._items.get(session_id)
        if convo is None:
            convo = Conversation(session_id=session_id)
            self._items[session_id] = convo
        convo.touched_at = time.time()
        return convo

    def reset(self, session_id: str) -> None:
        self._items.pop(session_id, None)

    def _prune(self) -> None:
        cutoff = time.time() - IDLE_TTL_SECONDS
        for sid in [s for s, c in self._items.items() if c.touched_at < cutoff]:
            self._items.pop(sid, None)


store = ConversationStore()
