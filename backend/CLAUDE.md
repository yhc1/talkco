# Backend CLAUDE.md

> This file defines the backend implementation spec.
> For product concepts and terminology, refer to the root /CLAUDE.md.

---

## Current Implementation Scope

**Phase 1 (now): Core Conversation**
- Session management
- OpenAI Realtime S2S (SSE streaming)
- System prompt injection
- Tool calling (search_news)

**Phase 2 (later): End-of-Conversation Review**
- Conversation transcript storage
- AI Mark generation (post-conversation analysis)
- User Learning Profile update

Do not implement Phase 2 until Phase 1 is verified locally.

---

## Architecture

The mobile app never connects directly to AI providers. All communication goes through this backend.

```
Mobile App
    ↕ REST (JSON + SSE)
Python Backend (FastAPI)
    → OpenAI Realtime API: audio → audio + text (single WebSocket hop)
```

### Provider

One provider only in Phase 1:
- `providers/openai_s2s.py` — OpenAI Realtime S2S via `openai` SDK
  - Interface: `chat_audio(history, audio) → async generator of SSE events`
  - Handles transcript, response text, and audio output in one hop

---

## REST Endpoints

**POST /sessions**
- Creates a new Conversation session
- Initializes conversation history with system prompt
- Request: `{ user_id: string }`
- Response: `{ session_id: string, created_at: timestamp }`

**DELETE /sessions/:id**
- Ends a session
- Phase 2 hook goes here (not implemented in Phase 1)
- Response: `{ session_id: string, status: "completed" }`

**POST /sessions/:id/chat**
- The core conversation endpoint
- Request: `multipart/form-data { audio: file (WAV/PCM) }`
- Response: `text/event-stream` (SSE) with the following events:

  ```
  event: transcript data: {"text": "What the user said"}
  event: response   data: {"text": "AI's text reply"}
  event: audio      data: {"audio": "<base64 encoded WAV>"}
  event: timing     data: {"step": "s2s", "duration_s": 3.2}
  event: timing     data: {"step": "total", "duration_s": 3.2}
  event: done       data: {}
  ```

- Internal flow:
  1. Receive audio file from request
  2. Send conversation history + audio to OpenAI Realtime API
  3. Yield transcript, response, and audio events as they arrive from OpenAI
  4. After all events, append user/assistant messages to session history

---

## LLM Tool-Call Loop

Tool calling is handled inside the S2S provider:

```
send history + audio + tools to OpenAI Realtime API
if response has tool_calls:
    execute each tool call
    send tool results back
return final transcript + response + audio
```

Currently implemented tools:
- `search_news` — mock news search (returns fake articles)

---

## Configuration

Settings in `config.py` (read from `.env`):
- `OPENAI_API_KEY` — required
- `S2S_MODEL` — default `gpt-realtime`

---

## Local Testing Guide

```bash
# Terminal 1 — start the server
cd backend && source .venv/bin/activate && python main.py

# Terminal 2 — run the test client
cd backend && source .venv/bin/activate && python test_client.py
```

1. Record and send a normal English sentence → verify transcript is correct, AI responds, audio plays
2. Say "What's in the news today?" → verify tool call in backend logs, AI discusses news
3. Continue conversation → verify context maintained across turns

---

## Key Constraints

- **S2S only**: Do not implement ASR + LLM + TTS pipeline mode. S2S is the only conversation mode in Phase 1.
- **Conversation history**: Stored in-memory on the Session object. Lost on server restart (acceptable for Phase 1).
- **SSE streaming**: Each POST to `/chat` returns an SSE stream. Events are yielded incrementally as they arrive from OpenAI.
- **No TTS in backend logic**: Audio output comes directly from OpenAI Realtime API, not from a separate TTS provider.