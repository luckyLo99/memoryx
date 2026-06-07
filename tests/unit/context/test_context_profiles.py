from memoryx.context_budget import get_context_profile, clamp_profile_to_model_window

def test_profiles_order():
    brief = get_context_profile("brief")
    deep = get_context_profile("deep")
    debug = get_context_profile("debug")
    assert brief.max_context_tokens < deep.max_context_tokens < debug.max_context_tokens

def test_profile_clamps_to_small_model():
    profile = get_context_profile("debug")
    clamped = clamp_profile_to_model_window(profile, 32000)
    assert clamped.max_context_tokens <= int(32000 * 0.08)
