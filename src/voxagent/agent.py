import asyncio
import json
import os
import time
import traceback

import aiohttp
from livekit.api import AccessToken, VideoGrants

import prompt
from config import (
    DEEPGRAM_API_KEY,
    LIVEKIT_API_KEY,
    LIVEKIT_API_SECRET,
    LIVEKIT_URL,
    SARVAM_API_KEY,
)
from conversation_manager import conversation_manager
from memory import memory
from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    EndFrame,
    ErrorFrame,
    Frame,
    StartFrame,
    TTSAudioRawFrame,
    TTSSpeakFrame,
    TranscriptionFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.services.deepgram.stt import DeepgramSTTService, LiveOptions
from pipecat.services.sarvam.stt import SarvamSTTService
from pipecat.services.sarvam.tts import SarvamHttpTTSService
from pipecat.transcriptions.language import Language
from pipecat.transports.livekit.transport import LiveKitParams, LiveKitTransport
from speech_orchestrator import SpeechOrchestrator


def _make_agent_token(room_name: str) -> str:
    token = (
        AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        .with_identity("vox-agent")
        .with_name("VoxAgent")
        .with_grants(
            VideoGrants(room_join=True, room=room_name, can_publish=True, can_subscribe=True)
        )
    )
    return token.to_jwt()


class FrameLogger(FrameProcessor):
    def __init__(self):
        super().__init__()
        self._audio_bytes = 0

    async def process_frame(self, frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, TTSAudioRawFrame):
            self._audio_bytes += len(frame.audio)
            if self._audio_bytes > 12000:
                print(f"[tts_first_audio] bytes={self._audio_bytes}")
                self._audio_bytes = 0
        elif isinstance(frame, ErrorFrame):
            print(f"[PIPELINE] Error frame: {frame.error}")

        await self.push_frame(frame, direction)


class VoiceLoopProcessor(FrameProcessor):
    def __init__(self, call_id: str):
        super().__init__()
        self.call_id = call_id
        self._pipeline_started = False
        self._response_task = None
        self._orchestrator = SpeechOrchestrator(call_id)

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, StartFrame):
            self._pipeline_started = True
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, BotStartedSpeakingFrame):
            self._orchestrator.notify_bot_started()
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, BotStoppedSpeakingFrame):
            self._orchestrator.notify_bot_stopped()
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, TranscriptionFrame):
            await self._handle_transcription(frame)
            return

        await self.push_frame(frame, direction)

    async def _handle_transcription(self, frame: TranscriptionFrame):
        transcript = frame.text.strip()
        # --- Change 3: STT telemetry before orchestrator decision ---
        stt_telemetry = {
            "transcript": transcript,
            "language": str(getattr(frame, 'language', 'unknown')),
            "result_meta": str(getattr(frame, 'result', ''))[:200],
            "timestamp": getattr(frame, 'timestamp', ''),
        }
        print(f"[stt_telemetry] {stt_telemetry}")
        # --- End STT telemetry ---
        if not transcript:
            return

        decision = self._orchestrator.process_finalized_transcript(transcript)
        if decision.kind == "ignore":
            return

        if self._response_task and not self._response_task.done():
            self._response_task.cancel()

        if decision.kind == "clarify":
            self._response_task = asyncio.create_task(
                self._speak_response(decision.text, action="nothing", source="clarify")
            )
            return

        self._response_task = asyncio.create_task(self._handle_accepted_turn(decision.text))

    async def _handle_accepted_turn(self, text: str):
        try:
            t0 = time.time()
            print(f"[response_start] transcript={text!r}")
            result = await conversation_manager.process_turn(self.call_id, "vox-agent", text)
            if isinstance(result, str):
                try:
                    data = json.loads(result)
                except Exception:
                    data = {"response": result, "action": "nothing"}
            else:
                data = result

            response_text = data.get("response", "")
            action = data.get("action", "nothing")
            print(
                f"[response_start] latency={time.time()-t0:.2f}s response={response_text!r} action={action}"
            )
            await self._speak_response(response_text, action=action, source="accepted")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"[PROCESSOR] Error: {exc}")
            traceback.print_exc()

    async def _speak_response(self, response_text: str, action: str, source: str):
        if not response_text:
            return

        self._orchestrator.notify_assistant_text(response_text)
        print(f"[tts_start] source={source} text={response_text!r}")
        await self.push_frame(TTSSpeakFrame(text=response_text))

        if action == "end_call":
            await asyncio.sleep(2)
            await self.push_frame(EndFrame())


