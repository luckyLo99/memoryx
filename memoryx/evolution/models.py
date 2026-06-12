"""Pydantic models for evolutionary memory trajectories."""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class EvolutionKind(str, Enum):
    """Type of evolution observed."""

    PREFERENCE = "PREFERENCE"
    OPINION = "OPINION"
    FACT = "FACT"


class EvolutionDecision(str, Enum):
    """How the system should treat a new observation."""

    ADD = "ADD"            # brand-new entity slot
    EVOLVE = "EVOLVE"      # append to an existing trajectory
    CONFLICT = "CONFLICT"  # real contradiction (do not evolve)


@dataclass
class EvolutionNode:
    """A single value held by an entity in a slot, valid for a time window."""

    id: str
    entity_id: str
    slot: str
    value: str
    kind: EvolutionKind
    valid_from: str
    valid_to: Optional[str] = None
    confidence: float = 1.0
    source_memory_id: Optional[str] = None
    context: str = ""
    created_at: str = field(default_factory=_utcnow)
    active_state: str = "active"
    decay_score: float = 0.0  # Ebbinghaus decay

    def is_active(self, as_of: Optional[str] = None) -> bool:
        if self.active_state != "active":
            return False
        if self.valid_to is None:
            return True
        return as_of is None or as_of <= self.valid_to

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "entity_id": self.entity_id,
            "slot": self.slot,
            "value": self.value,
            "kind": self.kind.value,
            "valid_from": self.valid_from,
            "valid_to": self.valid_to,
            "confidence": self.confidence,
            "source_memory_id": self.source_memory_id,
            "context": self.context,
            "created_at": self.created_at,
            "active_state": self.active_state,
            "decay_score": self.decay_score,
        }

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "EvolutionNode":
        return cls(
            id=row["id"],
            entity_id=row["entity_id"],
            slot=row["slot"],
            value=row["value"],
            kind=EvolutionKind(row["kind"]) if row.get("kind") else EvolutionKind.PREFERENCE,
            valid_from=row["valid_from"],
            valid_to=row.get("valid_to"),
            confidence=float(row.get("confidence", 1.0)),
            source_memory_id=row.get("source_memory_id"),
            context=row.get("context", ""),
            created_at=row.get("created_at", _utcnow()),
            active_state=row.get("active_state", "active"),
            decay_score=float(row.get("decay_score", 0.0)),
        )


@dataclass
class EvolutionTrajectory:
    """Ordered sequence of EvolutionNodes for one (entity, slot) pair."""

    entity_id: str
    slot: str
    nodes: list[EvolutionNode] = field(default_factory=list)

    @property
    def latest(self) -> Optional[EvolutionNode]:
        active = [n for n in self.nodes if n.active_state == "active"]
        if not active:
            return None
        return max(active, key=lambda n: n.valid_from)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "slot": self.slot,
            "latest": self.latest.value if self.latest else None,
            "history": [
                {
                    "id": n.id,
                    "value": n.value,
                    "valid_from": n.valid_from,
                    "valid_to": n.valid_to,
                    "context": n.context,
                    "active_state": n.active_state,
                    "decay_score": n.decay_score,
                }
                for n in sorted(self.nodes, key=lambda x: x.valid_from)
            ],
        }


@dataclass
class PreferenceSignal:
    """Heuristic-detected preference change signal."""

    entity_id: str
    slot: str
    value: str
    kind: EvolutionKind
    context: str = ""
    source_memory_id: Optional[str] = None
    confidence: float = 0.8

    @property
    def is_change(self) -> bool:
        return self.value.strip() != ""


