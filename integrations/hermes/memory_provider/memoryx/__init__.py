from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent.memory_provider import MemoryProvider
from tools.registry import tool_error

logger = logging.getLogger(__name__)
_GLOBAL_PROVIDER = None


def _run_async(coro):
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None

    if running and running.is_running():
        box = {}

        def runner():
            loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(loop)
                box["value"] = loop.run_until_complete(coro)
            except BaseException as exc:
                box["error"] = exc
            finally:
                loop.close()

        t = threading.Thread(target=runner, daemon=True)
        t.start()
        t.join()

        if "error" in box:
            raise box["error"]

        return box.get("value")

    return asyncio.run(coro)


class MemoryXProvider(MemoryProvider):
    @property
    def name(self) -> str:
        return "memoryx"

    def __init__(self):
        self._initialized = False
        self._session_id = "default"
        self._hermes_home = None
        self._data_dir = None
        self._db_path = None

    def is_available(self) -> bool:
        try:
            from memoryx.storage import MemoryRepository, MemoryRecord  # noqa: F401
            return True
        except Exception as exc:
            logger.warning("MemoryX is not importable: %s", exc)
            return False

    def initialize(self, session_id: str, **kwargs) -> None:
        self._session_id = session_id or "default"

        hermes_home = kwargs.get("hermes_home") or os.environ.get("HERMES_HOME")
        if not hermes_home:
            from hermes_constants import get_hermes_home
            hermes_home = str(get_hermes_home())

        self._hermes_home = Path(hermes_home).expanduser()
        self._data_dir = Path(
            os.environ.get("MEMORYX_HOME", str(self._hermes_home / "memoryx"))
        ).expanduser()
        self._data_dir.mkdir(parents=True, exist_ok=True)

        self._db_path = self._data_dir / "memoryx.db"

        os.environ.setdefault("MEMORYX_HOME", str(self._data_dir))
        os.environ.setdefault("MEMORYX_AUTHORITATIVE", "1")

        self._initialized = True

    def _ensure_initialized(self):
        if not self._initialized:
            self.initialize("memoryx-default")

    def _index_path(self) -> Path:
        self._ensure_initialized()
        return self._data_dir / "provider_index.json"

    def _load_index(self) -> List[Dict[str, Any]]:
        path = self._index_path()
        if not path.exists():
            return []

        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _save_index(self, rows: List[Dict[str, Any]]) -> None:
        path = self._index_path()
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    async def _with_repo(self):
        self._ensure_initialized()
        from memoryx.storage import MemoryRepository

        repo = MemoryRepository(self._db_path)
        await repo.open()
        return repo

    async def _store_async(self, target: str, content: str, source: str, memory_id: Optional[str] = None) -> str:
        self._ensure_initialized()
        from memoryx.storage import MemoryRecord

        repo = await self._with_repo()
        try:
            mid = memory_id or f"hermes_{target}_{uuid.uuid4().hex}"
            memory_type = "PERSONA" if target == "user" else "FACT"

            record = MemoryRecord(
                id=mid,
                session_id=self._session_id,
                memory_type=memory_type,
                content=content,
                importance_score=0.85,
                confidence_score=0.9,
                metadata_json=json.dumps(
                    {
                        "source": source,
                        "target": target,
                        "session_id": self._session_id,
                        "provider": "hermes-memoryx",
                    },
                    ensure_ascii=False,
                ),
                scope="hermes",
                tags_json=json.dumps(["hermes", target, source], ensure_ascii=False),
            )

            return await repo.store_memory(record)
        finally:
            await repo.close()

    async def _replace_async(self, memory_id: str, target: str, content: str) -> str:
        return await self._store_async(
            target=target,
            content=content,
            source="memory-tool-replace",
            memory_id=memory_id,
        )

    async def _remove_async(self, memory_id: str) -> None:
        repo = await self._with_repo()
        try:
            if hasattr(repo, "rollback_memory"):
                await repo.rollback_memory(memory_id)
            else:
                await repo.db.execute(
                    "UPDATE memories SET active_state='archived' WHERE id=?;",
                    (memory_id,),
                )
        finally:
            await repo.close()

    async def _search_async(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        repo = await self._with_repo()
        try:
            rows = await repo.search_full_text(query, limit=limit)
            out = []

            for row in rows or []:
                out.append(
                    {
                        "id": row.get("id") or row.get("memory_id"),
                        "memory_type": row.get("memory_type"),
                        "content": row.get("content", ""),
                        "importance_score": row.get("importance_score"),
                        "updated_at": row.get("updated_at"),
                    }
                )

            return out
        finally:
            await repo.close()

    async def _list_async(self, limit: int = 20) -> List[Dict[str, Any]]:
        repo = await self._with_repo()
        try:
            rows = await repo.list_active_memories(limit=limit)
            return [
                {
                    "id": row.get("id") or row.get("memory_id"),
                    "memory_type": row.get("memory_type"),
                    "content": row.get("content", ""),
                    "importance_score": row.get("importance_score"),
                    "updated_at": row.get("updated_at"),
                }
                for row in rows
            ]
        finally:
            await repo.close()

    def system_prompt_block(self) -> str:
        return (
            "MemoryX is active as the external memory provider. "
            "Durable user/profile facts and agent notes are stored in MemoryX."
        )

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        if not query:
            return ""

        try:
            hits = _run_async(self._search_async(query=query, limit=5))
        except Exception as exc:
            logger.warning("MemoryX prefetch failed: %s", exc)
            return ""

        if not hits:
            return ""

        lines = ["[MemoryX recall]"]
        for hit in hits:
            content = hit.get("content") or ""
            if content:
                lines.append(f"- {content}")

        return "\n".join(lines)

    def queue_prefetch(self, query: str, *, session_id: str = "") -> None:
        return None

    def sync_turn(
        self,
        user_content: str,
        assistant_content: str,
        *,
        session_id: str = "",
        messages: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        if os.environ.get("MEMORYX_AUTO_SYNC_TURNS", "1").strip() != "1":
            return None

        content = f"User: {user_content}\nAssistant: {assistant_content}"

        def worker():
            try:
                _run_async(self._store_async("memory", content, "sync_turn"))
            except Exception as exc:
                logger.warning("MemoryX sync_turn failed: %s", exc)

        threading.Thread(target=worker, daemon=True).start()

    def memory_tool(self, args: Dict[str, Any]) -> str:
        self._ensure_initialized()

        action = args.get("action", "")
        target = args.get("target", "memory")
        content = args.get("content")
        old_text = args.get("old_text")

        if target not in {"memory", "user"}:
            return tool_error("Invalid target. Use 'memory' or 'user'.", success=False)

        rows = self._load_index()

        if action == "add":
            if not content:
                return tool_error("content is required for add.", success=False)

            try:
                memory_id = _run_async(self._store_async(target, content, "memory-tool-add"))
            except Exception as exc:
                return tool_error(f"MemoryX add failed: {exc}", success=False)

            rows.append(
                {
                    "id": memory_id,
                    "target": target,
                    "content": content,
                }
            )
            self._save_index(rows)

            return json.dumps(
                {
                    "success": True,
                    "provider": "memoryx",
                    "action": "add",
                    "target": target,
                    "id": memory_id,
                },
                ensure_ascii=False,
            )

        if action in {"replace", "remove"}:
            if not old_text:
                return tool_error(f"old_text is required for {action}.", success=False)

            matches = [
                row
                for row in rows
                if row.get("target") == target and old_text in row.get("content", "")
            ]

            if not matches:
                return tool_error("No MemoryX entry matched old_text.", success=False)

            if len(matches) > 1:
                previews = [m.get("content", "")[:120] for m in matches[:5]]
                return json.dumps(
                    {
                        "success": False,
                        "error": "old_text matched multiple MemoryX entries. Use a more unique substring.",
                        "matches": previews,
                    },
                    ensure_ascii=False,
                )

            row = matches[0]
            memory_id = row["id"]

            if action == "replace":
                if not content:
                    return tool_error("content is required for replace.", success=False)

                try:
                    _run_async(self._replace_async(memory_id, target, content))
                except Exception as exc:
                    return tool_error(f"MemoryX replace failed: {exc}", success=False)

                for item in rows:
                    if item.get("id") == memory_id:
                        item["content"] = content

                self._save_index(rows)

                return json.dumps(
                    {
                        "success": True,
                        "provider": "memoryx",
                        "action": "replace",
                        "target": target,
                        "id": memory_id,
                    },
                    ensure_ascii=False,
                )

            try:
                _run_async(self._remove_async(memory_id))
            except Exception as exc:
                return tool_error(f"MemoryX remove failed: {exc}", success=False)

            rows = [item for item in rows if item.get("id") != memory_id]
            self._save_index(rows)

            return json.dumps(
                {
                    "success": True,
                    "provider": "memoryx",
                    "action": "remove",
                    "target": target,
                    "id": memory_id,
                },
                ensure_ascii=False,
            )

        if action == "read":
            try:
                hits = _run_async(self._list_async(limit=20))
            except Exception as exc:
                return tool_error(f"MemoryX read failed: {exc}", success=False)

            return json.dumps(
                {
                    "success": True,
                    "provider": "memoryx",
                    "action": "read",
                    "target": target,
                    "results": hits,
                },
                ensure_ascii=False,
            )

        return tool_error("Unknown action. Use add, replace, remove, or read.", success=False)

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "memoryx_search",
                "description": "Search MemoryX long-term memory.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "limit": {"type": "integer", "default": 5},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "memoryx_store",
                "description": "Store durable information directly into MemoryX.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target": {
                            "type": "string",
                            "enum": ["memory", "user"],
                            "default": "memory",
                        },
                        "content": {"type": "string"},
                    },
                    "required": ["content"],
                },
            },
        ]

    def handle_tool_call(self, tool_name: str, args: Dict[str, Any], **kwargs) -> str:
        if tool_name == "memoryx_search":
            query = args.get("query", "")
            limit = int(args.get("limit", 5))

            try:
                hits = _run_async(self._search_async(query=query, limit=limit))
            except Exception as exc:
                return tool_error(f"MemoryX search failed: {exc}", success=False)

            return json.dumps(
                {
                    "success": True,
                    "provider": "memoryx",
                    "results": hits,
                },
                ensure_ascii=False,
            )

        if tool_name == "memoryx_store":
            return self.memory_tool(
                {
                    "action": "add",
                    "target": args.get("target", "memory"),
                    "content": args.get("content"),
                }
            )

        return tool_error(f"Unknown MemoryX tool: {tool_name}", success=False)

    def on_memory_write(
        self,
        action: str,
        target: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        if os.environ.get("MEMORYX_AUTHORITATIVE", "1").strip() == "1":
            return None

        self.memory_tool(
            {
                "action": action,
                "target": target,
                "content": content,
                "old_text": (metadata or {}).get("old_text"),
            }
        )

    def shutdown(self) -> None:
        return None


def _global_provider() -> MemoryXProvider:
    global _GLOBAL_PROVIDER

    if _GLOBAL_PROVIDER is None:
        _GLOBAL_PROVIDER = MemoryXProvider()
        _GLOBAL_PROVIDER.initialize("memoryx-tool")

    return _GLOBAL_PROVIDER


def memoryx_tool_handler(args: Dict[str, Any], **kwargs) -> str:
    return _global_provider().memory_tool(args)


def register(ctx) -> None:
    ctx.register_memory_provider(MemoryXProvider())
