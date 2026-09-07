"""Logging configuration.

The agent's value is largely in *watching it work* — which tool it reached for,
what came back, how long Swiggy took. That needs readable console output, so
loguru handles formatting and colour, and stdlib records (uvicorn, httpx, mcp)
are routed into it so there is one stream rather than two competing formats.
"""
import logging
import sys

from loguru import logger

from app.config import settings

# Noisy at INFO and rarely what you're looking for.
_QUIET = {
    "httpx": "WARNING",
    "httpcore": "WARNING",
    "groq": "WARNING",
    "asyncio": "WARNING",
    "mcp": "WARNING",
    "uvicorn.access": "WARNING",
}


class _Intercept(logging.Handler):
    """Route stdlib logging into loguru so everything shares one format."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        # Walk back to the caller so the source location isn't this shim.
        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1
        # loguru derives {name} from the calling frame, which for an intercepted
        # record is this shim. Carry the originating logger's name explicitly.
        logger.bind(origin=record.name).opt(
            depth=depth, exception=record.exc_info
        ).log(level, record.getMessage())


_ALIASES = {
    "logging_setup": "startup",
    "swiggy_mcp": "mcp",
    "swiggy_auth": "auth",
    "live_planner": "orders",
    "error": "uvicorn",
    "components": "render",
}


def _short_name(record) -> str:
    """`app.services.agent` reads better as `agent` in a narrow terminal."""
    name = record["extra"].get("origin") or record["name"] or ""
    leaf = name.rsplit(".", 1)[-1]
    return _ALIASES.get(leaf, leaf)[:14]


def setup() -> None:
    level = settings.LOG_LEVEL.upper()

    logger.remove()
    logger.add(
        sys.stderr,
        level=level,
        colorize=True,
        backtrace=True,
        # `diagnose` prints local variables on a traceback — useful locally, but
        # those locals include Swiggy payloads and tokens, so keep it off in prod.
        diagnose=settings.APP_ENV != "production",
        format=(
            "<dim>{time:HH:mm:ss.SSS}</dim> "
            "<level>{level: <7}</level> "
            "<cyan>{extra[short]: <14}</cyan> "
            "<level>{message}</level>"
        ),
    )
    logger.configure(patcher=lambda r: r["extra"].update(short=_short_name(r)))

    logging.basicConfig(handlers=[_Intercept()], level=0, force=True)
    for name, lvl in _QUIET.items():
        logging.getLogger(name).setLevel(lvl)

    capture_uvicorn()
    logger.info("logging ready at {}", level)


def capture_uvicorn() -> None:
    """Re-route uvicorn's loggers into loguru.

    uvicorn installs its own handlers when it boots, which happens *after* this
    module is imported — so its lines arrive in a second, unrelated format unless
    its handlers are cleared and left to propagate to the intercepted root.
    Safe to call more than once.
    """
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "uvicorn.asgi", "fastapi"):
        target = logging.getLogger(name)
        target.handlers.clear()
        target.propagate = True
    logging.getLogger("uvicorn.access").setLevel(_QUIET["uvicorn.access"])
