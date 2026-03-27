"""
server.py
---------
FastAPI application entry-point.

Responsibilities:
  - Create the app and attach middleware.
  - Wire up the voice-pipeline routes (/join-room, /rooms, /inbound).
  - Mount API routers: knowledge, dashboard.
  - Wire runtime shims (active-room counter for dashboard).

Business logic lives in:
  api/knowledge.py   – document upload/list/delete
  api/dashboard.py   – stats & call records
"""

from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request, Response, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from twilio.twiml.voice_response import VoiceResponse
from livekit.api import AccessToken, VideoGrants

from agent import agent_loop
from config import LIVEKIT_API_KEY, LIVEKIT_API_SECRET
from memory import memory
from api.knowledge import router as knowledge_router
from api.dashboard import router as dashboard_router, set_active_room_counter

# ── active-room tracker (voice pipeline only) ────────────────────────────────
_active_rooms: dict[str, asyncio.Task] = {}


def _active_count() -> int:
    return sum(1 for t in _active_rooms.values() if not t.done())


# ── lifespan ─────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ping-check Redis at startup
    await memory.connect()
    # Wire dashboard shim so it can read live room count without importing this module
    set_active_room_counter(_active_count)
    yield


# ── app ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="VoxAgent MVP",
    description="Pipecat Voice Agent API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── routers ───────────────────────────────────────────────────────────────────
app.include_router(knowledge_router)
app.include_router(dashboard_router)


# ── voice-pipeline routes ─────────────────────────────────────────────────────

@app.get("/")
def read_root():
    return {"message": "Welcome to VoxAgent API"}


@app.post("/join-room")
async def join_room(request: Request):
    """
    Trigger the agent to join a LiveKit room.

    Body JSON (all optional):
      { "room": "test-room" }

    Returns immediately; agent_loop runs as a background task.
    """
    body: dict = {}
    try:
        body = await request.json()
    except Exception:
        pass

    room_name = body.get("room", "test-room")

    if room_name in _active_rooms and not _active_rooms[room_name].done():
        return {"room": room_name, "status": "already_running", "call_id": None}

    call_id = str(uuid.uuid4())
    print(f"[SERVER] Spawning agent_loop room='{room_name}' call_id={call_id}")

    task = asyncio.create_task(
        _run_agent(room_name, call_id),
        name=f"agent-{call_id}",
    )
    _active_rooms[room_name] = task

    return {"room": room_name, "call_id": call_id, "status": "started"}


@app.get("/token")
async def get_token(room: str = "test-room", identity: str = None):
    """
    Generate a participant token for the LiveKit room.
    Useful for browser-based clients.
    """
    if not identity:
        identity = f"user-{uuid.uuid4().hex[:6]}"
    
    try:
        token = AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        token.with_identity(identity)
        token.with_grants(VideoGrants(
            room_join=True,
            room=room,
            can_publish=True,
            can_subscribe=True
        ))
        return {"token": token.to_jwt(), "room": room, "identity": identity}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


async def _run_agent(room_name: str, call_id: str) -> None:
    """Run agent_loop and clean up _active_rooms on completion."""
    try:
        await agent_loop(room_name, call_id)
    except Exception as exc:
        print(f"[SERVER] agent_loop error room='{room_name}': {exc}")
    finally:
        _active_rooms.pop(room_name, None)
        print(f"[SERVER] agent_loop finished room='{room_name}'")


@app.get("/rooms")
def list_rooms():
    """List rooms that currently have an active agent."""
    return {"active_rooms": [r for r, t in _active_rooms.items() if not t.done()]}


@app.post("/inbound")
async def handle_incoming_call(request: Request):
    """Twilio inbound call webhook — returns TwiML greeting."""
    response = VoiceResponse()
    response.say(
        "Welcome to Callindri Vox Agent. The system is currently starting up backend services."
    )
    return Response(content=str(response), media_type="text/xml")


# ── entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)
