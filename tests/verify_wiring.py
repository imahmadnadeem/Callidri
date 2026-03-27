import asyncio
import os
import uuid
import requests
from livekit import rtc
from livekit.api import AccessToken, VideoGrants

# Livekit credentials (using defaults from start_livekit_dev.sh)
URL = "ws://localhost:7880"
KEY = "devkey"
SECRET = "secret"
ROOM = f"test-wiring-{uuid.uuid4().hex[:6]}"

async def run_verification():
    print(f"\n--- Starting Wiring Verification for Room: {ROOM} ---\n")
    
    # 1. Tell server to start agent
    try:
        resp = requests.post("http://0.0.0.0:8000/join-room", json={"room": ROOM})
        resp.raise_for_status()
        print(f"[VERIFY] Agent join request sent: {resp.json()}")
    except Exception as e:
        print(f"[ERROR] Could not trigger agent join: {e}")
        return

    # Give the agent a few seconds to initialize and connect to LiveKit
    await asyncio.sleep(4)

    # 2. Connect as a human participant
    token = (
        AccessToken(KEY, SECRET)
        .with_identity("test-human")
        .with_grants(VideoGrants(room_join=True, room=ROOM, can_publish=True))
        .to_jwt()
    )
    
    room = rtc.Room()
    try:
        await room.connect(URL, token)
        print("[VERIFY] Test-human participant joined the room.")
    except Exception as e:
        print(f"[ERROR] Could not join room as test-human: {e}")
        return

    # 3. Publish a transcription segment (simulates a final STT result)
    # Pipecat's LiveKitTransport receives these and publishes TranscriptionFrame
    try:
        # segment attributes: id, text, start_time, end_time, final, language
        segment = rtc.TranscriptionSegment(
            id=str(uuid.uuid4()),
            text="hello i want to book a demo meeting",
            final=True,
            start_time=0,
            end_time=1000,
            language="en"
        )
        transcription = rtc.Transcription(
            participant_identity="test-human",
            segments=[segment]
        )
        
        # publish_transcription is supported in livekit-python 1.1+
        await room.local_participant.publish_transcription(transcription)
        print(f"[VERIFY] Published fake transcription segment: '{segment.text}'")
    except Exception as e:
        print(f"[ERROR] Failed to publish transcription: {e}")
        # Fallback: maybe send as data message?
        print("[VERIFY] Attempting fallback: Sending as data message...")
        await room.local_participant.publish_data(b"hello i want to book a demo meeting", topic="transcription")

    # 4. Wait for processing
    print("[VERIFY] Waiting 10 seconds for agent to process and log intent...")
    await asyncio.sleep(10)
    
    await room.disconnect()
    print("\n--- Verification Run Complete ---\n")

if __name__ == "__main__":
    asyncio.run(run_verification())
