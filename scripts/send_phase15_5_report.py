"""发送 Phase 15.5 执行完成报告到飞书家庭频道。"""
import asyncio
import os
import sys
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent

# 加载 .env
for line in open(REPO_DIR / '.env'):
    line = line.strip()
    if line and not line.startswith('#') and '=' in line:
        k, v = line.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip())

sys.path.insert(0, str(REPO_DIR))

from memoryx.feishu.client import FeishuClient

MESSAGE_TEXT = """🚨 Phase 15.5 — P0 Context Governor + Stale Request Guard 执行报告

1. 文件变更（12 个新增文件）
- memoryx/context_budget/ (6个模块): tokens.py, policy.py, packer.py, run_guard.py, assembler.py, __init__.py
- 测试: tests/test_context_budget_tokens.py, tests/test_context_budget_packer.py, tests/test_budgeted_context_assembler.py, tests/test_run_guard.py
- 验证脚本: scripts/verify_phase15_5_context_governor.py
- 文档: docs/context_governor.md, docs/context_budget_policy.md

2. 验证结果
- verify_phase15_5_context_governor.py: ✅ PASS
- 5/5 专项测试通过: ✅

3. Context Budget 验收
- 120 条长记忆时 used_tokens: 1,552 ✅ (上限 4096)
- included_items: 12 ✅
- dropped_items: 12 ✅

4. Stale Request Guard 验收
- 旧 request 被 supersede: ✅
- 旧 request 返回 stale_result: ✅
- 当前 request 正常通过: ✅

5. 产物
- /home/lucky/phase15_5.patch (445 行)
- 结论: MemoryX 默认 query 从 350k tokens 降到约 1.5K tokens 🚀"""


async def main():
    home_channel = os.getenv("FEISHU_HOME_CHANNEL")
    if not home_channel:
        print("ERROR: FEISHU_HOME_CHANNEL not set in .env")
        sys.exit(1)

    client = FeishuClient()
    resp = await client.send_message(
        receive_id=home_channel,
        receive_id_type="chat_id",
        msg_type="text",
        content={"text": MESSAGE_TEXT},
    )
    msg_id = resp.get("data", {}).get("message_id", "unknown")
    print(f"✅ 消息已发送到家庭频道！message_id={msg_id}")


if __name__ == "__main__":
    asyncio.run(main())