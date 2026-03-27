## Root Cause Analysis: Audio Reliability & Latency

### THE PROBLEM
The agent is experiencing a **Pipeline Deadlock**. The logs show that the `StartFrame` is never reaching the end of the pipeline.

1. **WebSocket Hang**: The `SarvamTTSService` protocol is hanging while trying to establish a secure WebSocket connection. 
2. **Blocked Pipeline**: Because Pipecat is synchronous in its frame delivery for the `StartFrame`, if the TTS service hangs during its `_connect()` call, the entire bot freezes. This explains both the "long delay" and the "no voice."
3. **VAD Feedback**: Because the bot is frozen, the "Interruption" logs you see are likely noise or the aggregator timing out.

### THE SOLUTION (PIVOT TO HTTP)
To get voice working **instantly and reliably**, we will pivot from the WebSocket version to the **HTTP version** (`SarvamHttpTTSService`).

**Why HTTP?**
- **No Handshake Deadlock**: It doesn't need to stay connected. It sends text and gets audio back in one shot.
- **Reliable in Restricted Networks**: WebSockets are often blocked or throttled by local firewalls/ISPs.
- **Identical Voice Quality**: We can still use the premium `bulbul:v3` model.

### ACTION PLAN
1. **Swap to `SarvamHttpTTSService`** in `agent.py`.
2. **Remove Handshake Delays**: Since HTTP is stateless, we don't need the 2.5s wait anymore.
3. **Verify with HTTP-specific Telemetry**.

---
**Approved by Vibe Coder?**
