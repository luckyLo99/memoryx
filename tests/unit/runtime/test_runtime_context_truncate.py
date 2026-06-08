from memoryx.runtime_context import summarize_terminal_output, truncate_middle

def test_truncate_middle():
    text = "A" * 10000
    out = truncate_middle(text, 1000)
    assert out.truncated
    assert out.returned_chars <= 1100

def test_summarize_terminal_output_truncates():
    stdout = "\n".join("x" * 200 for _ in range(1000))
    out = summarize_terminal_output(stdout, "", max_stdout_chars=1000, max_lines=20)
    assert out["stdout_truncated"]
    assert len(out["stdout"]) <= 1200
