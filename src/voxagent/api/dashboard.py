"""
api/dashboard.py
-----------------
Dashboard read-only endpoints:
  GET /dashboard/stats   – aggregate statistics (total calls, today, avg duration, active)
  GET /dashboard/calls   – paginated recent call records

All data read from Supabase only.
Active call count is sourced via a runtime shim injected at app startup (see server.py).
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from fastapi import APIRouter

from memory import memory

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

# ── runtime shim ─────────────────────────────────────────────────────────────
# server.py injects a callable that returns the live active-room count so this
# module never needs to import the asyncio Task dict directly.
_get_active_count: Callable[[], int] = lambda: 0


def set_active_room_counter(fn: Callable[[], int]) -> None:
    """Called once at startup by server.py to wire up the live room counter."""
    global _get_active_count
    _get_active_count = fn


# ── routes ───────────────────────────────────────────────────────────────────

@router.get("/stats")
async def get_dashboard_stats():
    """
    Return aggregate call statistics.
    Reads from Supabase `calls` table.  Falls back to zeros if Supabase is unavailable.
    """
    print("[DASHBOARD] stats requested")
    active_calls = _get_active_count()

    try:
        if not memory.supabase:
            return {
                "total_calls": 0,
                "calls_today": 0,
                "average_call_duration": 0,
                "active_calls": active_calls,
            }

        today_str = datetime.utcnow().date().isoformat()

        # total calls
        total_res = (
            await memory.supabase.table("calls").select("call_id", count="exact").execute()
        )
        total_calls = (
            total_res.count if total_res.count is not None else len(total_res.data or [])
        )

        # calls today
        today_res = (
            await memory.supabase.table("calls")
            .select("call_id", count="exact")
            .gte("timestamp", today_str)
            .execute()
        )
        calls_today = (
            today_res.count if today_res.count is not None else len(today_res.data or [])
        )

        # average duration
        dur_res = await memory.supabase.table("calls").select("duration").execute()
        durations: list[float] = []
        for row in dur_res.data or []:
            try:
                durations.append(float(row["duration"]))
            except (ValueError, TypeError, KeyError):
                pass
        avg_duration = sum(durations) / len(durations) if durations else 0

        return {
            "total_calls": total_calls,
            "calls_today": calls_today,
            "average_call_duration": round(avg_duration, 2),
            "active_calls": active_calls,
        }

    except Exception as exc:
        print(f"[DASHBOARD] Error fetching stats: {exc}")
        return {
            "total_calls": 0,
            "calls_today": 0,
            "average_call_duration": 0,
            "active_calls": active_calls,
        }


@router.get("/calls")
async def get_dashboard_calls(page: int = 1, limit: int = 50):
    """
    Return recent call records with pagination (?page=1&limit=50).
    Reads from Supabase `calls` table only.
    """
    print(f"[DASHBOARD] calls requested (page={page}, limit={limit})")
    try:
        if not memory.supabase:
            return []

        limit = max(1, min(limit, 200))
        page = max(1, page)
        offset = (page - 1) * limit

        try:
            res = (
                await memory.supabase
                .table("calls")
                .select("call_id, call_status, duration, timestamp")
                .order("timestamp", desc=True)
                .range(offset, offset + limit - 1)
                .execute()
            )
        except Exception:
            # Fallback: no ordering, no pagination
            res = await memory.supabase.table("calls").select(
                "call_id, call_status, duration, timestamp"
            ).limit(limit).execute()

        return [
            {
                "call_id": c.get("call_id", ""),
                "status": c.get("call_status", "completed"),
                "duration": c.get("duration", 0),
                "created_at": c.get("timestamp", ""),
            }
            for c in (res.data or [])
        ]

    except Exception as exc:
        print(f"[DASHBOARD] Error fetching calls: {exc}")
        return []
