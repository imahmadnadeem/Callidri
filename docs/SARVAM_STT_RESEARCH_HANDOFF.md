# Sarvam STT Research Handoff

## Why This Document Exists

The current active voice path is:

- LiveKit input
- Sarvam STT
- speech_orchestrator
- Sarvam HTTP TTS
- LiveKit output

The latest live logs show:

- transport works
- Sarvam STT connects
- TTS works
- audio plays
- but STT is still transcribing real speech badly and in fragments

This document captures the exact findings from Sarvam’s official docs and what they imply for the next debugging pass.

## What The Latest Logs Prove

The problem is no longer “no audio” or “TTS broken.”

The current failure is:

- STT returns inaccurate / fragmented transcripts
- orchestrator then correctly classifies those fragments as incomplete
- user hears clarification instead of a useful answer

Examples from logs:

- user speech intended as greeting / identity-like phrase
  - transcript returned: `लीना फ्रॉम कनिंभ`
- user tried speaking clearly in Hindi
  - transcript returned: `हिंदी बोल रहे हैं।`
- later turns returned fragments like:
  - `आपको कि`
  - `इस चीज में help`
  - `चाहिए`

So the current blocker is STT quality/configuration in the real streaming path.

## Official Sarvam Findings

Sources used:

- STT REST: https://docs.sarvam.ai/api-reference-docs/speech-to-text/transcribe
- Streaming STT guide: https://docs.sarvam.ai/api-reference-docs/api-guides-tutorials/speech-to-text/streaming-api
- STT FAQ: https://docs.sarvam.ai/api-reference-docs/speech-to-text/faq
- LiveKit voice-agent integration: https://docs.sarvam.ai/api-reference-docs/integration/build-voice-agent-with-live-kit

### 1. Streaming STT supports both WAV and raw PCM

From the streaming STT guide and FAQ:

- WebSocket streaming supports:
  - `wav`
  - raw PCM: `pcm_s16le`, `pcm_l16`, `pcm_raw`
- recommended audio:
  - `16kHz or higher`
  - `16-bit`
  - mono/stereo

Important implication:

- The first `audio/pcm` error was a mismatch with the installed SDK validation path, not a proof that PCM is unsupported in Sarvam generally.
- The docs say raw PCM is supported, but the current SDK / Pipecat wrapper in this environment validated against `audio/wav`.

### 2. Sarvam’s own voice-agent integration example is much simpler than our current pipeline

Their LiveKit voice-agent guide shows a simple setup:

- `sarvam.STT(language="unknown", model="saaras:v3", mode="transcribe")`
- `sarvam.TTS(...)`
- minimal agent session

Important implication:

- Sarvam’s recommended integration does **not** push complicated app-layer turn heuristics first.
- It also defaults to:
  - `language="unknown"`
  - `mode="transcribe"`

This is important because our current config is:

- `language=hi-IN`
- `mode=codemix`
- `high_vad_sensitivity=False`

That differs from both:

- the simple LiveKit integration guide
- the streaming guide examples

### 3. The streaming guide strongly emphasizes VAD signals and high VAD sensitivity

The streaming guide’s enhanced example shows:

- `model="saaras:v3"`
- `mode="transcribe"`
- `language_code="hi-IN"`
- `high_vad_sensitivity=True`
- `vad_signals=True`

Important implication:

- Our current `high_vad_sensitivity=False` may be too weak for real phone/live mic segmentation.
- Sarvam’s own examples push toward enabling stronger VAD sensitivity.

### 4. The streaming guide explicitly supports `flush_signal`

The guide has an “Instant Processing with Flush Signals” example:

- connect with `flush_signal=True`
- call `ws.flush()` to force immediate processing

Important implication:

- if the current Pipecat wrapper does not flush aggressively enough at the right time, partial/late transcript behavior may worsen
- this is a high-value area for the next agent to inspect in the Sarvam STT wrapper behavior

### 5. `codemix` is supported, but the docs do not show it as the default voice-agent setup

Sarvam docs say `saaras:v3` supports:

- `transcribe`
- `translate`
- `verbatim`
- `translit`
- `codemix`

Important implication:

