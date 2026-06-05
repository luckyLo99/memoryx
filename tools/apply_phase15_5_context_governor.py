from pathlib import Path
import textwrap

ROOT = Path.cwd()

def write(path: str, content: str):
    p = ROOT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")
    print(f"[WRITE] {path}")

def append_once(path: str, marker: str, content: str):
    p = ROOT / path
    old = p.read_text(encoding="utf-8") if p.exists() else ""
    if marker in old:
        print(f"[SKIP] {path} already contains {marker}")
        return
    p.write_text(old.rstrip() + "\n\n" + textwrap.dedent(content).lstrip(), encoding="utf-8")
    print(f"[APPEND] {path}")
