"""P0: 为现有记忆生成 embedding 并迁移到 LanceDB。"""

import asyncio
import os
import sys
import hashlib
import json
from pathlib import Path

# 先加载 .env
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip())

sys.path.insert(0, '/home/lucky/memoryx')

from memoryx.storage import MemoryRepository
from memoryx.embeddings import LanceDBVectorStore
import aiohttp

# ── 配置 ──────────────────────────────────────────────────────────
MEMORYX_DB = Path("/home/lucky/memoryx/data/memoryx.db")
LANCEDB_URI = Path("/home/lucky/memoryx/data/lancedb")
EMBEDDING_ENDPOINT = "https://api.siliconflow.cn/v1/embeddings"
EMBEDDING_API_KEY = os.getenv("SILICONFLOW_API_KEY") or os.getenv("MEMORYX_EMBEDDING_API_KEY")
EMBEDDING_MODEL = "Qwen/Qwen3-Embedding-8B"
EMBEDDING_DIM = 4096

# ── 批量 embedding ────────────────────────────────────────────────
async def get_embedding(session: aiohttp.ClientSession, text: str) -> list[float]:
    """调用 SiliconFlow 获取 embedding。"""
    payload = {
        "model": EMBEDDING_MODEL,
        "input": text,
        "encoding_format": "float",
        "dimensions": EMBEDDING_DIM,
    }
    async with session.post(EMBEDDING_ENDPOINT, json=payload, headers={
        "Authorization": f"Bearer {EMBEDDING_API_KEY}",
        "Content-Type": "application/json",
    }) as resp:
        data = await resp.json()
        if resp.status != 200:
            raise RuntimeError(f"Embedding API error: {resp.status} {data}")
        return data["data"][0]["embedding"]


async def batch_embed_texts(
    session: aiohttp.ClientSession, texts: list[str], batch_size: int = 2
) -> list[list[float]]:
    """批量并发获取 embedding，带限流和重试。"""
    results = [None] * len(texts)
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        indices = list(range(i, i + len(batch)))
        
        async def retry_embedding(text: str, max_retries: int = 3) -> list[float]:
            for attempt in range(max_retries):
                try:
                    payload = {
                        "model": EMBEDDING_MODEL,
                        "input": text,
                        "encoding_format": "float",
                        "dimensions": EMBEDDING_DIM,
                    }
                    async with session.post(EMBEDDING_ENDPOINT, json=payload, headers={
                        "Authorization": f"Bearer {EMBEDDING_API_KEY}",
                        "Content-Type": "application/json",
                    }) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            return data["data"][0]["embedding"]
                        elif resp.status == 429:
                            wait = (2 ** attempt) * 2
                            print(f"    限流，等待 {wait}s... (attempt {attempt+1})")
                            await asyncio.sleep(wait)
                            continue
                        else:
                            body = await resp.text()
                            raise RuntimeError(f"Embedding API error: {resp.status} {body[:200]}")
                except Exception as e:
                    if attempt < max_retries - 1:
                        wait = (2 ** attempt) * 2
                        print(f"    重试 {attempt+1}/{max_retries}: {e}")
                        await asyncio.sleep(wait)
                    else:
                        raise
            raise RuntimeError("Max retries exceeded")

        tasks = [retry_embedding(t) for t in batch]
        embeddings = await asyncio.gather(*tasks)
        for idx, emb in zip(indices, embeddings):
            results[idx] = emb
        print(f"  进度: {min(i + batch_size, len(texts))}/{len(texts)}")
    return results


# ── 迁移主流程 ────────────────────────────────────────────────────
async def migrate():
    print("=== P0: 迁移现有记忆到 LanceDB ===\n")
    
    # 1. 读取所有记忆
    repo = MemoryRepository(MEMORYX_DB)
    await repo.open()
    memories = await repo.list_memories(limit=10000)
    print(f"总记忆数: {len(memories)}")
    
    # 2. 筛选需要生成 embedding 的记忆
    need_embed = []
    for m in memories:
        if not m.get("embedding"):
            need_embed.append(m)
    print(f"需要生成 embedding 的记忆: {len(need_embed)}")
    
    if not need_embed:
        print("所有记忆已有 embedding，跳过迁移。")
        await repo.close()
        return
    
    # 3. 批量生成 embedding
    print("\n生成 embedding...")
    texts = []
    for m in need_embed:
        # 优先用 content，其次用 summary
        text = m.get("content") or m.get("summary", "")
        texts.append(text)
    
    async with aiohttp.ClientSession() as session:
        embeddings = await batch_embed_texts(session, texts, batch_size=3)
    
    # 4. 写入 LanceDB
    print(f"\n初始化 LanceDB...")
    lance = LanceDBVectorStore(uri=LANCEDB_URI)
    await lance.open()
    
    # 5. 批量 upsert
    print("写入 LanceDB...")
    upsert_batch = []
    for m, emb in zip(need_embed, embeddings):
        upsert_batch.append({
            "id": m["id"],
            "vector": emb,
            "content": m.get("content", ""),
            "summary": m.get("summary", ""),
            "memory_type": m.get("memory_type", ""),
            "tags": json.dumps(m.get("tags", [])),
        })
        # 每 50 条 flush 一次
        if len(upsert_batch) >= 50:
            await lance.batch_upsert(upsert_batch)
            print(f"  已写入 {len(upsert_batch)} 条...")
            upsert_batch = []
    
    if upsert_batch:
        await lance.batch_upsert(upsert_batch)
        print(f"  已写入 {len(upsert_batch)} 条...")
    
    # 6. 更新 MemoryRepository 中的 embedding 字段
    print("\n回写 embedding 到 MemoryRepository...")
    for m, emb in zip(need_embed, embeddings):
        m["embedding"] = emb
        await repo.update_memory(m["id"], m)
    
    await repo.close()
    
    print(f"\n✅ 迁移完成！共 {len(need_embed)} 条记忆已生成 embedding 并写入 LanceDB")


if __name__ == "__main__":
    asyncio.run(migrate())
