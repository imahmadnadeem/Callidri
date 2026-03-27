import asyncio
from pipecat.frames.frames import TranscriptionFrame

class FakeTest:
    def __init__(self):
        self.transcript = "hello"

print("type:", type(FakeTest()).__name__)
