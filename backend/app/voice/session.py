"""Builds the AgentSession: Deepgram STT, Cartesia TTS, Silero VAD, OpenAI LLM.

STT/LLM/TTS all run through LiveKit Inference (`livekit.agents.inference`) rather
than the individual provider plugins — it proxies to the same underlying models,
authenticated with the project's existing LIVEKIT_API_KEY/SECRET, billed through
LiveKit Cloud instead of needing a separate Deepgram/Cartesia/OpenAI key each.
Swap to the `livekit.plugins.*` classes instead if direct provider billing is ever
preferred — the constructor shapes are close to identical.

A cascaded pipeline (not a realtime multimodal API) — chosen so the LLM leg can be
a plain function-calling chat model with reliable native tool calling, the exact
property the old Groq/gpt-oss-20b setup lacked.

VAD is the one leg that stays a plugin: it's a local ONNX model with no hosted
inference equivalent, so it never needed a provider key in the first place.
"""
from livekit.agents import AgentSession, inference
from livekit.plugins import silero

from app.config import settings

# Cartesia's default sonic-3 voice — same one the direct-plugin config used.
_TTS_VOICE = "9626c31c-bec5-4cca-baa8-f8ba9e84c8bc"


def build_session() -> AgentSession:
    return AgentSession(
        vad=silero.VAD.load(),
        stt=inference.STT(
            model="deepgram/nova-3",
            language="en",
            api_key=settings.LIVEKIT_API_KEY,
            api_secret=settings.LIVEKIT_API_SECRET,
        ),
        llm=inference.LLM(
            model=settings.VOICE_LLM_MODEL,
            api_key=settings.LIVEKIT_API_KEY,
            api_secret=settings.LIVEKIT_API_SECRET,
        ),
        tts=inference.TTS(
            model="cartesia/sonic-3",
            voice=_TTS_VOICE,
            api_key=settings.LIVEKIT_API_KEY,
            api_secret=settings.LIVEKIT_API_SECRET,
        ),
    )
