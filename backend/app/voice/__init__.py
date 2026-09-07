"""The LiveKit voice+text agent: a long-running worker process, separate from the
FastAPI web process (see app/routers/livekit_token.py for how a client joins its
room). Run with `python -m app.voice.worker <console|dev|start|download-files>`.
"""
