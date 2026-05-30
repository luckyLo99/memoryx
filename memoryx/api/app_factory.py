"""FastAPI app factory and lifespan wiring for MemoryX.

P12.1 replaces global-only REST state with an app-factory model while keeping a
backward-compatible module-level `app` in memoryx.api.rest_app.

Why this shape fits MemoryX + Hermes:
- MemoryRepository and MemoryQueryAPI are long-lived resources.
- Hermes plugin/runtime may inject pre-built repository/query objects.
- Lifespan guarantees open/close symmetry and avoids hidden global state.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from memoryx.api.auth import verify_api_key
from memoryx.api.errors import http_exception_handler, unhandled_exception_handler, validation_exception_handler
from memoryx.api.p11_routes import create_p11_router
from memoryx.api.p8_bootstrap import install_p8_observability
from memoryx.api.routes.learning import router as learning_router
from memoryx.api.routes.learning import distill_router
from memoryx.api.rate_limit import EmbeddingConcurrencyGate, SlidingWindowRateLimiter

# ── P14: Feishu UX Adapter ──
try:
    from memoryx.feishu import (
        FeishuClient,
        FeishuSQLiteQueue,
        FeishuCardRenderer,
        FeishuHermesBotService,
        FeishuTraceStore,
        create_feishu_router,
        build_feishu_runner,
    )
    FEISHU_AVAILABLE = True
except ImportError:
    FEISHU_AVAILABLE = False
from memoryx.api.rest_schemas import (
    ConsolidationRequest,
    FeedbackRequest,
    MemoryCreate,
    MemoryUpdate,
    SearchRequest,
    SelfEditApplyRequest,
    SelfEditPreviewRequest,
)
from memoryx.observability.metrics import CONTENT_TYPE_LATEST, metrics_response_bytes, record_rest_request


@dataclass(slots=True)
class MemoryXAppState:
    repository: Any | None = None
    query_api: Any | None = None
    self_editor: Any | None = None
    consolidation: Any | None = None
    lance_store: Any | None = None
    owns_repository: bool = False
    owns_query_api: bool = False
    owns_lance_store: bool = False


def _default_db_path() -> Path:
    """Determine REST DB path with priority:
    1. MEMORYX_DB_PATH env var (explicit)
    2. MEMORYX_HOME/memoryx.db (Hermes profile home)
    3. ./data/memoryx.db (fallback)
    """
    explicit = os.environ.get("MEMORYX_DB_PATH")
    if explicit:
        return Path(explicit)
    mhome = os.environ.get("MEMORYX_HOME")
    if mhome:
        return Path(mhome) / "memoryx.db"
    return Path("./data/memoryx.db")


def _default_lancedb_path() -> Path:
    return Path(os.getenv("LANCEDB_URI", "./data/lancedb"))


async def _build_default_state() -> MemoryXAppState:
    from memoryx.api import MemoryQueryAPI
    from memoryx.storage import MemoryRepository

    db_path = _default_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        repo = MemoryRepository(db_path)
        await repo.open()
    except Exception:
        repo = None
        return MemoryXAppState(
            repository=None, query_api=None, owns_repository=False, owns_query_api=False,
        )

    # P0: Optional LanceDB vector store — fallback if not installed
    lance_store = None
    try:
        from memoryx.embeddings import LanceDBVectorStore
        lancedb_path = _default_lancedb_path()
        lancedb_path.parent.mkdir(parents=True, exist_ok=True)
        lance_store = LanceDBVectorStore(uri=lancedb_path)
        await lance_store.open()
    except ImportError:
        pass
    except Exception:
        pass

    api = MemoryQueryAPI(repository=repo, vector_store=lance_store)
    return MemoryXAppState(
        repository=repo,
        query_api=api,
        lance_store=lance_store,
        owns_repository=True,
        owns_query_api=True,
        owns_lance_store=True,
    )


async def _close_state(state: MemoryXAppState) -> None:
    if state.owns_repository and state.repository is not None and hasattr(state.repository, "close"):
        await state.repository.close()


def create_app(
    *,
    repository: Any | None = None,
    query_api: Any | None = None,
    self_editor: Any | None = None,
    consolidation: Any | None = None,
    auto_open: bool = True,
) -> FastAPI:
    initial_state = MemoryXAppState(
        repository=repository,
        query_api=query_api,
        self_editor=self_editor,
        consolidation=consolidation,
        owns_repository=False,
        owns_query_api=False,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if auto_open and initial_state.repository is None:
            app.state.memoryx = await _build_default_state()
        else:
            app.state.memoryx = initial_state

        # ── P14: Initialize Feishu Bot Service ──
        feishu_task: asyncio.Task | None = None
        if FEISHU_AVAILABLE and os.getenv("FEISHU_APP_ID"):
            import logging
            _log = logging.getLogger("memoryx.feishu")
            try:
                feishu_client = FeishuClient()
                queue_db = os.getenv(
                    "FEISHU_QUEUE_DB",
                    str(Path(app.state.memoryx.repository.db.db_path).parent / "feishu_queue.db")
                )
                feishu_queue = FeishuSQLiteQueue(queue_db)
                feishu_renderer = FeishuCardRenderer()
                feishu_trace = FeishuTraceStore(queue_db)
                feishu_bot = FeishuHermesBotService(
                    client=feishu_client,
                    queue=feishu_queue,
                    renderer=feishu_renderer,
                    trace_store=feishu_trace,
                )

                # Build runner from FEISHU_RUNNER_MODE
                feishu_runner = build_feishu_runner()

                # Register feishu event routes (with card action support)
                app.include_router(create_feishu_router(
                    bot_service=feishu_bot,
                    queue_db_path=queue_db,
                    get_repository=lambda: app.state.memoryx.repository,
                    get_vector_store=lambda: app.state.memoryx.lance_store,
                ))

                # Background worker: polls feishu queue continuously
                async def _feishu_worker():
                    while True:
                        try:
                            await feishu_bot.run_worker_once(feishu_runner)
                        except Exception:
                            pass
                        await asyncio.sleep(1.0)

                feishu_task = asyncio.create_task(_feishu_worker(), name="feishu-worker")
                _log.info("Feishu bot service started")
            except Exception as exc:
                _log.warning("Feishu init skipped: %s", exc)

        try:
            yield
        finally:
            if feishu_task is not None:
                feishu_task.cancel()
                try:
                    await feishu_task
                except asyncio.CancelledError:
                    pass
            await _close_state(app.state.memoryx)

    app = FastAPI(title="MemoryX API", version="1.1.0", lifespan=lifespan)

    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    install_p8_observability(app)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    rate_limiter = SlidingWindowRateLimiter(max_requests=200, window_seconds=60.0)
    embedding_gate = EmbeddingConcurrencyGate(max_concurrent=4)

    def state() -> MemoryXAppState:
        if not hasattr(app.state, "memoryx"):
            app.state.memoryx = initial_state
        return app.state.memoryx

    async def ensure_repo():
        repo = state().repository
        if repo is None:
            raise HTTPException(503, "repository not configured")
        return repo

    async def ensure_api():
        api = state().query_api
        if api is None:
            raise HTTPException(503, "query api not configured")
        return api

    async def get_retrieval_engine():
        api = state().query_api
        return getattr(api, "retrieval_engine", None) if api is not None else None

    async def get_lesson_policy():
        engine = await get_retrieval_engine()
        return getattr(engine, "lesson_policy", None) if engine is not None else None

    @app.get("/live")
    async def live() -> dict:
        return {"status": "ok", "live": True, "version": "1.1.0"}

    @app.get("/ready")
    async def ready(_key: str | None = Depends(verify_api_key)) -> dict:
        """Enhanced readiness endpoint with DB path and memory statistics.

        This enables operators to confirm REST is connected to the same
        database as the Hermes runtime.  Returns degraded status when DB
        is unreachable rather than crashing.
        """
        import os as _os

        repo: Any = None
        try:
            repo = await ensure_repo()
        except HTTPException:
            return {
                "status": "degraded", "ready": False,
                "source": "rest",
                "warning": "repository not configured",
                "db": {"path": str(_default_db_path()), "exists": _default_db_path().exists()},
                "env": {"cwd": _os.getcwd(), "memoryx_home": _os.environ.get("MEMORYX_HOME", "")},
            }

        checks: dict[str, bool] = {}
        try:
            row = await repo.db.fetchone("SELECT 1 AS ok;", ())
            checks["db"] = bool(row and int(row["ok"]) == 1)
        except Exception:
            checks["db"] = False

        try:
            tables = await repo.db.fetchall("SELECT name FROM sqlite_master WHERE type IN ('table', 'virtual table');", ())
            names = {str(r["name"]) for r in tables}
            checks["memories"] = "memories" in names
            checks["memory_versions"] = "memory_versions" in names
            checks["memories_fts"] = "memories_fts" in names
            checks["conversation_logs"] = "conversation_logs" in names
        except Exception:
            checks["memories"] = checks["memory_versions"] = checks["memories_fts"] = checks["conversation_logs"] = False

        db_path = getattr(repo.db, "db_path", str(_default_db_path()))
        db_path_obj = Path(str(db_path))

        # Statistics (best-effort, degraded on failure)
        db_stats: dict[str, Any] = {
            "path": str(db_path_obj),
            "exists": db_path_obj.exists(),
        }
        try:
            db_stats["memory_count"] = await repo.count_memories_total()
            by_state = await repo.count_memories_by_state()
            db_stats["active_memory_count"] = by_state.get("active", 0)
            by_cs = await repo.count_memories_by_candidate_state()
            db_stats["candidate_count"] = by_cs.get("candidate", 0)
            db_stats["committed_count"] = by_cs.get("committed", 0)
        except Exception:
            db_stats["memory_count"] = -1
            db_stats["active_memory_count"] = -1
            db_stats["candidate_count"] = -1
            db_stats["committed_count"] = -1

        if not all(checks.values()):
            return {
                "status": "degraded", "ready": False,
                "source": "rest",
                "warning": "some tables missing",
                "checks": checks, "db": db_stats,
                "env": {"cwd": _os.getcwd(), "memoryx_home": _os.environ.get("MEMORYX_HOME", "")},
            }

        return {
            "status": "ready", "ready": True,
            "source": "rest",
            "checks": checks,
            "db": db_stats,
            "env": {"cwd": _os.getcwd(), "memoryx_home": _os.environ.get("MEMORYX_HOME", "")},
        }

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "version": "1.1.0"}

    @app.get("/health/auth-required")
    async def health_auth_required(_key: str | None = Depends(verify_api_key)) -> dict:
        return {"status": "ok", "auth_required": _key is not None}

    @app.get("/metrics")
    async def metrics(_key: str | None = Depends(verify_api_key)) -> Response:
        return Response(content=metrics_response_bytes(), media_type=CONTENT_TYPE_LATEST)

    @app.post("/v1/memories", status_code=201)
    async def create_memory(body: MemoryCreate, _key: str | None = Depends(verify_api_key)) -> dict:
        repo = await ensure_repo()
        from memoryx.storage import MemoryRecord

        record = MemoryRecord(
            id=uuid4().hex,
            memory_type=body.memory_type,
            content=body.content,
            importance_score=body.importance_score,
            confidence_score=body.confidence_score,
            session_id=body.session_id,
            scope=body.scope,
            metadata_json=json.dumps(body.metadata, ensure_ascii=False) if body.metadata else "{}",
        )
        mem_id = await repo.store_memory(record)
        record_rest_request(route="/v1/memories", method="POST", status_code=201)
        return {"id": mem_id}

    @app.get("/v1/memories/{memory_id}")
    async def get_memory(memory_id: str, _key: str | None = Depends(verify_api_key)) -> dict:
        repo = await ensure_repo()
        mem = await repo.get_memory(memory_id)
        if not mem:
            raise HTTPException(404, "not found")
        return dict(mem)

    @app.get("/v1/memories")
    async def list_memories(
        *,
        memory_type: str | None = None,
        scope: str | None = None,
        tag: str | None = None,
        limit: int = 50,
        offset: int = 0,
        _key: str | None = Depends(verify_api_key),
    ) -> dict:
        """列出记忆（支持按类型、范围、标签过滤）。"""
        repo = await ensure_repo()
        conditions: list[str] = []
        params_vals: list[str] = []

        if memory_type:
            conditions.append("memory_type = ?")
            params_vals.append(memory_type)
        if scope:
            conditions.append("scope = ?")
            params_vals.append(scope)
        if tag:
            conditions.append("tags_json LIKE ?")
            params_vals.append(f'%"{tag}"%')

        where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
        count_row = await repo.db.fetchone(
            f"SELECT COUNT(*) AS cnt FROM memories{where_clause};",
            tuple(params_vals),
        )
        total = int(count_row["cnt"]) if count_row else 0

        # 分页查询
        order = "ORDER BY created_at DESC LIMIT ? OFFSET ?"
        rows = await repo.db.fetchall(
            f"SELECT * FROM memories{where_clause} {order};",
            tuple(params_vals) + (limit, offset),
        )
        memories = [dict(r) for r in rows]
        record_rest_request(route="/v1/memories", method="GET", status_code=200)
        return {"memories": memories, "total": total, "limit": limit, "offset": offset}

    @app.patch("/v1/memories/{memory_id}")
    async def update_memory(memory_id: str, body: MemoryUpdate, _key: str | None = Depends(verify_api_key)) -> dict:
        repo = await ensure_repo()
        mem = await repo.get_memory(memory_id)
        if not mem:
            raise HTTPException(404, "not found")

        updates = body.model_dump(exclude_none=True)
        if updates:
            if not hasattr(repo, "update_memory_versioned"):
                raise HTTPException(500, "repository.update_memory_versioned is required for PATCH")
            await repo.update_memory_versioned(
                memory_id,
                updates,
                actor="rest_api",
                reason="PATCH /v1/memories/{memory_id}",
            )
        record_rest_request(route="/v1/memories/{memory_id}", method="PATCH", status_code=200)
        return {"id": memory_id, "updated_fields": sorted(updates)}

    @app.delete("/v1/memories/{memory_id}")
    async def delete_memory(memory_id: str, _key: str | None = Depends(verify_api_key)) -> dict:
        repo = await ensure_repo()
        mem = await repo.get_memory(memory_id)
        if not mem:
            raise HTTPException(404, "not found")
        if hasattr(repo, "rollback_memory"):
            await repo.rollback_memory(memory_id)
        elif hasattr(repo, "update_memory_versioned"):
            await repo.update_memory_versioned(
                memory_id,
                {"active_state": "inactive"},
                actor="rest_api",
                reason="DELETE /v1/memories/{memory_id}",
            )
        else:
            raise HTTPException(500, "repository lacks delete/rollback API")
        return {"id": memory_id, "deleted": True}

    @app.post("/v1/search")
    async def search(body: SearchRequest, _key: str | None = Depends(verify_api_key)) -> dict:
        api = await ensure_api()
        
        # 自动生成 query embedding（如果 vector_store 可用）
        query_vector: list[float] = []
        if api.vector_store is not None:
            try:
                import aiohttp
                api_key = os.getenv("SILICONFLOW_API_KEY") or os.getenv("MEMORYX_EMBEDDING_API_KEY")
                if api_key:
                    async with aiohttp.ClientSession() as s:
                        async with s.post(
                            "https://api.siliconflow.cn/v1/embeddings",
                            json={"model": "Qwen/Qwen3-Embedding-8B", "input": body.query,
                                  "encoding_format": "float", "dimensions": 4096},
                            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                        ) as r:
                            if r.status == 200:
                                d = await r.json()
                                query_vector = d["data"][0]["embedding"]
            except Exception:
                pass  # fallback to no vector search
        
        kwargs = {
            "query": body.query,
            "query_vector": query_vector,
            "limit": body.limit,
            "tag_filter": body.tag_filter,
            "tag_mode": body.tag_mode,
        }
        sig = inspect.signature(api.search)
        for key, value in {
            "session_id": body.session_id,
            "scope_filter": body.scope_filter,
            "include_global": body.include_global,
            "include_lessons": body.include_lessons,
            "explain_scores": body.explain_scores,
        }.items():
            if key in sig.parameters:
                kwargs[key] = value
        results = await api.search(**kwargs)
        return {"results": results, "total": len(results)}

    @app.post("/v1/feedback")
    async def feedback(body: FeedbackRequest, _key: str | None = Depends(verify_api_key)) -> dict:
        api = await ensure_api()
        sig = inspect.signature(api.feedback)
        kwargs = {"memory_id": body.memory_id, "positive": body.positive}
        for key, value in {
            "reason": body.reason,
            "session_id": body.session_id,
            "dry_run": body.dry_run,
            "propagate": body.propagate,
        }.items():
            if key in sig.parameters:
                kwargs[key] = value
        return await api.feedback(**kwargs)

    @app.post("/v1/self-edit/preview")
    async def self_edit_preview(body: SelfEditPreviewRequest, _key: str | None = Depends(verify_api_key)) -> dict:
        editor = state().self_editor
        if editor is None:
            raise HTTPException(503, "self editor not configured")
        from memoryx.self_editor import SelfEditRequest

        result = await editor.preview(SelfEditRequest(memory_id=body.memory_id, edit_type=body.edit_type, changes=body.changes, reason=body.reason))
        return {"preview": result}

    @app.post("/v1/self-edit/apply")
    async def self_edit_apply(body: SelfEditApplyRequest, _key: str | None = Depends(verify_api_key)) -> dict:
        editor = state().self_editor
        if editor is None:
            raise HTTPException(503, "self editor not configured")
        from memoryx.self_editor import SelfEditRequest

        result = await editor.apply(SelfEditRequest(memory_id=body.memory_id, edit_type=body.edit_type, changes=body.changes, reason=body.reason))
        return {"result": result}

    @app.post("/v1/consolidation/run")
    async def consolidation_run(body: ConsolidationRequest, _key: str | None = Depends(verify_api_key)) -> dict:
        consolidation = state().consolidation
        if consolidation is None:
            raise HTTPException(503, "consolidation not configured")
        result = await consolidation.run(limit=body.limit, dry_run=body.dry_run)
        return {"consolidation": result}

    app.include_router(
        create_p11_router(
            get_repository=ensure_repo,
            get_retrieval_engine=get_retrieval_engine,
            get_lesson_policy=get_lesson_policy,
            prefix="/v1/cognitive",
        )
    )

    # ── P16: Learning Loop + Skill Distillation ──
    app.include_router(learning_router)
    app.include_router(distill_router)

    app.state.memoryx = initial_state
    return app
