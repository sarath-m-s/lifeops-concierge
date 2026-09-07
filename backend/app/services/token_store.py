"""Swiggy token persistence.

Render's free tier restarts on every deploy and spins down after 15 minutes idle,
and its disk is ephemeral — so an in-process dict (or SQLite) means re-running the
whole phone-and-OTP flow constantly. Tokens live in Postgres instead.

Backed by DATABASE_URL when present, in-process memory otherwise, so local
development needs no database. A small cache sits in front of Postgres because
every authenticated request reads the token and the value only changes at login
and logout.
"""
import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Optional

from app.config import settings

log = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS swiggy_sessions (
    session_id  TEXT PRIMARY KEY,
    access_token TEXT NOT NULL,
    expires_at  DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS swiggy_sessions_expires_at ON swiggy_sessions (expires_at);
"""


@dataclass
class Token:
    access_token: str
    expires_at: float

    @property
    def expired(self) -> bool:
        # Treat the last 60s as expired, per the auth docs' guidance.
        return time.time() >= self.expires_at - 60


class TokenStore:
    def __init__(self) -> None:
        self._pool = None
        self._memory: dict[str, Token] = {}
        self._cache: dict[str, Token] = {}
        self._lock = asyncio.Lock()

    @property
    def persistent(self) -> bool:
        return self._pool is not None

    async def start(self) -> None:
        """Open the pool and ensure the schema. Falls back to memory on failure."""
        url = settings.DATABASE_URL.strip()
        if not url:
            log.warning("No DATABASE_URL — tokens are in-process only and will not survive a restart")
            return
        # Render hands out postgres:// URLs; asyncpg only accepts postgresql://.
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://") :]
        try:
            import asyncpg

            self._pool = await asyncpg.create_pool(url, min_size=1, max_size=5, command_timeout=10)
            async with self._pool.acquire() as conn:
                await conn.execute(_SCHEMA)
                deleted = await conn.fetchval(
                    "DELETE FROM swiggy_sessions WHERE expires_at < $1 RETURNING 1", time.time()
                )
            log.info("Token store ready on Postgres (pruned expired: %s)", bool(deleted))
        except Exception as exc:  # noqa: BLE001 — a DB outage must not take auth down
            log.error("Postgres unavailable (%s); falling back to in-process tokens", exc)
            self._pool = None

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def put(self, session_id: str, token: Token) -> None:
        self._cache[session_id] = token
        if self._pool is None:
            self._memory[session_id] = token
            return
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO swiggy_sessions (session_id, access_token, expires_at)
                VALUES ($1, $2, $3)
                ON CONFLICT (session_id) DO UPDATE
                    SET access_token = EXCLUDED.access_token, expires_at = EXCLUDED.expires_at
                """,
                session_id,
                token.access_token,
                token.expires_at,
            )

    async def get(self, session_id: str) -> Optional[Token]:
        token = self._cache.get(session_id)
        if token is None and self._pool is None:
            token = self._memory.get(session_id)
        elif token is None:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT access_token, expires_at FROM swiggy_sessions WHERE session_id = $1",
                    session_id,
                )
            if row is not None:
                token = Token(access_token=row["access_token"], expires_at=row["expires_at"])
                self._cache[session_id] = token

        if token is None:
            return None
        if token.expired:
            await self.drop(session_id)
            return None
        return token

    async def drop(self, session_id: str) -> None:
        self._cache.pop(session_id, None)
        self._memory.pop(session_id, None)
        if self._pool is not None:
            async with self._pool.acquire() as conn:
                await conn.execute("DELETE FROM swiggy_sessions WHERE session_id = $1", session_id)


store = TokenStore()
