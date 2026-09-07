"""Persistent Swiggy MCP sessions, one per (app session, server).

Two rules from the Swiggy rate-limit docs drive this whole module:

  "One session per user, not one per request. Auth happens once per connection."
  "Initialize domains sequentially, not in parallel."

Reinitializing per tool call is documented as the most common cause of production
rate-limit blocks, so a session is opened once and reused for every subsequent call.

Each session is owned by a single asyncio task that both enters and exits the
AsyncExitStack. That is deliberate: the MCP streamable-HTTP client is built on anyio
cancel scopes, which raise if entered in one task and closed in another, so callers
hand work to the owner task through a queue instead of touching the stack directly.
"""
import asyncio
import contextlib
import json
import logging
import random
import time
from contextlib import AsyncExitStack
from typing import Any, Optional

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from app.config import settings
from app.services import swiggy_auth
from app.services.swiggy_auth import SwiggyAuthError

log = logging.getLogger(__name__)

SERVERS = ("food", "instamart", "dineout")

_MAX_ATTEMPTS = 5
_RETRY_BUDGET_SECONDS = 30.0  # docs: cap user-facing retries at 30s wall clock
_INIT_TIMEOUT_SECONDS = 45.0
_CALL_TIMEOUT_SECONDS = 60.0  # check_payment_status is a ~19s long-poll


class SwiggyToolError(RuntimeError):
    """A tool returned success:false. Terminal — surface it, do not retry."""

    def __init__(self, message: str, report_hint: str = "", report_link: str = ""):
        super().__init__(message)
        self.message = message
        self.report_hint = report_hint
        self.report_link = report_link


class SwiggyRateLimited(RuntimeError):
    def __init__(self, retry_after: float):
        super().__init__(f"Rate limited by Swiggy MCP; retry after {retry_after:.0f}s")
        self.retry_after = retry_after


