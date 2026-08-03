# AI APMS Navigation Agent API

FastAPI service for secure APMS navigation, normal chat, PostgreSQL conversation memory, and pgvector retrieval.

## Run locally

```powershell
.\venv\Scripts\Activate.ps1
uvicorn main:app --reload
```

Open `http://127.0.0.1:8000/docs` for the API contract.

## Call the agent

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/v1/agent/chat `
  -Headers @{ "X-API-Key" = "your-api-key" } `
  -ContentType "application/json" `
  -Body '{"message":"Can you take me to authentication?","current_screen":"dashboard"}'
```

Do not type a conversation ID for a new conversation: omit `conversation_id`
and the API returns a unique UUID in its response. Save and send that UUID only
for later messages in the same conversation. Any non-UUID value (including the
Swagger UI placeholder `"string"`) is ignored and replaced with a new UUID. Pass
`current_screen` on each request so the assistant can use the user's current
screen as navigation context. The actual model tokens used for every assistant
response are stored in `chat_messages.token_usage` and also returned as
`token_usage` (cached responses record 0).

Set `API_KEYS` in `.env` before a production deployment. Multiple comma-separated keys are supported.
