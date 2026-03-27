"""
test_livekit_client.py
======================
LiveKit Client Integration Test
--------------------------------
Goal: Validate the full first audio interaction:
  microphone audio → LiveKit room → STT → router → LLM reasoning → TTS response

How it works:
  1. Generates a LiveKit access token (participant role) using the same dev
     credentials that the server/agent uses.
  2. Connects to the LiveKit room as a *human participant*.
  3. Reads microphone audio via sounddevice and publishes it to the room so
     the agent_loop (running in the server) can receive it via the pipecat
     LiveKitTransport.
  4. Subscribes to remote audio tracks so we can hear / log the agent's
     spoken response.
  5. Runs for a configurable duration and then exits cleanly.

Prerequisites:
  - LiveKit server must be running (see start_livekit_dev.sh).
  - The VoxAgent server must be running:
      cd voxagent && python server.py
  - sounddevice + numpy must be installed:
      pip install sounddevice numpy

Usage:
  python test_livekit_client.py [--room ROOM] [--duration SECONDS] [--list-mics]

  --room      Room name to join (default: test-room)
  --duration  How long to stream mic audio in seconds (default: 30)
  --list-mics List available microphone devices and exit

Environment (.env is loaded automatically):
  LIVEKIT_URL        e.g. ws://localhost:7880
  LIVEKIT_API_KEY    e.g. devkey
  LIVEKIT_API_SECRET e.g. secret
"""

import argparse
import asyncio
import audioop
import sys
import time
import os
from contextlib import suppress
import wave
from dotenv import load_dotenv

# ── Load .env so we pick up LIVEKIT_* vars ──────────────────────────────────
load_dotenv()

LIVEKIT_URL    = os.getenv("LIVEKIT_URL", "ws://localhost:7880")
LIVEKIT_API_KEY    = os.getenv("LIVEKIT_API_KEY", "devkey")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET", "secret")

# LiveKit uses ws:// scheme for the realtime client, not http://
if LIVEKIT_URL.startswith("http://"):
    LIVEKIT_URL = LIVEKIT_URL.replace("http://", "ws://", 1)
elif LIVEKIT_URL.startswith("https://"):
    LIVEKIT_URL = LIVEKIT_URL.replace("https://", "wss://", 1)

# ── Constants ─────────────────────────────────────────────────────────────────
SAMPLE_RATE    = 48000   # Hz – standard for WebRTC (matching LiveKit natively)
NUM_CHANNELS   = 1       # Mono
CHUNK_MS       = 20      # ms per audio chunk sent to LiveKit (20ms is WebRTC native)
NO_TRANSCRIPT_WARNING_SECS = 5
MIC_IDLE_RESTART_SECS = 2
LOG_FRAME_EVERY = 50
MIC_SPEECH_RMS_THRESHOLD = 300

# ── Soft dependency: sounddevice ──────────────────────────────────────────────
try:
    import sounddevice as sd
    import numpy as np
    HAS_SOUNDDEVICE = True
except ImportError:
    HAS_SOUNDDEVICE = False
    np = None

try:
    import pyaudio
    HAS_PYAUDIO = True
except ImportError:
    HAS_PYAUDIO = False


def list_microphones():
    """Print all available input devices."""
    if not HAS_SOUNDDEVICE:
        print("sounddevice is not installed. Run:  pip install sounddevice numpy")
        return
    print("\nAvailable microphone / input devices:")
    for i, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] > 0:
            print(f"  [{i:2d}] {dev['name']}  (channels: {dev['max_input_channels']})")
    print()

def list_speakers():
    """Print all available output devices."""
    if not HAS_SOUNDDEVICE:
        print("sounddevice is not installed. Run:  pip install sounddevice numpy")
        return
    print("\nAvailable speaker / output devices:")
    for i, dev in enumerate(sd.query_devices()):
        if dev["max_output_channels"] > 0:
            print(f"  [{i:2d}] {dev['name']}  (channels: {dev['max_output_channels']})")
    print()


