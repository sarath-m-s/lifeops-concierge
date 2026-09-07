"""Builds the AgentSession: Deepgram STT, Cartesia TTS, Silero VAD, OpenAI LLM.

A cascaded pipeline (not a realtime multimodal API) — chosen so the LLM leg can be
a plain function-calling chat model with reliable native tool calling, the exact
property the old Groq/gpt-oss-20b setup lacked.
"""
from livekit.agents import AgentSession
from livekit.plugins import cartesia, deepgram, openai, silero

from app.config import settings


def build_session() -> AgentSession:
    return AgentSession(
        vad=silero.VAD.load(),
        stt=deepgram.STT(api_key=settings.DEEPGRAM_API_KEY),
        llm=openai.LLM(model=settings.VOICE_LLM_MODEL, api_key=settings.OPENAI_API_KEY),
        tts=cartesia.TTS(api_key=settings.CARTESIA_API_KEY),
    )
