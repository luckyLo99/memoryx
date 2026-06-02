#!/usr/bin/env python3
from __future__ import annotations

__test__ = False

import json
import os
import urllib.request
from pathlib import Path


def load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')

        if key and key not in os.environ:
            os.environ[key] = value


load_env_file(Path.home() / "src" / "memoryx" / ".env")
load_env_file(Path.home() / ".hermes" / ".env")

endpoint = os.getenv("MEMORYX_EMBEDDING_ENDPOINT", "https://api.siliconflow.cn/v1/embeddings")
model = os.getenv("MEMORYX_EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-8B")
api_key = os.getenv("SILICONFLOW_API_KEY") or os.getenv("MEMORYX_EMBEDDING_API_KEY")

if not api_key:
    print("FAIL: SILICONFLOW_API_KEY or MEMORYX_EMBEDDING_API_KEY is missing")
    raise SystemExit(1)

payload = {
    "model": model,
    "input": "MemoryX SiliconFlow embedding connectivity test.",
}

data = json.dumps(payload).encode("utf-8")

request = urllib.request.Request(
    endpoint,
    data=data,
    headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    },
    method="POST",
)

with urllib.request.urlopen(request, timeout=30) as response:
    body = response.read().decode("utf-8")

result = json.loads(body)
dimension = len(result["data"][0]["embedding"])

print(f"Embedding model: {result.get('model', model)}")
print(f"Embedding dimension: {dimension}")
print("OK: SiliconFlow embedding API works")
