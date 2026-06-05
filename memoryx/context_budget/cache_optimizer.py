from __future__ import annotations

from time import perf_counter
from typing import Any

from .layout import PromptCacheLayoutBuilder
from .telemetry import ContextPackTelemetryStore, ContextTelemetryRecord


class PromptCacheContextOptimizer:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.layout_builder = PromptCacheLayoutBuilder()
        self.telemetry = ContextPackTelemetryStore(db_path)

    def enrich(self, pack: dict[str, Any], latency_ms: float = 0.0) -> dict[str, Any]:
        layout = self.layout_builder.build(pack)
        reuse = self.telemetry.estimate_reuse(
            session_id=pack.get("session_id"),
            static_prefix_hash=layout.static_prefix_hash,
            memory_block_hash=layout.memory_block_hash,
            dynamic_block_hash=layout.dynamic_block_hash,
        )

        pack["cache_layout"] = {
            "layout_version": layout.layout_version,
            "static_prefix_hash": layout.static_prefix_hash,
            "memory_block_hash": layout.memory_block_hash,
            "dynamic_block_hash": layout.dynamic_block_hash,
            "full_pack_hash": layout.full_pack_hash,
            "rendered_text": layout.rendered_text,
            "static_prefix_chars": len(layout.static_prefix),
            "memory_block_chars": len(layout.memory_block),
            "dynamic_block_chars": len(layout.dynamic_task_block) + len(layout.dynamic_runtime_block) + len(layout.warning_block),
        }

        pack["cache_reuse"] = reuse
        pack["text"] = layout.rendered_text

        self.telemetry.record(
            ContextTelemetryRecord(
                pack_id=pack.get("pack_id") or "",
                session_id=pack.get("session_id"),
                request_id=pack.get("request_id") or "",
                mode=pack.get("mode", "standard"),
                used_tokens=int(pack.get("used_tokens", 0)),
                included_items=int(pack.get("included_items", 0)),
                dropped_items=int(pack.get("dropped_items", 0)),
                static_prefix_hash=layout.static_prefix_hash,
                memory_block_hash=layout.memory_block_hash,
                dynamic_block_hash=layout.dynamic_block_hash,
                full_pack_hash=layout.full_pack_hash,
                estimated_cache_hit=bool(reuse.get("estimated_cache_hit")),
                cache_reuse_ratio=float(reuse.get("cache_reuse_ratio", 0.0)),
                latency_ms=float(latency_ms),
            )
        )

        return pack
