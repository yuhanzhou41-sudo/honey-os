from pathlib import Path


def _source():
    root = Path(__file__).resolve().parents[3]
    return (root / "honeyos/gateway/platforms/api_server.py").read_text(
        encoding="utf-8"
    )


def _shadow_block(src: str) -> str:
    return src.split("# TURN_ROUTER_SHADOW_V1", 1)[1].split(
        "max_iterations =", 1
    )[0]


def test_real_toolsets_remain_config_driven():
    src = _source()
    assert 'enabled_toolsets = sorted(_get_platform_tools(user_config, "api_server"))' in src
    assert '"enabled_toolsets": enabled_toolsets' in src


def test_shadow_reads_explicit_optional_parameter():
    src = _source()
    assert "shadow_user_message: Any = None" in src
    assert '_shadow_message = str(shadow_user_message or "")' in src


def test_exactly_two_api_entry_closures_pass_user_message():
    src = _source()
    assert src.count("shadow_user_message=user_message") == 2


def test_stale_direct_user_message_reference_removed():
    assert '_shadow_message = str(user_message or "")' not in _source()


def test_shadow_never_reassigns_real_toolsets():
    assert "enabled_toolsets =" not in _shadow_block(_source())


def test_shadow_failure_is_nonfatal_to_existing_runtime():
    assert (
        '"TURN_ROUTER_SHADOW failed; configured toolsets unchanged"'
        in _source()
    )


def test_raw_message_not_logged():
    block = _shadow_block(_source())
    log = block.split("logger.info(", 1)[1]
    assert "_shadow_message" not in log
    assert "shadow_user_message" not in log
