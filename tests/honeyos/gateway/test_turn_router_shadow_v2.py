from pathlib import Path


def _root():
    return Path(__file__).resolve().parents[3]


def _api_source():
    return (_root() / "honeyos/gateway/platforms/api_server.py").read_text(
        encoding="utf-8"
    )


def _shadow_source():
    return (_root() / "honeyos/routing/shadow.py").read_text(
        encoding="utf-8"
    )


def test_shadow_v2_marker_present():
    src = _api_source()
    assert "TURN_ROUTER_SHADOW_V2" in src
    assert "TURN_ROUTER_SHADOW_V1" not in src


def test_real_toolsets_remain_config_driven():
    src = _api_source()
    assert 'enabled_toolsets = sorted(_get_platform_tools(user_config, "api_server"))' in src
    assert '"enabled_toolsets": enabled_toolsets' in src


def test_shadow_uses_explicit_message_parameter():
    src = _api_source()
    assert "shadow_user_message: Any = None" in src
    assert src.count("shadow_user_message=user_message") == 2


def test_ambiguous_local_qwen_is_daemon_thread():
    src = _shadow_source()
    assert "threading.Thread(" in src
    assert "target=_run_local_shadow" in src
    assert "daemon=True" in src


def test_rules_are_checked_before_local_qwen():
    src = _shadow_source()

    route_fn = src.split(
        "def route_shadow_nonblocking", 1
    )[1]

    assert "decision = route_by_rules(text)" in route_fn
    assert "if decision is not None:" in route_fn
    assert "threading.Thread(" in route_fn
    assert "target=_run_local_shadow" in route_fn

    assert (
        route_fn.index("decision = route_by_rules(text)")
        < route_fn.index("threading.Thread(")
    )


def test_shadow_success_log_is_visible_warning():
    src = _shadow_source()
    assert "logger.warning(" in src
    assert "TURN_ROUTER_SHADOW phase=%s" in src


def test_raw_user_message_is_not_logged():
    src = _shadow_source()
    assert "message=%s" not in src
    assert "text=%s" not in src


def test_shadow_block_does_not_mutate_enabled_toolsets():
    src = _api_source()
    block = src.split("# TURN_ROUTER_SHADOW_V2", 1)[1].split(
        "max_iterations = _current_max_iterations()", 1
    )[0]
    assert "enabled_toolsets =" not in block
