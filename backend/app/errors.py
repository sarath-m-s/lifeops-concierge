"""Map Swiggy failures onto HTTP responses using Swiggy's own error envelope."""
from fastapi import HTTPException

from app.services.swiggy_auth import SwiggyAuthError
from app.services.swiggy_mcp import SwiggyRateLimited, SwiggyToolError


def _envelope(message: str, hint: str = "", link: str = "") -> dict:
    error = {"message": message}
    if hint:
        error["reportHint"] = hint
    if link:
        error["reportLink"] = link
    return {"success": False, "error": error}


def as_http(exc: Exception) -> HTTPException:
    if isinstance(exc, SwiggyAuthError):
        return HTTPException(
            status_code=401,
            detail=_envelope(str(exc), "POST /auth/login and complete the flow again."),
        )
    if isinstance(exc, SwiggyRateLimited):
        return HTTPException(
            status_code=429,
            detail=_envelope(str(exc), "Back off and retry after the interval."),
            headers={"Retry-After": str(int(exc.retry_after))},
        )
    if isinstance(exc, SwiggyToolError):
        # Domain failure (out of stock, slot gone, restaurant closed). Terminal:
        # surface the message, do not invite a retry.
        return HTTPException(status_code=400, detail=_envelope(exc.message, exc.report_hint, exc.report_link))
    return HTTPException(
        status_code=502,
        detail=_envelope(str(exc) or "Upstream failure", "If this persists, contact builders@swiggy.in"),
    )
