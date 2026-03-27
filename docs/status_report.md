# Status Report: Remove Invalid `max_idle_connections` Parameter

## Problem
`MemoryManager.__init__` in `memory.py` was passing `max_idle_connections` to the Redis client via `redis_kwargs`. This parameter does not exist in the installed version of the `redis` library, causing a `TypeError` at startup.

## Fix Applied
Removed the single offending line from `redis_kwargs`:

```diff
 redis_kwargs = {
     "decode_responses": True,
     "socket_connect_timeout": REDIS_TIMEOUT,
     "socket_timeout": REDIS_TIMEOUT,
     "retry": retry_policy,
     "retry_on_timeout": True,
     "max_connections": REDIS_MAX_CONNECTIONS,
-    "max_idle_connections": REDIS_MAX_IDLE,
     "health_check_interval": 60,
 }
```

No other changes were made.

## Verification
- **Syntax check** (`ast.parse`): ✅ Passed

## Status: ✅ FIXED