def _status_of(exc: BaseException) -> Optional[int]:
    """Best-effort HTTP status for an exception raised under the MCP client."""
    for attr in ("status_code", "status"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    response = getattr(exc, "response", None)
    if response is not None and isinstance(getattr(response, "status_code", None), int):
        return response.status_code
    return None


def _retry_after_of(exc: BaseException) -> float:
    for part in _flatten(exc):
        response = getattr(part, "response", None)
        headers = getattr(response, "headers", None) or {}
        raw = headers.get("Retry-After") if hasattr(headers, "get") else None
        if raw is not None:
            try:
                return float(raw)
            except (TypeError, ValueError):
                pass
    return 30.0


def _jsonrpc_code_of(exc: BaseException) -> Optional[int]:
    error = getattr(exc, "error", None)
    code = getattr(error, "code", None)
    return code if isinstance(code, int) else None


def _flatten(exc: BaseException, depth: int = 0) -> list[BaseException]:
    """Walk exception groups and causes.

    anyio task groups wrap the real failure, so a 401 arrives as a BaseExceptionGroup.
    Classifying the wrapper instead of its contents would bucket an expired token as
    "fatal" and never prompt the user to re-authorize.
    """
    if depth > 5:
        return [exc]
    found = [exc]
    for nested in getattr(exc, "exceptions", ()) or ():
        found.extend(_flatten(nested, depth + 1))
    for attr in ("__cause__", "__context__"):
        nested = getattr(exc, attr, None)
        if nested is not None and nested is not exc:
            found.extend(_flatten(nested, depth + 1))
    return found


def classify(exc: BaseException) -> str:
    """Bucket a transport/protocol failure per docs/reference/errors.

    Returns one of: "auth", "rate_limit", "retryable", "fatal".
    """
    parts = _flatten(exc)
    status = next((s for s in (_status_of(p) for p in parts) if s is not None), None)
    code = next((c for c in (_jsonrpc_code_of(p) for p in parts) if c is not None), None)
    text = " ".join(str(p) for p in parts).lower()

    # JSON-RPC -32001 is Swiggy's unauthenticated/expired signal at the transport layer.
    if status in (401, 419) or code == -32001 or "invalid_token" in text:
        return "auth"
    if status == 429:
        return "rate_limit"
    if status is not None and 500 <= status < 600:
        return "retryable"
    if status is not None:  # any other explicit 4xx is a client bug — do not retry
        return "fatal"
    if isinstance(exc, asyncio.TimeoutError) or "timeout" in text or "timed out" in text:
        return "retryable"
    if code == -32603:
        return "retryable"
    return "fatal"


def _unwrap(result: Any) -> dict:
    """Turn a CallToolResult into the tool's JSON payload, raising on error envelopes."""
    structured = getattr(result, "structuredContent", None)
    payload: Any = structured

    if payload is None:
        texts = [
            block.text
            for block in (getattr(result, "content", None) or [])
            if getattr(block, "type", None) == "text" and getattr(block, "text", None)
        ]
        joined = "\n".join(texts).strip()
        if not joined:
            payload = {}
        else:
            try:
                payload = json.loads(joined)
            except json.JSONDecodeError:
                # Some tools answer in prose. Keep it rather than losing the message.
                payload = {"message": joined}

    if getattr(result, "isError", False):
        # Keep whatever the server actually said. Collapsing this to a generic
        # string made a real failure indistinguishable from every other failure.
        message = None
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                message = error.get("message")
            message = message or payload.get("message") or payload.get("detail")
            if not message:
                message = json.dumps(payload)[:400]
        else:
            message = str(payload)[:400]
        raise SwiggyToolError(message or "Swiggy tool reported an error with no message")

    if isinstance(payload, dict) and payload.get("success") is False:
        error = payload.get("error") or {}
        raise SwiggyToolError(
            error.get("message", "Swiggy tool failed"),
            report_hint=error.get("reportHint", ""),
            report_link=error.get("reportLink", ""),
        )

    if isinstance(payload, dict):
        # Tools wrap their result in `data`; unwrap so callers read one shape.
        return payload.get("data") if isinstance(payload.get("data"), dict) else payload
    return {"data": payload}


class _Session:
    """A single live MCP connection, driven by its own owner task."""

    def __init__(self, session_id: str, server: str, token: str):
        self.session_id = session_id
        self.server = server
        self.url = settings.server_url(server)
        self._token = token
        self._queue: asyncio.Queue = asyncio.Queue()
        self._ready: asyncio.Future = asyncio.get_running_loop().create_future()
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name=f"swiggy-{self.server}-{self.session_id[:8]}")
        try:
            await asyncio.wait_for(asyncio.shield(self._ready), timeout=_INIT_TIMEOUT_SECONDS)
        except Exception:
            await self.close()
            raise

    async def _run(self) -> None:
        headers = {"Authorization": f"Bearer {self._token}"}
        try:
            async with AsyncExitStack() as stack:
                read, write, _ = await stack.enter_async_context(
                    streamablehttp_client(self.url, headers=headers)
                )
                session = await stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                if not self._ready.done():
                    self._ready.set_result(None)

                while True:
                    job = await self._queue.get()
                    if job is None:
                        return
                    tool, args, future = job
                    if future.cancelled():
                        continue
                    try:
                        future.set_result(await session.call_tool(tool, args))
                    except BaseException as exc:  # noqa: BLE001 — relayed to the caller
                        if not future.done():
                            future.set_exception(exc)
                        if classify(exc) == "auth":
                            return  # connection is useless now; let the pool rebuild it
        except BaseException as exc:  # noqa: BLE001 — connect/initialize failure
            if not self._ready.done():
                self._ready.set_exception(exc)
            else:
                log.warning("Swiggy %s session ended: %s", self.server, exc)
        finally:
            self._drain(ConnectionError(f"Swiggy {self.server} session closed"))

    def _drain(self, exc: BaseException) -> None:
        while not self._queue.empty():
            job = self._queue.get_nowait()
            if job is None:
                continue
            _, _, future = job
            if not future.done():
                future.set_exception(exc)

    @property
    def alive(self) -> bool:
        return self._task is not None and not self._task.done()

    async def call_raw(self, tool: str, args: dict) -> Any:
        if not self.alive:
            raise ConnectionError(f"Swiggy {self.server} session is not connected")
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        await self._queue.put((tool, args, future))
        return await asyncio.wait_for(future, timeout=_CALL_TIMEOUT_SECONDS)

    async def close(self) -> None:
        if self._task is None:
            return
        await self._queue.put(None)
        with contextlib.suppress(asyncio.TimeoutError, asyncio.CancelledError):
            await asyncio.wait_for(asyncio.shield(self._task), timeout=10)
        if not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task
        self._task = None


