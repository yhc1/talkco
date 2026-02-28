"""
Interactive test client for the TalkCo backend.

Records audio from the microphone, sends it to the backend,
reads SSE events, and plays back the AI's audio response.

Usage:
    python test_client.py
"""

import base64
import io
import struct
import sys
import threading
import time

import httpx
import numpy as np
import sounddevice as sd

BASE_URL = "http://localhost:8000"
SAMPLE_RATE = 24000  # OpenAI Realtime API uses 24kHz PCM16
CHANNELS = 1


def record_audio(duration_hint: float = 0.0) -> bytes:
    """Record audio from the microphone. Press Enter to stop."""
    print("\n🎤 Recording... (press Enter to stop)")
    frames = []
    recording = True

    def callback(indata, frame_count, time_info, status):
        if recording:
            frames.append(indata.copy())

    stream = sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="int16",
        callback=callback,
    )
    stream.start()
    input()  # blocks until Enter
    recording = False
    stream.stop()
    stream.close()

    if not frames:
        return b""

    audio = np.concatenate(frames, axis=0)
    pcm_bytes = audio.tobytes()
    print(f"   Recorded {len(pcm_bytes)} bytes ({len(pcm_bytes) / (SAMPLE_RATE * 2):.1f}s)")
    return pcm_bytes


def wrap_pcm_as_wav(pcm_bytes: bytes, sample_rate: int = SAMPLE_RATE) -> bytes:
    """Wrap raw PCM16 mono bytes in a WAV header."""
    buf = io.BytesIO()
    num_samples = len(pcm_bytes) // 2
    data_size = num_samples * 2
    # WAV header
    buf.write(b"RIFF")
    buf.write(struct.pack("<I", 36 + data_size))
    buf.write(b"WAVE")
    buf.write(b"fmt ")
    buf.write(struct.pack("<I", 16))  # chunk size
    buf.write(struct.pack("<H", 1))  # PCM format
    buf.write(struct.pack("<H", 1))  # mono
    buf.write(struct.pack("<I", sample_rate))
    buf.write(struct.pack("<I", sample_rate * 2))  # byte rate
    buf.write(struct.pack("<H", 2))  # block align
    buf.write(struct.pack("<H", 16))  # bits per sample
    buf.write(b"data")
    buf.write(struct.pack("<I", data_size))
    buf.write(pcm_bytes)
    return buf.getvalue()


def play_audio_chunks(audio_chunks: list[bytes]) -> None:
    """Play concatenated PCM16 audio chunks."""
    if not audio_chunks:
        return
    pcm = b"".join(audio_chunks)
    if not pcm:
        return
    audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    print(f"   🔊 Playing {len(pcm)} bytes ({len(pcm) / (SAMPLE_RATE * 2):.1f}s)")
    sd.play(audio, samplerate=SAMPLE_RATE)
    sd.wait()


