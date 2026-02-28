# Backend CLAUDE.md

> This file defines the backend implementation spec.

## Architecture

The mobile app never connects directly to AI providers. All communication goes through this backend.

```
Mobile App
    ↕ REST (JSON + SSE)
Python Backend (FastAPI)
    → OpenAI Realtime API: audio → audio + text (single WebSocket hop)
    → OpenAI Chat Completions (GPT-4o): review analysis, corrections, session review, profile update, chat summary
```

### Providers

- `providers/openai_s2s.py` — OpenAI Realtime S2S via `openai` SDK
  - Handles transcript, response text, and audio output in one hop
  - Uses `gpt-4o-mini-transcribe` for input audio transcription
  - Dynamic system prompt built from topic + learner profile context + same-topic chat history
  - Two modes: `conversation` (normal topic chat) and `review` (weak point practice)
  - Review mode uses a dedicated system prompt focused on targeted exercises with immediate feedback
  - Triggers AI greeting on connect; `stream_greeting()` streams it without persisting as segment
  - Persists segments to SQLite after each turn (only when both transcript and response are non-empty)
  - Drains stale events from the queue before sending new audio to avoid race conditions
  - Audio silence detection: frontend checks RMS energy before sending; empty transcripts are discarded
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
- Tables: `sessions`, `segments`, `ai_marks`, `corrections`, `user_profiles`, `session_summaries`, `chat_summaries`
- Migrations: `init_db()` runs `ALTER TABLE` for columns added after initial schema (e.g. `sessions.mode`, `sessions.topic_id`)

### Sessions

- `sessions.py` — Session lifecycle management
  - `create_session(user_id, topic, mode)` — Creates session, fetches learner profile, builds system prompt
    - `mode="conversation"`: requires topic; queries same-topic chat history to inject into system prompt
    - `mode="review"`: no topic needed; builds weak points detail from profile for targeted practice
  - `delete_session(session_id)` — Closes WebSocket, launches background review (conversation mode) or ends immediately (review mode)
  - In-memory dicts track active sessions, user IDs, and modes

### Review & Profile

- `review.py` — Four functions:
  - `generate_review(session_id)` — AI Marks (one per segment, combining all issue types), runs in background after conversation ends. Skips malformed marks with warning log.
  - `generate_correction(session_id, segment_id, user_message) → dict` — Synchronous correction for user questions during review. Stores result in `corrections` table.
  - `generate_session_review(session_id) → dict` — Final structured review when user presses End. Stores result in `session_summaries` table.
  - `generate_chat_summary(session_id) → dict` — Generates a content summary of the conversation (topic discussed, key points covered). Stored in `chat_summaries` table. Used to provide context when starting future conversations on the same topic.
- `profile.py` — User Learning Profile CRUD and post-session update
  - `get_or_create_profile(user_id) → dict` — Returns existing or creates default profile (default level: B1)
  - `update_profile_after_session(user_id, session_id) → dict` — Gathers session data (segments, marks, corrections, summary) plus last 5 completed session summaries for trend context, and calls GPT-4o to update profile. Uses CEFR scale (A1–C2) for level assessment.
  - `compute_needs_review(profile_data) → bool` — Returns true if any weak point pattern has 3+ examples (repeated errors)
  - Profile `weak_points` uses structured format: `{ dimension: [{ pattern: "繁中描述", examples: [{ wrong, correct }] }] }`

### Tests

- `tests/test_review.py` — pytest tests for review functions with mocked `chat_json`
- Run with: `python -m pytest tests/ -v`
- Config: `pytest.ini` (asyncio_mode = auto)

---

## REST Endpoints

### Conversation

**GET /topics**
- Returns the list of predefined conversation topics
- Response: `[{ id, label_en, label_zh, prompt_hint }, ...]`

**POST /sessions**
- Creates a new session (conversation or review mode)
- `mode="conversation"`: validates `topic_id`, fetches same-topic chat history, builds context-rich system prompt
- `mode="review"`: no topic needed, builds weak points detail from profile
- Fetches user's Learning Profile to build learner context for the AI
- Persists to DB and initializes WebSocket connection in background
- After WebSocket connects, AI greeting is triggered automatically
- Request: `{ user_id: string, topic_id: string | null, mode: "conversation" | "review" }`
- Response: `{ session_id: string, created_at: timestamp }`

**POST /sessions/{id}/start**
- Streams the AI's greeting message (triggered during session creation)
- Returns 503 if session is still connecting
- Greeting is NOT persisted as a segment (no user utterance to review)
- Response: `text/event-stream` (SSE) with events: response, audio, timing, done

**DELETE /sessions/{id}**
- Ends the real-time conversation
- Conversation mode: closes WebSocket, updates DB status to "reviewing", launches background AI Mark generation
- Review mode: closes WebSocket, marks session as "ended" immediately (no review generation)
- Response: `{ session_id: string, status: "reviewing" | "ended", mode: string }`

**POST /sessions/{id}/chat**
- The core conversation endpoint
- Returns 503 if session is still connecting
- Request: `multipart/form-data { audio: file (WAV/PCM) }`
- Response: `text/event-stream` (SSE) with events: transcript, response, audio, timing, done

**POST /sessions/{id}/chat/text**
- Text-based chat (alternative to audio)
- Request: `{ text: string }`
- Response: `text/event-stream` (SSE) with same events as audio chat

### Review

**GET /sessions/{id}/review**
- Returns segments with AI marks, corrections, and session summary (if available)
- If still generating (status=reviewing), returns partial data (marks may still be populating)
- Each segment includes `ai_marks` and `corrections` arrays
- Response: `{ session_id, status, segments: [...], summary: { strengths, weaknesses, overall } | null }`

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
- Background job: generates session review, generates chat summary, updates User Learning Profile, sets status to "completed"
- Returns 400 if session already completed
- Response: `{ session_id, status: "completing" }`
- Client polls GET /sessions/{id}/review until status="completed" and summary is present

### Profile

**GET /users/{user_id}/profile**
- Returns current User Learning Profile
- Creates default profile if none exists
- Includes `needs_review: bool` indicating if repeated errors detected
- Response: `{ user_id, level, profile_data, updated_at, needs_review }`

**POST /users/{user_id}/evaluate**
- Re-evaluates user's CEFR level based on recent session history
- Response: `{ user_id, level, profile_data, updated_at, needs_review }`

---

## Chat Summary & History Context

Each completed conversation session generates a **chat summary** stored in `chat_summaries`:
- `session_id` — links to the session
- `topic_id` — the topic of the conversation
- `summary` — brief description of what was discussed (generated by GPT-4o)

When a new conversation session starts on a topic, the backend queries `chat_summaries` for previous sessions on the **same topic** (by the same user). These summaries are injected into the system prompt so the AI can:
- Reference what the user discussed before on this topic
- Avoid repeating the same conversation
- Build on previous discussions naturally

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

## Configuration

Settings in `config.py` (Pydantic BaseSettings, read from `.env`):
- `OPENAI_API_KEY` — required
- `S2S_MODEL` — default `gpt-4o-realtime-preview`
- `S2S_VOICE` — default `alloy`
- `CHAT_MODEL` — default `gpt-4o` (used for review/profile)
- `DB_PATH` — default `talkco.db`

---

## Key Constraints

- **SSE streaming**: Each POST to `/chat` returns an SSE stream. Events are yielded incrementally as they arrive from OpenAI.
- **No TTS in backend logic**: Audio output comes directly from OpenAI Realtime API, not from a separate TTS provider.
- **Single SQLite connection**: Shared across the app via `db.get_db()`. Acceptable for single-server deployment.