class PreferenceSignalDetector:
    """Heuristic detector for preference/opinion/fact change signals.

    Recognizes patterns in Chinese and English such as:
    - "我最喜欢/最爱的 X 是 Y"
    - "my favorite X is Y"
    - "我不再喜欢 X，现在喜欢 Y"  (preference shift)
    - "I used to like X, now I like Y"
    - "I think Z is / was ..."  (opinion)
    """

    ZH_LIKE = ["喜欢", "最爱", "最爱的", "中意", "偏好", "欣赏", "热衷", "粉"]
    ZH_DISLIKE = ["不喜欢", "讨厌", "嫌", "不再喜欢", "不再爱"]
    ZH_SHIFT = ["现在", "改为", "改成", "换成", "变成了", "现在是", "如今", "改", "变"]
    ZH_OWN = ["我", "本人"]

    EN_LIKE = ["favorite", "prefer", "like", "love", "enjoy"]
    EN_DISLIKE = ["dislike", "hate", "don't like", "no longer"]
    EN_SHIFT = ["now", "currently", "switched to", "changed to", "is now"]
    EN_OWN = ["i", "my", "me", "myself"]

    SLOT_PATTERNS_ZH = [
        r"歌星|歌手|明星|偶像|艺人|乐队",
        r"颜色|色彩",
        r"食物|菜|饭|料理|口味",
        r"运动|运动方式|运动项目",
        r"电影|影片|电视剧|剧",
        r"书|书籍|读物|小说",
        r"宠物|动物|猫|狗",
    ]

    SLOT_PATTERNS_EN = [
        r"singer|artist|band|musician|celebrity",
        r"color|colour",
        r"food|cuisine|meal|dish|drink|beverage",
        r"sport|exercise",
        r"movie|film|show|series|anime",
        r"book|novel|read",
        r"pet|dog|cat|animal",
    ]

    def __init__(self) -> None:
        self._zh_like_re = re.compile(
            r"(?P<verb>" + "|".join(self.ZH_LIKE) + r")(?P<slot>[\u4e00-\u9fff]{1,10}?)(?:是|为|就是)(?P<val>[^\s,.，。；;！!]{1,30})"
        )
        self._en_like_re = re.compile(
            r"\b(?P<verb>" + "|".join(self.EN_LIKE) + r")\s+(?P<slot>[a-zA-Z ]{2,30}?)\s+(?:is|are|=)\s+(?P<val>[A-Za-z0-9' \-]{1,40})",
            re.IGNORECASE,
        )
        self._zh_shift_re = re.compile(
            r"(?P<old_slot>[\u4e00-\u9fff]{1,10}?)(?:是|为)(?P<old_val>[^\s,.，。；;！!的]{1,20})[,，;；]?\s*(?P<shift>" + "|".join(self.ZH_SHIFT) + r")\s*(?:是|为|的是)?(?P<new_val>[^\s,.，。；;！!]{1,30})"
        )
        self._en_shift_re = re.compile(
            r"\b(?:i\s+)?(?:used\s+to\s+)?(?P<verb>" + "|".join(self.EN_LIKE) + r")\s+(?P<slot>[a-zA-Z ]{2,30}?)\s+(?:was|were|is|are)\s+(?P<old_val>[A-Za-z0-9' \-]{1,30}),?\s*(?:but\s+)?(?:now|currently)\s+(?:(?:it's\s+)|(?:it\s+is\s+)|(?:it\s+)?(?:is|are|=)\s+)(?P<new_val>[A-Za-z0-9' \-]{1,40})",
            re.IGNORECASE,
        )

    def detect(self, content: str, entity_id: str = "user", memory_id: Optional[str] = None) -> list[PreferenceSignal]:
        """Detect preference signals in a piece of text."""
        if not content or not content.strip():
            return []
        signals: list[PreferenceSignal] = []
        text = content.strip()

        # 1) Chinese: "我最喜欢的歌星是张杰"
        for m in self._zh_like_re.finditer(text):
            slot_raw = m.group("slot")
            val = m.group("val").strip("的")
            if not val or len(val) < 1:
                continue
            slot = self._canonicalize_slot(slot_raw, "zh")
            signals.append(PreferenceSignal(
                entity_id=entity_id,
                slot=slot,
                value=val,
                kind=EvolutionKind.PREFERENCE,
                context=text,
                source_memory_id=memory_id,
                confidence=0.85,
            ))

        # 2) English: "my favorite singer is Jay Chou"
        for m in self._en_like_re.finditer(text):
            slot_raw = m.group("slot").strip()
            val = m.group("val").strip()
            if not val or len(val) < 1:
                continue
            slot = self._canonicalize_slot(slot_raw, "en")
            signals.append(PreferenceSignal(
                entity_id=entity_id,
                slot=slot,
                value=val,
                kind=EvolutionKind.PREFERENCE,
                context=text,
                source_memory_id=memory_id,
                confidence=0.85,
            ))

        # 3) Chinese shift: "我最喜欢的歌星是张杰，现在最喜欢的是房东的猫"
        for m in self._zh_shift_re.finditer(text):
            slot_raw = m.group("old_slot")
            slot = self._canonicalize_slot(slot_raw, "zh")
            new_val = m.group("new_val").strip("的")
            if new_val:
                signals.append(PreferenceSignal(
                    entity_id=entity_id,
                    slot=slot,
                    value=new_val,
                    kind=EvolutionKind.PREFERENCE,
                    context=text,
                    source_memory_id=memory_id,
                    confidence=0.9,  # shift signals are more explicit
                ))

        # 4) English shift: "my favorite singer was Jay Chou, now it's Taylor Swift"
        for m in self._en_shift_re.finditer(text):
            slot_raw = m.group("slot").strip()
            new_val = m.group("new_val").strip()
            if new_val:
                slot = self._canonicalize_slot(slot_raw, "en")
                signals.append(PreferenceSignal(
                    entity_id=entity_id,
                    slot=slot,
                    value=new_val,
                    kind=EvolutionKind.PREFERENCE,
                    context=text,
                    source_memory_id=memory_id,
                    confidence=0.9,
                ))

        return signals

    def _canonicalize_slot(self, raw: str, lang: str) -> str:
        """Normalize slot names to canonical English keys."""
        raw_lower = raw.lower()
        slot_maps_zh = [
            ("singer", ["歌星", "歌手", "明星", "偶像", "艺人", "乐队"]),
            ("color", ["颜色", "色彩"]),
            ("food", ["食物", "菜", "饭", "料理", "口味"]),
            ("sport", ["运动"]),
            ("movie", ["电影", "影片", "电视剧", "剧"]),
            ("book", ["书", "书籍", "读物", "小说"]),
            ("pet", ["宠物", "猫", "狗", "动物"]),
        ]
        for canonical, keys in slot_maps_zh:
            for k in keys:
                if k in raw:
                    return canonical
        slot_maps_en = [
            ("singer", ["singer", "artist", "band", "musician", "celebrity"]),
            ("color", ["color", "colour"]),
            ("food", ["food", "cuisine", "meal", "dish", "drink", "beverage"]),
            ("sport", ["sport", "exercise"]),
            ("movie", ["movie", "film", "show", "series", "anime"]),
            ("book", ["book", "novel", "read"]),
            ("pet", ["pet", "dog", "cat", "animal"]),
        ]
        for canonical, keys in slot_maps_en:
            for k in keys:
                if k in raw_lower:
                    return canonical
        # Fallback: keep raw (lowercased, trimmed) as slot name
        return raw.strip().lower().replace(" ", "_")[:30]
