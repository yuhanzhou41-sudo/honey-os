from pathlib import Path


def _source():
    root = Path(__file__).resolve().parents[3]
    return (root / "honeyos/agent/turn_context.py").read_text(encoding="utf-8")


def test_probe_markers_present():
    src = _source()
    assert "MEMORY_PREFETCH_PROBE start" in src
    assert "MEMORY_PREFETCH_PROBE done" in src


def test_prefetch_call_preserved():
    src = _source()
    assert 'ext_prefetch_cache = agent._memory_manager.prefetch_all(_query) or ""' in src


def test_probe_does_not_log_raw_query():
    src = _source()

    # The probe must still pass _query to prefetch_all(); that is normal.
    # We only forbid logging the raw query value itself.
    assert 'prefetch_all(_query)' in src

    assert 'query=%s", _query' not in src
    assert 'query=%r", _query' not in src
    assert 'message=%s", _query' not in src
    assert 'text=%s", _query' not in src

    # Logging only the Python type name is safe and expected.
    assert 'query_type=%s", type(_query).__name__' in src
