# LifeOps Concierge — Backend

FastAPI backend providing the orchestration API, Swiggy MCP integration, and OAuth handling for the LifeOps Concierge mobile app.

## Quick Start

```bash
cp .env.example .env
python3.13 -m venv venv313 && source venv313/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Self-check (no network, no framework):

```bash
python test_backend.py
```

## Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Version, mock-mode flag, configured MCP base |
| POST | `/auth/login` | Start a session. Returns `session_id` + `authorize_url` |
| GET | `/auth/callback` | OAuth redirect target — exchanges the code, then deep-links back to the app |
| GET | `/auth/status?session_id=…` | Whether that specific session is connected |
| POST | `/auth/logout` | Revoke the Swiggy session and close its MCP connections |
| POST | `/chat` | Send a message, receive an `AgentResponse` |
| POST | `/confirm` | Execute a confirmed pending action |

Every data endpoint requires the `X-Session-Id` header returned by `/auth/login`. An unknown session id gets a 401 — the body's `session_id` field is advisory and cannot be used to act as another session.

## Auth

OAuth 2.1 with PKCE (S256). **There is no client secret**, and the `client_id` is not something you apply for:

- `https://mcp.swiggy.com/.well-known/oauth-authorization-server` advertises `token_endpoint_auth_methods_supported: ["none", …]` — a public client.
- The `client_id` is issued by Dynamic Client Registration (RFC 7591) at `POST /auth/register`, which the backend performs on first live boot.
- The registered id is logged at WARNING level. Pin it into `SWIGGY_CLIENT_ID` so restarts reuse the registration instead of re-registering — every registration counts as an auth event against the rate limit.

Access tokens live 5 days and **there is no refresh grant in Swiggy v1.0**. A 401 means re-running the whole authorization flow.

## Mode

`APP_ENV=development` (default) answers from `app/services/mock_mcp`. `APP_ENV=production` routes to the real servers at `https://mcp.swiggy.com` — `/food`, `/im`, `/dineout`.

`mcp-staging.swiggy.com` does not resolve in DNS; production is the only reachable host.

## Rate-limit behaviour

Enforced by Swiggy at 70 req/min per user per server (30/min for writes). The client in `app/services/swiggy_mcp.py` follows the documented hygiene rules:

- one persistent MCP session per user per server, reused across tool calls
- servers connected **sequentially**, never in parallel
- exponential backoff with jitter on 5xx/timeouts, capped at 5 attempts and 30s wall clock
- `429` surfaces `Retry-After` verbatim, with no backoff stacked on top

## Order safety

`place_food_order`, `checkout`, and `book_table` are non-idempotent, guarded on two axes:

- **Double-tap** — `/confirm` holds a per-action lock and replays the stored result rather than placing twice.
- **Mid-flight failure** — `swiggy_mcp.place_with_verification` waits, calls `get_food_orders` / `get_orders` / `get_booking_status`, and only re-places if the order genuinely did not land.

Food carts are checked against the ₹1000 Builders Club cap before placing. A `PENDING_PAYMENT` response (the UPI leg, which this app does not implement) is never reported to the user as a placed order.

## Going live

1. Set `APP_ENV=production` — this also switches CORS from wildcard to the `CORS_ORIGINS` allowlist.
2. Put the real app origins in `CORS_ORIGINS`.
3. Confirm `SWIGGY_REDIRECT_URI` exactly matches what Swiggy whitelisted (exact-match, no wildcards).
4. First boot performs Dynamic Client Registration; copy the logged `client_id` into `SWIGGY_CLIENT_ID`.
5. Remove `SWIGGY_CLIENT_SECRET` from the environment — it is not part of the protocol.
