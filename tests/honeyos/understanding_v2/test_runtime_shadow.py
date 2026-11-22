import time
import pytest

from honeyos.understanding.u2_runtime import RuntimeMode, bounded_call, expose


def test_off_shadow_and_active_authorization():
    assert expose(RuntimeMode.OFF, context="secret", candidate_count=2, estimated_tokens=9).candidate_count == 0
    shadow = expose(RuntimeMode.SHADOW, context="secret", candidate_count=2, estimated_tokens=9)
    assert shadow.context == "" and not shadow.injected and shadow.candidate_count == 2
    with pytest.raises(PermissionError):
        expose(RuntimeMode.ACTIVE, context="secret", candidate_count=2, estimated_tokens=9)


def test_total_deadline_is_bounded():
    with pytest.raises(TimeoutError):
        bounded_call(lambda: time.sleep(.15), timeout_seconds=.01)
