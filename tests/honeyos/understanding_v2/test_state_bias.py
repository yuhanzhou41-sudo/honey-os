from honeyos.understanding.u2_runtime import normalize_state_bias


def test_state_bias_is_neutral_when_missing_and_clamped_when_present():
    assert normalize_state_bias(None) == (0.0, False)
    assert normalize_state_bias("0.1") == (0.0, False)
    assert normalize_state_bias(.7) == (.15, True)
    assert normalize_state_bias(-.7) == (-.15, True)
