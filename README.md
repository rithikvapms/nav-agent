# AI APMS Navigation Agent API

FastAPI service for secure APMS navigation, normal chat, PostgreSQL conversation memory, and pgvector retrieval.

## Run locally

```powershell
.\venv\Scripts\Activate.ps1
uvicorn main:app --reload
```

Voice chat requires FFmpeg for WebM-to-WAV conversion. On Windows, install
FFmpeg and add its `bin` directory to `PATH`, or set `FFMPEG_BINARY` in `.env`
to the full path of `ffmpeg.exe`. The Docker image installs FFmpeg automatically.

VAD uses the vendored official model at `models/silero_vad.onnx` through ONNX
Runtime; it does not import PyTorch, torchaudio, torchcodec, or the
`silero-vad` Python package. Set `SILERO_VAD_MODEL` only to override the
bundled model path.

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

Voice responses use Kokoro ONNX. Download the official `kokoro-v1.0.onnx` and
`voices-v1.0.bin` files from the kokoro-onnx model release into `models/`, or
set `KOKORO_MODEL_PATH` and `KOKORO_VOICES_PATH` in `.env`. The API returns the
generated WAV as a base64 string in the unified `audio` field so it remains a
single JSON response.
