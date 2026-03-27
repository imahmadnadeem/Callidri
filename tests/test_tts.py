import asyncio
import aiohttp
from config import DEEPGRAM_API_KEY
from pipecat.services.deepgram.tts import DeepgramHttpTTSService

async def main():
    session = aiohttp.ClientSession()
    tts = DeepgramHttpTTSService(
        api_key=DEEPGRAM_API_KEY,
        voice="aura-asteria-en",
        sample_rate=24000,
        aiohttp_session=session,
    )
    # Mimic pipeline start
    from pipecat.frames.frames import StartFrame
    await tts.start(StartFrame(audio_out_sample_rate=24000))

    async for frame in tts.run_tts("Hello there, this is a test.", "123"):
        if hasattr(frame, 'error'):
            print("ERROR FRAME:", frame.error)
        else:
            print("Generated Frame:", type(frame))
    await session.close()
    print("Done")

asyncio.run(main())
