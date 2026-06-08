from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True)
class TruncatedText:
    text: str
    original_chars: int
    returned_chars: int
    truncated: bool
    omitted_chars: int

def truncate_middle(text: str, max_chars: int, marker: str = "\n...[truncated]...\n") -> TruncatedText:
    text = text or ""
    original = len(text)
    if max_chars <= 0:
        return TruncatedText(text="", original_chars=original, returned_chars=0, truncated=original > 0, omitted_chars=original)
    if original <= max_chars:
        return TruncatedText(text=text, original_chars=original, returned_chars=original, truncated=False, omitted_chars=0)
    marker_len = len(marker)
    side = max(0, int((max_chars - marker_len) / 2))
    out = text[:side] + marker + text[-side:] if side > 0 else text[:max_chars]
    return TruncatedText(text=out, original_chars=original, returned_chars=len(out), truncated=True, omitted_chars=original - len(out))

def keep_head_tail_lines(text: str, max_lines: int) -> str:
    lines = (text or "").splitlines()
    if max_lines <= 0:
        return ""
    if len(lines) <= max_lines:
        return "\n".join(lines)
    head_count = max(1, max_lines // 2)
    tail_count = max(1, max_lines - head_count)
    omitted = len(lines) - head_count - tail_count
    return "\n".join(lines[:head_count] + [f"...[truncated {omitted} lines]..."] + lines[-tail_count:])

def summarize_terminal_output(stdout: str, stderr: str = "", *, max_stdout_chars: int = 8000, max_stderr_chars: int = 4000, max_lines: int = 120) -> dict:
    stdout_lines = keep_head_tail_lines(stdout or "", max_lines=max_lines)
    stderr_lines = keep_head_tail_lines(stderr or "", max_lines=max_lines)
    out = truncate_middle(stdout_lines, max_stdout_chars)
    err = truncate_middle(stderr_lines, max_stderr_chars)
    return {"stdout": out.text, "stderr": err.text, "stdout_original_chars": out.original_chars, "stderr_original_chars": err.original_chars, "stdout_truncated": out.truncated, "stderr_truncated": err.truncated, "stdout_omitted_chars": out.omitted_chars, "stderr_omitted_chars": err.omitted_chars}
