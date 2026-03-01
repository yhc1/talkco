import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import uvicorn
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import sessions
from constants import SessionMode, SessionStatus
from db import init_db, close_db, get_db
from profile import get_or_create_profile, update_profile_after_session, evaluate_level, generate_progress_notes, generate_quick_review, compute_needs_review
from review import generate_correction, generate_session_review, generate_chat_summary
from topics import get_topics, get_topic_by_id

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    log.info("Database initialized")
    yield
    await close_db()
    log.info("Database closed")


app = FastAPI(title="TalkCo Backend", lifespan=lifespan)


# -- Request models --

class CreateSessionRequest(BaseModel):
    user_id: str
    topic_id: str | None = None
    mode: str = SessionMode.CONVERSATION


class CorrectionRequest(BaseModel):
    segment_id: int
    user_message: str


# -- Session endpoints --

@app.get("/topics")
async def list_topics():
    return get_topics()


@app.post("/sessions")
async def create_session(req: CreateSessionRequest):
    if req.mode not in SessionMode:
        raise HTTPException(status_code=400, detail=f"Invalid mode: {req.mode}")

    topic = None
    if req.mode == SessionMode.CONVERSATION:
        if not req.topic_id:
            raise HTTPException(status_code=400, detail="topic_id is required for conversation mode")
        topic = get_topic_by_id(req.topic_id)
        if topic is None:
            raise HTTPException(status_code=400, detail=f"Unknown topic_id: {req.topic_id}")

    result = await sessions.create_session(req.user_id, topic=topic, mode=req.mode)
    return result


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    result = await sessions.delete_session(session_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return result


@app.post("/sessions/{session_id}/start")
async def start_session(session_id: str):
    session = sessions.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    if not session._connected:
        connected = await session.wait_until_connected()
        if not connected:
            raise HTTPException(
                status_code=504, detail="Session connection timed out"
            )

    return StreamingResponse(
        session.stream_greeting(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/sessions/{session_id}/chat")
async def chat(session_id: str, audio: UploadFile = File(...)):
    session = sessions.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    if not session._connected:
        raise HTTPException(
            status_code=503, detail="Session still connecting, try again shortly"
        )

    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio file")

    return StreamingResponse(
        session.send_audio_and_stream(audio_bytes),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )



class TextChatRequest(BaseModel):
    text: str


@app.post("/sessions/{session_id}/chat/text")
async def chat_text(session_id: str, req: TextChatRequest):
    session = sessions.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    if not session._connected:
        raise HTTPException(
            status_code=503, detail="Session still connecting, try again shortly"
        )

    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Empty text")

    return StreamingResponse(
        session.send_text_and_stream(req.text.strip()),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# -- Review endpoints --

@app.get("/sessions/{session_id}/review")
async def get_review(session_id: str):
    db = await get_db()

    # Check session exists
    session_rows = await db.execute_fetchall(
        "SELECT id, status FROM sessions WHERE id = ?", (session_id,)
    )
    if not session_rows:
        raise HTTPException(status_code=404, detail="Session not found")

    status = session_rows[0]["status"]

    # Fetch segments
    segments = await db.execute_fetchall(
        "SELECT id, turn_index, user_text, ai_text FROM segments "
        "WHERE session_id = ? ORDER BY turn_index",
        (session_id,),
    )

    # Fetch AI marks for these segments
    seg_ids = [s["id"] for s in segments]
    marks_by_segment: dict[int, list] = {}
    if seg_ids:
        placeholders = ",".join("?" * len(seg_ids))
        marks = await db.execute_fetchall(
            f"SELECT id, segment_id, issue_types, original, suggestion, explanation "
            f"FROM ai_marks WHERE segment_id IN ({placeholders})",
            seg_ids,
        )
        for m in marks:
            marks_by_segment.setdefault(m["segment_id"], []).append({
                "id": m["id"],
                "issue_types": json.loads(m["issue_types"]),
                "original": m["original"],
                "suggestion": m["suggestion"],
                "explanation": m["explanation"],
            })

    # Fetch corrections for this session
    corrections_by_segment: dict[int, list] = {}
    corrections = await db.execute_fetchall(
        "SELECT id, segment_id, user_message, correction, explanation, created_at "
        "FROM corrections WHERE session_id = ?",
        (session_id,),
    )
    for c in corrections:
        corrections_by_segment.setdefault(c["segment_id"], []).append({
            "id": c["id"],
            "user_message": c["user_message"],
            "correction": c["correction"],
            "explanation": c["explanation"],
            "created_at": c["created_at"],
        })

    # Build response
    segments_out = []
    for s in segments:
        segments_out.append({
            "id": s["id"],
            "turn_index": s["turn_index"],
            "user_text": s["user_text"],
            "ai_text": s["ai_text"],
            "ai_marks": marks_by_segment.get(s["id"], []),
            "corrections": corrections_by_segment.get(s["id"], []),
        })

    # Fetch summary
    summary = None
    summary_rows = await db.execute_fetchall(
        "SELECT strengths, weaknesses, overall "
        "FROM session_summaries WHERE session_id = ?",
        (session_id,),
    )
    if summary_rows:
        row = summary_rows[0]
        summary = {
            "strengths": json.loads(row["strengths"]),
            "weaknesses": json.loads(row["weaknesses"]),
            "overall": row["overall"],
        }

    return {
        "session_id": session_id,
        "status": status,
        "segments": segments_out,
        "summary": summary,
    }


# -- Correction endpoint --

@app.post("/sessions/{session_id}/corrections")
async def create_correction(session_id: str, req: CorrectionRequest):
    db = await get_db()

    # Verify session exists and is in reviewing state
    session_rows = await db.execute_fetchall(
        "SELECT id, status FROM sessions WHERE id = ?", (session_id,)
    )
    if not session_rows:
        raise HTTPException(status_code=404, detail="Session not found")

    if session_rows[0]["status"] not in (SessionStatus.REVIEWING, SessionStatus.COMPLETED):
        raise HTTPException(status_code=400, detail="Session is not in review state")

    # Verify segment belongs to session
    seg_rows = await db.execute_fetchall(
        "SELECT id FROM segments WHERE id = ? AND session_id = ?",
        (req.segment_id, session_id),
    )
    if not seg_rows:
        raise HTTPException(status_code=404, detail="Segment not found in this session")

    result = await generate_correction(session_id, req.segment_id, req.user_message)
    return result


# -- End session (finalize review) --

@app.post("/sessions/{session_id}/end")
async def end_session(session_id: str):
    db = await get_db()

    session_rows = await db.execute_fetchall(
        "SELECT id, user_id, status FROM sessions WHERE id = ?", (session_id,)
    )
    if not session_rows:
        raise HTTPException(status_code=404, detail="Session not found")

    session = session_rows[0]
    if session["status"] == SessionStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Session already completed")

    # Check if there are any segments to review
    seg_count = await db.execute_fetchall(
        "SELECT COUNT(*) as cnt FROM segments WHERE session_id = ?", (session_id,)
    )
    if seg_count[0]["cnt"] == 0:
        # No conversation happened — mark completed immediately, no review needed
        await db.execute(
            "UPDATE sessions SET status = ? WHERE id = ?",
            (SessionStatus.COMPLETED, session_id),
        )
        await db.commit()
        return {"session_id": session_id, "status": SessionStatus.COMPLETED}

    # Mark as completing immediately
    await db.execute(
        "UPDATE sessions SET status = ? WHERE id = ?",
        (SessionStatus.COMPLETING, session_id),
    )
    await db.commit()

    # Launch session review + profile update in background
    asyncio.create_task(_finalize_session(session_id, session["user_id"]))

    return {
        "session_id": session_id,
        "status": SessionStatus.COMPLETING,
    }


async def _finalize_session(session_id: str, user_id: str) -> None:
    """Background: generate session review + update profile + chat summary in parallel, mark completed."""
    import time as _time
    try:
        t0 = _time.monotonic()

        tasks = [
            generate_session_review(session_id, user_id),
            update_profile_after_session(user_id, session_id),
        ]

        # Add chat summary for conversation mode (has topic_id)
        db = await get_db()
        rows = await db.execute_fetchall(
            "SELECT topic_id FROM sessions WHERE id = ?", (session_id,)
        )
        topic_id = rows[0]["topic_id"] if rows and rows[0]["topic_id"] else None
        if topic_id:
            tasks.append(generate_chat_summary(session_id, topic_id))

        results = await asyncio.gather(*tasks)
        t1 = _time.monotonic()
        log.info("Session %s finalize took %.1fs (review=%s, chat_summary=%s)",
                 session_id, t1 - t0,
                 "skipped" if results[0] is None else "done",
                 "done" if topic_id else "skipped")
    except Exception as e:
        log.error("Failed to finalize session %s: %s", session_id, e)
    finally:
        # Always mark session as completed so the client stops polling
        try:
            db = await get_db()
            await db.execute(
                "UPDATE sessions SET status = ? WHERE id = ?",
                (SessionStatus.COMPLETED, session_id),
            )
            await db.commit()
            log.info("Session %s marked completed", session_id)
        except Exception as e:
            log.error("Failed to mark session %s completed: %s", session_id, e)


# -- User profile endpoint --

@app.get("/users/{user_id}/profile")
async def get_user_profile(user_id: str):
    profile = await get_or_create_profile(user_id)
    profile["needs_review"] = compute_needs_review(profile.get("profile_data", {}))
    return profile


async def _update_profile_data_sequentially(user_id: str) -> None:
    """Run profile_data updates sequentially to avoid overwrite race."""
    await generate_progress_notes(user_id)
    await generate_quick_review(user_id)


@app.post("/users/{user_id}/evaluate")
async def evaluate_user_level(user_id: str):
    # evaluate_level only updates `level` column, safe to run in parallel.
    # progress_notes and quick_review both update profile_data — run sequentially to avoid overwrite race.
    await asyncio.gather(
        evaluate_level(user_id),
        _update_profile_data_sequentially(user_id),
    )
    profile = await get_or_create_profile(user_id)
    profile["needs_review"] = compute_needs_review(profile.get("profile_data", {}))
    return profile


if __name__ == "__main__":
    import os
    reload = os.environ.get("NO_RELOAD", "").lower() not in ("1", "true")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=reload)
