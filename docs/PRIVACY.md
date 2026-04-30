# Privacy Policy — LifeOps Concierge

This document describes what data LifeOps Concierge collects, how it is used, and what it does not collect or store. It is intended for users of the application and for Swiggy's compliance review.

---

## What Data Is Collected

### Voice Transcripts
- **Scope:** Session-only. Transcripts are used to parse the user's intent and are not written to permanent storage.
- **Retention:** Automatically cleared when the session ends or after 24 hours of inactivity, whichever is sooner.
- **Purpose:** Intent parsing only. Transcripts are not used for training, profiling, or advertising.

### Plan Summaries
- **Scope:** A structured summary of the generated plan (e.g., "Dineout: Trattoria Roma, Friday 8 PM, 2 people") is stored server-side to support timeline display across app restarts within the same session.
- **Retention:** Cleared with the session. Not retained beyond 24 hours.
- **Purpose:** Rendering the timeline UI and recovering plan state if the app is backgrounded.

### User Preferences
- **Scope:** Optional. Stored only if the user explicitly enables preference memory (e.g., default delivery address, cuisine preferences, typical party size).
- **Retention:** Persisted until the user clears them or deletes their account.
- **Purpose:** Pre-filling plan parameters to speed up future sessions.

---

## What Data Is NOT Stored

| Data type | Reason not stored |
|---|---|
| Swiggy transaction IDs, order IDs, booking references | Not needed after the current session; Swiggy retains this in their own systems |
| Payment information | LifeOps Concierge never has access to payment details; checkout is handled entirely within Swiggy's infrastructure |
| Full cart contents beyond the current session | Cart state is fetched fresh from the MCP API at the start of each session |
| Raw Swiggy API responses | Only human-readable fields (name, price, time) are extracted and used |
| Voice audio recordings | Audio is transcribed on-device or via a speech-to-text API; only the text transcript is sent to the backend |
| Location history | Current location is used only for the active search query; it is not logged or stored |

---

## Data Handling Declaration

**Controller:** Sarath M S (individual developer)

**Processing basis:** The user explicitly initiates each session and each action. Data is processed solely to fulfill the user's stated intent within that session.

**Third-party processors:**

| Processor | Data shared | Purpose |
|---|---|---|
| Swiggy MCP APIs (Food, Instamart, Dineout) | Search queries, cart updates, booking parameters | Fulfilling user-confirmed actions |
| LLM provider (Claude / GPT-4) | Voice transcript text | Intent parsing and plan generation |
| Speech-to-text provider | Voice audio (if server-side transcription is used) | Converting voice to text; audio is not retained by the provider beyond the API call |

**No data is sold, rented, or shared** with any party other than those listed above, and only to the extent necessary for the stated purpose.

**Swiggy OAuth tokens** are stored server-side only, never on the user's device. Tokens are scoped to the minimum permissions required to call the three MCP server APIs.

---

## User Rights

Users may at any time:
- Clear their session data and preferences via the app settings
- Revoke Swiggy OAuth access, which immediately disables all MCP calls
- Request deletion of any stored preferences by contacting the developer

---

## Contact

For privacy inquiries: sarathms789@gmail.com
