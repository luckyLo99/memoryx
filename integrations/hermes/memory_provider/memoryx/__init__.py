from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
import os
import queue
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Iterable

from agent.memory_provider import MemoryProvider
from tools.registry import tool_error

logger = logging.getLogger(__name__)
_GLOBAL_PROVIDER = None


def _now_ms() -> int:
    return int(time.time() * 1000)


def _safe_json_loads(raw: Any, default: Any) -> Any:
    if raw is None:
        return default
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(str(raw))
    except Exception:
        return default


def _row_to_dict(row: Any) -> Dict[str, Any]:
    if row is None:
        return {}
    if isinstance(row, dict):
        return dict(row)
    try:
        return dict(row)
    except Exception:
        out: Dict[str, Any] = {}
        for key in ("id", "memory_id", "memory_type", "content", "importance_score", "confidence_score", "updated_at", "metadata_json", "tags_json"):
            try:
                out[key] = row[key]
            except Exception:
                pass
        return out


def _contains_cjk(text: str) -> bool:
    return any(
        "\u3400" <= ch <= "\u4dbf"
        or "\u4e00" <= ch <= "\u9fff"
        or "\uf900" <= ch <= "\ufaff"
        or "\u3040" <= ch <= "\u30ff"
        or "\uac00" <= ch <= "\ud7af"
        for ch in text
    )


class AsyncLoopRunner:
    def __init__(self, name: str = "memoryx-provider-loop") -> None:
        self._name = name
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._ready = threading.Event()
        self._closed = False
        self._lock = threading.Lock()

    @property
    def loop(self) -> Optional[asyncio.AbstractEventLoop]:
        return self._loop

    def start(self) -> None:
        with self._lock:
            if self._closed:
                raise RuntimeError("AsyncLoopRunner is closed")
            if self._loop is not None and self._thread is not None and self._thread.is_alive():
                return
            self._ready.clear()
            def runner() -> None:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                self._loop = loop
                self._ready.set()
                try:
                    loop.run_forever()
                finally:
                    pending = asyncio.all_tasks(loop)
                    for task in pending:
                        task.cancel()
                    if pending:
                        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                    loop.run_until_complete(loop.shutdown_asyncgens())
                    loop.close()
            self._thread = threading.Thread(target=runner, name=self._name, daemon=True)
            self._thread.start()
        if not self._ready.wait(timeout=5):
            raise RuntimeError("MemoryX background event loop did not start")

    def run(self, coro, timeout: Optional[float] = None):
        self.start()
        if self._loop is None:
            raise RuntimeError("MemoryX background event loop is unavailable")
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)

    def stop(self, timeout: float = 5.0) -> None:
        with self._lock:
            self._closed = True
            loop = self._loop
            thread = self._thread
            self._loop = None
            self._thread = None
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(loop.stop)
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)


