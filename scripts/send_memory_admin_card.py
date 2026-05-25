"""发送 MemoryX 记忆管理卡片到飞书 home channel。"""

import asyncio
import json
import os
import sys
from pathlib import Path

# 加载 .env
for line in open('/home/lucky/memoryx/.env'):
    line = line.strip()
    if line and not line.startswith('#') and '=' in line:
        k, v = line.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip())

sys.path.insert(0, '/home/lucky/memoryx')

from memoryx.storage import MemoryRepository
from memoryx.embeddings import LanceDBVectorStore
from memoryx.feishu.memory_admin_card import build_card, collect_memory_stats, collect_recent_memories, collect_lancedb_stats
from memoryx.feishu.client import FeishuClient


async def main():
    # 收集数据
    repo = MemoryRepository(Path('/home/lucky/memoryx/data/memoryx.db'))
    await repo.open()
    lance = LanceDBVectorStore(uri=Path('/home/lucky/memoryx/data/lancedb'))
    await lance.open()

    stats = await collect_memory_stats(repo)
    recent = await collect_recent_memories(repo, limit=5)
    lancedb_stats = await collect_lancedb_stats(lance)

    card = build_card(stats, recent, lancedb_stats)
    print(json.dumps(card, indent=2, ensure_ascii=False)[:200])

    # 发送到飞书
    client = FeishuClient()
    resp = await client.send_message(
        receive_id="oc_61a38f265bb24b9df24b2d6791e72fe6",
        receive_id_type="chat_id",
        msg_type="interactive",
        content=card,
    )
    msg_id = resp.get("data", {}).get("message_id", "unknown")
    print(f"\n✅ 卡片已发送！message_id={msg_id}")

    await repo.close()


if __name__ == "__main__":
    asyncio.run(main())