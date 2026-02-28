import asyncio
import base64
import json
import logging
import time
from datetime import datetime, timezone
from typing import AsyncGenerator

from openai import AsyncOpenAI

from config import settings
from db import get_db
from tools import TOOL_DEFINITIONS, execute_tool

log = logging.getLogger(__name__)

BASE_SYSTEM_PROMPT = """\
You are a friendly, patient English conversation partner for a Mandarin Chinese native speaker.
Your goals:
- Help the learner practice natural, real-life English conversation.
- Adapt continuously to the learner’s level and recent performance.
- Keep the learner relaxed and motivated.
Conversation style:
- Speak ONLY in English unless the user explicitly asks for Chinese.
- Match the learner’s level: if they use simple sentences, keep yours simple; if they are advanced, you can be more complex.
- Keep each turn concise: usually 1–3 sentences.
- Use natural, idiomatic expressions that a native speaker would actually say in everyday conversation.
- Ask clear, engaging follow-up questions to keep the conversation going, but don’t overwhelm the learner.
Error handling:
- Do NOT explicitly correct grammar or vocabulary during the conversation.
- Instead, always respond with natural, correct English so the learner can absorb patterns implicitly.
- If the learner directly asks for an explanation or correction, you may briefly explain in simple English.
Context & tools:
- You are chatting about the topic and context provided separately (e.g. today’s conversation topic and learner profile).
- If the learner asks about news or current events, and you need up‑to‑date information, use the `search_news` tool instead of guessing.
Overall:
- Prioritize fluency, confidence, and naturalness over dense teaching.
- Avoid long lectures; stay conversational and interactive.
"""


REVIEW_MODE_SYSTEM_PROMPT = """\
You are a dedicated English teacher conducting targeted practice for a Mandarin Chinese native speaker.
Your goals:
- Design exercises based on the learner's specific weak points provided below.
- Create realistic scenarios that require the learner to use correct grammar/vocabulary/sentence patterns.
Interaction style:
- After each learner response, give immediate feedback:
  - If correct: brief encouragement (1 sentence), then present the next exercise.
  - If incorrect: correct the mistake, briefly explain why (1-2 sentences), then give a similar exercise.
- If the learner's response is unclear, off-topic, seems unrelated to the exercise, or is just noise/silence, \
do NOT guess what they meant. Instead, gently ask them to try again. \
For example: "I didn't quite catch that. Could you try answering the question again?"
- Speak ONLY in English unless the learner explicitly asks for a Chinese explanation.
- Keep exercises focused and varied — use different scenarios for the same pattern.
- Maintain an encouraging, patient tone throughout.
- Keep each turn concise: 2-4 sentences maximum.
"""


def _build_system_prompt(topic: str, learner_summary: str, mode: str = "conversation",
                         weak_points_detail: str = "",
                         prior_topic_summaries: list[str] | None = None) -> str:
    """Build a dynamic system prompt with topic and learner context."""
    if mode == "review":
        parts = [REVIEW_MODE_SYSTEM_PROMPT]
        if weak_points_detail:
            parts.append(f"\nLearner's weak points to practice:\n{weak_points_detail}")
        if learner_summary:
            parts.append(f"\nLearner context: {learner_summary}")
        parts.append(
            "\nStart by briefly greeting the learner, then immediately present the first exercise. "
            "Keep the greeting to 1 sentence."
        )
        return "\n".join(parts)

    parts = [BASE_SYSTEM_PROMPT]
    parts.append(f"\nToday's conversation topic: {topic}")
    if learner_summary:
        parts.append(f"\nLearner context: {learner_summary}")
    if prior_topic_summaries:
        summaries_text = "\n".join(f"- {s}" for s in prior_topic_summaries)
        parts.append(
            f"\nPrevious conversations on this topic:\n{summaries_text}\n"
            "Use this context to avoid repeating topics and build on what was discussed before."
        )
    parts.append(
        "\nStart the conversation by greeting the learner and naturally introducing the topic. "
        "Keep the greeting warm but brief (1-2 sentences)."
    )
    return "\n".join(parts)


