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
- **Voice capture**: Push-to-talk button records audio; transcript is rendered as editable text so the user can correct misrecognitions before submitting.
- **Timeline UI**: Displays the assembled plan as a vertical timeline of cards — one card per action. Each card shows human-readable details (restaurant name, estimated time, price) never raw IDs.
- **Confirmation screens**: Each actionable card has a dedicated confirmation view: summary of the action, cost, and a single explicit "Confirm" button. Dismissing returns to the timeline without side effects.
- **TTS responses**: Short spoken feedback (plan ready, booking confirmed, order placed) via ElevenLabs or system TTS.

### FastAPI Backend
- **Auth handler**: Manages the OAuth 2.0 flow for Swiggy. Initiates the redirect from mobile, receives the callback, exchanges the code for tokens, and stores tokens server-side tied to the session.
- **Session manager**: Maintains per-user session state: current plan, confirmed actions, voice transcript history.
- **Orchestration API**: Exposes a single `/plan` endpoint. Receives the parsed transcript, calls the LLM Orchestrator, fans out read-only MCP queries in parallel, assembles the plan, and returns it to the mobile app.

### LLM Orchestrator
- **Intent parsing**: Takes the raw voice transcript and extracts structured intent: service targets (Food / Instamart / Dineout), query parameters (cuisine, time, party size, product names), and any ordering constraints.
- **Plan generation**: Converts parsed intent into a set of MCP tool calls. Separates read-only calls (safe to execute immediately) from mutating calls (held behind the Confirmation Gate).
- **Tool selection**: Chooses the appropriate MCP tools per service and constructs the arguments — e.g., `search_restaurants_dineout` with cuisine="Italian" and date=Friday.

### Swiggy MCP Client
- A thin wrapper that manages authenticated connections to all three MCP servers.
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

4. **Parallel read-only queries** — The backend fans out three MCP calls simultaneously:
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

**Redirect URIs:**
- Development: `http://localhost:8000/auth/callback`
- Production: `https://lifeops-concierge.onrender.com/auth/callback`

Tokens are stored server-side only. The mobile app receives a session token; it never sees the Swiggy OAuth access token directly.
