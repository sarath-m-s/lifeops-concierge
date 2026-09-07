# Architecture — LifeOps Concierge

## System Architecture

LifeOps Concierge is a voice-first AI orchestration layer on top of Swiggy's three MCP server APIs. The user speaks (or types) a natural-language intent; the system resolves it into a structured plan across Food, Instamart, and Dineout; and every action that changes real-world state requires an explicit confirmation before it executes.

```
┌─────────────────────────────────────────────────────────────────┐
│                        User Device                              │
│                                                                 │
│   Push-to-talk voice  ──►  React Native App  ──►  Timeline UI  │
│                              ▲         │                        │
│                              │  HTTPS  │                        │
│                              │         ▼                        │
└──────────────────────────────┼─────────┼────────────────────────┘
                               │         │
┌──────────────────────────────┼─────────┼────────────────────────┐
│                        FastAPI Backend                          │
│                               │                                 │
│   Auth Handler ◄──────────────┘                                 │
│   Session Manager                                               │
│   Orchestration API  ──►  LLM Orchestrator                      │
│                                   │                             │
│                     ┌─────────────┼─────────────┐              │
│                     │             │             │              │
│                 read-only     Confirmation   read-only         │
│                 queries         Gate          queries          │
│                     │             │             │              │
└─────────────────────┼─────────────┼─────────────┼──────────────┘
                      │             │             │
              ┌───────┴───┐  ┌──────┴──────┐  ┌──┴────────┐
              │ Food MCP  │  │Instamart MCP│  │Dineout MCP│
              └───────────┘  └─────────────┘  └───────────┘
```

---

## Component Breakdown

### Mobile App (React Native / Expo)
- **Text input**: Typed requests. Voice *input* is not implemented — there is no speech-to-text dependency, and the hardcoded fake transcript that used to stand in for one has been removed.
- **Timeline UI**: Displays the assembled plan as a vertical timeline of cards — one card per action. Each card shows human-readable details (restaurant name, estimated time, price) never raw IDs.
- **Confirmation screens**: Each actionable card has a dedicated confirmation view: summary of the action, cost, and a single explicit "Confirm" button. Dismissing returns to the timeline without side effects.
- **Spoken replies**: `expo-speech` reads each response aloud. This half of the voice story is real.

### FastAPI Backend
- **Auth handler**: Manages the OAuth 2.0 flow for Swiggy. Initiates the redirect from mobile, receives the callback, exchanges the code for tokens, and stores tokens server-side tied to the session.
- **Session manager**: Maintains per-user session state: current plan, confirmed actions, voice transcript history.
- **Orchestration API**: Exposes a single `/plan` endpoint. Receives the parsed transcript, calls the LLM Orchestrator, fans out read-only MCP queries in parallel, assembles the plan, and returns it to the mobile app.

### Intent extraction (`app/services/intent.py`)
- One structured Groq call (`openai/gpt-oss-120b`) per message using strict `json_schema` output, so the response is schema-valid by construction — no JSON parsing or repair.
- Strict mode requires a closed schema; on a schema rejection the call retries once in best-effort mode before giving up, since a validated-but-loose response still beats dropping to keywords.
- Its main job is producing the **single search term** Swiggy's tools require. Their docs are explicit that `query` takes one term, not a sentence.
- Falls back to keyword matching when no API key is set or the call fails, so the app degrades instead of dying.
- **Plan generation**: Converts parsed intent into a set of MCP tool calls. Separates read-only calls (safe to execute immediately) from mutating calls (held behind the Confirmation Gate).
- **Tool selection**: Chooses the appropriate MCP tools per service and constructs the arguments — e.g., `search_restaurants_dineout` with cuisine="Italian" and date=Friday.

### Swiggy MCP Client
- One persistent session per user per server, opened **sequentially**. Each session is owned by a single asyncio task that both enters and exits its exit stack — the streamable-HTTP client sits on anyio cancel scopes, which raise if entered in one task and closed in another.
- Enforces cart-state refresh before any mutation: calls `get_food_cart` before `update_food_cart`, `get_cart` before `update_cart`.
- Strips internal Swiggy IDs from responses before they reach the orchestrator or mobile layer.

### Confirmation Gate Manager
- Intercepts all mutating tool calls: `place_food_order`, `checkout`, `book_table`.
- Holds the call in a pending state and pushes a confirmation request to the mobile app.
- Only executes the mutation after receiving an explicit user approval signal.
- Times out pending confirmations after a configurable window (default: 5 minutes) to avoid stale executions.

---

## Data Flow — "Plan My Evening" Scenario

1. **Voice capture** — User presses push-to-talk and says: *"Plan Friday evening for two. Italian dinner around 8 PM, dessert later at home, and restock coffee for tomorrow."* The transcript is displayed for review.

2. **Submit to backend** — Mobile app POSTs the transcript to `POST /plan` with the user's session token.

3. **Intent parsing** — The LLM Orchestrator parses the transcript into three intent slots:
   - `{service: "dineout", cuisine: "italian", party_size: 2, time: "Friday ~20:00"}`
   - `{service: "food", category: "dessert", delivery_window: "Friday ~22:00"}`
   - `{service: "instamart", items: ["coffee"], delivery_window: "Saturday morning"}`

4. **Read-only queries** — The backend opens the three MCP sessions **sequentially** (parallel multi-domain initialization is a named rate-limit trigger), then fans the read calls out concurrently over those established sessions:
   - `search_restaurants_dineout(cuisine="italian", date="Friday")` → list of restaurants
   - `get_available_slots(restaurant_id=..., date="Friday", party_size=2)` → slot options
   - `search_restaurants(query="dessert", filter="delivery")` → dessert options
   - `search_products(query="coffee")` → grocery options

