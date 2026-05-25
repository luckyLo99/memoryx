# memoryx/feishu/routes.py
"""
FastAPI 路由：接收飞书事件 → 去重 → 入队 → 返回 job_id。
含 P14.4 卡片动作回调处理。

流程：
  1. 接收 POST /feishu/events
  2. 签名验证 + 解密（event_security）
  3. URL Verification 响应 challenge
  4. 事件去重（dedupe）
  5. 创建 FeishuRenderJob 入队
  6. 发送 queued 卡片
  7. 返回 job_id

卡片动作：
  - POST /feishu/card_actions  处理按钮点击（刷新/搜索/查看全部）
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Any

from fastapi import APIRouter, Request, HTTPException

from .dedupe import FeishuEventDedupe
from .event_security import parse_event_request, verify_challenge
from .schemas import AttachmentRef, FeishuRenderJob

logger = logging.getLogger(__name__)


def create_feishu_router(
    *,
    bot_service,
    queue_db_path: str,
    get_repository: Any | None = None,
    get_vector_store: Any | None = None,
) -> APIRouter:
    """创建飞书事件路由（含卡片动作回调）"""
    router = APIRouter(prefix="/feishu", tags=["feishu"])
    dedupe = FeishuEventDedupe(queue_db_path)

    app_id = os.getenv("FEISHU_APP_ID", "")
    app_secret = os.getenv("FEISHU_APP_SECRET", "")
    verification_token = os.getenv("FEISHU_VERIFICATION_TOKEN", "")

    @router.post("/events")
    async def feishu_events(request: Request):
        raw = await request.body()

        # 1. Parse payload (skip security for Hermes-gateway forwarded events)
        forwarded_by = request.headers.get("x-forwarded-by", "")
        if forwarded_by == "hermes-gateway":
            payload = json.loads(raw.decode("utf-8"))
        else:
            try:
                payload = parse_event_request(raw, app_id, app_secret)
            except Exception as exc:
                raise HTTPException(400, f"event parse error: {exc}")

        # 2. URL Verification
        challenge_result = verify_challenge(payload, verification_token)
        if challenge_result:
            return challenge_result

        # 3. 提取事件信息
        header = payload.get("header", {})
        event = payload.get("event", {})

        event_id = header.get("event_id") or event.get("event_id")
        message = event.get("message", {})
        message_id = message.get("message_id")

        if not event_id:
            raise HTTPException(400, "missing event_id")

        # 4. 事件去重
        payload_hash = hashlib.sha256(raw).hexdigest()
        if dedupe.seen_or_mark(event_id=event_id, message_id=message_id, payload_hash=payload_hash):
            return {"ok": True, "deduped": True}

        # 5. 提取文本和附件
        chat_id = message.get("chat_id")
        sender = event.get("sender", {})
        user_id = (sender.get("sender_id") or {}).get("user_id")
        text = _extract_text(message)
        attachments = _extract_attachments(message)

        # 6. 创建 job 入队
        job = FeishuRenderJob(
            chat_id=chat_id or "",
            user_id=user_id,
            message_id=message_id,
            text=text,
            title="Hermes · MemoryX",
            trace_id=event_id[:12],
            memoryx_badges=["MemoryX ✅", "Semantic ✅", "P13 ✅"],
            attachments=attachments,
        )

        await bot_service.accept_event(job)

        return {"ok": True, "job_id": job.job_id}

    @router.post("/card_actions")
    async def feishu_card_actions(request: Request):
        """处理 MemoryX 管理卡片按钮点击回调。"""
        raw = await request.body()
        payload = json.loads(raw.decode("utf-8"))

        # 提取卡片动作上下文
        event = payload.get("event", payload)
        action = event.get("action", {})
        context = event.get("context", {})
        operator = event.get("operator", {})

        chat_id = context.get("open_chat_id", "")
        message_id = context.get("open_message_id", "")
        open_id = operator.get("open_id", "")
        action_value = action.get("value", {})
        action_name = action_value.get("action", "")

        if not chat_id or not message_id:
            logger.warning("[Feishu] Card action missing chat_id/message_id: %s", payload)
            return {"ok": False, "error": "missing chat_id or message_id"}

        logger.info(
            "[Feishu] Card action '%s' from %s in %s (msg=%s)",
            action_name, open_id, chat_id, message_id,
        )

        # 根据动作类型处理
        if action_name == "refresh_memory_stats":
            await _handle_refresh_action(
                bot_service=bot_service,
                chat_id=chat_id,
                message_id=message_id,
                get_repository=get_repository,
                get_vector_store=get_vector_store,
            )
        elif action_name == "list_all_memories":
            await _handle_list_all_action(
                bot_service=bot_service,
                chat_id=chat_id,
                get_repository=get_repository,
            )
        elif action_name == "search_memories":
            await _handle_search_action(
                bot_service=bot_service,
                chat_id=chat_id,
            )
        else:
            logger.debug("[Feishu] Unknown card action '%s', ignoring", action_name)

        return {"ok": True}

    return router


async def _handle_refresh_action(
    *,
    bot_service,
    chat_id: str,
    message_id: str,
    get_repository: Any | None = None,
    get_vector_store: Any | None = None,
) -> None:
    """刷新统计卡片：重新查询 DB + LanceDB，构建新卡片并 patch。"""
    from .memory_admin_card import build_card, collect_lancedb_stats, collect_memory_stats, collect_recent_memories

    repo = get_repository() if get_repository else None
    if repo is None:
        logger.warning("[Feishu] No repository available for card refresh")
        return

    vector_store = get_vector_store() if get_vector_store else None

    try:
        stats = await collect_memory_stats(repo)
        recent = await collect_recent_memories(repo, limit=5)
        lancedb_stats = await collect_lancedb_stats(vector_store) if vector_store else None

        new_card = build_card(stats, recent, lancedb_stats)

        await bot_service.client.patch_message_card(message_id=message_id, card=new_card)

        if bot_service.trace_store:
            bot_service.trace_store.record(
                job_id=f"card-{message_id[:12]}",
                trace_id=f"action-{message_id[:8]}",
                phase="card_action",
                event_type="card_refreshed",
                payload={"message_id": message_id, "total": stats["total"], "active": stats["active"]},
            )

        logger.info("[Feishu] Card refreshed: %s (total=%d, active=%d)", message_id, stats["total"], stats["active"])
    except Exception as exc:
        logger.error("[Feishu] Card refresh failed for %s: %s", message_id, exc, exc_info=True)


async def _handle_list_all_action(
    *,
    bot_service,
    chat_id: str,
    get_repository: Any | None = None,
) -> None:
    """列出所有记忆——以文本消息发送。"""
    repo = get_repository() if get_repository else None
    if repo is None:
        return

    try:
        rows = await repo.db.fetchall(
            "SELECT id, memory_type, substr(content,1,100) as preview, created_at, active_state "
            "FROM memories ORDER BY created_at DESC LIMIT 50;", ()
        )
        lines = ["**📋 MemoryX 记忆列表（最近 50 条）**\n"]
        for i, r in enumerate(rows, 1):
            mtype = r["memory_type"]
            preview = (r["preview"] or "")[:80]
            state = "✅" if r["active_state"] == "active" else "🔴"
            lines.append(f"{i}. {state} **{mtype}**: {preview}")
        body = "\n".join(lines)

        await bot_service.client.send_message(
            receive_id=chat_id,
            receive_id_type="chat_id",
            msg_type="text",
            content=body,
        )
        logger.info("[Feishu] Sent memory list to %s (%d items)", chat_id, len(rows))
    except Exception as exc:
        logger.error("[Feishu] Failed to send memory list: %s", exc, exc_info=True)


async def _handle_search_action(
    *,
    bot_service,
    chat_id: str,
) -> None:
    """搜索记忆 —— 提示用户在聊天框输入搜索词。"""
    hint = "🔍 **搜索记忆**\n请在聊天框输入 `搜索 <关键词>` 来搜索记忆。"
    try:
        await bot_service.client.send_message(
            receive_id=chat_id,
            receive_id_type="chat_id",
            msg_type="text",
            content=hint,
        )
    except Exception as exc:
        logger.error("[Feishu] Failed to send search hint: %s", exc, exc_info=True)


def _extract_text(message: dict) -> str:
    """从飞书消息中提取文本"""
    content = message.get("content") or ""

    if isinstance(content, str):
        try:
            data = json.loads(content)
            # 如果是纯对象但没有 text/content/items 字段，返回空字符串
            if isinstance(data, dict) and not any(k in data for k in ("text", "content", "items")):
                return ""
            # 优先返回 text 或 content 字段
            if "text" in data:
                return data["text"]
            if "content" in data:
                return data["content"]
            # 富文本 items 格式 - 提取所有 text 项
            if "items" in data:
                parts = []
                for item in data["items"]:
                    if item.get("tag") == "text":
                        text = item.get("text", "").strip()
                        if text:
                            parts.append(text)
                return " ".join(parts)
            return content
        except Exception:
            return content

    if isinstance(content, dict):
        # 已经是 dict 格式
        if "text" in content:
            return content["text"]
        if "content" in content:
            return content["content"]
        # 富文本 items 格式
        if "items" in content:
            parts = []
            for item in content["items"]:
                if item.get("tag") == "text":
                    text = item.get("text", "").strip()
                    if text:
                        parts.append(text)
            return " ".join(parts)
        return ""

    return ""


def _extract_attachments(message: dict) -> list[AttachmentRef]:
    """从飞书消息中提取附件"""
    attachments: list[AttachmentRef] = []
    content = message.get("content") or "{}"

    if isinstance(content, str):
        try:
            data = json.loads(content)
        except Exception:
            return attachments
    elif isinstance(content, dict):
        data = content
    else:
        return attachments

    # 提取图片
    for item in data.get("items", []):
        if item.get("tag") == "img":
            image_key = item.get("image_key") or item.get("src")
            if image_key:
                attachments.append(AttachmentRef(
                    kind="image",
                    image_key=image_key,
                    name=item.get("alt", "image"),
                ))

    # 提取文件
    for item in data.get("items", []):
        if item.get("tag") == "file":
            file_key = item.get("file_key")
            if file_key:
                attachments.append(AttachmentRef(
                    kind="file",
                    file_key=file_key,
                    name=item.get("name", "file"),
                    size=item.get("size"),
                ))

    return attachments
