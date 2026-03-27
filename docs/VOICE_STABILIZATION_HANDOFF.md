# VoxAgent Voice Stabilization Handoff

## Goal Right Now

The immediate goal is to make the conversation feel smooth and reliable:

- user speaks
- speech is transcribed correctly
- turn ends quickly and naturally
- assistant answers in clear Hindi + English Hinglish
- audio plays every time
- no random silence
- no awkward lag between user stop and bot start

Infrastructure work like Redis, Vercel, Twilio, dashboard wiring, and advanced knowledge/document ingestion should come after this voice path is stable.

## What Was Going Wrong

### 1. Audio was being generated inconsistently or not heard

The main issue was not Sarvam itself. Sarvam was working and returning audio.

The real problems were inside the pipeline:

- the greeting path was incorrectly calling the processor in a way that did not reliably forward frames into TTS
- the custom processor was swallowing some downstream frames instead of forwarding them
- framework interruptions were still active, so false user-start events could cut off TTS/output playback
- a custom TTS frame conversion layer had been added even though Pipecat already supports `TTSAudioRawFrame` correctly

Result:

- logs looked like the model responded
- but audio playback could be interrupted, dropped, or never properly reach the output transport

### 2. Turn detection was too slow

There were too many overlapping "end of turn" delays:

- VAD stop threshold was conservative
- Deepgram endpointing was conservative
- aggregator stop timeout was also conservative
- smart-turn logic was heavier than needed for current stability goals

Result:

- the user stopped speaking
- the system waited too long before starting response generation
- conversation felt laggy and unnatural

### 3. Voice language output was inconsistent

The assistant was supposed to speak Hinglish, but the spoken text was often:

- pure English
- romanized Hindi
- or phrasing that TTS pronounced badly

This is why it sometimes sounded like the voice drifted into the wrong accent or something closer to another Indian language pattern.

The issue was mostly text formatting for TTS, not only the voice provider.

### 4. Browser client path had separate problems

The web client had two independent issues:

- `/token` route was missing needed LiveKit auth imports
- remote audio track subscription handling happened too late, so the browser could miss already-published tracks

Result:

- browser tests could fail even if server-side audio was actually fine

### 5. Conversation path had avoidable latency

Before each response, the system was doing too much work in sequence:

- session lookup
- history write
- knowledge fetch
- history fetch
- LLM call
- assistant history write

Some of this was safe to parallelize or move off the critical path.

Result:

- even when audio transport worked, response startup still felt slower than necessary

## What Was Fixed

### In `agent.py`

The following stabilizing fixes were made:

- the conversation processor now forwards frames properly instead of swallowing them
- the automated greeting now enters the pipeline correctly
- the custom TTS frame converter was removed
- framework-level interruptions were disabled for now to stop false playback cutoffs
- VAD and turn-stop settings were tightened for faster replies
- the smart-turn-heavy stop path was replaced with a simpler speech-timeout strategy
- the first spoken greeting was changed to natural Hindi/Hinglish
- telemetry logging now confirms when audio bytes are actually flowing

### In `conversation_manager.py`

The following latency and language fixes were made:

- shorter state I/O timeout for request-path memory operations
- knowledge fetch and history fetch now run in parallel
- assistant history write was moved off the critical path
- fast-path replies were added for greetings and obvious short/noisy turns
- response text is normalized for Hindi/Hinglish TTS
- Hindi now uses Devanagari where needed instead of romanized Hindi
- feminine assistant phrasing is encouraged so Nina sounds consistent

### In `server.py`

- LiveKit token generation imports were fixed
- `/token` now works properly for browser testing

### In `web_client.html`

- track handlers are registered before connect
- already-subscribed tracks are attached after connect
- attached audio elements are explicitly played and managed

### In prompt files

- instructions were strengthened so spoken text stays in natural Hinglish
- Hindi is requested in Devanagari script
- English is kept for product names and technical terms only

## What Was Verified

The system was locally verified with:

- Python compile checks for touched files
- token endpoint test
- LiveKit integration test using injected WAV audio

Successful validation included:

- remote audio track subscription
- Sarvam TTS request firing
- audio flowing to LiveKit output
- full pipeline validation with measured time-to-first-audio