class RealtimeSession:
    """Manages one persistent WebSocket connection to OpenAI Realtime API."""

    def __init__(self, session_id: str, topic: str = "free conversation", learner_summary: str = "",
                 mode: str = "conversation", weak_points_detail: str = "",
                 prior_topic_summaries: list[str] | None = None):
        self.session_id = session_id
        self._topic = topic
        self._learner_summary = learner_summary
        self._mode = mode
        self._weak_points_detail = weak_points_detail
        self._prior_topic_summaries = prior_topic_summaries
        self._client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self._conn = None
        self._event_queue: asyncio.Queue = asyncio.Queue()
        self._listener_task: asyncio.Task | None = None
        self._connected = False
        self._connected_event = asyncio.Event()
        self._turn_index = 0

    async def connect(self) -> None:
        """Open WebSocket and configure the session."""
        self._conn = await self._client.beta.realtime.connect(
            model=settings.S2S_MODEL
        ).enter()

        system_prompt = _build_system_prompt(self._topic, self._learner_summary,
                                               self._mode, self._weak_points_detail,
                                               self._prior_topic_summaries)
        log.info("System prompt for session %s:\n%s", self.session_id, system_prompt)

        await self._conn.session.update(
            session={
                "modalities": ["text", "audio"],
                "instructions": system_prompt,
                "voice": settings.S2S_VOICE,
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "input_audio_transcription": {"model": "gpt-4o-mini-transcribe"},
                "turn_detection": None,  # manual — backend controls turns
                "tools": TOOL_DEFINITIONS,
            }
        )

        # Wait for session.updated confirmation
        first_event = await self._conn.recv()
        log.info("Session configured: %s", first_event.type)

        self._connected = True
        self._connected_event.set()
        self._listener_task = asyncio.create_task(self._listen_loop())

        # Trigger AI greeting — events will flow into _event_queue
        await self._conn.response.create()

    async def wait_until_connected(self, timeout: float = 15.0) -> bool:
        """Wait for the WebSocket connection to be ready. Returns True if connected."""
        try:
            await asyncio.wait_for(self._connected_event.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            log.error("WebSocket connection timed out for session %s", self.session_id)
            return False

    async def _listen_loop(self) -> None:
        """Background task: read events from WebSocket and push to queue."""
        try:
            async for event in self._conn:
                await self._event_queue.put(event)
        except Exception as e:
            log.error("WebSocket listener error: %s", e)
            await self._event_queue.put(None)  # sentinel

    async def send_audio_and_stream(
        self, audio_bytes: bytes
    ) -> AsyncGenerator[str, None]:
        """
        Send user audio, commit buffer, trigger response, and yield SSE events.

        Yields SSE-formatted strings: "event: <type>\ndata: <json>\n\n"
        """
        if not self._connected:
            raise RuntimeError("Session not connected")

        t_start = time.monotonic()

        # Drain any stale events from previous turns BEFORE sending new audio
        while not self._event_queue.empty():
            try:
                self._event_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        # Send audio as base64 PCM16 chunks (max ~15MB per append)
        audio_b64 = base64.b64encode(audio_bytes).decode()
        await self._conn.input_audio_buffer.append(audio=audio_b64)
        await self._conn.input_audio_buffer.commit()
        await self._conn.response.create()

        # Read events until response.done
        transcript_text = ""
        response_text = ""
        t_first_audio = None

        while True:
            try:
                event = await asyncio.wait_for(
                    self._event_queue.get(), timeout=30.0
                )
            except asyncio.TimeoutError:
                log.warning("Timeout waiting for event")
                break

            if event is None:
                break

            event_type = event.type
            log.debug("Event: %s", event_type)

            if event_type == "conversation.item.input_audio_transcription.completed":
                transcript_text = event.transcript or ""
                yield _sse("transcript", {"text": transcript_text})

            elif event_type == "response.audio_transcript.delta":
                response_text += event.delta or ""

            elif event_type == "response.audio.delta":
                if t_first_audio is None:
                    t_first_audio = time.monotonic()
                yield _sse("audio", {"audio": event.delta})

            elif event_type == "response.output_item.done":
                item = event.item
                if getattr(item, "type", None) == "function_call":
                    await self._handle_tool_call(item)
                    continue  # new response will follow

            elif event_type == "response.done":
                break

            elif event_type == "error":
                log.error("Realtime API error: %s", event)
                break

        if response_text:
            yield _sse("response", {"text": response_text})

        # Persist segment to DB
        if transcript_text and response_text:
            try:
                db = await get_db()
                await db.execute(
                    "INSERT INTO segments (session_id, turn_index, user_text, ai_text, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (self.session_id, self._turn_index, transcript_text, response_text,
                     datetime.now(timezone.utc).isoformat()),
                )
                await db.commit()
                log.info(
                    "Segment saved: session=%s turn=%d user_text=%s",
                    self.session_id, self._turn_index, transcript_text[:80],
                )
                self._turn_index += 1
            except Exception as e:
                log.error("Failed to persist segment: %s", e)
        else:
            log.warning(
                "Segment NOT saved (empty): session=%s transcript=%r response=%r",
                self.session_id, bool(transcript_text), bool(response_text),
            )

        t_end = time.monotonic()
        if t_first_audio:
            yield _sse(
                "timing",
                {"step": "first_audio", "duration_s": round(t_first_audio - t_start, 3)},
            )
        yield _sse(
            "timing",
            {"step": "total", "duration_s": round(t_end - t_start, 3)},
        )
        yield _sse("done", {})

    async def stream_greeting(self) -> AsyncGenerator[str, None]:
        """
        Stream the AI's greeting (triggered during connect).
        Does NOT persist as a segment — greeting has no user utterance.
        """
        if not self._connected:
            raise RuntimeError("Session not connected")

        t_start = time.monotonic()
        response_text = ""
        t_first_audio = None

        while True:
            try:
                event = await asyncio.wait_for(
                    self._event_queue.get(), timeout=30.0
                )
            except asyncio.TimeoutError:
                log.warning("Timeout waiting for greeting event")
                break

            if event is None:
                break

            event_type = event.type
            log.debug("Greeting event: %s", event_type)

            if event_type == "response.audio_transcript.delta":
                response_text += event.delta or ""

            elif event_type == "response.audio.delta":
                if t_first_audio is None:
                    t_first_audio = time.monotonic()
                yield _sse("audio", {"audio": event.delta})

            elif event_type == "response.done":
                break

            elif event_type == "error":
                log.error("Realtime API error during greeting: %s", event)
                break

        if response_text:
            yield _sse("response", {"text": response_text})

        t_end = time.monotonic()
        if t_first_audio:
            yield _sse(
                "timing",
                {"step": "first_audio", "duration_s": round(t_first_audio - t_start, 3)},
            )
        yield _sse(
            "timing",
            {"step": "total", "duration_s": round(t_end - t_start, 3)},
        )
        yield _sse("done", {})

    async def send_text_and_stream(
        self, text: str
    ) -> AsyncGenerator[str, None]:
        """
        Send user text, trigger response, and yield SSE events.
        Same flow as send_audio_and_stream but with text input.
        """
        if not self._connected:
            raise RuntimeError("Session not connected")

        t_start = time.monotonic()

        # Drain stale events
        while not self._event_queue.empty():
            try:
                self._event_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        # Send text as a conversation item
        await self._conn.conversation.item.create(
            item={
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": text}],
            }
        )
        await self._conn.response.create()

        # Yield the user transcript immediately
        yield _sse("transcript", {"text": text})

        # Read events until response.done
        response_text = ""
        t_first_audio = None

        while True:
            try:
                event = await asyncio.wait_for(
                    self._event_queue.get(), timeout=30.0
                )
            except asyncio.TimeoutError:
                log.warning("Timeout waiting for event")
                break

            if event is None:
                break

            event_type = event.type
            log.debug("Event: %s", event_type)

            if event_type == "response.audio_transcript.delta":
                response_text += event.delta or ""

            elif event_type == "response.audio.delta":
                if t_first_audio is None:
                    t_first_audio = time.monotonic()
                yield _sse("audio", {"audio": event.delta})

            elif event_type == "response.output_item.done":
                item = event.item
                if getattr(item, "type", None) == "function_call":
                    await self._handle_tool_call(item)
                    continue

            elif event_type == "response.done":
                break

            elif event_type == "error":
                log.error("Realtime API error: %s", event)
                break

        if response_text:
            yield _sse("response", {"text": response_text})

        # Persist segment to DB
        if text and response_text:
            try:
                db = await get_db()
                await db.execute(
                    "INSERT INTO segments (session_id, turn_index, user_text, ai_text, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (self.session_id, self._turn_index, text, response_text,
                     datetime.now(timezone.utc).isoformat()),
                )
                await db.commit()
                log.info(
                    "Segment saved: session=%s turn=%d user_text=%s",
                    self.session_id, self._turn_index, text[:80],
                )
                self._turn_index += 1
            except Exception as e:
                log.error("Failed to persist segment: %s", e)

        t_end = time.monotonic()
        if t_first_audio:
            yield _sse(
                "timing",
                {"step": "first_audio", "duration_s": round(t_first_audio - t_start, 3)},
            )
        yield _sse(
            "timing",
            {"step": "total", "duration_s": round(t_end - t_start, 3)},
        )
        yield _sse("done", {})

    async def _handle_tool_call(self, item) -> None:
        """Execute a tool call and send the result back, triggering a new response."""
        name = item.name
        args_str = item.arguments or "{}"
        call_id = item.call_id
        log.info("Tool call: %s(%s)", name, args_str)

        try:
            args = json.loads(args_str)
        except json.JSONDecodeError:
            args = {}

        result = execute_tool(name, args)
        log.info("Tool result: %s", result[:200])

        await self._conn.conversation.item.create(
            item={
                "type": "function_call_output",
                "call_id": call_id,
                "output": result,
            }
        )
        await self._conn.response.create()

    async def close(self) -> None:
        """Shut down the session."""
        self._connected = False
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
        if self._conn:
            try:
                await self._conn.close()
            except Exception:
                pass


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"
