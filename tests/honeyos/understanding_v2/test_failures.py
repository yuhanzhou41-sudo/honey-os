import pytest
from honeyos.understanding.u2_runtime import bounded_call


def test_resolver_failure_does_not_become_context():
    def fail():
        raise RuntimeError("bad index")
    with pytest.raises(RuntimeError, match="bad index"):
        bounded_call(fail, timeout_seconds=.2)
