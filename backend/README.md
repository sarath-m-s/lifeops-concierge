# LifeOps Concierge — Backend

FastAPI backend providing the orchestration API, mock MCP services, and auth handling for the LifeOps Concierge mobile app.

## Quick Start

```bash
cp .env.example .env
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Health check — returns version and mock_mode flag |
| POST | `/chat` | Send a message, receive an `AgentResponse` |
| POST | `/confirm` | Execute a confirmed pending action |
| GET | `/auth/callback` | OAuth callback handler |
| GET | `/auth/status` | Current auth state |

## Example

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Plan Friday evening for two. Italian dinner around 8 PM, dessert later at home, and restock coffee for tomorrow."}'
```

## Mock Mode

All MCP calls are mocked in Phase 2. Set `APP_ENV=production` and provide real Swiggy credentials for Phase 3 integration.
