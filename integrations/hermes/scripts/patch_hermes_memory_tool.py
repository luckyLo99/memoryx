from __future__ import annotations
import hashlib
import sys
from pathlib import Path

_HERMES_MEMORY_TOOL = Path.home() / ".hermes" / "hermes-agent" / "tools" / "memory_tool.py"
_BACKUP_SUFFIX = ".hermes_memory_tool.bak"
_CHECKSUM_FILE = _HERMES_MEMORY_TOOL.with_name(".memoryx_patch_checksum.txt")

_PATCH_MARKERS = [
    "# --- Registry ---",
    "def memory_tool(",
    "handler=lambda args",
    "from tools.registry",
]


def _bridge_code() -> str:
    return '''
# --- MemoryX authoritative bridge: begin ---
def memoryx_authoritative_memory_tool(
    action: str,
    target: str = "memory",
    content: str = None,
    old_text: str = None,
    store=None,
) -> str:
    enabled = os.environ.get("MEMORYX_AUTHORITATIVE", "1").strip().lower()
    if enabled in {"1", "true", "yes", "on"}:
        try:
            from plugins.memory.memoryx import memoryx_tool_handler
            return memoryx_tool_handler({
                "action": action,
                "target": target,
                "content": content,
                "old_text": old_text,
            })
        except Exception as exc:
            return tool_error(f"MemoryX authoritative backend failed: {exc}", success=False)
    return memory_tool(
        action=action,
        target=target,
        content=content,
        old_text=old_text,
        store=store,
    )
# --- MemoryX authoritative bridge: end ---
'''


def _sha256(path_arg):
    return hashlib.sha256(path_arg.read_bytes()).hexdigest()


def _has_bridge(text):
    return "MemoryX authoritative bridge: begin" in text


def _find_marker(text):
    for marker in _PATCH_MARKERS:
        if marker in text:
            return marker
    return None


def do_patch():
    if not _HERMES_MEMORY_TOOL.exists():
        print(f"ERROR: not found: {_HERMES_MEMORY_TOOL}")
        sys.exit(1)
    text = _HERMES_MEMORY_TOOL.read_text(encoding="utf-8")
    if _has_bridge(text):
        print("INFO: patch already applied (bridge marker found)")
        return
    marker = _find_marker(text)
    if marker is None:
        print("ERROR: cannot find any known marker")
        print(f"  Tried: {_PATCH_MARKERS}")
        sys.exit(1)
    backup = _HERMES_MEMORY_TOOL.with_name(_BACKUP_SUFFIX)
    if not backup.exists():
        backup.write_bytes(_HERMES_MEMORY_TOOL.read_bytes())
        print(f"BACKUP: saved to {backup}")
    before_hash = _sha256(_HERMES_MEMORY_TOOL)
    text2 = text.replace(marker, _bridge_code() + marker, 1)
    old_handler = "handler=lambda args, **kw: memory_tool("
    new_handler = "handler=lambda args, **kw: memoryx_authoritative_memory_tool("
    if old_handler in text2:
        text2 = text2.replace(old_handler, new_handler, 1)
    elif new_handler in text2:
        pass
    else:
        print("ERROR: cannot find memory tool registry handler")
        sys.exit(1)
    _HERMES_MEMORY_TOOL.write_text(text2, encoding="utf-8")
    after_hash = _sha256(_HERMES_MEMORY_TOOL)
    _CHECKSUM_FILE.write_text(f"before={before_hash}\nafter={after_hash}\nmarker={marker}\n")
    print("PATCH_OK: memory() routed to MemoryX (MEMORYX_AUTHORITATIVE=1)")
    print(f"  SHA256 before: {before_hash[:16]}...")
    print(f"  SHA256 after:  {after_hash[:16]}...")


def do_check():
    if not _HERMES_MEMORY_TOOL.exists():
        print(f"CHECK_FAIL: not found: {_HERMES_MEMORY_TOOL}")
        sys.exit(1)
    text = _HERMES_MEMORY_TOOL.read_text(encoding="utf-8")
    current_hash = _sha256(_HERMES_MEMORY_TOOL)
    if not _has_bridge(text):
        print("CHECK_FAIL: MemoryX bridge not found")
        sys.exit(1)
    if _CHECKSUM_FILE.exists():
        stored = {}
        for line in _CHECKSUM_FILE.read_text().strip().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                stored[k] = v
        expected = stored.get("after")
        if expected and current_hash != expected:
            print("CHECK_WARN: file checksum mismatch")
        else:
            print(f"CHECK_OK: file integrity verified (SHA256: {current_hash[:16]}...)")
    else:
        print(f"CHECK_OK: bridge found (SHA256: {current_hash[:16]}...)")
    if "memoryx_authoritative_memory_tool" in text:
        print("CHECK_OK: handler routes to MemoryX")
    else:
        print("CHECK_FAIL: handler does not route to MemoryX")


def do_rollback():
    backup = _HERMES_MEMORY_TOOL.with_name(_BACKUP_SUFFIX)
    if not backup.exists():
        print(f"ROLLBACK_FAIL: no backup found: {backup}")
        sys.exit(1)
    _HERMES_MEMORY_TOOL.write_bytes(backup.read_bytes())
    backup.unlink()
    if _CHECKSUM_FILE.exists():
        _CHECKSUM_FILE.unlink()
    print("ROLLBACK_OK: original restored")


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "--check":
        do_check()
    elif arg == "--rollback":
        do_rollback()
    else:
        do_patch()