Observed validated result during testing:

- full pipeline worked
- time-to-first-agent-audio was about `1.11s` in the successful test path

## What Should Not Be Touched Right Now

Until conversation smoothness is stable, avoid making major changes to these areas:

### 1. Do not reintroduce aggressive interruption logic

Avoid changing:

- `allow_interruptions=False`
- current simplified turn-stop strategy
- current VAD tuning

Why:

- this is the biggest risk for bringing back "response generated but no sound"

### 2. Do not add custom frame conversion around TTS audio

Avoid adding back:

- custom conversion from `TTSAudioRawFrame` to other frame types
- custom transport hacks unless absolutely necessary

Why:

- Pipecat already handles this path
- extra conversion made the pipeline harder to reason about

### 3. Do not heavily refactor the voice pipeline structure yet

Avoid major changes to:

- `transport.input() -> stt -> aggregator -> conversation -> tts -> output`

Why:

- the current pipeline is finally understandable and testable
- now we need stability, not architecture churn

### 4. Do not add Redis dependency into the speech-critical path yet

You can add Redis later, but do not make voice turns depend on Redis availability before stabilization is complete.

Why:

- speech must still work when state services are slow or unavailable

### 5. Do not change the Sarvam provider path until text quality is judged first

Before changing voices/models/providers:

- first confirm whether the remaining issue is pronunciation/text
- not transport

Why:

- transport is now working
- changing provider too early will mix two variables at once

## What To Focus On Next

## Phase 1: Smooth Conversation First

This is the current priority.

### Success criteria

- bot always speaks
- bot starts speaking quickly
- responses sound natural in Hindi/Hinglish
- greetings, confirmations, and short questions feel human
- no accidental silence after valid user input
- no weird interruption during playback

### Recommended tasks

1. Review and improve common fast-path responses
2. Tune Hindi/Hinglish wording for TTS pronunciation
3. Test with real microphone input, not only WAV injection
4. Log these per turn:
   - transcription text
   - turn-end timestamp
   - LLM start/end
   - TTS request start/end
   - first audio byte / first audio frame
5. Reduce bad responses for partial transcripts like:
   - "What"
   - "Ji"
   - "Hello"
   - "How are you"

## Phase 2: Integrate Infra After Voice Feels Good

Only after Phase 1 feels stable:

### Redis

Add Redis for:

- session persistence
- history
- state across instances

But keep fallback behavior so voice does not die if Redis is down.

### Twilio

Add Twilio after the web/livekit voice path is consistently solid.

Twilio should be introduced only when:

- the assistant already answers correctly in LiveKit test flows
- you can measure call quality changes clearly

### Vercel

Vercel deployment should come after:

- environment variable strategy is stable
- token generation works in deployed environment
- LiveKit URL and callback routing are finalized

## Phase 3: Post-Test Product Wiring

After voice and infra testing:

### Dashboard connection

Then connect:

- live calls
- transcripts
- call states
- knowledge upload status
- session analytics

Do this after voice testing, not before.

Reason:

- dashboard depends on reliable underlying events
- unstable voice behavior makes dashboard debugging noisy

## Knowledge and Behavioral Document Parsing Goal

Your later goal is:

- upload knowledge documents
- upload behavioral instruction documents
- parse them clearly
- have the assistant act on them correctly

That is the right direction, but it should be treated as a separate subsystem from audio stabilization.

## Recommended approach for knowledge/behavior docs

### 1. Separate document types

Treat these as different classes:

- product knowledge
- FAQ knowledge
- sales/process instructions
- assistant behavior rules
- conversation policy / escalation logic

Why:

- not every document should go straight into semantic retrieval
- some docs should become prompt/policy rules instead

### 2. Build a parsing pipeline, not just upload storage

For uploaded files, the system should:

1. extract text cleanly
2. detect document type
3. chunk intelligently
4. store metadata
5. index searchable content
6. optionally promote behavior rules into structured config/prompt instructions

### 3. Do not rely on raw file text alone

Behavioral documents especially should be converted into structured rules such as:

- greeting style
- escalation conditions
- tone constraints
- forbidden claims
- required upsell lines
- booking logic

This is better than hoping retrieval alone makes the assistant behave correctly.

## Recommended Project Order

Use this order:

1. Smooth conversation quality
2. Real mic testing
3. Twilio/phone-path testing
4. Redis integration
5. Vercel deployment hardening
6. Dashboard wiring
7. Knowledge + behavior document ingestion pipeline

This order reduces confusion and makes failures easier to isolate.

## Current Stable Baseline

Right now, the stable baseline should be considered:

- current `agent.py` voice pipeline
- current faster turn handling
- current no-interruptions mode
- current token/browser fixes
- current Hinglish normalization path

If future tuning breaks voice again, return to this baseline first.

## Open Risks Still Remaining

These are not fully solved yet:

### 1. General LLM latency

Some turns still spend noticeable time in the LLM path.

This is much less dangerous than missing audio, but still affects smoothness.

### 2. Pronunciation quality may still need tuning

Even with better text formatting, some words may still sound unnatural depending on:

- chosen Sarvam voice
- exact Hindi/English balance
- punctuation style

### 3. Real phone conditions are still untested

LiveKit local validation succeeded, but phone conditions may add:

- noisy audio
- clipping
- packet delay
- different timing behavior

### 4. Knowledge injection is not production-grade yet

The current knowledge path is not yet the final document ingestion system for:

- strict policy behavior
- precise behavior documents
- guaranteed parsing accuracy

### Latest Tuning Status

Based on the latest real run:

- audio output is working
- greeting is spoken correctly
- the agent listens and responds
- latency is improved compared to the broken state
- some turns are still fragmented into partial transcripts
- some responses were too Hindi-heavy or too long
- in noisy / overlapping conditions, STT can still split one user question into multiple short turns

Additional stabilization changes were made after the first handoff:

- stricter VAD thresholds for noisy environments
- shorter endpointing for lower wait time
- user mute while bot is speaking to reduce self-echo and speaker bleed
- better Hindi greeting detection like `नमस्ते`
- echo suppression for transcripts that match the bot's own last reply
- shorter, more mixed Hinglish fast-path replies
- safer generic answer for course/offer questions to avoid hallucination

## Phase 1 Tuning Changes (2025-03-25)

The following changes were applied to improve conversation smoothness and noisy-environment robustness.

### In `agent.py`

1. **Fragment buffering improvements**:
   - Added more Hindi connectors/postpositions to `_should_buffer_text` (verb forms, particles)
   - Raised threshold from ≤5 words to ≤6 words for buffering
   - Added terminal punctuation bypass: if text ends with `?`, `!`, or `।`, never buffer it
   - Increased merge delay from 0.65s to 0.8s (1.0s for ≤3 word fragments)

2. **Processor-level echo suppression**:
   - Added `_last_tts_text` tracking — stores every text sent to TTS
   - Before dispatching any user turn, word-overlap comparison against last TTS output
   - If almost all user words match the bot's last reply → silently suppress (prevents STT echo loops)
   - Greeting also primes the echo tracker

3. **Trivial non-question gate**:
   - Added `_is_trivial_non_question` — suppresses ≤2 word inputs that aren't greetings or questions
   - Allows `hello`, `namaste`, `क्या`, question words through but blocks fragments like `हो.`, `मैं`

### In `conversation_manager.py`

1. **Fragment detection improvements**:
   - `_looks_incomplete_fragment` now checks terminal punctuation on original text before stripping
   - Questions ending with `?` are never treated as fragments, even if short
   - Expanded connector/particle set for better Hindi coverage

2. **Echo detection improvements**:
   - `_looks_like_echo` now handles Devanagari characters via Unicode regex `[\w\u0900-\u097F]+`
   - Lowered detection threshold — catches echoes from 2+ words
   - Uses set intersection instead of substring search

3. **New fast-path canned responses** (all proper Devanagari Hinglish):
   - Fees/pricing → safe response offering demo
   - Goodbye/thanks → warm sign-off with `end_call` action
   - Yes/okay/हां → acknowledge and ask what they need
   - Who are you → short Nina introduction
   - How are you / कैसी हो → natural response

