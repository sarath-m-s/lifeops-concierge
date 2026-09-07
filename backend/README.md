# LifeOps Concierge — Backend

FastAPI backend: OAuth handling, Swiggy MCP session management, LLM intent extraction, and the confirmation gate.

**There is no mock mode.** Every request goes to the real Swiggy MCP servers.

## Quick start

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
| GET | `/health` | Version, env, MCP base, whether an LLM key is configured |
| POST | `/auth/login` | Start a login. Returns `session_id` + `authorize_url` |
| GET | `/auth/callback` | OAuth redirect target — exchanges the code, deep-links back to the app |
| GET | `/auth/status?session_id=…` | Whether that session is connected |
| POST | `/auth/logout` | Revoke the Swiggy session and close its MCP connections |
| POST | `/chat` | Send a message, receive an `AgentResponse` |
| POST | `/confirm` | Execute a confirmed action |

`/chat` and `/confirm` require the `X-Session-Id` header returned by `/auth/login`. An unknown session id gets a 401; the body's `session_id` field is advisory and cannot be used to act as another session.

## Auth

OAuth 2.1 with PKCE (S256). **There is no client secret**, and the `client_id` is not something you apply for:

- The metadata document advertises `token_endpoint_auth_methods_supported: ["none", …]` — a public client.
- The `client_id` comes from Dynamic Client Registration (RFC 7591) at `POST /auth/register`, performed on first boot.
- That id is logged at WARNING. Pin it into `SWIGGY_CLIENT_ID` so restarts reuse the registration — every registration counts as an auth event against the rate limit.

Access tokens live 5 days and **there is no refresh grant in Swiggy v1**. A 401 means re-running the whole authorization flow.

`mcp-staging.swiggy.com` does not resolve in DNS. Production (`https://mcp.swiggy.com`) is the only reachable host; servers are `/food`, `/im`, `/dineout`.

## Intent extraction

`app/services/agent.py` runs a tool-calling loop on Groq (`openai/gpt-oss-20b`). Its main job is turning a sentence into the *single search term* Swiggy's tools expect — "somewhere Italian in Indiranagar" becomes `Italian`, not the whole sentence.

Set `LLM_API_KEY` to a Groq key. `LLM_MODEL` defaults to `openai/gpt-oss-20b`, which measured 12/12 clean tool calls where `gpt-oss-120b` managed 9/12 and `qwen3.8-27b` 8/12. Without a key it falls back to keyword matching — degraded but real, so the app stays usable when the model is unreachable.

Strict mode needs a fully closed schema (`additionalProperties: false`, every field in `required`); `test_backend.py` asserts that so a model change can't silently turn every call into a 400.

## Rate-limit behaviour

Swiggy enforces 70 req/min per user per server (30/min for writes). `app/services/swiggy_mcp.py` follows the documented hygiene rules:

- one persistent MCP session per user per server, reused across tool calls
- servers connected **sequentially**, never in parallel
- exponential backoff with jitter on 5xx/timeouts, capped at 5 attempts and 30s wall clock
- `429` surfaces `Retry-After` verbatim, with no backoff stacked on top

## Order safety

`place_food_order`, `checkout`, and `book_table` are non-idempotent, guarded on two axes:

- **Double-tap** — `/confirm` holds a per-action lock and replays the stored result rather than placing twice.
- **Mid-flight failure** — `swiggy_mcp.place_with_verification` waits, calls `get_food_orders` / `get_orders` / `get_booking_status`, and only re-places if the order genuinely did not land.

Food carts are checked against the ₹1000 Builders Club cap before placing, and a `PENDING_PAYMENT` response (the UPI leg, which this app does not implement) is never reported as a placed order.

## Dineout argument contract

Two doc pages disagree; the per-tool reference wins over the recipe.

- `get_saved_locations` returns `index`, `id`, `addressLine` — **not** coordinates. Pass that `id` to `search_restaurants_dineout` as `addressId`.
- `slotId` and `itemId` come from `slot.deals[]`, not from the slot itself. A slot can carry a free and a paid deal at the same time.
- `book_table` wants the **restaurant's** `latitude`/`longitude` from the search result, not the user's location.

Paid prebook deals need `create_cart` plus the UPI stage and are filtered out in `live_planner._free_deal`.

## Going live

1. `APP_ENV=production` and real origins in `CORS_ORIGINS`.
2. `SWIGGY_REDIRECT_URI` must exactly match what Swiggy whitelisted (exact-match, no wildcards).
3. First boot performs Dynamic Client Registration — copy the logged `client_id` into `SWIGGY_CLIENT_ID`.
4. Set `LLM_API_KEY` (Groq) for real intent parsing.