5. **Plan assembly** — The orchestrator selects top options from each result set and assembles a structured timeline: three action cards with human-readable content.

6. **Timeline returned to mobile** — The plan is returned as a JSON timeline. Mobile renders it as an ordered list of cards.

7. **User reviews** — User sees the timeline, reads each option, taps "Confirm Reservation" on the Dineout card.

8. **Confirmation gate fires** — Mobile sends `POST /confirm/{action_id}`. The Confirmation Gate Manager releases the held `book_table(...)` call to the Dineout MCP.

9. **Result surfaced** — Booking reference (human-readable: "Table confirmed at Trattoria Roma for Friday 8:00 PM") is shown and spoken. Internal booking ID is never displayed.

10. **Repeat for remaining actions** — User independently confirms or dismisses the Food and Instamart actions.

---

## Auth Flow

```
Mobile App                FastAPI Backend             Swiggy OAuth
     │                          │                          │
     │  1. Tap "Connect Swiggy" │                          │
     │─────────────────────────►│                          │
     │                          │  2. Generate OAuth URL   │
     │                          │─────────────────────────►│
     │  3. Redirect to browser  │                          │
     │◄─────────────────────────│                          │
     │                          │                          │
     │  [User authorizes in browser]                       │
     │                          │                          │
     │                          │◄─────────────────────────│
     │                          │  4. Callback with code   │
     │                          │                          │
     │                          │  5. Exchange code for    │
     │                          │     access + refresh     │
     │                          │     tokens               │
     │                          │─────────────────────────►│
     │                          │◄─────────────────────────│
     │                          │  6. Tokens received      │
     │                          │                          │
     │                          │  7. Store tokens         │
     │                          │     server-side, tied    │
     │                          │     to session           │
     │  8. Session ready        │                          │
     │◄─────────────────────────│                          │
```

**Protocol:** OAuth 2.1 with PKCE (S256).

There is **no client secret**. `https://mcp.swiggy.com/.well-known/oauth-authorization-server` advertises `token_endpoint_auth_methods_supported: ["none", ...]` — a public client. The `client_id` is not applied for either; it is issued by Dynamic Client Registration (RFC 7591) at `POST /auth/register` on first boot, then pinned into `SWIGGY_CLIENT_ID` so restarts reuse it.

**Endpoints** (base `https://mcp.swiggy.com`): `GET /auth/authorize`, `POST /auth/token`, `POST /auth/register`, `POST /auth/logout`.

**Token lifecycle:** the access token lives 5 days and **refresh-token issuance is not wired in Swiggy v1.0** — the metadata advertises the grant, but `/auth/token` only implements `authorization_code`. A 401 therefore means "re-run the whole authorization flow", never "refresh". Step 5 below reads *access token*, not *access + refresh*.

**Redirect URIs:**
- Development: `http://localhost:8000/auth/callback`
- Production: `https://lifeops-concierge.onrender.com/auth/callback`

Tokens are stored server-side only. The mobile app receives a session token; it never sees the Swiggy OAuth access token directly.

---

## Real MCP Contract Notes (from Swiggy Builders Club docs v1.0)

These notes supplement the architecture above with specifics from the official Swiggy MCP documentation.

### Error Envelope
All MCP tools return a uniform error shape on failure:
```json
{ "success": false, "error": { "message": "...", "reportLink": "...", "reportHint": "..." } }
```

### Idempotency
- **Safe to retry freely:** `search_*`, `get_*`, `track_*`, `apply_food_coupon`
- **Non-idempotent — check status before retry:** `place_food_order`, `checkout`, `book_table`
  - These must never be blind-retried. Call the corresponding status/tracking tool first.

### Rate Limiting
Enforced at the MCP layer. Quotas are keyed on the authenticated user:
- 70 requests/minute per user per server; 30/minute for write tools; burst 2x over a 10s window.
- `X-RateLimit-Limit` / `-Remaining` / `-Reset` on every successful response; `429` + `Retry-After` when throttled.
- Honour `Retry-After` directly — never stack exponential backoff on top of it.

Connection hygiene matters more than call volume. Auth events are counted separately, so:
- **One session per user per server**, reused for every tool call. Reinitializing per call is the documented top cause of production rate-limit blocks.
- **Initialize servers sequentially**, never in parallel — a simultaneous `/food` + `/im` + `/dineout` connect triples the auth-event count.

### Dineout argument contract
The recipe page and the per-tool reference disagree. **The per-tool reference wins** — it is generated from the live schema, and following the recipe is what broke this flow originally.

- `get_saved_locations` returns `index`, `id`, `addressLine` — **not** lat/lng. Pass that `id` as `addressId` to `search_restaurants_dineout`. (The recipe claims it returns coordinates. It does not.)
- `slotId` and `itemId` come from `slot.deals[]`, not the slot. One slot can carry a free and a paid deal simultaneously.
- `book_table` takes the **restaurant's** `latitude`/`longitude` from the search result, not the user's location.

Paid prebook deals *are* supported by the server (`create_cart` with `cartType="DEAL_TICKET_PURCHASE"` plus the UPI stage). LifeOps offers **free reservations only** (`isFree`, `bookingPrice` 0) because it does not implement UPI. That is a product constraint, not a platform limit; the filter lives in `live_planner._free_deal`.

### Cart State
Cart is server-side, keyed to session. Always call `get_food_cart` / `get_cart` at the start of each turn before any mutation — do not rely on locally cached cart state across turns.

### Address Sharing
Swiggy Food and Instamart share address endpoints. One address lookup serves both services.
