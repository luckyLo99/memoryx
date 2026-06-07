from memoryx.context_budget import TokenEstimator

def test_token_estimator_truncates():
    e = TokenEstimator()
    text = "x" * 1000
    short = e.truncate_to_tokens(text, 10)
    assert len(short) < len(text)
    assert short.endswith("\u2026")
    
def test_estimate_text():
    e = TokenEstimator()
    est = e.estimate_text("hello")
    assert est.text_chars == 5
    assert est.estimated_tokens >= 1
