"""Generate embeddings for all memories without embedding and migrate to LanceDB."""

import asyncio, os, sys
from pathlib import Path

# Load .env
for line in open('/home/lucky/memoryx/.env'):
    line = line.strip()
    if line and not line.startswith('#') and '=' in line:
        k, v = line.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip())

sys.path.insert(0, '/home/lucky/memoryx')
from memoryx.storage import MemoryRepository
from memoryx.embeddings import LanceDBVectorStore
import aiohttp

API_KEY = os.getenv('SILICONFLOW_API_KEY')
BATCH = 3


async def embed_one(s, text):
    for rtry in range(5):
        try:
            async with s.post('https://api.siliconflow.cn/v1/embeddings',
                json={'model': 'Qwen/Qwen3-Embedding-8B', 'input': text,
                      'encoding_format': 'float', 'dimensions': 4096},
                headers={'Authorization': f'Bearer {API_KEY}', 'Content-Type': 'application/json'}) as r:
                if r.status == 200:
                    d = await r.json()
                    return d['data'][0]['embedding']
                elif r.status == 429:
                    await asyncio.sleep(10)
                else:
                    await asyncio.sleep(5)
        except Exception:
            await asyncio.sleep(5)
    return None


async def main():
    repo = MemoryRepository(Path('/home/lucky/memoryx/data/memoryx.db'))
    await repo.open()
    mems = await repo.list_memories(limit=10000)
    need = [m for m in mems if not m.get('embedding')]
    print(f'Total:{len(mems)} Need:{len(need)}')
    if not need:
        print('All done!')
        return

    texts = [m.get('content', '') for m in need]
    embs = [None] * len(texts)
    async with aiohttp.ClientSession() as s:
        for i in range(0, len(texts), BATCH):
            batch = texts[i:i + BATCH]
            tasks = [embed_one(s, t) for t in batch]
            results = await asyncio.gather(*tasks)
            for j, res in enumerate(results):
                embs[i + j] = res
            done = sum(1 for e in embs[:i + BATCH] if e is not None)
            print(f'P{i // BATCH}: {min(i + BATCH, len(texts))}/{len(texts)} ({done} ok)')

    valid = [(m, emb) for m, emb in zip(need, embs) if emb is not None]
    print(f'Embeddings done: {len(valid)}/{len(need)}')

    if valid:
        lance = LanceDBVectorStore(uri=Path('/home/lucky/memoryx/data/lancedb'))
        await lance.open()
        batch_data = []
        for m, emb in valid:
            batch_data.append((m['id'], emb, {'content': m.get('content', ''), 'memory_type': m.get('memory_type', '')}))
            if len(batch_data) >= 50:
                await lance.batch_upsert(batch_data)
                print(f'LanceDB: {len(batch_data)}')
                batch_data.clear()
        if batch_data:
            await lance.batch_upsert(batch_data)
            print(f'LanceDB: {len(batch_data)}')

    await repo.close()
# 验证 LanceDB 可检索
    lance2 = LanceDBVectorStore(uri=Path('/home/lucky/memoryx/data/lancedb'))
    await lance2.open()
    import numpy as np
    test_vec = np.random.randn(4096).astype(np.float32).tolist()
    r = await lance2.search(test_vec, limit=5)
    results = await lance2.search(test_vec, limit=500)
    print(f'Verify: LanceDB has {len(results)} vectors, search OK')
    print(f'DONE! {len(valid)} memories migrated to LanceDB')


if __name__ == '__main__':
    asyncio.run(main())