async def generate_token(room_name: str, participant_name: str) -> str:
    """
    Create a signed LiveKit access token for a human participant.
    Uses the livekit-api package which is already in requirements.txt.
    """
    from livekit.api import AccessToken, VideoGrants

    token = (
        AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        .with_identity(participant_name)
        .with_name(participant_name)
        .with_grants(
            VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=True,
            )
        )
    )
    return token.to_jwt()


async def run_client(
    room_name: str,
    duration: int,
    mic_device=None,
    speaker_device=None,
    dump_mic_wav: str | None = None,
    mic_self_test: bool = False,
    inject_wav: str | None = None,
):
    """
    Main test coroutine.

    1. Connect to the LiveKit room.
    2. Publish microphone audio.
    3. Subscribe and log incoming agent audio frames.
    4. Exit after `duration` seconds.
    """
    from livekit import rtc

    token = await generate_token(room_name, participant_name="test-human")
    print(f"\n{'='*60}")
    print(f"  LiveKit Client Test")
    print(f"{'='*60}")
    print(f"  Server URL : {LIVEKIT_URL}")
    print(f"  Room       : {room_name}")
    print(f"  Duration   : {duration}s")
    print(f"{'='*60}\n")

    # ── Create room ───────────────────────────────────────────────────────────
    room = rtc.Room()
    playback_workers: list[asyncio.Task] = []
    session_started_at = time.time()
    session_end_at = session_started_at + duration

    # Track events ─────────────────────────────────────────────────────────────
    response_received = asyncio.Event()
    first_frame_time: list[float] = []
    disconnect_requested = asyncio.Event()
    transcript_seen = asyncio.Event()
    sent_frame_count = 0
    silence_frame_count = 0
    last_mic_audio_at = time.time()
    last_frame_log_at = 0.0
    last_silence_log_at = 0.0
    mic_dump_audio = bytearray()
    mic_dump_limit = SAMPLE_RATE * NUM_CHANNELS * 2 * min(duration, 5)

    @room.on("participant_connected")
    def on_participant_connected(participant: rtc.RemoteParticipant):
        print(f"[ROOM] participant_connected identity={participant.identity}")

    @room.on("participant_disconnected")
    def on_participant_disconnected(participant: rtc.RemoteParticipant):
        print(f"[ROOM] participant_disconnected identity={participant.identity}")

    @room.on("track_subscribed")
    def on_track_subscribed(
        track: rtc.Track,
        publication: rtc.RemoteTrackPublication,
        participant: rtc.RemoteParticipant,
    ):
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            publication.set_subscribed(True)
            print(f"[CLIENT] audio_track_subscribed participant={participant.identity}")
            playback_workers.append(
                asyncio.ensure_future(_consume_audio(track, participant.identity))
            )

    async def _publish_track_with_retry(
        local_track,
        options,
        label: str,
        retries: int = 3,
    ):
        for attempt in range(1, retries + 1):
            try:
                publication = await room.local_participant.publish_track(local_track, options)
                print(f"[CLIENT] audio track published label={label} attempt={attempt}")
                return publication
            except Exception as exc:
                print(f"[CLIENT] publish retry label={label} attempt={attempt} error={exc}")
                if attempt == retries:
                    raise
                await asyncio.sleep(0.5)

    def _open_playback_stream(sample_rate: int, num_channels: int, samples_per_channel: int):
        if HAS_SOUNDDEVICE:
            if speaker_device is not None:
                dev_info = sd.query_devices(speaker_device)
            else:
                default_out = sd.default.device[1]
                dev_info = sd.query_devices(default_out)
            print(f"[CLIENT] Playback device: {dev_info['name']}")
            out_stream = sd.RawOutputStream(
                samplerate=sample_rate,
                channels=num_channels,
                dtype="int16",
                blocksize=samples_per_channel,
                device=speaker_device,
            )
            out_stream.start()
            return ("sounddevice", out_stream)

        if HAS_PYAUDIO:
            pa = pyaudio.PyAudio()
            out_stream = pa.open(
                format=pyaudio.paInt16,
                channels=num_channels,
                rate=sample_rate,
                output=True,
                frames_per_buffer=samples_per_channel,
                output_device_index=speaker_device,
            )
            return ("pyaudio", (pa, out_stream))

        return (None, None)

    def _close_playback_stream(stream_kind, stream_obj):
        if stream_kind == "sounddevice" and stream_obj is not None:
            try:
                stream_obj.stop()
                stream_obj.close()
            except Exception:
                pass
            return

        if stream_kind == "pyaudio" and stream_obj is not None:
            pa, out_stream = stream_obj
            try:
                out_stream.stop_stream()
                out_stream.close()
            except Exception:
                pass
            try:
                pa.terminate()
            except Exception:
                pass

    async def _consume_audio(track: rtc.AudioTrack, source: str):
        """Read incoming audio frames and play them on local speakers."""
        audio_stream = rtc.AudioStream(track)
        stream_kind = None
        stream_obj = None
        frame_count = 0
        try:
            async for frame_event in audio_stream:
                frame = frame_event.frame
                if frame_count == 0:
                    t = time.time()
                    first_frame_time.append(t)
                    print(f"[CLIENT] remote_audio_started source={source}")
                    response_received.set()
                    transcript_seen.set()

                    stream_kind, stream_obj = _open_playback_stream(
                        frame.sample_rate,
                        frame.num_channels,
                        frame.samples_per_channel,
                    )
                    if stream_kind is not None:
                        print("[CLIENT] playing audio")
                    else:
                        print(
                            "[CLIENT] audio playback backend unavailable "
                            "(install sounddevice or pyaudio)"
                        )

                frame_count += 1

                if stream_kind == "sounddevice":
                    stream_obj.write(frame.data.cast("B").tobytes())
                elif stream_kind == "pyaudio":
                    _, out_stream = stream_obj
                    out_stream.write(frame.data.cast("B").tobytes())
        finally:
            _close_playback_stream(stream_kind, stream_obj)

    @room.on("track_unsubscribed")
    def on_track_unsubscribed(
        track: rtc.Track,
        publication: rtc.RemoteTrackPublication,
        participant: rtc.RemoteParticipant,
    ):
        print(f"[ROOM] track_unsubscribed participant={participant.identity}")

    @room.on("disconnected")
    def on_disconnected(reason):
        print(f"[ROOM] disconnected reason={reason}")
        disconnect_requested.set()

    async def _warn_if_no_transcript():
        try:
            await asyncio.wait_for(transcript_seen.wait(), timeout=NO_TRANSCRIPT_WARNING_SECS)
        except asyncio.TimeoutError:
            print("[WARN] No audio detected from mic")

    def _maybe_log_frame(kind: str, frame_count: int, now: float):
        nonlocal last_frame_log_at, last_silence_log_at
        if kind == "audio":
            if frame_count == 1 or frame_count % LOG_FRAME_EVERY == 0 or (now - last_frame_log_at) >= 1.0:
                print("[CLIENT] Sending audio frame")
                last_frame_log_at = now
        else:
            if frame_count == 1 or frame_count % LOG_FRAME_EVERY == 0 or (now - last_silence_log_at) >= 1.0:
                print("[CLIENT] Silence frame sent")
                last_silence_log_at = now

    async def _send_audio_frame(source: rtc.AudioSource, frame: rtc.AudioFrame, kind: str):
        nonlocal sent_frame_count, silence_frame_count
        await source.capture_frame(frame)
        now = time.time()
        if kind == "audio":
            sent_frame_count += 1
            _maybe_log_frame("audio", sent_frame_count, now)
        else:
            silence_frame_count += 1
            _maybe_log_frame("silence", silence_frame_count, now)

    def _resolve_mic_device():
        if mic_device is not None:
            return mic_device
        if sys.platform == "darwin":
            return sd.default.device[0]
        return sd.default.device[0]

    def _analyze_pcm16(raw_bytes: bytes) -> tuple[int, int, str]:
        rms = audioop.rms(raw_bytes, 2) if raw_bytes else 0
        peak = audioop.max(raw_bytes, 2) if raw_bytes else 0
        state = "speech" if rms >= MIC_SPEECH_RMS_THRESHOLD else "silence"
        return rms, peak, state

    def _dump_mic_audio_if_needed():
        if not dump_mic_wav or not mic_dump_audio:
            return
        try:
            with wave.open(dump_mic_wav, "wb") as wav_file:
                wav_file.setnchannels(NUM_CHANNELS)
                wav_file.setsampwidth(2)
                wav_file.setframerate(SAMPLE_RATE)
                wav_file.writeframes(bytes(mic_dump_audio))
            print(f"[CLIENT] dumped_mic_wav={dump_mic_wav}")
        except Exception as exc:
            print(f"[CLIENT] dump_mic_wav_failed error={exc}")

    def _start_mic_stream(mic_queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
        selected_device = _resolve_mic_device()

        def mic_callback(indata, frames, ts, status):
            nonlocal last_mic_audio_at
            if status:
                print(f"[MIC] sounddevice status: {status}")

            raw_bytes = bytes(indata)
            if raw_bytes:
                last_mic_audio_at = time.time()
                loop.call_soon_threadsafe(mic_queue.put_nowait, raw_bytes)

        device_info = sd.query_devices(selected_device)
        print(f"[CLIENT] Selected microphone: {device_info['name']}")
        print(f"[CLIENT] Sample rate: {SAMPLE_RATE} Hz")
        print(f"[CLIENT] Audio buffer size: {chunk_samples} frames")

        mic_stream = sd.RawInputStream(
            samplerate=SAMPLE_RATE,
            channels=NUM_CHANNELS,
            dtype="int16",
            blocksize=chunk_samples,
            device=selected_device,
            callback=mic_callback,
        )
        mic_stream.start()
        print("[CLIENT] Mic stream started")
        return mic_stream

    if mic_self_test:
        if not HAS_SOUNDDEVICE:
            print("[CLIENT] mic_self_test requires sounddevice")
            return
        mic_queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_event_loop()
        chunk_samples = int(SAMPLE_RATE * CHUNK_MS / 1000)
        mic_stream = _start_mic_stream(mic_queue, loop)
        start = time.time()
        try:
            while time.time() - start < duration:
                try:
                    raw = await asyncio.wait_for(mic_queue.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    print("[WARN] No audio detected from mic")
                    continue

                rms, peak, state = _analyze_pcm16(raw)
                print(f"[MIC_TEST] rms={rms} peak={peak} state={state} bytes={len(raw)}")
                if len(mic_dump_audio) < mic_dump_limit:
                    remaining = mic_dump_limit - len(mic_dump_audio)
                    mic_dump_audio.extend(raw[:remaining])
        finally:
            with suppress(Exception):
                mic_stream.stop()
                mic_stream.close()
            _dump_mic_audio_if_needed()
        return

    # ── Connect ────────────────────────────────────────────────────────────────
    print(f"[CLIENT] Connecting to LiveKit at {LIVEKIT_URL} …")
    try:
        await room.connect(LIVEKIT_URL, token)
    except Exception as exc:
        print(f"\n[ERROR] Could not connect to LiveKit: {exc}")
        print("  → Make sure the LiveKit server is running.")
        print("  → Start it with:  ./start_livekit_dev.sh\n")
        return

    print(f"[CLIENT] session_start room={room_name} duration={duration}s")
    print(f"[CLIENT] ✅ Connected. Local participant SID: {room.local_participant.sid}")
    print(f"[CLIENT] Room: {room.name}  |  Participants: {len(room.remote_participants)}")

    # ── Publish microphone audio ───────────────────────────────────────────────
    chunk_samples = int(SAMPLE_RATE * CHUNK_MS / 1000)
    silence_frame = rtc.AudioFrame.create(SAMPLE_RATE, NUM_CHANNELS, chunk_samples)
    transcript_watchdog = asyncio.create_task(_warn_if_no_transcript())

    if not HAS_SOUNDDEVICE and not inject_wav:
        print("\n[WARNING] sounddevice not installed and no audio injected – publishing silence instead.\n"
              "          Install with:  pip install sounddevice numpy\n")
        source = rtc.AudioSource(SAMPLE_RATE, NUM_CHANNELS)
        track = rtc.LocalAudioTrack.create_audio_track("mic-silence", source)
        options = rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
        await _publish_track_with_retry(track, options, "mic-silence")
        print("[CLIENT] Mic stream (silence) started")

        # Feed silence for the full session so the room remains active.
        while time.time() < session_end_at and not disconnect_requested.is_set():
            await _send_audio_frame(source, silence_frame, "silence")
            await asyncio.sleep(CHUNK_MS / 1000)
    elif inject_wav:
        print(f"[CLIENT] Injecting WAV file instead of real mic: {inject_wav}")
        source = rtc.AudioSource(SAMPLE_RATE, NUM_CHANNELS)
        track = rtc.LocalAudioTrack.create_audio_track("mic-injected", source)
        options = rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
        await _publish_track_with_retry(track, options, "mic-injected")
        print("[CLIENT] Mic stream started via WAV file!")

        with wave.open(inject_wav, 'rb') as w:
            framerate = w.getframerate()
            nchannels = w.getnchannels()
            sampwidth = w.getsampwidth()
            print(f"[CLIENT] WAV specs: {framerate}Hz {nchannels}ch {sampwidth}B")
            chunk_bytes = int(framerate * CHUNK_MS / 1000) * nchannels * sampwidth

            # Wait a few seconds for room connection matching then play
            await asyncio.sleep(3)

            while True:
                data = w.readframes(int(framerate * CHUNK_MS / 1000))
                if not data:
                    break
                if len(data) < chunk_bytes:
                    data = data + b'\x00' * (chunk_bytes - len(data))
                
                # Resample or just send it (assuming it matches SAMPLE_RATE)
                frame = rtc.AudioFrame(data=data, sample_rate=framerate, num_channels=nchannels, samples_per_channel=int(framerate * CHUNK_MS / 1000))
                await _send_audio_frame(source, frame, "audio")
                await asyncio.sleep(CHUNK_MS / 1000)
            
            print("[CLIENT] Finished sending WAV audio. Waiting for response...")
            while time.time() < session_end_at and not disconnect_requested.is_set():
                await _send_audio_frame(source, silence_frame, "silence")
                await asyncio.sleep(CHUNK_MS / 1000)
    else:
        source = rtc.AudioSource(SAMPLE_RATE, NUM_CHANNELS)
        track = rtc.LocalAudioTrack.create_audio_track("mic", source)
        options = rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
        await _publish_track_with_retry(track, options, "mic")
        print(f"[CLIENT] 🎤 Microphone track published. Streaming for {duration}s …")
        print("[CLIENT]    Speak into your mic — the room will stay active until the session ends.\n")

        mic_queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_event_loop()

        try:
            mic_stream = _start_mic_stream(mic_queue, loop)
        except Exception as e:
            print(f"\n[ERROR] Microphone initialization failed: {e}")
            print("  → Exiting gracefully. Please check your audio devices and permissions.\n")
            await room.disconnect()
            return

        try:
            while time.time() < session_end_at and not disconnect_requested.is_set():
                if not mic_stream.active:
                    print("[WARN] Mic stream became inactive; restarting")
                    with suppress(Exception):
                        mic_stream.stop()
                        mic_stream.close()
                    mic_stream = _start_mic_stream(mic_queue, loop)

                try:
                    raw = await asyncio.wait_for(mic_queue.get(), timeout=0.1)
                except asyncio.TimeoutError:
                    if time.time() - last_mic_audio_at >= MIC_IDLE_RESTART_SECS:
                        print("[WARN] Mic input idle; restarting stream")
                        with suppress(Exception):
                            mic_stream.stop()
                            mic_stream.close()
                        mic_stream = _start_mic_stream(mic_queue, loop)
                        last_mic_audio_at = time.time()
                    # Publish silence during pauses so the session stays warm.
                    await _send_audio_frame(source, silence_frame, "silence")
                    continue

                if not raw:
                    print("[WARN] Empty mic frame received; sending silence instead")
                    await _send_audio_frame(source, silence_frame, "silence")
                    continue

                expected_bytes = chunk_samples * NUM_CHANNELS * 2
                if len(raw) != expected_bytes:
                    print(f"[WARN] Mic frame size mismatch bytes={len(raw)} expected={expected_bytes}")
                    if len(raw) < expected_bytes:
                        raw = raw + (b"\x00" * (expected_bytes - len(raw)))
                    else:
                        raw = raw[:expected_bytes]

                rms, peak, state = _analyze_pcm16(raw)
                print(f"[MIC] rms={rms} peak={peak} state={state}")
                if len(mic_dump_audio) < mic_dump_limit:
                    remaining = mic_dump_limit - len(mic_dump_audio)
                    mic_dump_audio.extend(raw[:remaining])

                frame = rtc.AudioFrame(
                    data=raw,
                    sample_rate=SAMPLE_RATE,
                    num_channels=NUM_CHANNELS,
                    samples_per_channel=chunk_samples,
                )
                await _send_audio_frame(source, frame, "audio")
        finally:
            with suppress(Exception):
                mic_stream.stop()
                mic_stream.close()
            _dump_mic_audio_if_needed()

    # ── Session summary ────────────────────────────────────────────────────────
    if response_received.is_set() and first_frame_time:
        latency = first_frame_time[0] - session_started_at
        print(f"\n{'='*60}")
        print("  ✅ FULL PIPELINE VALIDATED")
        print("  audio → LiveKit → STT → router → LLM → response")
        print(f"  Time-to-first-agent-audio: {latency:.2f}s")
        print(f"{'='*60}\n")
    else:
        print("\n[WARN] No agent audio track received during the session.")
        print("  → Check that the VoxAgent server is running and agent_loop")
        print("    has connected to the same room.\n")

    # ── Disconnect ─────────────────────────────────────────────────────────────
    for task in playback_workers:
        task.cancel()
    if playback_workers:
        await asyncio.gather(*playback_workers, return_exceptions=True)
    transcript_watchdog.cancel()
    with suppress(asyncio.CancelledError):
        await transcript_watchdog

    await room.disconnect()
    total_runtime = time.time() - session_started_at
    print(f"[CLIENT] session_end room={room_name} runtime={total_runtime:.2f}s")
    print("[CLIENT] Disconnected from LiveKit room. Test complete.")


def main():
    parser = argparse.ArgumentParser(
        description="LiveKit client integration test – mic audio → VoxAgent pipeline"
    )
    parser.add_argument(
        "--room", default="test-room",
        help="LiveKit room name to join (default: test-room)"
    )
    parser.add_argument(
        "--duration", type=int, default=30,
        help="How many seconds to stream microphone audio (default: 30)"
    )
    parser.add_argument(
        "--list-mics", action="store_true",
        help="List available microphone devices and exit"
    )
    parser.add_argument(
        "--list-speakers", action="store_true",
        help="List available speaker/output devices and exit"
    )
    parser.add_argument(
        "--mic-device", type=int, default=None,
        help="sounddevice device index for microphone (default: system default)"
    )
    parser.add_argument(
        "--speaker-device", type=int, default=None,
        help="sounddevice/pyaudio output device index for playback (default: system default)"
    )
    parser.add_argument(
        "--dump-mic-wav", default=None,
        help="Optional path to dump the first few seconds of mic audio to a wav file"
    )
    parser.add_argument(
        "--mic-self-test", action="store_true",
        help="Capture mic locally with diagnostics only, without connecting to LiveKit"
    )
    parser.add_argument(
        "--inject-wav", default=None,
        help="Path to an existing WAV file to publish instead of live microphone"
    )
    args = parser.parse_args()

    if args.list_mics:
        list_microphones()
        sys.exit(0)
    if args.list_speakers:
        list_speakers()
        sys.exit(0)

    asyncio.run(
        run_client(
            args.room,
            args.duration,
            args.mic_device,
            args.speaker_device,
            args.dump_mic_wav,
            args.mic_self_test,
            args.inject_wav,
        )
    )


if __name__ == "__main__":
    main()