4. **Fixed all existing fast-path responses**:
   - Converted romanized Hindi to Devanagari throughout (fixed `"bolिए"` mixed-encoding bug)
   - All responses now ≤15 words and use proper Devanagari

5. **New rule-based intents**:
   - `confirmation` intent for yes/okay/हां/जी (bypasses fragment suppression)
   - `farewell` intent for bye/thanks/धन्यवाद (bypasses fragment suppression)
   - `?` in original text always triggers `ask_question` intent

6. **Tighter TTS response limits**:
   - Hard character limit reduced from 160 → 120 chars
   - Word-count cap added: ≤18 words
   - Response policy now says "MAXIMUM 15 words"

### In `prompt.py`

1. **Explicit word limit**: "Keep every reply under 15 words and under 2 sentences"
2. **Stronger anti-hallucination**: "NEVER invent" with explicit fallback text
3. **Fragment handling**: "If the transcript is very short or looks like a fragment, ask the user to repeat"
4. **More natural Hinglish examples** in style guidelines
5. **Removed markdown/list/long-paragraph instructions** reinforced

## What Was Verified

- All three files compile and import successfully
- 48 unit tests pass covering:
  - Fragment detection (9 known fragments correctly caught, 5 non-fragments correctly passed)
  - Echo detection (greeting echo caught, genuine speech passed through)
  - Fast-path responses (7 intents correctly matched)
  - Devanagari quality (12 responses checked for romanized Hindi — zero found)
  - TTS shortening (character limit, sentence limit, word count limit all enforced)
  - Buffer logic (5 should-buffer cases correct, 3 should-not-buffer cases correct)

## What Still Needs Work Next

If another agent picks this up, the highest-value next tasks are:

1. Real mic testing in noisy environments
   - test with fan noise, café background, speaker bleed
   - verify the bot does not respond to its own speech (echo suppression is now implemented but untested with real audio)

2. Fine-tuning fragment buffer delays
   - 0.8s/1.0s delays are conservative estimates
   - may need adjustment based on real Deepgram transcript arrival patterns

3. LLM response quality audit
   - run 10+ full conversations and check that LLM responses also stay ≤15 words
   - the `response_policy` enforces this via prompt but LLMs can still exceed

4. TTS pronunciation spot-checks
   - verify Sarvam pronounces the Devanagari correctly
   - some words may need phonetic adjustments

5. Streaming TTS evaluation
   - if batch HTTP TTS latency is still too high, evaluate Sarvam streaming

## Do Not Change Yet

Until the above is stable, do not:

- re-enable aggressive interruptions
- reintroduce custom TTS frame conversion
- move voice-critical behavior behind Redis or dashboard dependencies
- do major refactors of the core pipeline order
- mix Twilio debugging into the same phase

## If This Is Handed To Another Agent

They should assume:

- transport/audio path is fixed
- fragment/echo suppression is now implemented at both processor and conversation_manager levels
- all fast-path responses are in proper Devanagari Hinglish
- current issues are now **real-world audio testing** issues, not code logic issues
- infrastructure integrations come after this phase

## Suggested Next Work Item

The best next task is:

`Run 10 real-mic test conversations with background noise and verify fragment suppression, echo suppression, response quality, and TTS latency in live conditions.`

## 2026-03-25 Adaptive Understanding Pass

Latest tuning focused on improving understanding without destabilizing the working HTTP TTS path.

### What Changed

- Kept `SarvamHttpTTSService` as the stable voice path.
- Reworked turn management in `agent.py` toward asymmetric detection:
  - stricter turn start for noisy environments
  - smarter turn stop using `TurnAnalyzerUserTurnStopStrategy(LocalSmartTurnAnalyzerV3)`
  - `SpeechTimeoutUserTurnStopStrategy` kept as a fallback
  - Deepgram `utterance_end_ms` enabled to reduce cut-word finalization
- Added adaptive fragment buffering in `ConversationProcessor`:
  - short fragments are buffered briefly
  - if several short fragments happen close together, the processor shifts into a noisier profile and waits slightly longer before dispatch
