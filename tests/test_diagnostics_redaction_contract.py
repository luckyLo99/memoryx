import json

from memoryx.diagnostics.redactor import hash_text, redact_mapping, redact_text


def test_redact_openai_api_key_assignment():
    key_name = "OPENAI" + "_API_KEY"
    text = f"{key_name}=fake-test-value"
    redacted = redact_text(text)
    assert "fake-test-value" not in redacted
    assert f"{key_name}=[REDACTED]" in redacted


def test_redact_siliconflow_api_key_assignment():
    key_name = "SILICONFLOW" + "_API_KEY"
    text = f"{key_name}=fake-test-value"
    redacted = redact_text(text)
    assert "fake-test-value" not in redacted
    assert f"{key_name}=[REDACTED]" in redacted


def test_redact_sensitive_keys_in_text():
    text = (
        "api_key=abc token: def password=ghi secret=jkl "
        "authorization: Bearer mno cookie=sessionid"
    )
    redacted = redact_text(text)
    for raw in ["abc", "def", "ghi", "jkl", "mno", "sessionid"]:
        assert raw not in redacted
    assert redacted.count("[REDACTED]") >= 6


def test_redact_memoryx_home_path():
    text = "db=/home/lucky/.memoryx/data/memoryx.db"
    redacted = redact_text(text)
    assert "/home/lucky/.memoryx" not in redacted
    assert "$MEMORYX_HOME/[REDACTED_PATH]" in redacted


def test_redact_mapping_recursively_redacts_dicts_and_lists():
    value = {
        "api_key": "abc123",
        "nested": [
            {"token": "tok123"},
            "path=/home/lucky/.memoryx/data/memoryx.db",
        ],
        "safe": "ok",
    }
    redacted = redact_mapping(value)
    dumped = json.dumps(redacted, ensure_ascii=False)
    assert "abc123" not in dumped
    assert "tok123" not in dumped
    assert "/home/lucky/.memoryx" not in dumped
    assert redacted["safe"] == "ok"


def test_hash_text_is_stable_short_and_not_plaintext():
    first = hash_text("session-123")
    second = hash_text("session-123")
    assert first == second
    assert first != "session-123"
    assert len(first) == 16
