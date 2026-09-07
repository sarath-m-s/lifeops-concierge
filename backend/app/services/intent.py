"""Intent extraction from a natural-language utterance.

One structured Groq call per user message. Groq's structured outputs constrain the
response to a JSON schema, so there is no prose to strip and no JSON to repair —
the payload either validates against ParsedIntent or we fall back.

Swiggy's search tools want a single search term ("Italian", "Indiranagar",
"rooftop"), explicitly not the user's sentence. Extracting that term is the whole
reason this call exists: the keyword matcher it replaces passed whole sentences
through and only worked on the one rehearsed phrasing.

`_keyword_intent` remains as the fallback for a missing key, a network failure, or
an unparseable response. It is a real (if blunt) implementation, not a mock — the
app stays usable when the model is unreachable, which on a demo stage matters more
than elegance.
"""
import asyncio
import logging
from datetime import date, timedelta
from typing import Literal, Optional

import groq
from groq import AsyncGroq
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.config import settings

log = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 12.0

IntentKind = Literal["plan_evening", "food_order", "dineout", "instamart", "general"]


class ParsedIntent(BaseModel):
    # Strict structured outputs require additionalProperties:false, which is what
    # extra="forbid" emits. Every field is required (none carries a default) —
    # also a strict-mode requirement; "unstated" is expressed as null, not absence.
    model_config = ConfigDict(extra="forbid")

    intent: IntentKind = Field(description="Which Swiggy journey the user is asking for.")
    search_term: str = Field(
        description=(
            "The single thing to search for — a cuisine, area, restaurant name, or vibe "
            "such as 'Italian', 'Indiranagar', 'rooftop'. Never the user's whole sentence. "
            "For a dish, use the cuisine that serves it ('dosa' becomes 'South Indian'). "
            "Empty string when the intent is general."
        )
    )
    party_size: int = Field(description="Number of people dining. Use 2 when unstated.")
    booking_date: Optional[str] = Field(
        description="Date for a table booking as YYYY-MM-DD, resolved against today's date. Null if unstated."
    )
    booking_time: Optional[str] = Field(
        description="Preferred time as 24-hour HH:MM. Null if unstated."
    )
    dessert_term: Optional[str] = Field(
        description="What to order for delivery, when delivery was requested alongside a booking. Null otherwise."
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

Resolve relative dates ("Friday", "tomorrow") using the calendar supplied below —
look the weekday up, do not calculate it. Use null when the user did not say
something; do not invent times or dates.

Reply with JSON only."""


def _calendar(today: date, days: int = 8) -> str:
    """Spell out the next week by name.

    Models are unreliable at calendar arithmetic — asked for "Friday" from a
    Monday, the model returned the Wednesday. Turning the arithmetic into a
    lookup removes the whole error class for the cost of a few tokens.
    """
    lines = [
        f"{(today + timedelta(days=offset)).isoformat()} is "
        f"{(today + timedelta(days=offset)).strftime('%A')}"
        + (" (today)" if offset == 0 else " (tomorrow)" if offset == 1 else "")
        for offset in range(days)
    ]
    return "\n".join(lines)


def _client() -> Optional[AsyncGroq]:
    if not settings.llm_enabled:
        return None
    return AsyncGroq(api_key=settings.LLM_API_KEY.strip())


def _schema_param(strict: bool) -> dict:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "parsed_intent",
            "strict": strict,
            "schema": ParsedIntent.model_json_schema(),
        },
    }


async def parse_intent(message: str) -> ParsedIntent:
    """Extract intent, falling back to keyword matching if the model is unavailable."""
    client = _client()
    if client is None:
        log.info("No LLM_API_KEY configured; using keyword intent fallback")
        return _keyword_intent(message)

    messages = [
        {"role": "system", "content": f"{_SYSTEM}\n\nCalendar:\n{_calendar(date.today())}"},
        {"role": "user", "content": message},
    ]

    try:
        raw = await asyncio.wait_for(_complete(client, messages, strict=True), timeout=_TIMEOUT_SECONDS)
    except groq.BadRequestError as exc:
        # Strict mode rejects schemas some models won't compile. Best-effort mode
        # accepts them and may return schema-invalid JSON, which the validation
        # below catches — better than dropping straight to keyword matching.
        log.warning("Strict structured output rejected (%s); retrying best-effort", exc)
        try:
            raw = await asyncio.wait_for(_complete(client, messages, strict=False), timeout=_TIMEOUT_SECONDS)
        except (asyncio.TimeoutError, groq.APIError) as retry_exc:
            log.warning("Intent extraction failed (%s); falling back to keywords", retry_exc)
            return _keyword_intent(message)
    except (asyncio.TimeoutError, groq.APIError) as exc:
        log.warning("Intent extraction failed (%s); falling back to keywords", exc)
        return _keyword_intent(message)
    finally:
        await client.close()

    if not raw:
        log.warning("Intent extraction returned empty content; falling back to keywords")
        return _keyword_intent(message)

    try:
        return ParsedIntent.model_validate_json(raw)
    except ValidationError as exc:
        log.warning("Intent payload did not validate (%s); falling back to keywords", exc)
        return _keyword_intent(message)


async def _complete(client: AsyncGroq, messages: list[dict], strict: bool) -> Optional[str]:
    response = await client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=messages,
        response_format=_schema_param(strict),
        # Extraction is deterministic work; sampling variance is pure downside here.
        temperature=0,
        max_completion_tokens=600,
    )
    return response.choices[0].message.content


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
