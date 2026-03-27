import asyncio
import os
import sys
from dotenv import load_dotenv

# Ensure we can import from local directory
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from agent import InterceptSTTProcessor
from pipecat.frames.frames import TranscriptionFrame
from memory import memory

async def verify_isolated():
    load_dotenv()
    
    # Setup session in memory
    call_id = "verify_isolated_call"
    print(f"Connecting to Redis at {os.getenv('REDIS_URL', 'localhost:6379')}...")
    await memory.connect()
    await memory.create_session(call_id, "agent_mvp")
    
    # Create processor
    processor = InterceptSTTProcessor(call_id)
    
    # Simulate a final transcription frame
    # Note: We manually set finalized=True
    frame = TranscriptionFrame(
        text="Hello, I would like to book a demo meeting for tomorrow at 2pm.",
        user_id="test-user",
        timestamp="2026-03-11T08:35:00"
    )
    frame.finalized = True 
    
    print("\n[VERIFY] Pushing final TranscriptionFrame to InterceptSTTProcessor...")
    
    from pipecat.processors.frame_processor import FrameDirection
    # This will trigger the processor logic: CM.process_turn -> [INTENT] log
    await processor.process_frame(frame, FrameDirection.DOWNSTREAM)
    
    # Fetch session to confirm intent was updated in Redis too
    session = await memory.get_session(call_id)
    print(f"\n[VERIFY] Final session state in Redis: {session}")
    
    print("\n--- Isolated Wiring Verification Complete ---")

if __name__ == "__main__":
    asyncio.run(verify_isolated())
