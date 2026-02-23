import logging

import uvicorn
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import sessions

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger(__name__)

app = FastAPI(title="TalkCo Backend")


class CreateSessionRequest(BaseModel):
    user_id: str


@app.post("/sessions")
async def create_session(req: CreateSessionRequest):
    result = await sessions.create_session(req.user_id)
    return result


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    deleted = await sessions.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session_id": session_id, "status": "completed"}


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


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
