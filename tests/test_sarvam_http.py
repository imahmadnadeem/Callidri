import asyncio
import aiohttp
import os
from pipecat.services.sarvam.tts import SarvamHttpTTSService
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineTask
from pipecat.frames.frames import TextFrame, LLMFullResponseStartFrame, LLMFullResponseEndFrame, TTSAudioRawFrame
from pipecat.processors.frame_processor import FrameProcessor, FrameDirection

class AudioCatcher(FrameProcessor):
    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        print(f"[CATCHER] Caught frame: {type(frame).__name__}")
        if isinstance(frame, TTSAudioRawFrame):
            print(f"   -> Audio size: {len(frame.audio)} bytes")

async def test_sarvam_http():
    api_key = "sk_c5sdewra_kfeZuGho9VUKXdWgbn1fl1WV" # From .env
    
    async with aiohttp.ClientSession() as session:
        # Explicitly set sample_rate to avoid "NOT_GIVEN" error
        tts = SarvamHttpTTSService(
            api_key=api_key,
            aiohttp_session=session,
            model="bulbul:v2",
            voice_id="anushka",
            sample_rate=22050,  # Explicitly set
            params=SarvamHttpTTSService.InputParams(
                language="hi-IN",
            ),
        )

        catcher = AudioCatcher()
        pipeline = Pipeline([tts, catcher])
        runner = PipelineRunner()
        task = PipelineTask(pipeline)

        print("Starting HTTP TTS Test (with sample_rate=22050)...")
        
        async def push_test_frames():
            await asyncio.sleep(2)
            print("Pushing TextFrame...")
            await task.queue_frame(LLMFullResponseStartFrame())
            await task.queue_frame(TextFrame(text="नमस्ते, आप कैसे हैं?"))
            await task.queue_frame(LLMFullResponseEndFrame())
            await asyncio.sleep(5)
            await task.queue_frame(LLMFullResponseEndFrame())

        await asyncio.gather(runner.run(task), push_test_frames())

if __name__ == "__main__":
    asyncio.run(test_sarvam_http())
