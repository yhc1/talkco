# Backend CLAUDE.md

> This file defines the backend implementation spec.
> For product concepts and terminology, refer to the root /CLAUDE.md.
> **Always read /CORRECTNESS.md before starting work** to avoid repeating past mistakes.

---

## Current Implementation Scope

**Phase 1 : Core Conversation**
- Session management
- OpenAI Realtime S2S (SSE streaming)
- System prompt injection
- Tool calling (search_news)

**Phase 2 : End-of-Conversation Review**
- Conversation transcript storage (SQLite via aiosqlite)
- AI Mark generation (post-conversation GPT-4o analysis, 4 dimensions)
- Interactive corrections (user asks about segments, gets immediate responses)
- Final session review with structured weaknesses and level assessment
- User Learning Profile creation and update

---

## Architecture

The mobile app never connects directly to AI providers. All communication goes through this backend.

```
Mobile App
    ↕ REST (JSON + SSE)
Python Backend (FastAPI)
    → OpenAI Realtime API: audio → audio + text (single WebSocket hop)
    → OpenAI Chat Completions (GPT-4o): review analysis, corrections, session review, profile update
```

### Providers

- `providers/openai_s2s.py` — OpenAI Realtime S2S via `openai` SDK
  - Handles transcript, response text, and audio output in one hop
  - Uses `gpt-4o-mini-transcribe` for input audio transcription
  - Dynamic system prompt built from topic + learner profile context
  - Triggers AI greeting on connect; `stream_greeting()` streams it without persisting as segment
  - Persists segments to SQLite after each turn (only when both transcript and response are non-empty)
  - Drains stale events from the queue before sending new audio to avoid race conditions
- `providers/openai_chat.py` — OpenAI Chat Completions wrapper
  - `chat_json(system_prompt, user_message) → dict` with JSON response format

### Tools

- `tools.py` — Tool definitions and execution for S2S conversation
  - `TOOL_DEFINITIONS` — JSON schema definitions passed to OpenAI Realtime API
  - `execute_tool(name, args) → str` — Dispatches tool calls
  - Currently implemented: `search_news` (mock news search, returns fake articles)

### Storage

- `db.py` — SQLite via aiosqlite (raw SQL, no ORM)
- Database file: `talkco.db` (configurable via `DB_PATH`)
- Tables: `sessions`, `segments`, `ai_marks`, `corrections`, `user_profiles`, `session_summaries`

### Review & Profile

- `review.py` — Three functions:
  - `generate_review(session_id)` — AI Marks (one per segment, combining all issue types), runs in background after conversation ends. Skips malformed marks with warning log.
  - `generate_correction(session_id, segment_id, user_message) → dict` — Synchronous correction for user questions during review. Stores result in `corrections` table.
  - `generate_session_review(session_id) → dict` — Final structured review when user presses End. Stores result in `session_summaries` table.
- `profile.py` — User Learning Profile CRUD and post-session update
  - `get_or_create_profile(user_id) → dict` — Returns existing or creates default profile (default level: B1)
  - `update_profile_after_session(user_id, session_id) → dict` — Gathers session data (segments, marks, corrections, summary) plus last 5 completed session summaries for trend context, and calls GPT-4o to update profile. Uses CEFR scale (A1–C2) for level assessment.

### Tests

- `tests/test_review.py` — pytest tests for all 3 review functions with mocked `chat_json`
- Run with: `python -m pytest tests/ -v`
- Config: `pytest.ini` (asyncio_mode = auto)

---

## REST Endpoints

### Phase 1 — Conversation

**GET /topics**
- Returns the list of predefined conversation topics
- Response: `[{ id, label_en, label_zh, prompt_hint }, ...]`

**POST /sessions**
- Creates a new Conversation session
- Validates `topic_id` against predefined topics (returns 400 if unknown)
- Fetches user's Learning Profile to build learner context for the AI
- Persists to DB and initializes WebSocket connection in background
- After WebSocket connects, AI greeting is triggered automatically
- Request: `{ user_id: string, topic_id: string }`
- Response: `{ session_id: string, created_at: timestamp }`

**POST /sessions/{id}/start**
- Streams the AI's greeting message (triggered during session creation)
- Returns 503 if session is still connecting
- Greeting is NOT persisted as a segment (no user utterance to review)
- Response: `text/event-stream` (SSE) with events: response, audio, timing, done

**DELETE /sessions/{id}**
- Ends the real-time conversation
- Closes WebSocket, updates DB status to "reviewing", launches background AI Mark generation
- Response: `{ session_id: string, status: "reviewing" }`

**POST /sessions/{id}/chat**
- The core conversation endpoint
- Returns 503 if session is still connecting
- Request: `multipart/form-data { audio: file (WAV/PCM) }`
- Response: `text/event-stream` (SSE) with events: transcript, response, audio, timing, done

### Phase 2 — Review