class SwiggyClient:
    """Per-app-session pool of MCP connections."""

    def __init__(self) -> None:
        self._sessions: dict[tuple[str, str], _Session] = {}
        # One lock per app session: connects must be sequential across servers, since
        # parallel multi-domain initialization is a named rate-limit trigger.
        self._connect_locks: dict[str, asyncio.Lock] = {}

    def _lock_for(self, session_id: str) -> asyncio.Lock:
        return self._connect_locks.setdefault(session_id, asyncio.Lock())

    async def ensure(self, session_id: str, servers: tuple[str, ...] = SERVERS) -> None:
        """Open any missing sessions, one server at a time."""
        token = swiggy_auth.get_token(session_id)
        async with self._lock_for(session_id):
            for server in servers:
                existing = self._sessions.get((session_id, server))
                if existing is not None and existing.alive:
                    continue
                if existing is not None:
                    await existing.close()
                session = _Session(session_id, server, token)
                try:
                    await session.start()
                except BaseException as exc:  # noqa: BLE001
                    if classify(exc) == "auth":
                        swiggy_auth.drop_token(session_id)
                        raise SwiggyAuthError("Swiggy session expired. Re-run the login flow.") from exc
                    raise
                self._sessions[(session_id, server)] = session
                log.info("Connected Swiggy %s for session %s", server, session_id[:8])

    async def call(self, session_id: str, server: str, tool: str, args: Optional[dict] = None) -> dict:
        """Call a tool, retrying only what the docs say is safe to retry.

        Callers must not use this for a bare retry of place_food_order / checkout /
        book_table — those are non-idempotent. Use `place_with_verification`.
        """
        args = args or {}
        deadline = time.monotonic() + _RETRY_BUDGET_SECONDS
        attempt = 0

        while True:
            attempt += 1
            await self.ensure(session_id, (server,))
            session = self._sessions[(session_id, server)]
            try:
                return _unwrap(await session.call_raw(tool, args))
            except SwiggyToolError:
                raise  # domain failure on HTTP 200: terminal by contract
            except BaseException as exc:  # noqa: BLE001
                bucket = classify(exc)
                if bucket == "auth":
                    swiggy_auth.drop_token(session_id)
                    await self.close_session(session_id)
                    raise SwiggyAuthError("Swiggy session expired. Re-run the login flow.") from exc
                if bucket == "rate_limit":
                    # Honour Retry-After exactly; never stack backoff on top of it.
                    raise SwiggyRateLimited(_retry_after_of(exc)) from exc
                if bucket != "retryable" or attempt >= _MAX_ATTEMPTS:
                    raise

                base = 0.5 * (2 ** (attempt - 1))  # 0.5, 1, 2, 4
                delay = min(base, 8.0) + random.random() * base * 0.3
                if time.monotonic() + delay > deadline:
                    raise
                log.warning("Retrying %s/%s in %.1fs (attempt %d): %s", server, tool, delay, attempt, exc)
                await asyncio.sleep(delay)

    async def place_with_verification(
        self,
        session_id: str,
        server: str,
        tool: str,
        args: dict,
        verify,
    ) -> dict:
        """Run a non-idempotent order/booking call using check-then-retry.

        Per docs/build/ship-to-production: on a 5xx or network failure, wait, ask the
        status tool whether the order actually landed, and only re-place if it did not.
        `verify` is an async callable returning the placed order/booking, or None.
        """
        try:
            await self.ensure(session_id, (server,))
            session = self._sessions[(session_id, server)]
            return _unwrap(await session.call_raw(tool, args))
        except (SwiggyToolError, SwiggyAuthError):
            raise
        except BaseException as exc:  # noqa: BLE001
            bucket = classify(exc)
            if bucket == "auth":
                swiggy_auth.drop_token(session_id)
                await self.close_session(session_id)
                raise SwiggyAuthError("Swiggy session expired. Re-run the login flow.") from exc
            if bucket == "rate_limit":
                raise SwiggyRateLimited(_retry_after_of(exc)) from exc
            if bucket != "retryable":
                raise

            log.warning("%s failed (%s); verifying before any retry", tool, exc)
            await asyncio.sleep(3)
            existing = await verify()
            if existing is not None:
                return existing  # it landed after all — the failure was cosmetic
            return await self.call(session_id, server, tool, args)

    async def close_session(self, session_id: str) -> None:
        for key in [k for k in self._sessions if k[0] == session_id]:
            await self._sessions.pop(key).close()
        self._connect_locks.pop(session_id, None)

    async def close_all(self) -> None:
        for key in list(self._sessions):
            await self._sessions.pop(key).close()
        self._connect_locks.clear()


client = SwiggyClient()