def _build_stt_service():
    use_deepgram = os.getenv("USE_DEEPGRAM_STT", "false").lower() == "true"
    if use_deepgram:
        print("[speech_input] provider=deepgram_fallback")
        return DeepgramSTTService(
            api_key=DEEPGRAM_API_KEY,
            sample_rate=16000,
            live_options=LiveOptions(
                model="nova-3",
                language="multi",
                interim_results=True,
                endpointing=700,
                utterance_end_ms="1200",
                smart_format=True,
            ),
        )

    print("[speech_input] provider=sarvam_stt")
    return SarvamSTTService(
        api_key=SARVAM_API_KEY,
        model="saaras:v3",
        sample_rate=16000,
        input_audio_codec="wav",
        params=SarvamSTTService.InputParams(
            language=None,              # auto-detect ("unknown" path) per Sarvam guide
            mode="transcribe",          # matches Sarvam LiveKit integration example
            vad_signals=True,
            high_vad_sensitivity=True,   # per streaming guide enhanced example
        ),
    )


async def agent_loop(room_name: str, call_id: str):
    print(f"[AGENT] Starting optimized loop: {call_id} (Room: {room_name})")
    await memory.create_session(call_id, "agent_sarvam_voice_loop")

    lk_url = LIVEKIT_URL
    if lk_url.startswith("http://"):
        lk_url = lk_url.replace("http://", "ws://", 1)
    elif lk_url.startswith("https://"):
        lk_url = lk_url.replace("https://", "wss://", 1)

    transport = LiveKitTransport(
        url=lk_url,
        token=_make_agent_token(room_name),
        room_name=room_name,
        params=LiveKitParams(
            audio_in_enabled=True,
            audio_in_sample_rate=16000,
            audio_out_enabled=True,
            audio_out_sample_rate=24000,
        ),
    )

    async with aiohttp.ClientSession() as session:
        stt = _build_stt_service()
        tts = SarvamHttpTTSService(
            api_key=SARVAM_API_KEY,
            aiohttp_session=session,
            model="bulbul:v3",
            voice_id="shreya",
            sample_rate=24000,
            params=SarvamHttpTTSService.InputParams(language=Language.HI),
        )
        voice_loop = VoiceLoopProcessor(call_id)

        pipeline = Pipeline([
            transport.input(),
            stt,
            voice_loop,
            tts,
            FrameLogger(),
            transport.output(),
        ])

        runner = PipelineRunner()
        task = PipelineTask(
            pipeline,
            params=PipelineParams(
                allow_interruptions=False,
                enable_metrics=True,
            ),
        )

        @transport.event_handler("on_first_participant_joined")
        async def on_first_participant_joined(transport, participant):
            identity = getattr(participant, "identity", participant)
            print(f"[AGENT] First participant joined: {identity}")
            for _ in range(20):
                if voice_loop._pipeline_started:
                    break
                await asyncio.sleep(0.1)
            print("[AGENT] Sending automated greeting...")
            greeting = "Hi, मैं Nina from Callindri बोल रही हूं. आपको किस चीज़ में help चाहिए?"
            voice_loop._orchestrator.notify_assistant_text(greeting)
            await voice_loop.push_frame(TTSSpeakFrame(text=greeting), FrameDirection.DOWNSTREAM)

        @tts.event_handler("on_connection_error")
        async def on_tts_error(service, error):
            print(f"[TTS] ERROR: {error}")

        @tts.event_handler("on_tts_request")
        async def on_tts_request(service, context_id, text):
            print(f"[TTS] Synthesizing: {text}")

        try:
            print("[AGENT] Pipeline running...")
            await runner.run(task)
        finally:
            await memory.finalize_call(call_id)
            print("[AGENT] Session stopped.")