**GET /sessions/{id}/review**
- Returns segments with AI marks, corrections, and session summary (if available)
- If still generating (status=reviewing), returns partial data (marks may still be populating)
- Each segment includes `ai_marks` and `corrections` arrays
- Response: `{ session_id, status, segments: [...], summary: { strengths, weaknesses, level_assessment, overall } | null }`

**POST /sessions/{id}/corrections**
- User asks about a segment (can use Chinese, broken English, or mix)
- Synchronous — returns correction immediately
- Validates session is in "reviewing" or "completed" state
- Validates segment belongs to session
- Request: `{ segment_id: int, user_message: string }`
- Response: `{ id, segment_id, user_message, correction, explanation, created_at }`

**POST /sessions/{id}/end**
- User finalizes the review (presses End)
- Sets status to "completing" and returns immediately
- Background job: generates session review, updates User Learning Profile, sets status to "completed"
- Returns 400 if session already completed
- Response: `{ session_id, status: "completing" }`
- Client polls GET /sessions/{id}/review until status="completed" and summary is present

**GET /users/{user_id}/profile**
- Returns current User Learning Profile
- Creates default profile if none exists
- Response: `{ user_id, level, profile_data, updated_at }`

---

## Key Flow: Conversation Lifecycle

```
1. POST /sessions { user_id, topic }
   → Creates session, connects WebSocket in background
   → After connect: AI greeting triggered automatically

2. POST /sessions/{id}/start
   → Streams AI greeting (text + audio via SSE)
   → Client plays AI's opening message
   → Greeting is NOT stored as a segment

3. POST /sessions/{id}/chat  (repeatable)
   → Normal user audio → AI response cycle
   → turn_index starts at 0 (greeting excluded)

4. DELETE /sessions/{id}
   → Close WebSocket, update DB status to "reviewing"
   → Background: generate_review() → AI Marks (4 dimensions)

5. GET /sessions/{id}/review  (frontend polls)
   → Returns segments + AI marks + corrections
   → summary is null until POST /sessions/{id}/end is called

6. POST /sessions/{id}/corrections  (user asks about a segment, repeatable)
   → Synchronous: generate_correction() → immediate response

7. POST /sessions/{id}/end  (user presses End)
   → Sets status to "completing", returns immediately
   → Background: generate_session_review() + update_profile_after_session()
   → Sets status to "completed" when done

8. GET /sessions/{id}/review  (client polls until status=completed)
   → summary appears once background finalization completes
```

---

## Weakness Dimensions

Used in AI Marks, session review, and profile:

| Key | 中文 | Scope |
|---|---|---|
| `grammar` | 語法 | Tense, agreement, articles, prepositions |
| `naturalness` | 自然度 | Grammatically correct but unnatural |
| `vocabulary` | 詞彙 | Word choice too basic or imprecise |
| `sentence_structure` | 句式 | Chinese-influenced word order, missing connectors |

All Chinese-language output (explanations, review, assessment) is in Traditional Chinese (繁體中文).

---

## LLM Tool-Call Loop

Tool calling is handled inside the S2S provider (`providers/openai_s2s.py`):

```
send history + audio + tools to OpenAI Realtime API
if response has tool_calls:
    execute each tool call (via tools.execute_tool)
    send tool results back
    trigger new response
return final transcript + response + audio
```

Currently implemented tools:
- `search_news` — mock news search (returns fake articles)

---

## Configuration

Settings in `config.py` (Pydantic BaseSettings, read from `.env`):
- `OPENAI_API_KEY` — required
- `S2S_MODEL` — default `gpt-4o-realtime-preview`
- `S2S_VOICE` — default `alloy`
- `CHAT_MODEL` — default `gpt-4o` (used for review/profile)
- `DB_PATH` — default `talkco.db`

---

## Local Testing Guide

```bash
# Terminal 1 — start the server
cd backend && source .venv/bin/activate && python main.py

# Terminal 2 — run the test client
cd backend && source .venv/bin/activate && python test_client.py

# Run unit tests (no API key needed)
cd backend && source .venv/bin/activate && python -m pytest tests/ -v
```

### Phase 1 verification
1. Record and send a normal English sentence → verify transcript is correct, AI responds, audio plays
2. Say "What's in the news today?" → verify tool call in backend logs, AI discusses news
3. Continue conversation → verify context maintained across turns

### Phase 2 verification
1. Have a conversation (using test_client.py)
2. End the session (DELETE /sessions/{id})
3. Poll GET /sessions/{id}/review — verify AI Marks appear with 4 dimensions
4. POST /sessions/{id}/corrections — ask about a segment, get immediate correction
5. Finalize — POST /sessions/{id}/end — verify structured review + profile update
6. Check profile — GET /users/test-user/profile

---

## Key Constraints

- **SSE streaming**: Each POST to `/chat` returns an SSE stream. Events are yielded incrementally as they arrive from OpenAI.
- **No TTS in backend logic**: Audio output comes directly from OpenAI Realtime API, not from a separate TTS provider.
- **Single SQLite connection**: Shared across the app via `db.get_db()`. Acceptable for single-server deployment.