- `codemix` is valid and designed for Hindi-English speech
- but the simple LiveKit integration example uses `transcribe`, not `codemix`
- there is still a real possibility that `codemix` is hurting consistency in this exact live-call path

### 6. Language auto-detection may matter

Sarvam docs say:

- `language_code="unknown"` enables auto-detection
- `language_probability` is returned when language is not fixed

Important implication:

- for true Hinglish / mixed Hindi-English, hard-coding `hi-IN` may be too restrictive
- the docs’ simplest agent example uses `unknown`

### 7. Sarvam’s own FAQ says quality depends heavily on audio quality, noise, accent, and terminology

The FAQ says typical accuracy is:

- clear speech, minimal noise: `95-98%`
- moderate noise: `90-95%`
- heavy noise or strong accents: `85-90%`

Important implication:

- if our local WebRTC / LiveKit input is not being delivered to Sarvam in the most compatible shape, accuracy will degrade fast
- this means we must validate the exact format Sarvam receives, not just assume the provider is wrong

## Most Likely Problems Right Now

Based on the docs plus logs, the highest-probability issues are:

1. **Wrong STT mode choice**
   - `codemix` may be less stable than `transcribe` for this specific live-call path

2. **Language setting is too strict**
   - `hi-IN` may be reducing quality for mixed Hindi-English input
   - `unknown` may work better

3. **VAD tuning is too weak**
   - current `high_vad_sensitivity=False`
   - docs examples lean toward `True`

4. **Flush behavior may not be optimized**
   - docs explicitly call out `flush_signal=True`
   - current wrapper behavior should be verified

5. **Audio compatibility may still be suboptimal**
   - even though the codec error is fixed, we still need to confirm the shape of audio Sarvam is actually receiving from Pipecat/LiveKit

## Recommended Next Changes For The Next Agent

Do these one at a time, with logs after each:

### Change 1

Switch Sarvam STT config from:

- `language=Language.HI_IN`
- `mode="codemix"`
- `high_vad_sensitivity=False`

to:

- `language=None` / auto-detect (`unknown` path)
- `mode="transcribe"`
- `high_vad_sensitivity=True`
- keep `vad_signals=True`

Reason:

- this matches Sarvam’s own simple LiveKit integration more closely
- it also matches the streaming guide’s enhanced example more closely

### Change 2

Verify whether the Pipecat Sarvam STT wrapper is actually using `flush_signal=True` in the right way for this pipeline.

Things to inspect:

- connection parameters inside `SarvamSTTService._connect()`
- whether end-of-speech events should force `flush()`
- whether the wrapper behavior differs when `vad_signals=True`

### Change 3

Add explicit STT-result telemetry before orchestrator decisions:

- transcript text
- `language_code`
- Sarvam metrics returned in the message
- utterance duration
- whether transcript came immediately after `END_SPEECH`

This should be logged before any accept/clarify logic.

### Change 4

If STT is still bad after changes 1-3, create a **direct Sarvam SDK streaming test script** outside Pipecat:

- feed a known WAV sample with a Hindi/Hinglish phrase
- test:
  - `transcribe + unknown`
  - `transcribe + hi-IN`
  - `codemix + unknown`
  - `codemix + hi-IN`
- compare transcripts

This isolates whether the issue is:

- Sarvam model/mode choice
- or the LiveKit/Pipecat transport path

## What Not To Change Yet

Until the above is tested, do not:

- switch back to Deepgram
- reintroduce the old app-layer timer buffering logic
- add more keyword heuristics in `conversation_manager.py`
- mix Google Calendar / booking integration into this phase
- change Sarvam HTTP TTS path

## Current Status

What is working:

- server startup
- pipeline wiring
- LiveKit connection
- Sarvam STT connection
- Sarvam TTS playback
- speech_orchestrator structure

What is not working well enough:

- STT recognition quality in real live calls

## Short Conclusion

The codebase is now finally simple enough that the remaining problem is visible:

**Sarvam STT configuration / streaming behavior is the current bottleneck.**

The next agent should focus on:

1. `transcribe` vs `codemix`
2. `unknown` vs `hi-IN`
3. `high_vad_sensitivity=True`
4. flush behavior
5. direct Sarvam SDK A/B test if live-call transcripts still look wrong
