#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path

home = Path.home()
memoryx_home = Path(os.environ.get("MEMORYX_HOME", home / ".hermes" / "memoryx"))
memoryx_db = memoryx_home / "memoryx.db"
memory_file = home / ".hermes" / "memories" / "MEMORY.md"
user_file = home / ".hermes" / "memories" / "USER.md"

os.environ.setdefault("MEMORYX_AUTHORITATIVE", "1")
os.environ.setdefault("MEMORYX_HOME", str(memoryx_home))

from plugins.memory.memoryx import MemoryXProvider
from tools.memory_tool import memoryx_authoritative_memory_tool

provider = MemoryXProvider()
assert provider.name == "memoryx"
assert provider.is_available() is True
provider.initialize("verify-hermes-memoryx")

content = f"MemoryX GitHub verification test {int(time.time())}"

result = memoryx_authoritative_memory_tool(
    action="add",
    target="memory",
    content=content,
    old_text=None,
    store=None,
)

print(result)

data = json.loads(result)
assert data.get("success") is True
assert data.get("provider") == "memoryx"

memory_file.parent.mkdir(parents=True, exist_ok=True)
memory_file.touch()
user_file.touch()

memory_text = memory_file.read_text(encoding="utf-8", errors="ignore")
user_text = user_file.read_text(encoding="utf-8", errors="ignore")

assert content not in memory_text
assert content not in user_text

conn = sqlite3.connect(memoryx_db)
try:
    count = conn.execute(
        "SELECT COUNT(*) FROM memories WHERE content LIKE ?;",
        (f"%{content}%",),
    ).fetchone()[0]
finally:
    conn.close()

assert count >= 1

print("PASS: MemoryXProvider available")
print("PASS: memory() returned provider=memoryx")
print("PASS: memory() did not write MEMORY.md or USER.md")
print("PASS: memory() wrote to MemoryX database")