class MemoryXProvider(MemoryProvider):
    @property
    def name(self) -> str:
        return "memoryx"

    def __init__(self) -> None:
        self._initialized = False
        self._session_id = "default"
        self._hermes_home: Optional[Path] = None
        self._data_dir: Optional[Path] = None
        self._db_path: Optional[Path] = None
        self._repo = None
        self._repo_lock = None
        self._runner = AsyncLoopRunner()
        self._sync_queue: "queue.Queue[Dict[str, Any]]" = queue.Queue(
            maxsize=int(os.environ.get("MEMORYX_SYNC_QUEUE_MAX", "1000"))
        )
        self._sync_stop = threading.Event()
        self._sync_worker: Optional[threading.Thread] = None

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
            try:
                from hermes_constants import get_hermes_home
                hermes_home = str(get_hermes_home())
            except Exception:
                hermes_home = str(Path.home() / ".hermes")
        self._hermes_home = Path(hermes_home).expanduser()
        self._data_dir = Path(
            os.environ.get("MEMORYX_HOME", str(self._hermes_home / "memoryx"))
        ).expanduser()
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = self._data_dir / "memoryx.db"
        os.environ.setdefault("MEMORYX_HOME", str(self._data_dir))
        os.environ.setdefault("MEMORYX_AUTHORITATIVE", "1")
        os.environ.setdefault("MEMORYX_AUTO_SYNC_TURNS", "0")
        os.environ.setdefault("MEMORYX_ENTRY_MAX_CHARS", "500")
        os.environ.setdefault("MEMORYX_SYSTEM_PROMPT_MAX_CHARS", "5000")
        self._runner.start()
        self._runner.run(self._ensure_repo_async(), timeout=10)
        self._start_sync_worker()
        self._initialized = True
        logger.info(
            "MemoryX provider initialized session_id=%s db=%s auto_sync=%s",
            self._session_id,
            self._db_path,
            os.environ.get("MEMORYX_AUTO_SYNC_TURNS"),
        )

    def _ensure_initialized(self) -> None:
        if not self._initialized:
            self.initialize("memoryx-default")

    async def _ensure_repo_async(self):
        self._ensure_initialized_light()
        if self._repo is not None:
            return self._repo
        if self._repo_lock is None:
            self._repo_lock = asyncio.Lock()
        async with self._repo_lock:
            if self._repo is not None:
                return self._repo
            from memoryx.storage import MemoryRepository
            repo = MemoryRepository(self._db_path)
            await repo.open()
            self._repo = repo
            return self._repo

    def _ensure_initialized_light(self) -> None:
        if self._data_dir is None or self._db_path is None:
            hermes_home = Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))).expanduser()
            self._hermes_home = hermes_home
            self._data_dir = Path(os.environ.get("MEMORYX_HOME", str(hermes_home / "memoryx"))).expanduser()
            self._data_dir.mkdir(parents=True, exist_ok=True)
            self._db_path = self._data_dir / "memoryx.db"

    def _run(self, coro, timeout: Optional[float] = None):
        self._ensure_initialized()
        return self._runner.run(coro, timeout=timeout)

    def _index_path(self) -> Path:
        self._ensure_initialized()
        assert self._data_dir is not None
        return self._data_dir / "provider_index.json"

    def _load_index(self) -> List[Dict[str, Any]]:
        path = self._index_path()
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception as exc:
            logger.warning("MemoryX index load failed session_id=%s path=%s error=%s", self._session_id, path, exc)
            return []

    def _save_index(self, rows: List[Dict[str, Any]]) -> None:
        path = self._index_path()
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    def _normalize_content(self, content: str) -> str:
        text = (content or "").strip()
        max_chars = int(os.environ.get("MEMORYX_ENTRY_MAX_CHARS", "500"))
        if max_chars > 0 and len(text) > max_chars:
            text = text[: max_chars - 1].rstrip() + "\u2026"
        return text

    def _metadata(self, *, target: str, source: str, memory_type: str, extra: Optional[Dict[str, Any]] = None) -> str:
        meta = {
            "provider": "hermes-memoryx",
            "session_id": self._session_id,
            "target": target,
            "source": source,
            "memory_type": memory_type,
            "confidence": 0.90,
            "importance_score": 0.85,
            "candidate_state": "committed",
            "created_by": "MemoryXProvider",
        }
        if extra:
            meta.update(extra)
        return json.dumps(meta, ensure_ascii=False)

    def _tags(self, *, target: str, source: str, memory_type: str) -> str:
        return json.dumps(
            ["hermes", target, source, memory_type, f"session:{self._session_id}"],
            ensure_ascii=False,
        )

    async def _store_async(
        self,
        target: str,
        content: str,
        source: str,
        memory_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        from memoryx.storage import MemoryRecord
        repo = await self._ensure_repo_async()
        text = self._normalize_content(content)
        if not text:
            raise ValueError("content is empty")
        mid = memory_id or f"hermes_{target}_{uuid.uuid4().hex}"
        memory_type = "PERSONA" if target == "user" else "FACT"
        record = MemoryRecord(
            id=mid,
            session_id=self._session_id,
            memory_type=memory_type,
            content=text,
            importance_score=float((metadata or {}).get("importance_score", 0.85)),
            confidence_score=float((metadata or {}).get("confidence_score", 0.90)),
            metadata_json=self._metadata(
                target=target,
                source=source,
                memory_type=memory_type,
                extra=metadata,
            ),
            scope=str((metadata or {}).get("scope", "hermes")),
            tags_json=self._tags(target=target, source=source, memory_type=memory_type),
        )
        return await repo.store_memory(record)

    async def _replace_async(self, memory_id: str, target: str, content: str) -> str:
        return await self._store_async(
            target=target,
            content=content,
            source="memory-tool-replace",
            memory_id=memory_id,
            metadata={"replaced_at_ms": _now_ms()},
        )

    async def _remove_async(self, memory_id: str) -> None:
        repo = await self._ensure_repo_async()
        if hasattr(repo, "rollback_memory"):
            await repo.rollback_memory(memory_id)
            return
        await repo.db.execute(
            "UPDATE memories SET active_state='archived', updated_at=CURRENT_TIMESTAMP WHERE id=?;",
            (memory_id,),
        )

    async def _like_search_async(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        repo = await self._ensure_repo_async()
        if not hasattr(repo, "db"):
            return []
        rows = await repo.db.fetchall(
            "SELECT id AS memory_id, id, memory_type, content, importance_score, confidence_score, "
            "updated_at, metadata_json, tags_json "
            "FROM memories "
            "WHERE active_state='active' AND content LIKE ? "
            "ORDER BY importance_score DESC, updated_at DESC "
            "LIMIT ?;",
            (f"%{query}%", int(limit)),
        )
        return [_row_to_dict(row) for row in rows]

    async def _search_async(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        repo = await self._ensure_repo_async()
        rows: List[Dict[str, Any]] = []
        try:
            raw = await repo.search_full_text(query, limit=limit)
            rows = [_row_to_dict(row) for row in (raw or [])]
        except Exception as exc:
            logger.warning("MemoryX FTS search failed session_id=%s query=%r error=%s", self._session_id, query, exc)
            rows = []
        if not rows and query and _contains_cjk(query):
            logger.debug("MemoryX CJK LIKE fallback session_id=%s query=%r", self._session_id, query)
            rows = await self._like_search_async(query, limit=limit)
        out: List[Dict[str, Any]] = []
        for row in rows or []:
            meta = _safe_json_loads(row.get("metadata_json"), {})
            out.append(
                {
                    "id": row.get("id") or row.get("memory_id"),
                    "memory_id": row.get("memory_id") or row.get("id"),
                    "memory_type": row.get("memory_type"),
                    "content": row.get("content", ""),
                    "importance_score": row.get("importance_score"),
                    "confidence_score": row.get("confidence_score"),
                    "updated_at": row.get("updated_at"),
                    "metadata": meta,
                }
            )
        return out

    async def _list_async(self, limit: int = 20) -> List[Dict[str, Any]]:
        repo = await self._ensure_repo_async()
        rows = await repo.list_active_memories(limit=limit)
        out: List[Dict[str, Any]] = []
        for row in rows or []:
            item = _row_to_dict(row)
            meta = _safe_json_loads(item.get("metadata_json"), {})
            out.append(
                {
                    "id": item.get("id") or item.get("memory_id"),
                    "memory_id": item.get("memory_id") or item.get("id"),
                    "memory_type": item.get("memory_type"),
                    "content": item.get("content", ""),
                    "importance_score": item.get("importance_score"),
                    "confidence_score": item.get("confidence_score"),
                    "updated_at": item.get("updated_at"),
                    "metadata": meta,
                }
            )
        return out

    async def _find_by_old_text_async(self, target: str, old_text: str, limit: int = 10) -> List[Dict[str, Any]]:
        repo = await self._ensure_repo_async()
        memory_type = "PERSONA" if target == "user" else "FACT"
        rows = await repo.db.fetchall(
            "SELECT id AS memory_id, id, memory_type, content, importance_score, confidence_score, "
            "updated_at, metadata_json, tags_json "
            "FROM memories "
            "WHERE active_state='active' AND memory_type=? AND content LIKE ? "
            "ORDER BY updated_at DESC "
            "LIMIT ?;",
            (memory_type, f"%{old_text}%", int(limit)),
        )
        return [_row_to_dict(row) for row in rows]

    def _start_sync_worker(self) -> None:
        if self._sync_worker is not None and self._sync_worker.is_alive():
            return
        def worker() -> None:
            while not self._sync_stop.is_set():
                try:
                    item = self._sync_queue.get(timeout=0.5)
                except queue.Empty:
                    continue
                try:
                    self._run(
                        self._store_async(
                            item["target"],
                            item["content"],
                            item["source"],
                            metadata=item.get("metadata"),
                        ),
                        timeout=30,
                    )
                except Exception as exc:
                    logger.warning("MemoryX sync worker failed session_id=%s error=%s", self._session_id, exc)
                finally:
                    self._sync_queue.task_done()
        self._sync_worker = threading.Thread(target=worker, name="memoryx-sync-worker", daemon=True)
        self._sync_worker.start()

    def system_prompt_block(self) -> str:
        try:
            rows = self._run(self._list_async(limit=300), timeout=10)
        except Exception as exc:
            logger.warning("MemoryX system_prompt_block fetch failed session_id=%s error=%s", self._session_id, exc)
            return ""
        if not rows:
            return ""
        facts: List[str] = []
        personas: List[str] = []
        for row in rows:
            content = (row.get("content") or "").strip()
            if not content:
                continue
            mtype = row.get("memory_type", "FACT")
            if mtype == "PERSONA":
                personas.append(content)
            else:
                facts.append(content)
        separator = "\u2550" * 46
        blocks: List[str] = []
        if facts:
            header = f"MEMORY (your personal notes) [MemoryX \u2014 {len(facts)} entries]"
            blocks.append(f"{separator}\n{header}\n{separator}\n" + "\n\u00a7\n".join(facts))
        if personas:
            header = f"USER PROFILE (who the user is) [MemoryX \u2014 {len(personas)} entries]"
            blocks.append(f"{separator}\n{header}\n{separator}\n" + "\n\u00a7\n".join(personas))
        rendered = "\n\n".join(blocks)
        max_chars = int(os.environ.get("MEMORYX_SYSTEM_PROMPT_MAX_CHARS", "5000"))
        if max_chars > 0 and len(rendered) > max_chars:
            rendered = rendered[: max_chars - 1].rstrip() + "\u2026"
        return rendered

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        if not query:
            return ""
        try:
            hits = self._run(
                self._search_async(query=query, limit=int(os.environ.get("MEMORYX_PREFETCH_LIMIT", "5"))),
                timeout=10,
            )
        except Exception as exc:
            logger.warning("MemoryX prefetch failed session_id=%s query=%r error=%s", self._session_id, query, exc)
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

    def sync_turn(self, user_content: str, assistant_content: str, *, session_id: str = "", messages: Optional[List[Dict[str, Any]]] = None) -> None:
        if os.environ.get("MEMORYX_AUTO_SYNC_TURNS", "0").strip() != "1":
            return None
        content = f"User: {user_content}\nAssistant: {assistant_content}"
        item = {
            "target": "memory",
            "content": content,
            "source": "sync_turn",
            "metadata": {
                "session_id": session_id or self._session_id,
                "memory_layer": "session",
                "source": "sync_turn",
            },
        }
        try:
            self._sync_queue.put_nowait(item)
        except queue.Full:
            logger.warning("MemoryX sync queue full; dropping sync_turn session_id=%s", self._session_id)
        return None

    def _success(self, **payload: Any) -> str:
        data = {"success": True, "provider": "memoryx"}
        data.update(payload)
        return json.dumps(data, ensure_ascii=False)

    def _error(self, message: str) -> str:
        return tool_error(message, success=False)

    def memory_tool(self, args: Dict[str, Any]) -> str:
        self._ensure_initialized()
        action = args.get("action", "")
        target = args.get("target", "memory")
        content = args.get("content")
        old_text = args.get("old_text")
        if target not in {"memory", "user"}:
            return self._error("Invalid target. Use 'memory' or 'user'.")
        rows = self._load_index()
        if action == "add":
            if not content:
                return self._error("content is required for add.")
            try:
                memory_id = self._run(
                    self._store_async(target, content, "memory-tool-add", metadata=args.get("metadata") if isinstance(args.get("metadata"), dict) else None),
                    timeout=15,
                )
            except Exception as exc:
                return self._error(f"MemoryX add failed: {exc}")
            normalized = self._normalize_content(content)
            rows.append({"id": memory_id, "target": target, "content": normalized})
            self._save_index(rows)
            return self._success(action="add", target=target, id=memory_id)
        if action in {"replace", "remove"}:
            if not old_text:
                return self._error(f"old_text is required for {action}.")
            matches = [row for row in rows if row.get("target") == target and old_text in row.get("content", "")]
            if not matches:
                try:
                    db_matches = self._run(self._find_by_old_text_async(target, old_text, limit=10), timeout=10)
                except Exception:
                    db_matches = []
                matches = [{"id": m.get("id") or m.get("memory_id"), "target": target, "content": m.get("content", "")} for m in db_matches]
            if not matches:
                return self._error("No MemoryX entry matched old_text.")
            if len(matches) > 1:
                previews = [m.get("content", "")[:120] for m in matches[:5]]
                return json.dumps({"success": False, "provider": "memoryx", "error": "old_text matched multiple MemoryX entries. Use a more unique substring.", "matches": previews}, ensure_ascii=False)
            row = matches[0]
            memory_id = row["id"]
            if action == "replace":
                if not content:
                    return self._error("content is required for replace.")
                try:
                    self._run(self._replace_async(memory_id, target, content), timeout=15)
                except Exception as exc:
                    return self._error(f"MemoryX replace failed: {exc}")
                normalized = self._normalize_content(content)
                found = False
                for item in rows:
                    if item.get("id") == memory_id:
                        item["content"] = normalized
                        item["target"] = target
                        found = True
                if not found:
                    rows.append({"id": memory_id, "target": target, "content": normalized})
                self._save_index(rows)
                return self._success(action="replace", target=target, id=memory_id)
            try:
                self._run(self._remove_async(memory_id), timeout=15)
            except Exception as exc:
                return self._error(f"MemoryX remove failed: {exc}")
            rows = [item for item in rows if item.get("id") != memory_id]
            self._save_index(rows)
            return self._success(action="remove", target=target, id=memory_id)
        if action == "read":
            try:
                hits = self._run(self._list_async(limit=int(args.get("limit", 20))), timeout=10)
            except Exception as exc:
                return self._error(f"MemoryX read failed: {exc}")
            if target == "user":
                hits = [h for h in hits if h.get("memory_type") == "PERSONA"]
            elif target == "memory":
                hits = [h for h in hits if h.get("memory_type") != "PERSONA"]
            return self._success(action="read", target=target, results=hits)
        return self._error("Unknown action. Use add, replace, remove, or read.")

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return [
            {"name": "memoryx_search", "description": "Search MemoryX long-term memory.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer", "default": 5}}, "required": ["query"]}},
            {"name": "memoryx_store", "description": "Store durable information directly into MemoryX.", "parameters": {"type": "object", "properties": {"target": {"type": "string", "enum": ["memory", "user"], "default": "memory"}, "content": {"type": "string"}}, "required": ["content"]}},
        ]

    def handle_tool_call(self, tool_name: str, args: Dict[str, Any], **kwargs) -> str:
        if tool_name == "memoryx_search":
            query = args.get("query", "")
            limit = int(args.get("limit", 5))
            try:
                hits = self._run(self._search_async(query=query, limit=limit), timeout=10)
            except Exception as exc:
                return self._error(f"MemoryX search failed: {exc}")
            return self._success(results=hits)
        if tool_name == "memoryx_store":
            return self.memory_tool({"action": "add", "target": args.get("target", "memory"), "content": args.get("content")})
        return self._error(f"Unknown MemoryX tool: {tool_name}")

    def on_memory_write(self, action: str, target: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        if os.environ.get("MEMORYX_AUTHORITATIVE", "1").strip() == "1":
            return None
        self.memory_tool({"action": action, "target": target, "content": content, "old_text": (metadata or {}).get("old_text"), "metadata": metadata or {}})

    def shutdown(self) -> None:
        self._sync_stop.set()
        if self._sync_worker is not None and self._sync_worker.is_alive():
            self._sync_worker.join(timeout=2)
        try:
            if self._repo is not None:
                self._runner.run(self._repo.close(), timeout=5)
                self._repo = None
        except Exception as exc:
            logger.warning("MemoryX repo close failed session_id=%s error=%s", self._session_id, exc)
        self._runner.stop()
        self._initialized = False


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
