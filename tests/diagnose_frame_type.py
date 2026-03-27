import asyncio
from pipecat.frames.frames import Frame

class PrintFrameProcessor:
    async def process_frame(self, frame: Frame, direction):
        print(f"DEBUG: I received frame type {type(frame).__name__}")