def pick_topic() -> str:
    """Fetch topics from backend and let the user choose one."""
    resp = httpx.get(f"{BASE_URL}/topics")
    resp.raise_for_status()
    topics = resp.json()

    print("Pick a topic:")
    for i, t in enumerate(topics, 1):
        print(f"  [{i}] {t['label_en']} ({t['label_zh']})")

    while True:
        choice = input("> ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(topics):
            selected = topics[int(choice) - 1]
            print(f"Selected: {selected['label_en']}")
            return selected["id"]
        print(f"Enter a number 1-{len(topics)}")


def create_session(user_id: str, topic_id: str) -> str:
    resp = httpx.post(
        f"{BASE_URL}/sessions",
        json={"user_id": user_id, "topic_id": topic_id},
    )
    resp.raise_for_status()
    data = resp.json()
    print(f"Session created: {data['session_id']}")
    return data["session_id"]


def send_chat(session_id: str, pcm_bytes: bytes) -> None:
    """Send audio to /chat and process the SSE stream."""
    wav_bytes = wrap_pcm_as_wav(pcm_bytes)
    audio_chunks = []

    with httpx.stream(
        "POST",
        f"{BASE_URL}/sessions/{session_id}/chat",
        files={"audio": ("audio.wav", wav_bytes, "audio/wav")},
        timeout=60.0,
    ) as resp:
        resp.raise_for_status()
        current_event = None

        for line in resp.iter_lines():
            if line.startswith("event: "):
                current_event = line[7:]
            elif line.startswith("data: ") and current_event:
                import json
                data = json.loads(line[6:])

                if current_event == "transcript":
                    print(f"\n   You said: {data['text']}")
                elif current_event == "response":
                    print(f"   AI said:  {data['text']}")
                elif current_event == "audio":
                    chunk = base64.b64decode(data["audio"])
                    audio_chunks.append(chunk)
                elif current_event == "timing":
                    print(f"   ⏱ {data['step']}: {data['duration_s']}s")
                elif current_event == "done":
                    pass

                current_event = None

    play_audio_chunks(audio_chunks)


def stream_greeting(session_id: str) -> None:
    """Call /start and play the AI's greeting."""
    import json

    audio_chunks = []

    with httpx.stream(
        "POST",
        f"{BASE_URL}/sessions/{session_id}/start",
        timeout=60.0,
    ) as resp:
        resp.raise_for_status()
        current_event = None

        for line in resp.iter_lines():
            if line.startswith("event: "):
                current_event = line[7:]
            elif line.startswith("data: ") and current_event:
                data = json.loads(line[6:])

                if current_event == "response":
                    print(f"\n   AI: {data['text']}")
                elif current_event == "audio":
                    chunk = base64.b64decode(data["audio"])
                    audio_chunks.append(chunk)
                elif current_event == "timing":
                    print(f"   ⏱ {data['step']}: {data['duration_s']}s")

                current_event = None

    play_audio_chunks(audio_chunks)


def delete_session(session_id: str) -> None:
    resp = httpx.delete(f"{BASE_URL}/sessions/{session_id}")
    resp.raise_for_status()
    print("Session ended. Generating review...")


def show_review(session_id: str) -> list[dict]:
    """Fetch segments (already in DB), then wait briefly for AI marks."""
    import json as _json

    print("\n--- Review ---")

    # Segments are persisted during chat — fetch immediately
    resp = httpx.get(f"{BASE_URL}/sessions/{session_id}/review")
    resp.raise_for_status()
    data = resp.json()
    segments = data.get("segments", [])

    if not segments:
        print("   No segments recorded in this session.")
        return []

    # Show segments right away
    print(f"   {len(segments)} segment(s) found.\n")

    # Wait briefly for AI marks (background GPT-4o call)
    has_marks = any(s.get("ai_marks") for s in segments)
    if not has_marks:
        print("   Waiting for AI marks...", end="", flush=True)
        for attempt in range(5):
            time.sleep(2)
            resp = httpx.get(f"{BASE_URL}/sessions/{session_id}/review")
            resp.raise_for_status()
            data = resp.json()
            segments = data.get("segments", [])
            has_marks = any(s.get("ai_marks") for s in segments)
            if has_marks:
                break
            print(".", end="", flush=True)
        print(" done." if has_marks else " no marks returned.")

    for seg in segments:
        print(f"\n   [{seg['turn_index']}] You: {seg['user_text']}")
        print(f"       AI: {seg['ai_text']}")
        for mark in seg.get("ai_marks", []):
            types = mark.get("issue_types", [])
            if isinstance(types, str):
                types = _json.loads(types)
            print(f"       ⚠ [{', '.join(types)}] \"{mark['original']}\" → \"{mark['suggestion']}\"")
            print(f"         {mark.get('explanation', '')}")

    return segments


def ask_corrections(session_id: str, segments: list[dict]) -> None:
    """Let the user ask about specific segments interactively."""
    if not segments:
        return

    print("\n--- Corrections ---")
    print("Ask about a segment (enter segment number), or [s]kip:")

    while True:
        choice = input("> ").strip().lower()
        if choice == "s" or choice == "":
            break

        if not choice.isdigit():
            print("Enter a segment number or 's' to skip.")
            continue

        turn_idx = int(choice)
        seg = next((s for s in segments if s["turn_index"] == turn_idx), None)
        if not seg:
            print(f"No segment with turn_index={turn_idx}. Available: {[s['turn_index'] for s in segments]}")
            continue

        msg = input("   Your question (Chinese OK): ").strip()
        if not msg:
            continue

        resp = httpx.post(
            f"{BASE_URL}/sessions/{session_id}/corrections",
            json={"segment_id": seg["id"], "user_message": msg},
        )
        resp.raise_for_status()
        data = resp.json()
        print(f"   ✏ Correction: {data.get('correction', '')}")
        print(f"   💡 Explanation: {data.get('explanation', '')}")
        print("\nAsk about another segment, or [s]kip:")


def end_session(user_id: str, session_id: str) -> None:
    """Call POST /end (returns immediately), then poll for results."""
    print("\n--- Finalizing Session ---")
    resp = httpx.post(f"{BASE_URL}/sessions/{session_id}/end", timeout=10.0)
    resp.raise_for_status()
    end_data = resp.json()

    # If already completed (e.g. 0 segments), skip polling
    if end_data.get("status") == "completed":
        print("   No conversation to review.")
        return

    # Poll GET /review until status=completed
    print("   Waiting for session review", end="", flush=True)
    data = {}
    for _ in range(10):
        time.sleep(1)
        resp = httpx.get(f"{BASE_URL}/sessions/{session_id}/review")
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") == "completed":
            break
        print(".", end="", flush=True)
    print()

    summary = data.get("summary")
    if summary:
        print(f"\n   Strengths: {summary.get('strengths', '')}")
        print(f"   Weaknesses: {summary.get('weaknesses', '')}")
        print(f"   Overall: {summary.get('overall', '')}")
    else:
        print("   (Session review not ready yet — check GET /review later)")

    # Fetch updated profile
    resp = httpx.get(f"{BASE_URL}/users/{user_id}/profile")
    resp.raise_for_status()
    profile = resp.json()
    print(f"\n   Profile — Level: {profile.get('level', '?')}")
    pdata = profile.get("profile_data", {})
    print(f"   Needs review: {profile.get('needs_review', False)}")
    print(f"   Progress: {pdata.get('progress_notes', '')}")


def main():
    print("=== TalkCo Test Client ===")
    print("This will record audio from your microphone and send it to the backend.\n")

    user_id = input("Enter your user ID (default: test-user): ").strip() or "test-user"
    print(f"Using user_id: {user_id}\n")

    topic_id = pick_topic()
    session_id = create_session(user_id, topic_id)
    # Give the WebSocket a moment to connect
    print("Waiting for session to initialize...")
    time.sleep(2)

    print("\n--- AI Greeting ---")
    stream_greeting(session_id)

    try:
        while True:
            print("\nOptions: [r]ecord and send, [q]uit")
            choice = input("> ").strip().lower()
            if choice == "q":
                break
            elif choice == "r":
                pcm = record_audio()
                if pcm:
                    send_chat(session_id, pcm)
                else:
                    print("No audio recorded.")
            else:
                print("Unknown option.")
    except KeyboardInterrupt:
        print("\nInterrupted.")

    # --- End conversation, enter review flow ---
    delete_session(session_id)
    segments = show_review(session_id)
    ask_corrections(session_id, segments)
    end_session(user_id, session_id)


if __name__ == "__main__":
    main()
