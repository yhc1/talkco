"""
Test whether backend returns audio SSE events for greeting and chat.

Usage:
    cd backend
    python scripts/test_audio_events.py

Requires backend running at http://127.0.0.1:8000
"""

import httpx
import json
import sys
import os

BASE_URL = "http://127.0.0.1:8000"
USER_ID = "audio-test-user"
TOPIC_ID = "daily_life"


def parse_sse(text: str) -> list[dict]:
    """Parse SSE text into list of {event, data} dicts."""
    events = []
    current_event = None
    for line in text.split("\n"):
        if line.startswith("event: "):
            current_event = line[7:]
        elif line.startswith("data: ") and current_event:
            events.append({"event": current_event, "data": line[6:]})
            current_event = None
    return events


def count_events(events: list[dict]) -> dict:
    counts = {}
    for e in events:
        counts[e["event"]] = counts.get(e["event"], 0) + 1
    return counts


def main():
    client = httpx.Client(base_url=BASE_URL, timeout=30.0)

    # 1. Create session
    print("1. Creating session...")
    resp = client.post("/sessions", json={
        "user_id": USER_ID,
        "topic_id": TOPIC_ID,
        "mode": "conversation",
    })
    resp.raise_for_status()
    session_id = resp.json()["session_id"]
    print(f"   Session: {session_id}")

    # 2. Stream greeting
    print("\n2. Streaming greeting...")
    resp = client.post(f"/sessions/{session_id}/start", timeout=60.0)
    resp.raise_for_status()
    greeting_events = parse_sse(resp.text)
    greeting_counts = count_events(greeting_events)
    print(f"   Event counts: {greeting_counts}")

    # Check for audio
    audio_events = [e for e in greeting_events if e["event"] == "audio"]
    print(f"   Audio chunks: {len(audio_events)}")
    if audio_events:
        first_audio = json.loads(audio_events[0]["data"])
        print(f"   First audio chunk size: {len(first_audio.get('audio', ''))} base64 chars")

    # Show text
    for e in greeting_events:
        if e["event"] == "response":
            data = json.loads(e["data"])
            print(f"   AI text: {data.get('text', '')[:100]}")

    # 3. Send text message (easier than audio for testing)
    print("\n3. Sending text message...")
    resp = client.post(
        f"/sessions/{session_id}/chat/text",
        json={"text": "I like to play basketball on weekends."},
        timeout=60.0,
    )
    resp.raise_for_status()
    chat_events = parse_sse(resp.text)
    chat_counts = count_events(chat_events)
    print(f"   Event counts: {chat_counts}")

    audio_events = [e for e in chat_events if e["event"] == "audio"]
    print(f"   Audio chunks: {len(audio_events)}")
    if audio_events:
        first_audio = json.loads(audio_events[0]["data"])
        print(f"   First audio chunk size: {len(first_audio.get('audio', ''))} base64 chars")

    for e in chat_events:
        if e["event"] == "response":
            data = json.loads(e["data"])
            print(f"   AI text: {data.get('text', '')[:100]}")
        elif e["event"] == "transcript":
            data = json.loads(e["data"])
            print(f"   Transcript: {data.get('text', '')[:100]}")

    # 4. Clean up
    print("\n4. Cleaning up...")
    resp = client.delete(f"/sessions/{session_id}")
    resp.raise_for_status()
    print(f"   Session ended: {resp.json()}")

    # Summary
    print("\n=== SUMMARY ===")
    print(f"Greeting: {greeting_counts.get('audio', 0)} audio chunks, {greeting_counts.get('response', 0)} text events")
    print(f"Chat:     {chat_counts.get('audio', 0)} audio chunks, {chat_counts.get('response', 0)} text events")

    if greeting_counts.get("audio", 0) > 0 and chat_counts.get("audio", 0) > 0:
        print("\n✓ Backend sends audio for BOTH greeting and chat → issue is in frontend")
    elif greeting_counts.get("audio", 0) > 0 and chat_counts.get("audio", 0) == 0:
        print("\n✗ Backend sends audio for greeting but NOT chat → issue is in backend")
    else:
        print("\n✗ No audio events at all → check OpenAI API configuration")


if __name__ == "__main__":
    main()
