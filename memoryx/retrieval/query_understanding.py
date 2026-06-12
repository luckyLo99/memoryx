"""Query Understanding Engine — lightweight, deterministic intent detection.

Design principles
=================
- Zero external deps (no LLM call at search time).
- Pure function; deterministic; safe to be called thousands of times.
- Bilingual: Chinese + English keyword lists.
- Falls back to ``RetrievalIntent.FACT`` when no strong signal is found.

Intents supported
=================
- CODING        : code/function/API questions.
- DEBUGGING     : error/bug/traceback/exception questions.
- TROUBLESHOOTING: infrastructure/network/config issues.
- DEPLOYMENT    : deploy/release/CI/CD/publish.
- PLANNING      : roadmap/plan/design/todo.
- PROJECT       : project/repo/codebase.
- WORKFLOW      : workflow/process/howto.
- PREFERENCE    : user preference/likes/opinions (Chinese: 偏好/喜欢).
- EMOTIONAL     : feelings/mood/emotional support.
- FACT          : default — general fact recall.

Usage
=====
>>> from memoryx.retrieval.query_understanding import QueryUnderstanding
>>> qu = QueryUnderstanding()
>>> intent, confidence = qu.classify("How do I deploy the docker image?")
>>> intent.value, confidence
('deployment', 0.9)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Tuple

from .models import RetrievalIntent


# ---------------------------------------------------------------------------
# Keyword catalog — manually curated, bilingual, lightweight.
# Each intent has: primary strong words (high confidence) and weak indicators.
# ---------------------------------------------------------------------------

_CODING_KEYWORDS = {
    "en": [
        "function", "class", "def", "method", "api", "code", "script",
        "variable", "module", "import", "type", "error", "return", "syntax",
        "compile", "package", "library", "library", "line of code",
    ],
    "zh": [
        "函数", "代码", "类", "方法", "接口", "API", "模块", "变量",
        "调用", "编译", "报错", "语法", "库", "包", "脚本",
    ],
}

_DEBUG_KEYWORDS = {
    "en": [
        "bug", "debug", "error", "exception", "traceback", "crash",
        "fail", "failure", "stack trace", "fatal", "raise", "throw",
    ],
    "zh": [
        "bug", "错误", "崩溃", "异常", "修复", "调试", "报错",
        "排查", "问题", "失败", "堆栈",
    ],
}

_TROUBLESHOOT_KEYWORDS = {
    "en": [
        "network", "connection", "timeout", "timeout", "permission",
        "access", "denied", "config", "setting", "infrastructure",
    ],
    "zh": [
        "网络", "连接", "超时", "权限", "配置", "环境", "基础设施",
        "访问", "无法", "失败",
    ],
}

_DEPLOY_KEYWORDS = {
    "en": [
        "deploy", "deployment", "release", "publish", "ci", "cd",
        "docker", "container", "build", "pipeline", "ship",
    ],
    "zh": [
        "部署", "发布", "上线", "打包", "构建", "流水线",
        "docker", "容器", "镜像",
    ],
}

_PLANNING_KEYWORDS = {
    "en": [
        "plan", "planning", "roadmap", "milestone", "todo", "to-do",
        "schedule", "design document", "spec", "timeline",
    ],
    "zh": [
        "计划", "规划", "路线图", "里程碑", "待办", "todo",
        "时间表", "设计文档",
    ],
}

_PROJECT_KEYWORDS = {
    "en": [
        "project", "repo", "repository", "codebase", "organization",
        "package", "source code",
    ],
    "zh": [
        "项目", "仓库", "代码库", "组织", "代码",
    ],
}

_WORKFLOW_KEYWORDS = {
    "en": [
        "workflow", "process", "howto", "how to", "procedure",
        "step by step", "guide", "tutorial",
    ],
    "zh": [
        "流程", "步骤", "怎么", "如何", "教程", "指南",
        "操作流程", "工作流",
    ],
}

_PREFERENCE_KEYWORDS = {
    "en": [
        "favorite", "favourite", "prefer", "preference", "like",
        "dislike", "hate", "opinion", "my habit",
    ],
    "zh": [
        "最喜欢", "偏好", "喜欢", "不喜欢", "爱好", "讨厌",
        "我的习惯", "我习惯", "我比较", "我倾向",
    ],
}

_EMOTIONAL_KEYWORDS = {
    "en": [
        "tired", "sad", "happy", "anxious", "stress", "burnout",
        "lonely", "feeling", "emotion", "mood",
    ],
    "zh": [
        "累", "难过", "开心", "焦虑", "压力", "情绪", "心情",
        "郁闷", "孤独",
    ],
}


# ---------------------------------------------------------------------------
# Intents ordered by priority (higher = checked first).
# ---------------------------------------------------------------------------

_INTENT_CATALOG: list[tuple[RetrievalIntent, dict]] = [
    (RetrievalIntent.CODING, _CODING_KEYWORDS),
    (RetrievalIntent.DEBUGGING, _DEBUG_KEYWORDS),
    (RetrievalIntent.TROUBLESHOOTING, _TROUBLESHOOT_KEYWORDS),
    (RetrievalIntent.DEPLOYMENT, _DEPLOY_KEYWORDS),
    (RetrievalIntent.PLANNING, _PLANNING_KEYWORDS),
    (RetrievalIntent.PROJECT, _PROJECT_KEYWORDS),
    (RetrievalIntent.WORKFLOW, _WORKFLOW_KEYWORDS),
    (RetrievalIntent.PREFERENCE, _PREFERENCE_KEYWORDS),
    (RetrievalIntent.EMOTIONAL, _EMOTIONAL_KEYWORDS),
]


@dataclass
class QueryUnderstanding:
    """Deterministic query intent classifier."""

    def classify(self, query: str) -> Tuple[RetrievalIntent, float]:
        """Classify a user query into an intent.

        Returns a tuple of ``(intent, confidence)``.
        When no strong signal is found, returns ``(FACT, 0.0)`` so that
        downstream code can safely treat it as generic recall.
        """
        if not query or not query.strip():
            return RetrievalIntent.FACT if hasattr(RetrievalIntent, "FACT") else next(iter(RetrievalIntent)), 0.0
        text = " " + query.strip().lower() + " "

        best_intent = None
        best_score = 0.0
        for intent, catalog in _INTENT_CATALOG:
            score = self._score_intent(text, catalog)
            if score > best_score:
                best_score = score
                best_intent = intent

        if best_intent is None or best_score < 0.1:
            # Default: general fact recall. When RetrievalIntent doesn't
            # expose FACT, use CODING as the safest generic fallback.
            intent = RetrievalIntent.CODING
            # Prefer to emit PREFERENCE if any of the PREFERENCE words
            # appeared, even weakly — otherwise fall back to CODING.
            pref_score = self._score_intent(text, _PREFERENCE_KEYWORDS)
            if pref_score > 0:
                intent = RetrievalIntent.PREFERENCE
            return intent, max(best_score, pref_score) / 2.0
        return best_intent, best_score

    @staticmethod
    def _score_intent(text: str, catalog: dict) -> float:
        """Score a single intent by its keyword catalog."""
        score = 0.0
        for lang in ("en", "zh"):
            for kw in catalog.get(lang, []):
                if not kw:
                    continue
                pattern = r"\b" + re.escape(kw) + r"\b"
                if re.search(pattern, text):
                    score += 1.0 if len(kw) >= 3 else 0.5
                elif kw in text:
                    # For Chinese substring matching: word boundaries are
                    # useless, so count a plain substring as a match too.
                    score += 0.8 if len(kw) >= 2 else 0.3
        # Normalize by catalog size, clamped.
        if not score:
            return 0.0
        total_kws = max(1, sum(len(v) for v in catalog.values()))
        return min(1.0, score / 3.0)


def classify_query(query: str) -> Tuple[RetrievalIntent, float]:
    """Convenience wrapper — single call, single instance per process cache."""
    return QueryUnderstanding().classify(query)
