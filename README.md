# LifeOps Concierge

> **Powered by Swiggy** — Food · Instamart · Dineout

[![Status](https://img.shields.io/badge/status-Phase%201%20%E2%80%94%20Applying-orange)](https://github.com/sarath-m-s/lifeops-concierge)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Built with](https://img.shields.io/badge/built%20with-React%20Native%20%2B%20FastAPI-green)](docs/ARCHITECTURE.md)

---

**A voice-first AI concierge that plans your evening across food delivery, grocery restocks, and restaurant dining — all in one conversation, with your explicit approval before anything gets ordered.**

---

## Problem

Planning a real evening out — dinner reservation, dessert delivery, and tomorrow's groceries — means juggling three separate apps: Swiggy Food, Instamart, and Dineout. Each requires its own search, its own cart, its own checkout. There is no single place to say "plan my Friday evening" and get an actionable, confirmed timeline back.

The result: people either under-plan (forget the groceries), or give up on the coordination entirely and just order whatever is easiest.

---

## Solution

LifeOps Concierge lets you speak one intent and get a complete, multi-service plan back in seconds.

A single voice prompt kicks off parallel queries across all three Swiggy MCP servers. The app assembles a timeline — dinner slots, delivery windows, restock options — and presents each action for your explicit confirmation before anything is committed. One conversation, three services, zero surprise charges.

The key design principle: **the app never acts without asking.** Every booking, order, or checkout requires a dedicated confirmation step. You stay in control; the AI handles the coordination.

---

## Hero Demo — "Plan My Evening"

**User says:**
> "Plan Friday evening for two. Italian dinner around 8 PM, dessert later at home, and restock coffee for tomorrow."

**What LifeOps Concierge does:**

```
Step 1 — Parse intent
  → Identifies 3 sub-tasks: Dineout reservation, Food delivery, Instamart restock
  → Extracts constraints: Friday, 2 people, ~8 PM, Italian cuisine

Step 2 — Query all three MCP servers in parallel
  → Dineout: search_restaurants_dineout("Italian", Friday) → get_available_slots(...)
  → Food:    search_restaurants("dessert delivery") → search_menu(...)
  → Instamart: search_products("coffee", "breakfast items")

Step 3 — Present the timeline
  ┌──────────────────────────────────────────────────────────┐
  │  Friday Evening Plan                                     │
  │                                                          │
  │  7:45 PM  🍽  Trattoria Roma · Table for 2              │
  │               Available: 8:00 PM, 8:15 PM, 8:30 PM      │
  │               [Confirm Reservation]                      │
  │                                                          │
  │  10:30 PM 🍮  Tiramisu + Panna Cotta                    │
  │               Estimated delivery: 35 min                 │
  │               [Confirm Order — ₹480]                     │
  │                                                          │
  │  Tonight  ☕  Nescafé Gold 200g + Britannia bread       │
  │               Delivery: tomorrow 7 AM                    │
  │               [Confirm Checkout — ₹340]                  │
  └──────────────────────────────────────────────────────────┘

Step 4 — Confirmation gates (one per action)
  → User taps "Confirm Reservation" → book_table(...) called
  → User taps "Confirm Order" → place_food_order(...) called
  → User taps "Confirm Checkout" → checkout(...) called
```

Each action is independent. You can confirm the dinner and skip the dessert. Nothing is grouped or forced.

---

## Architecture Overview

```
User Voice Input
      │
      ▼
React Native App  (push-to-talk, transcript editing, timeline UI)
      │
      │  HTTPS
      ▼
FastAPI Backend  (auth, session management, orchestration API)
      │
      │  LLM API call
      ▼
LLM Orchestrator  (intent parsing, plan generation, tool selection)
      │
      ├──────────────────────────────────────────────┐
      │  read-only queries (no confirmation needed)  │
      │                                              │
      ▼                                              ▼
 Confirmation Gate  ◄──── User Approval ────  Read Results
      │
      │  only after explicit user confirmation
      ▼
Swiggy MCP Servers
  ├── Food MCP       → place_food_order
  ├── Instamart MCP  → checkout
  └── Dineout MCP    → book_table
```

The Confirmation Gate is a hard interlock: mutating MCP calls (`place_food_order`, `checkout`, `book_table`) are never issued until the user has tapped a confirmation button on a screen that clearly describes what will happen and what it will cost.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for full component breakdown and data flow.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Mobile | React Native + Expo (iOS & Android) |
| Voice input | Push-to-talk with editable transcript |
| Voice output | Short TTS responses (ElevenLabs or system TTS) |
| Backend | FastAPI (Python) |
| AI orchestration | LLM API (Claude / GPT-4) for intent parsing and plan generation |
| Swiggy integration | Food MCP, Instamart MCP, Dineout MCP |
| Auth | OAuth 2.0 via Swiggy, handled by FastAPI backend |
| Storage | Minimal: user preferences, consent records, session plan summaries |

---

## MCP Servers Used

### Swiggy Food MCP
Real-time restaurant search, menu lookup, cart management, and order placement for food delivery.

| Tool | Purpose |
|---|---|
| `search_restaurants` | Find restaurants matching cuisine, location, and time constraints |
| `search_menu` | Search across restaurant menus for specific items |
| `get_restaurant_menu` | Fetch full menu for a specific restaurant |
| `update_food_cart` | Add/remove items from the food delivery cart |
| `get_food_cart` | Read current cart state before any mutation |
| `place_food_order` | Place order — **requires user confirmation** |
| `track_food_order` | Show live delivery status |

### Swiggy Instamart MCP
Grocery search, cart management, and checkout for same-day / scheduled grocery delivery.

| Tool | Purpose |
|---|---|
| `search_products` | Find grocery items by name or category |
| `update_cart` | Add/remove items from the grocery cart |
| `get_cart` | Read current cart state before any mutation |
| `checkout` | Complete grocery order — **requires user confirmation** |
| `track_order` | Show delivery status |
| `get_orders` | Review past orders for context |

### Swiggy Dineout MCP
Restaurant discovery, slot availability, and table booking for dining out.

| Tool | Purpose |
|---|---|
| `search_restaurants_dineout` | Find dine-in restaurants by cuisine, location, date |
| `get_restaurant_details` | Fetch full details, menu, ratings |
| `get_available_slots` | Check real-time table availability |
| `book_table` | Book a table — **requires user confirmation** |
| `get_booking_status` | Check status of an existing reservation |

---

## Safety Principles

1. **Confirmation-first** — No order is placed, no table is booked, no grocery checkout is triggered without a dedicated confirmation step. The user sees what will happen and the cost before anything is committed.

2. **No silent mutations** — Every state change (cart update, booking, order) is visible to the user in the UI before it executes. Background mutations do not occur.

3. **Cart state refresh before mutation** — Before any `update_food_cart`, `update_cart`, or similar write call, the app fetches the current cart state to prevent stale-write conflicts.

4. **ID sanitization** — Internal Swiggy resource IDs (restaurant IDs, item IDs, slot IDs, booking references) are never displayed to the user or read aloud. Only human-readable names and descriptions are surfaced.

5. **Data minimization** — Voice transcripts are used only within the session and not persisted. Swiggy transaction details and cart contents are not stored beyond what is needed to render the current plan.

See [docs/SAFETY.md](docs/SAFETY.md) for full policy documentation.

---

## Roadmap

| Phase | Description | Status |
|---|---|---|
| **Phase 1** | Application package: repo, architecture docs, application form | ✅ Done |
| **Phase 2** | Mock-mode prototype: full UI with simulated MCP responses, no live API calls | ✅ Done |
| **Phase 3** | Real MCP integration: live Swiggy Food, Instamart, Dineout connections | 🔲 Waiting for confirmation |
| **Phase 4** | Safety & observability: confirmation gate hardening, audit logging, error recovery | 🔲 Planned |
| **Phase 5** | Demo polish: voice quality, animation, edge-case handling, submission video | 🔲 Planned |

---

## Running Locally

### Backend
```bash
cd backend
cp .env.example .env
python3.13 -m venv venv313 && source venv313/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Test: `curl http://localhost:8000/health`

Test the hero flow:
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Plan Friday evening for two. Italian dinner around 8 PM, dessert later at home, and restock coffee for tomorrow."}'
```

### Mobile
```bash
cd mobile
npm install
npx expo start
```

Then press `i` for iOS simulator or `a` for Android.

---

## Status

**Phase 2 complete — Mock-mode prototype running with simulated Swiggy MCP data. Awaiting Builders Club access for real API integration.**

Application acknowledged by Swiggy Builders Club team. Real MCP credentials pending.

Previously: Phase 1 — Applying to Swiggy Builders Club via [application form](https://forms.gle/4vkeKyqm15Qb6fnJA).

---

## Author

**Sarath M S**
- GitHub: [github.com/sarath-m-s](https://github.com/sarath-m-s)
- LinkedIn: [linkedin.com/in/iamsarathms](https://www.linkedin.com/in/iamsarathms/)

---

## License

MIT © 2025 Sarath M S. See [LICENSE](LICENSE).

> **Powered by Swiggy** — This project integrates with Swiggy Food, Swiggy Instamart, and Swiggy Dineout via their official MCP server APIs.
