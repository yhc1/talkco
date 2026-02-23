import asyncio
import logging
import uuid
from datetime import datetime, timezone

from providers.openai_s2s import RealtimeSession

log = logging.getLogger(__name__)

_sessions: dict[str, RealtimeSession] = {}


async def create_session(user_id: str) -> dict:
    session_id = str(uuid.uuid4())
    session = RealtimeSession(session_id)
    _sessions[session_id] = session

    # Connect in background so the endpoint can return immediately
    asyncio.create_task(_connect_with_retry(session_id, session))

    return {
        "session_id": session_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


async def _connect_with_retry(session_id: str, session: RealtimeSession) -> None:
    try:
        await session.connect()
        log.info("Session %s connected", session_id)
    except Exception as e:
        log.error("Failed to connect session %s: %s", session_id, e)
        _sessions.pop(session_id, None)


def get_session(session_id: str) -> RealtimeSession | None:
    return _sessions.get(session_id)


async def delete_session(session_id: str) -> bool:
    session = _sessions.pop(session_id, None)
    if session is None:
        return False
    await session.close()
    log.info("Session %s deleted", session_id)
    return True
