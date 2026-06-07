from pathlib import Path
import json

from memoryx.runtime_context.hermes_policy import HermesContextPolicy, write_policy_files

def test_hermes_context_policy_defaults():
    p = HermesContextPolicy()
    assert p.disable_session_search is True
    assert p.disable_auto_recall is True
    assert p.disable_raw_terminal_injection is True
    assert p.max_active_context_tokens == 64000

def test_write_policy_files(tmp_path):
    files = write_policy_files(str(tmp_path))
    assert Path(files["json"]).exists()
    assert Path(files["markdown"]).exists()
    data = json.loads(Path(files["json"]).read_text(encoding="utf-8"))
    assert data["disable_session_search"] is True
    text = Path(files["markdown"]).read_text(encoding="utf-8")
    assert "Do not call session_search" in text
