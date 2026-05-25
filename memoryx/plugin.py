from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from typing import Any

from memoryx.events import MemoryEventType
from memoryx.manager import MemoryHookManager


MEMORYX_DB = os.getenv("MEMORYX_DB_PATH", "/home/lucky/memoryx/data/memoryx.db")


def _ensure_session(session_id: str) -> None:
    """确保会话存在，不存在则创建"""
    try:
        conn = sqlite3.connect(MEMORYX_DB)
        exists = conn.execute(
            "SELECT 1 FROM sessions WHERE session_id=?", (session_id,)
        ).fetchone()
        if not exists:
            now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
            conn.execute(
                "INSERT OR IGNORE INTO sessions(session_id, title, start_time, status, created_at, updated_at) "
                "VALUES (?, ?, ?, 'active', ?, ?)",
                (session_id, f"Session {session_id[:16]}", now, now, now),
            )
            conn.commit()
        conn.close()
    except Exception:
        pass  # 不要阻断 Hermes 主流程


def _close_session(session_id: str) -> None:
    """关闭会话并记录结束时间"""
    try:
        conn = sqlite3.connect(MEMORYX_DB)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        conn.execute(
            "UPDATE sessions SET status='closed', end_time=?, updated_at=? WHERE session_id=?",
            (now, now, session_id),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


try:
    from memoryx.hermes_bridge import HermesMemoryBridge
except Exception:  # pragma: no cover
    HermesMemoryBridge = None  # type: ignore[assignment]


def register(ctx: Any) -> None:
    """Register MemoryX Hermes hooks.

    This keeps the existing async event pipeline while adding optional bridge
    returns for Hermes runtimes that can consume context/guard results.
    """
    settings = getattr(ctx, "memoryx_settings", None)
    logger = getattr(ctx, "logger", None)
    manager = MemoryHookManager(settings=settings, logger=logger)
    ctx.memoryx_manager = manager

    bridge = getattr(ctx, "memoryx_bridge", None)

    async def _emit(event_type: MemoryEventType, session_id: str, payload: dict[str, Any]) -> None:
        await manager.emit(event_type, session_id, payload)

    async def on_user_message(session_id: str, content: str = "", **extra: Any):
        # 确保会话被追踪
        _ensure_session(session_id)
        await _emit(MemoryEventType.ON_USER_MESSAGE, session_id, {"content": content, **extra})
        if bridge is not None and hasattr(bridge, "on_user_message"):
            return await bridge.on_user_message(session_id=session_id, content=content, **extra)
        return None

    async def on_assistant_response(session_id: str, content: str = "", **extra: Any):
        await _emit(MemoryEventType.ON_ASSISTANT_RESPONSE, session_id, {"content": content, **extra})
        if bridge is not None and hasattr(bridge, "on_assistant_response"):
            return await bridge.on_assistant_response(session_id=session_id, content=content, **extra)
        return None

    async def on_tool_call(session_id: str, tool_name: str = "", args: dict | None = None, **extra: Any):
        payload = {"tool_name": tool_name, "args": args or {}, **extra}
        await _emit(MemoryEventType.ON_TOOL_CALL, session_id, payload)
        if bridge is not None and hasattr(bridge, "on_tool_call"):
            return await bridge.on_tool_call(session_id=session_id, tool_name=tool_name, args=args or {}, **extra)
        return None

    async def on_tool_result(session_id: str, tool_name: str = "", result: dict | str | None = None, **extra: Any):
        payload = {"tool_name": tool_name, "result": result, **extra}
        await _emit(MemoryEventType.ON_TOOL_RESULT, session_id, payload)
        if bridge is not None and hasattr(bridge, "on_tool_result"):
            return await bridge.on_tool_result(session_id=session_id, tool_name=tool_name, result=result, **extra)
        return None

    async def on_session_end(session_id: str, **extra: Any):
        # 关闭会话
        _close_session(session_id)
        await _emit(MemoryEventType.ON_SESSION_END, session_id, extra)
        if bridge is not None and hasattr(bridge, "on_session_end"):
            return await bridge.on_session_end(session_id=session_id, **extra)
        return None

    async def on_session_finalize():
        await manager.stop()

    # Hermes-like contexts in tests expose register_hook; some expose dict hooks.
    if hasattr(ctx, "register_hook"):
        ctx.register_hook("on_user_message", on_user_message)
        ctx.register_hook("on_assistant_response", on_assistant_response)
        ctx.register_hook("on_tool_call", on_tool_call)
        ctx.register_hook("on_tool_result", on_tool_result)
        ctx.register_hook("on_session_end", on_session_end)
        ctx.register_hook("on_session_finalize", on_session_finalize)
    else:
        hooks = getattr(ctx, "hooks", None)
        if hooks is None:
            hooks = {}
            ctx.hooks = hooks
        hooks["on_user_message"] = on_user_message
        hooks["on_assistant_response"] = on_assistant_response
        hooks["on_tool_call"] = on_tool_call
        hooks["on_tool_result"] = on_tool_result
        hooks["on_session_end"] = on_session_end
        hooks["on_session_finalize"] = on_session_finalize

    if hasattr(ctx, "register_middleware"):
        ctx.register_middleware(manager.middleware)
    else:
        middlewares = getattr(ctx, "middlewares", None)
        if middlewares is None:
            middlewares = []
            ctx.middlewares = middlewares
        middlewares.append(manager.middleware)
