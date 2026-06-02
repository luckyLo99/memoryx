from pathlib import Path

root = Path.home() / ".hermes" / "hermes-agent"
path = root / "tools" / "memory_tool.py"

if not path.exists():
    raise SystemExit(f"ERROR: not found: {path}")

text = path.read_text(encoding="utf-8")

bridge = '''
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

if "MemoryX authoritative bridge: begin" not in text:
    marker = "# --- Registry ---"
    if marker not in text:
        raise SystemExit("ERROR: cannot find '# --- Registry ---' in memory_tool.py")
    text = text.replace(marker, bridge + marker, 1)

old = "handler=lambda args, **kw: memory_tool("
new = "handler=lambda args, **kw: memoryx_authoritative_memory_tool("

if old in text:
    text = text.replace(old, new, 1)
elif new in text:
    pass
else:
    raise SystemExit("ERROR: cannot find memory tool registry handler")

path.write_text(text, encoding="utf-8")
print("PATCH_OK: Hermes memory() now routes to MemoryX when MEMORYX_AUTHORITATIVE=1")
