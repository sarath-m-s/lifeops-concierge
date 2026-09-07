"""Intent extraction from a natural-language utterance.

One structured Claude call per user message. Structured outputs guarantee the
response validates against ParsedIntent, so there is no JSON parsing or repair
here — a malformed shape is impossible rather than handled.

Swiggy's search tools want a single search term ("Italian", "Indiranagar",
"rooftop"), explicitly not the user's sentence. Extracting that term is the whole
reason this call exists: the keyword matcher it replaces passed whole sentences
through and only worked on the one rehearsed phrasing.

`_keyword_intent` remains as the fallback for a missing key, a network failure,
or a refusal. It is a real (if blunt) implementation, not a mock — the app stays
usable when the LLM is unreachable, which on a demo stage matters more than
elegance.
"""
import asyncio
import logging
from datetime import date, timedelta
from typing import Literal, Optional

import anthropic
from pydantic import BaseModel, Field

from app.config import settings

log = logging.getLogger(__name__)

MODEL = "claude-opus-5"
_TIMEOUT_SECONDS = 12.0

IntentKind = Literal["plan_evening", "food_order", "dineout", "instamart", "general"]


class ParsedIntent(BaseModel):
    intent: IntentKind = Field(description="Which Swiggy journey the user is asking for.")
    search_term: str = Field(
        description=(
            "The single thing to search for — a cuisine, area, restaurant name, or vibe "
            "such as 'Italian', 'Indiranagar', 'rooftop'. Never the user's whole sentence. "
            "For a dish, use the cuisine that serves it ('dosa' becomes 'South Indian'). "
            "Empty string when the intent is general."
        )
    )
    party_size: int = Field(description="Number of people dining. Default 2 when unstated.")
    booking_date: Optional[str] = Field(
        description="Date for a table booking as YYYY-MM-DD, resolved against today's date. Null if unstated."
    )
    booking_time: Optional[str] = Field(
        description="Preferred time as 24-hour HH:MM. Null if unstated."
    )
    dessert_term: Optional[str] = Field(
        description="What to order for delivery, when the user asked for delivery alongside a booking. Null otherwise."
    )
    grocery_terms: list[str] = Field(
        description="Grocery items to restock, one search term each. Empty list if none requested."
    )


_SYSTEM = """You extract structured intent from a user talking to a Swiggy concierge.

Pick exactly one intent:
- plan_evening: wants several things at once — a table AND delivery AND/OR groceries
- dineout: wants to book a table at a restaurant
- food_order: wants food delivered
- instamart: wants groceries
- general: greeting, unclear, or unrelated

The search_term field feeds Swiggy's search directly, and Swiggy expects one term,
not a sentence. "somewhere Italian in Indiranagar for dinner" has a search_term of
"Italian". "any good rooftop places" has a search_term of "rooftop".

Resolve relative dates ("Friday", "tomorrow") against today's date into YYYY-MM-DD.
Leave a field null when the user did not say it — do not invent times or dates."""


def _client() -> Optional[anthropic.AsyncAnthropic]:
    if not settings.llm_enabled:
        return None
    return anthropic.AsyncAnthropic(api_key=settings.LLM_API_KEY.strip())


async def parse_intent(message: str) -> ParsedIntent:
    """Extract intent, falling back to keyword matching if the model is unavailable."""
    client = _client()
    if client is None:
        log.info("No LLM_API_KEY configured; using keyword intent fallback")
        return _keyword_intent(message)

    try:
        response = await asyncio.wait_for(
            client.messages.parse(
                model=MODEL,
                max_tokens=2048,  # thinking and output share this budget
                # Effort is the latency lever for a voice surface. Extraction is a
                # shallow task; low keeps the round trip short without hurting it.
                output_config={"effort": "low"},
                system=f"{_SYSTEM}\n\nToday's date is {date.today().isoformat()}.",
                messages=[{"role": "user", "content": message}],
                output_format=ParsedIntent,
            ),
            timeout=_TIMEOUT_SECONDS,
        )
    except (asyncio.TimeoutError, anthropic.APIError) as exc:
        log.warning("Intent extraction failed (%s); falling back to keywords", exc)
        return _keyword_intent(message)
    finally:
        await client.close()

    # A refusal returns HTTP 200 with no parsed output — guard before reading it.
    if response.stop_reason == "refusal" or response.parsed_output is None:
        log.warning("Intent extraction returned no parsed output (stop_reason=%s)", response.stop_reason)
        return _keyword_intent(message)

    return response.parsed_output


def _keyword_intent(message: str) -> ParsedIntent:
    """Blunt fallback. Handles the common phrasings; misses anything unusual."""
    msg = message.lower()

    def _default_friday() -> str:
        today = date.today()
        return (today + timedelta(days=(4 - today.weekday()) % 7 or 7)).isoformat()

    plan_evening = (
        ("evening" in msg or "dinner" in msg)
        and "dessert" in msg
        and any(w in msg for w in ("coffee", "restock", "grocery", "groceries", "instamart"))
    )
    if plan_evening:
        return ParsedIntent(
            intent="plan_evening",
            search_term="Italian" if "italian" in msg else "dinner",
            party_size=2,
            booking_date=_default_friday(),
            booking_time="20:00",
            dessert_term="dessert",
            grocery_terms=["coffee"],
        )

    base = dict(party_size=2, booking_date=None, booking_time=None, dessert_term=None, grocery_terms=[])
    if any(w in msg for w in ("order food", "delivery", "hungry", "food delivery")):
        return ParsedIntent(intent="food_order", search_term=message, **base)
    if any(w in msg for w in ("book", "table", "reservation", "dine", "restaurant")):
        return ParsedIntent(intent="dineout", search_term=message, **base)
    if any(w in msg for w in ("grocery", "restock", "instamart", "buy", "milk", "bread")):
        return ParsedIntent(intent="instamart", search_term=message, **base)
    return ParsedIntent(intent="general", search_term="", **base)
