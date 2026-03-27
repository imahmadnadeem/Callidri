import json
import asyncio
import redis.asyncio as redis
from redis.asyncio.retry import Retry
from redis.backoff import ExponentialBackoff
from datetime import timedelta, datetime
from supabase import acreate_client, AsyncClient, ClientOptions
from config import REDIS_URL, SUPABASE_URL, SUPABASE_KEY, REDIS_TIMEOUT, SUPABASE_TIMEOUT, REDIS_MAX_CONNECTIONS, REDIS_MAX_IDLE, REDIS_RETRY_ATTEMPTS, REDIS_KEEPALIVE

class MemoryManager:
    def __init__(self):
        self.url = REDIS_URL
        # Requirement: Use rediss:// (with double 's') for Upstash URLs
        if "upstash.io" in self.url and self.url.startswith("redis://"):
            self.url = self.url.replace("redis://", "rediss://", 1)

        # Requirement: SSL configuration, pool limits, and timeout
        retry_policy = Retry(ExponentialBackoff(), REDIS_RETRY_ATTEMPTS)
        
        redis_kwargs = {
            "decode_responses": True,
            "socket_connect_timeout": REDIS_TIMEOUT,
            "socket_timeout": REDIS_TIMEOUT,
            "retry": retry_policy,
            "retry_on_timeout": True,
            "max_connections": REDIS_MAX_CONNECTIONS,
            "health_check_interval": 60,
        }
        if REDIS_KEEPALIVE:
            redis_kwargs["socket_keepalive"] = True

        if self.url.startswith("rediss://"):
            redis_kwargs["ssl_cert_reqs"] = None

        self.r = redis.from_url(self.url, **redis_kwargs)
        
        self.ttl = timedelta(minutes=30)
        self.supabase: AsyncClient = None
        self.use_fallback = False
        self._fallback_storage = {} # {key: {field: value}}
        self._fallback_history = {} # {key: [messages]}

    async def connect(self):
        """Perform startup checks like ping asynchronously."""
        try:
            # Initialize Supabase client if configured
            if SUPABASE_URL and SUPABASE_KEY and not self.supabase:
                options = ClientOptions(postgrest_client_timeout=SUPABASE_TIMEOUT)
                self.supabase = await acreate_client(SUPABASE_URL, SUPABASE_KEY, options=options)
                print("✅ Supabase client initialized (async)")
                
            # Fail immediately on startup if unreachable (e.g. timeout, no retry)
            try:
                ping_client = redis.from_url(self.url, socket_connect_timeout=REDIS_TIMEOUT)
                await ping_client.ping()
                await ping_client.aclose()
                print("✅ Redis connected successfully (async)")
            except Exception as redis_e:
                print(f"⚠️ Redis unavailable ({redis_e}). Switching to IN-MEMORY fallback.")
                self.use_fallback = True
        except Exception as e:
            print(f"❌ Initialization Failure: {e}")
            # We only raise if it's a fatal non-Redis error (e.g. library missing)
            if not isinstance(e, (ConnectionError, RuntimeError)):
                raise e

    async def create_session(self, call_id: str, agent_id: str):
        key = f"call_session:{call_id}"
        session_data = {
            "call_id": call_id,
            "agent_id": agent_id,
            "current_intent": "greeting",
            "collected_data": json.dumps({}),
            "tools_executed": json.dumps([]),
            "call_status": "active",
            "created_at": datetime.utcnow().isoformat()
        }
        if self.use_fallback:
            self._fallback_storage[key] = session_data
            return

        await self.r.hset(key, mapping=session_data)
        await self.r.expire(key, self.ttl)

    async def get_session(self, call_id: str):
        key = f"call_session:{call_id}"
        if self.use_fallback:
            data = self._fallback_storage.get(key)
        else:
            data = await self.r.hgetall(key)

        if not data:
            return None
        return {
            "call_id": data.get("call_id"),
            "agent_id": data.get("agent_id"),
            "current_intent": data.get("current_intent"),
            "collected_data": json.loads(data.get("collected_data", "{}")),
            "tools_executed": json.loads(data.get("tools_executed", "[]")),
            "call_status": data.get("call_status"),
            "created_at": data.get("created_at")
        }

    async def update_intent(self, call_id: str, intent: str):
        key = f"call_session:{call_id}"
        if self.use_fallback:
            if key in self._fallback_storage:
                self._fallback_storage[key]["current_intent"] = intent
            return
        await self.r.hset(key, "current_intent", intent)

    async def update_collected_data(self, call_id: str, updates: dict):
        key = f"call_session:{call_id}"
        if self.use_fallback:
            data_str = self._fallback_storage.get(key, {}).get("collected_data")
            data = json.loads(data_str) if data_str else {}
            data.update(updates)
            if key in self._fallback_storage:
                self._fallback_storage[key]["collected_data"] = json.dumps(data)
            return

        data_str = await self.r.hget(key, "collected_data")
        data = json.loads(data_str) if data_str else {}
        data.update(updates)
        await self.r.hset(key, "collected_data", json.dumps(data))

    async def log_tool_executed(self, call_id: str, tool_name: str, result: str):
        key = f"call_session:{call_id}"
        if self.use_fallback:
            tools_str = self._fallback_storage.get(key, {}).get("tools_executed")
            tools = json.loads(tools_str) if tools_str else []
            tools.append({"tool": tool_name, "result": result, "timestamp": datetime.utcnow().isoformat()})
            if key in self._fallback_storage:
                self._fallback_storage[key]["tools_executed"] = json.dumps(tools)
            return

        tools_str = await self.r.hget(key, "tools_executed")
        tools = json.loads(tools_str) if tools_str else []
        tools.append({"tool": tool_name, "result": result, "timestamp": datetime.utcnow().isoformat()})
        await self.r.hset(key, "tools_executed", json.dumps(tools))

    async def add_history_message(self, call_id: str, role: str, content: str):
        """
        Add a message to the conversation history asynchronously.
        - Redis: Truncated to last 5 turns (10 messages) to save memory.
        - Supabase: Never store conversation history in Supabase.
        """
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # 1. Update fallback/Redis
        hist_key = f"history:{call_id}"
        if self.use_fallback:
            if hist_key not in self._fallback_history:
                self._fallback_history[hist_key] = []
            self._fallback_history[hist_key].append(json.dumps(message))
            if len(self._fallback_history[hist_key]) > 10:
                self._fallback_history[hist_key] = self._fallback_history[hist_key][-10:]
        else:
            await self.r.rpush(hist_key, json.dumps(message))
            await self.r.ltrim(hist_key, -10, -1)
            await self.r.expire(hist_key, self.ttl)

            # 2. Update session hash to prevent premature expiry
            session_key = f"call_session:{call_id}"
            await self.r.expire(session_key, self.ttl)

    async def get_history(self, call_id: str):
        """Retrieve the last 5 turns (max 10 messages) from Redis."""
        hist_key = f"history:{call_id}"
        if self.use_fallback:
            messages = self._fallback_history.get(hist_key, [])
        else:
            messages = await self.r.lrange(hist_key, 0, -1)
        if not messages:
            return []
        return [json.loads(m) for m in messages]

    async def flush_to_supabase(self, call_id: str) -> bool:
        """Persist session data to Supabase with retries (async)."""
        session = await self.get_session(call_id)
        if not session or not self.supabase:
            return False

        now = datetime.utcnow()

        # Compute duration in whole seconds from session start time
        duration_seconds: int = 0
        created_at_str = session.get("created_at")
        if created_at_str:
            try:
                start = datetime.fromisoformat(created_at_str)
                duration_seconds = max(0, int((now - start).total_seconds()))
            except (ValueError, TypeError):
                pass

        record = {
            "call_id": session["call_id"],
            "intent_summary": session["current_intent"],
            "tools_executed": session["tools_executed"],
            "call_status": session["call_status"] or "completed",
            "duration": duration_seconds,
            "timestamp": now.isoformat(),
        }

        max_attempts = 3
        from config import SUPABASE_TIMEOUT
        for attempt in range(1, max_attempts + 1):
            try:
                # Use upsert for idempotency (prevents duplicates on retry)
                await asyncio.wait_for(
                    self.supabase.table("calls").upsert(record, on_conflict="call_id").execute(),
                    timeout=SUPABASE_TIMEOUT
                )
                print(f"Successfully flushed session {call_id} to Supabase on attempt {attempt}.")
                return True
            except asyncio.TimeoutError:
                timestamp = datetime.utcnow().isoformat()
                print(f"[{timestamp}] Attempt {attempt}/{max_attempts} timed out flushing session {call_id} to Supabase after {SUPABASE_TIMEOUT}s")
                if attempt < max_attempts:
                    await asyncio.sleep(1)
                else:
                    print(f"[{timestamp}] ERROR: Final flush failed for call_id {call_id} after {max_attempts} attempts. Call ID: {call_id}")
            except Exception as e:
                timestamp = datetime.utcnow().isoformat()
                print(f"[{timestamp}] Attempt {attempt}/{max_attempts} failed to flush session {call_id}: {e}")
                if attempt < max_attempts:
                    await asyncio.sleep(1) 
                else:
                    print(f"[{timestamp}] ERROR: Final flush failed for call_id {call_id} after {max_attempts} attempts. Call ID: {call_id}")
        
        return False

    async def finalize_call(self, call_id: str):
        """End-of-call logic: Flush to DB then clean up Redis guaranteed (async)."""
        success = await self.flush_to_supabase(call_id)
        
        if success:
            key = f"call_session:{call_id}"
            hist_key = f"history:{call_id}"
            if self.use_fallback:
                self._fallback_storage.pop(key, None)
                self._fallback_history.pop(hist_key, None)
                print(f"Cleared in-memory session for {call_id}.")
            else:
                deleted = await self.r.delete(key)
                await self.r.delete(hist_key)
                if deleted:
                    print(f"Deleted Redis session for {call_id} after finalization.")
                else:
                    print(f"Warning: Redis session for {call_id} not found during cleanup.")
        else:
            timestamp = datetime.utcnow().isoformat()
            print(f"[{timestamp}] ERROR: Supabase flush failed for call_id {call_id}. Redis session kept intact.")

memory = MemoryManager()
