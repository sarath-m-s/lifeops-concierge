# Safety Policy — LifeOps Concierge

LifeOps Concierge operates as an agent on behalf of the user. The following policies exist to ensure the user retains control over every real-world action, and that the app never acts as a proxy for unintended purchases, bookings, or data exposure.

---

## 1. Confirmation-First Principle

Every action that changes real-world state — placing a food order, checking out a grocery cart, booking a restaurant table — requires an explicit confirmation step from the user.

**What this means in practice:**
- The orchestrator generates a plan with pending actions.
- Pending actions are displayed to the user as individual cards in the timeline UI, each clearly describing what will happen and what it will cost.
- A mutating MCP call (`place_food_order`, `checkout`, `book_table`) is never issued until the user has tapped a dedicated confirmation button for that specific action.
- Confirming one action does not confirm others. Each action is an independent gate.

**No grouping:** The app never batches confirmations or asks the user to "confirm all." Each action is presented and confirmed separately to ensure clarity.

---

## 2. No Silent Mutations Policy

The app does not perform background mutations. No cart is modified, no order is placed, and no table is booked as a side effect of reading, searching, or assembling a plan.

Read-only MCP calls (`search_restaurants`, `get_food_cart`, `search_products`, `get_available_slots`, etc.) are executed freely to build the plan. Write calls are held in a pending state until the user explicitly releases them.

**Audit trail:** Every mutation call — attempted or completed — is logged server-side with the user session ID, the action type, the timestamp, and the outcome. This log is available to the user on request.

---

## 3. Cart State Refresh Before Mutation

Before issuing any write call that modifies a cart, the app first reads the current cart state:

| Mutation call | Preceding read call |
|---|---|
| `update_food_cart` | `get_food_cart` |
| `update_cart` (Instamart) | `get_cart` |

This prevents stale-write conflicts where a previous session or device has modified the cart between the time the plan was generated and the time the user confirms.

If the cart state has changed since the plan was presented, the user is notified and must re-confirm with the updated state before the mutation proceeds.

---

## 4. ID Sanitization

Internal Swiggy resource identifiers (restaurant IDs, item IDs, slot IDs, booking reference codes, order IDs) are never surfaced to the user in any form:

- Not displayed in the UI
- Not read aloud by the TTS system
- Not included in error messages shown to the user
- Not stored in any user-facing log or export

All user-facing content uses human-readable names, descriptions, times, and prices only. Internal IDs are handled exclusively within the backend and MCP client layers.

---

## 5. Data Minimization Policy

The app collects only what is needed to render the current plan and fulfill confirmed actions.

**What is retained:**
- Session-scoped voice transcripts (cleared when the session ends or after 24 hours, whichever is sooner)
- Plan summaries (the structured timeline, without raw API response data)
- User preferences (cuisine preferences, delivery address, party size defaults) — stored only with explicit user opt-in

**What is not retained:**
- Raw Swiggy API responses beyond the current session
- Cart contents after an order is placed or a session ends
- Payment information (handled entirely by Swiggy; LifeOps never sees payment details)
- Order history beyond what is needed to show the current plan's status

See [PRIVACY.md](PRIVACY.md) for the full data handling declaration.
