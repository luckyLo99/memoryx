from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from uuid import uuid4


_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "the",
    "to",
    "uses",
    "user",
    "with",
}

_TOKEN_ALIASES = {
    "prefers": "prefer",
    "preferred": "prefer",
    "preferences": "preference",
    "coding": "code",
    "coded": "code",
    "patterns": "pattern",
}

_COMPRESSION_METHOD_VERSION = "semantic_compression.det_v2"


class SemanticCompressionEngine:
    """Deterministic semantic compression with provenance and conservative archival.

    The engine intentionally avoids network/model dependencies. It uses token-overlap
    clustering and representative summaries as a stable local fallback, while keeping
    source memory ids/checksums and archive decisions auditable.
    """

    def __init__(self, *, repository) -> None:
        self.repository = repository

    async def cluster_memories(self) -> list[dict]:
        """Cluster active memories by normalized token overlap."""
        memories = await self.repository.list_active_memories(limit=1000)
        buckets: dict[str, list[dict]] = defaultdict(list)
        token_sets: dict[str, set[str]] = {}

        for memory in memories:
            memory_id = str(memory.get("id") or memory.get("memory_id") or "")
            tokens = set(self._tokens(str(memory.get("content", ""))))
            token_sets[memory_id] = tokens
            buckets[self._cluster_key(str(memory.get("content", "")))].append(memory)

        clusters: list[dict] = []
        seen: set[str] = set()
        for group in buckets.values():
            if len(group) < 2:
                continue
            refined = self._refine_by_overlap(group, token_sets)
            for subgroup in refined:
                ids = [str(item.get("id") or item.get("memory_id")) for item in subgroup]
                if len(ids) < 2 or any(memory_id in seen for memory_id in ids):
                    continue
                seen.update(ids)
                clusters.append(
                    {
                        "cluster_id": self._cluster_id(ids),
                        "memory_ids": ids,
                        "memories": subgroup,
                        "reason": "token_overlap",
                        "confidence": self._cluster_confidence(subgroup),
                        "provenance": self._cluster_provenance(subgroup, reason="token_overlap"),
                    }
                )
        return clusters

    def summarize_cluster(self, memories: list[dict]) -> str:
        """Build a deterministic representative summary for a memory cluster."""
        if not memories:
            return ""
        contents = [
            str(item.get("content", "")).strip()
            for item in memories
            if str(item.get("content", "")).strip()
        ]
        if not contents:
            return ""

        token_counts = Counter(token for content in contents for token in self._tokens(content))
        representative = self._representative_content(memories, token_counts)
        keywords = [token for token, _ in token_counts.most_common(6)]
        if keywords:
            return f"{representative} [common_terms: {', '.join(keywords)}]"
        return representative

    async def merge_duplicate_chunks(self) -> int:
        """Merge exact duplicate memories by superseding lower-importance copies."""
        memories = await self.repository.list_active_memories(limit=1000)
        by_content: dict[str, list[dict]] = defaultdict(list)
        for memory in memories:
            by_content[str(memory.get("content", "")).strip().lower()].append(memory)

        merged = 0
        for group in by_content.values():
            if len(group) < 2:
                continue
            ordered = sorted(
                group,
                key=lambda item: float(item.get("importance_score", 0.0)),
                reverse=True,
            )
            primary = ordered[0]
            for duplicate in ordered[1:]:
                await self.repository.supersede_memory(duplicate["id"], primary["id"])
                merged += 1
        return merged

    async def compress_to_hierarchical_summary(self, *, session_id: str) -> dict:
        """Create a hierarchical summary and archive only low-value stale memories."""
        clusters = await self.cluster_memories()
        summaries: list[str] = []
        summary_provenance: list[dict] = []
        archive_decisions: list[dict] = []
        archived = 0

        for cluster in clusters:
            summary = self.summarize_cluster(cluster["memories"])
            if summary:
                summaries.append(summary)
                summary_provenance.append(
                    {
                        **cluster["provenance"],
                        "summary_checksum": self.repository.checksum(summary),
                        "summary": summary,
                    }
                )

        memories = await self.repository.list_memories(limit=1000)
        for memory in memories:
            decision = self._archive_decision(memory)
            archive_decisions.append(decision)
            if not decision["archive"]:
                continue
            metadata = {
                "method_version": _COMPRESSION_METHOD_VERSION,
                "reason": decision["reason"],
                "source_memory_ids": [memory["id"]],
                "source_checksums": [str(memory.get("checksum") or self.repository.checksum(str(memory.get("content", ""))))],
                "rollback": {"table": "memories", "id": memory["id"], "previous_active_state": memory.get("active_state", "active")},
                "decision": decision,
            }
            await self.repository.db.execute(
                """
                INSERT INTO archived_memories (
                    id, memory_id, archived_reason, archived_at, checksum, metadata_json
                ) VALUES (?, ?, ?, datetime('now'), ?, ?);
                """,
                (
                    uuid4().hex,
                    memory["id"],
                    "semantic_compression_low_value_stale",
                    self.repository.checksum(f"archive:{memory['id']}:{metadata['reason']}"),
                    json.dumps(metadata, ensure_ascii=False, sort_keys=True),
                ),
            )
            await self.repository.rollback_memory(memory["id"])
            archived += 1

        hierarchical_summary = (
            " || ".join(summaries) if summaries else "No compressible clusters found."
        )
        summary_metadata = {
            "method_version": _COMPRESSION_METHOD_VERSION,
            "source_cluster_count": len(summary_provenance),
            "source_memory_ids": sorted(
                {
                    memory_id
                    for item in summary_provenance
                    for memory_id in item.get("source_memory_ids", [])
                }
            ),
            "provenance": summary_provenance,
            "archive_decisions": archive_decisions,
        }
        await self.repository.add_session_summary(
            session_id=session_id,
            summary=hierarchical_summary,
            source_count=len(summary_provenance),
        )
        await self._patch_latest_session_summary_metadata(session_id, summary_metadata)
        return {
            "clusters": len(clusters),
            "archived": archived,
            "provenance": summary_provenance,
            "archive_decisions": archive_decisions,
            "method_version": _COMPRESSION_METHOD_VERSION,
        }

    async def run_llm_consolidation(
        self,
        *,
        limit: int = 100,
        dry_run: bool = True,
        cluster_key: str | None = None,
    ) -> dict:
        from memoryx.llm_consolidation_engine import LLMConsolidationEngine

        engine = LLMConsolidationEngine(repository=self.repository)
        return await engine.run(
            limit=limit,
            dry_run=dry_run,
            cluster_key=cluster_key,
        )

    def _cluster_key(self, content: str) -> str:
        tokens = self._tokens(content)
        if not tokens:
            return "empty"
        counts = Counter(tokens)
        return "|".join(token for token, _ in counts.most_common(3))

    def _tokens(self, content: str) -> list[str]:
        return [
            _TOKEN_ALIASES.get(token, token)
            for token in re.findall(r"[a-z0-9]+", content.lower())
            if len(token) > 2 and token not in _STOPWORDS
        ]

    def _refine_by_overlap(self, group: list[dict], token_sets: dict[str, set[str]]) -> list[list[dict]]:
        clusters: list[list[dict]] = []
        for memory in group:
            memory_id = str(memory.get("id") or memory.get("memory_id") or "")
            tokens = token_sets.get(memory_id, set())
            placed = False
            for cluster in clusters:
                representative = cluster[0]
                representative_id = str(representative.get("id") or representative.get("memory_id") or "")
                if self._jaccard(tokens, token_sets.get(representative_id, set())) >= 0.35:
                    cluster.append(memory)
                    placed = True
                    break
            if not placed:
                clusters.append([memory])
        return clusters

    @staticmethod
    def _jaccard(left: set[str], right: set[str]) -> float:
        if not left or not right:
            return 0.0
        return len(left & right) / len(left | right)

    def _cluster_confidence(self, memories: list[dict]) -> float:
        if len(memories) < 2:
            return 0.0
        token_sets = [set(self._tokens(str(item.get("content", "")))) for item in memories]
        scores = []
        for idx, left in enumerate(token_sets):
            for right in token_sets[idx + 1 :]:
                scores.append(self._jaccard(left, right))
        return round(sum(scores) / len(scores), 4) if scores else 0.0

    def _cluster_provenance(self, memories: list[dict], *, reason: str) -> dict:
        ids = [str(item.get("id") or item.get("memory_id")) for item in memories]
        checksums = [
            str(item.get("checksum") or self.repository.checksum(str(item.get("content", ""))))
            for item in memories
        ]
        return {
            "cluster_id": self._cluster_id(ids),
            "method_version": _COMPRESSION_METHOD_VERSION,
            "reason": reason,
            "source_memory_ids": ids,
            "source_checksums": checksums,
            "cluster_confidence": self._cluster_confidence(memories),
        }

    def _representative_content(self, memories: list[dict], token_counts: Counter) -> str:
        def score(item: dict) -> tuple[float, float, int]:
            content = str(item.get("content", ""))
            tokens = self._tokens(content)
            coverage = sum(token_counts[token] for token in set(tokens))
            importance = float(item.get("importance_score", 0.0))
            return (coverage, importance, -len(content))

        representative = max(memories, key=score)
        content = str(representative.get("content", "")).strip()
        return content[:280] + "..." if len(content) > 280 else content

    def _archive_decision(self, memory: dict) -> dict:
        decay = float(memory.get("decay_score", 0.0) or 0.0)
        access = int(memory.get("access_count", 0) or 0)
        active = str(memory.get("active_state", "active") or "active")
        importance = float(memory.get("importance_score", 0.0) or 0.0)
        confidence = float(memory.get("confidence_score", 0.0) or 0.0)
        reinforcement = float(memory.get("reinforcement_score", 0.0) or 0.0)
        safety = float(memory.get("safety_score", 1.0) or 1.0)
        memory_type = str(memory.get("memory_type", "") or "")

        blockers = []
        if active != "active":
            blockers.append("not_active")
        if decay < 0.95:
            blockers.append("decay_below_0.95")
        if access != 0:
            blockers.append("has_access_history")
        if importance >= 0.75:
            blockers.append("high_importance")
        if confidence >= 0.8:
            blockers.append("high_confidence")
        if reinforcement > 0:
            blockers.append("reinforced")
        if safety < 0.8:
            blockers.append("safety_ambiguous")
        if memory_type in {"PREFERENCE", "LESSON", "POLICY", "PROJECT", "TASK"}:
            blockers.append("protected_memory_type")

        archive = not blockers
        return {
            "memory_id": str(memory.get("id") or memory.get("memory_id") or ""),
            "archive": archive,
            "reason": "low_value_stale_decay" if archive else "protected_or_insufficient_decay_evidence",
            "blockers": blockers,
            "signals": {
                "decay_score": decay,
                "access_count": access,
                "importance_score": importance,
                "confidence_score": confidence,
                "reinforcement_score": reinforcement,
                "safety_score": safety,
                "active_state": active,
                "memory_type": memory_type,
            },
        }

    async def _patch_latest_session_summary_metadata(self, session_id: str, metadata: dict) -> None:
        rows = await self.repository.db.fetchall(
            """
            SELECT id FROM session_summaries
            WHERE session_id = ?
            ORDER BY created_at DESC
            LIMIT 1;
            """,
            (session_id,),
        )
        if not rows:
            return
        await self.repository.db.execute(
            "UPDATE session_summaries SET metadata_json = ? WHERE id = ?;",
            (json.dumps(metadata, ensure_ascii=False, sort_keys=True), rows[0]["id"]),
        )

    @staticmethod
    def _cluster_id(memory_ids: list[str]) -> str:
        return "cluster:" + "-".join(sorted(memory_ids))
