"""The LiveKit voice+text agent: a long-running worker process, separate from the
FastAPI web process (see app/routers/livekit_token.py for how a client joins its
room). Run with `python -m app.voice.worker <console|dev|start|download-files>`.
"""

# Named so the worker only accepts EXPLICIT dispatch (see WorkerOptions in
# worker.py) rather than LiveKit's automatic "first participant in a brand-new
# room" dispatch. Automatic dispatch only fires once per room's lifetime; since
# a session's room name is stable and reused across reconnects
# (`lifeops-<session_id>`, see livekit_token.py), a returning participant would
# never get a fresh agent job without dispatching explicitly every time a token
# is minted.
AGENT_NAME = "lifeops-concierge"
