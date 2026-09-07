"""The voice agent worker entrypoint.

Run locally against a terminal mic/speaker (no LiveKit networking, fastest loop
for checking tool calls and index-resolution):

    python -m app.voice.worker console

Run against a real LiveKit Cloud project, driven from the Agents Playground:

    python -m app.voice.worker dev

Deploy as a long-running process (Render Background Worker or equivalent):

    python -m app.voice.worker start
"""
import asyncio
import json
import logging

from livekit import agents
from livekit.agents import (
    Agent,
    AgentSession,
    ConversationItemAddedEvent,
    JobContext,
    WorkerOptions,
)
from livekit.agents.llm import ChatMessage
from livekit.protocol.models import DataPacket

from app.config import settings
from app.services import conversation
from app.voice.session import build_session
from app.voice.tools import ConciergeAgent

log = logging.getLogger(__name__)

# Custom topics. `lifeops.turn` carries the combined {say, components} payload —
# the exact AgentTurn shape the mobile app already knows how to render — published
# once per finished turn regardless of whether it started from voice or lk.chat
# text. `lifeops.confirm_result` is the one topic the *web process* (not a room
# participant) sends into the room via the server API after /confirm succeeds;
# built-in topics (lk.chat, lk.transcription) need no handling here at all — the
# framework's default text-input/transcription behavior already covers them.
TURN_TOPIC = "lifeops.turn"
CONFIRM_RESULT_TOPIC = "lifeops.confirm_result"


def _publish_turn(ctx: JobContext, say: str, components: list[dict]) -> None:
    payload = json.dumps({"say": say, "components": components})
    asyncio.create_task(ctx.room.local_participant.send_text(payload, topic=TURN_TOPIC))


def _wire_turn_publisher(ctx: JobContext, session: AgentSession, agent: ConciergeAgent) -> None:
    """Bundle the LLM's final reply with whatever show_components staged this
    turn into one lifeops.turn message, whenever an assistant item lands in the
    chat history — the natural turn-boundary signal, whether that turn started
    from STT or from typed lk.chat text."""

    @session.on("conversation_item_added")
    def _on_item(event: ConversationItemAddedEvent) -> None:
        if not isinstance(event.item, ChatMessage) or event.item.role != "assistant":
            return
        say = event.item.text_content or ""
        components = agent.pop_pending_components()
        if not say and not components:
            return  # nothing to show for this item (e.g. a tool-call-only turn)
        _publish_turn(ctx, say, components)


def _wire_confirm_result_listener(ctx: JobContext, session: AgentSession) -> None:
    """/confirm (web process, plain REST) signals the room on success via the
    LiveKit server API — it is not a room participant, so this arrives as a raw
    data packet (packet.participant is None), not a text stream. The worker
    speaks the deterministic result verbatim; session.say()'s resulting chat
    item flows through the same conversation_item_added hook above, so it also
    lands in the mobile transcript without any extra publish here."""

    @ctx.room.on("data_received")
    def _on_data(packet: DataPacket) -> None:
        if packet.topic != CONFIRM_RESULT_TOPIC:
            return
        try:
            payload = json.loads(packet.data.decode("utf-8"))
            say = str(payload["say"])
        except (ValueError, KeyError, UnicodeDecodeError) as exc:
            log.warning("bad %s payload: %s", CONFIRM_RESULT_TOPIC, exc)
            return
        session.say(say)


async def entrypoint(ctx: JobContext) -> None:
    await ctx.connect()
    participant = await ctx.wait_for_participant()
    session_id = participant.identity
    log.info("voice agent joined room %s for session %s…", ctx.room.name, session_id[:8])

    convo = conversation.store.get(session_id)
    agent = ConciergeAgent(session_id, convo)
    session = build_session()

    _wire_turn_publisher(ctx, session, agent)
    _wire_confirm_result_listener(ctx, session)

    await session.start(agent=agent, room=ctx.room)


if __name__ == "__main__":
    agents.cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            ws_url=settings.LIVEKIT_URL,
            api_key=settings.LIVEKIT_API_KEY,
            api_secret=settings.LIVEKIT_API_SECRET,
        )
    )