- Added smarter clarification logic in `conversation_manager.py`:
  - short real intents like `fees`, `demo`, `callback` still count as valid user input
  - broken carry-over fragments like `से. मैं` are clarified instead of being answered blindly
  - common intents now steer toward `course`, `fees`, `demo`, or `callback`

### Why This Is Better Than Simply Removing Suppression

The previous loosening pass helped reduce cut-offs, but it also weakened crowded-environment handling.

This pass keeps real user speech flowing while moving suppression to safer places:
- stricter turn start
- smarter buffering
- targeted clarification instead of blanket blocking

### What Was Verified In This Pass

- `agent.py`, `conversation_manager.py`, and `prompt.py` compile successfully
- method-level checks confirmed:
  - `fees` remains a valid short intent
  - `demo` remains a valid short intent
  - `से. मैं` becomes a clarification response
  - full course questions route to the course fast-path

### Still Needs Live Validation

- crowded room / market noise
- user pausing mid-sentence
- mixed Hindi + English utterances
- whether smart-turn timing should be tightened or loosened slightly after real-call tests

## 2026-03-26 Plan B Refactor

This refactor changed the active speech path from a mixed aggregator-driven loop to a simpler STT-led loop.

### What Changed

- Added [speech_orchestrator.py](/Users/ahmad/Gemini/antigravity/Callindri/voxagent/speech_orchestrator.py)
  - single authority for finalized transcript acceptance
  - returns only `accept`, `clarify`, or `ignore`
  - owns:
    - last spoken assistant text
    - bot speaking / recently stopped state
    - short-fragment tracking
    - echo / residual / incomplete-turn decisions
- Replaced the old `ConversationProcessor` approach in [agent.py](/Users/ahmad/Gemini/antigravity/Callindri/voxagent/agent.py)
  - active path is now:
    - `LiveKit input`
    - `SarvamSTTService`
    - `VoiceLoopProcessor`
    - `SarvamHttpTTSService`
    - `LiveKit output`
  - `DeepgramSTTService` remains only as a fallback via `USE_DEEPGRAM_STT=true`
  - active Sarvam STT config uses:
    - model `saaras:v3`
    - mode `codemix`
    - Sarvam VAD signals
- Narrowed [conversation_manager.py](/Users/ahmad/Gemini/antigravity/Callindri/voxagent/conversation_manager.py)
  - no longer responsible for deciding whether partial speech is complete
  - now acts as response routing after the orchestrator accepts a turn
  - fast-path behavior is kept only for explicit intents and structured questions

### What Was Removed From The Active Path

- app-layer timer logic that upgraded partial buffered text into a real user turn
- active `LLMUserAggregator`-based turn acceptance
- active echo / fragment acceptance logic inside `conversation_manager.py`
- active `DeepgramSTTService` path as the default speech recognizer

### What Was Intentionally Not Touched

- `SarvamHttpTTSService` remains the active TTS path
- Redis / Supabase remain persistence only
- knowledge-base lookup remains post-acceptance only
- Google Workspace / booking integration is still out of scope for this phase
- dashboard / Twilio / Vercel work remains untouched

### Verification Performed

- Python compile checks passed for:
  - `agent.py`
  - `conversation_manager.py`
  - `speech_orchestrator.py`
- direct orchestrator behavior checks passed:
  - `मुझे courses के बारे में` => clarify
  - `मुझे courses के बारे में पता करना है` => accept
  - `demo` => accept
  - greeting echo fragment => ignore
- `server.py` startup path runs with the new refactor
- agent spawn path initializes Sarvam STT successfully and reaches pipeline-ready state

### Validation Still Pending

- full live call with working local/cloud LiveKit room
- real mic test with:
  - complete Hindi/Hinglish request
  - pause mid-sentence
  - bare topic word
  - demo request
  - noisy environment

### Next Safe Step

Run live validation with LiveKit actually available and verify:

1. Greeting is spoken once and never re-consumed
2. `मुझे courses के बारे में` gets only clarification
3. `मुझे courses ke baare mein pata karna hai` is accepted as one request
4. `fees` does not hallucinate pricing
5. `demo` still routes quickly

That gives the clearest signal on whether the tuning values need further adjustment.
