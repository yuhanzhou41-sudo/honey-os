from __future__ import annotations

from honeyos.agent.transports.codex_app_server_session import CodexAppServerSession


class FakeCodexClient:
    """Minimal app-server stand-in that records JSON-RPC requests."""

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.calls: list[tuple[str, dict]] = []
        self._notes: list[dict] = []

    # -- lifecycle -----------------------------------------------------
    def initialize(self, **kwargs):
        self.calls.append(("initialize", dict(kwargs)))

    def is_alive(self) -> bool:
        return True

    def close(self) -> None:
        pass

    def stderr_tail(self, limit: int = 20):
        return []

    # -- JSON-RPC ------------------------------------------------------
    def request(self, method: str, params: dict, timeout: float = 10):
        self.calls.append((method, params))
        if method == "thread/start":
            return {"thread": {"id": "thread-1"}}
        if method == "turn/start":
            self._notes.append(
                {
                    "method": "turn/completed",
                    "params": {
                        "threadId": "thread-1",
                        "turn": {"id": "turn-1", "status": "completed"},
                    },
                }
            )
            return {"turn": {"id": "turn-1"}}
        raise AssertionError(f"unexpected method {method}")

    def take_server_request(self, timeout: float = 0):
        return None

    def take_notification(self, timeout: float = 0):
        return self._notes.pop(0) if self._notes else None


def _session(tmp_path):
    return CodexAppServerSession(
        cwd=str(tmp_path),
        client_factory=lambda **kwargs: FakeCodexClient(**kwargs),
    )


def _turn_start_params(session):
    return [params for method, params in session._client.calls if method == "turn/start"][0]


def test_default_turn_start_payload_is_unchanged(tmp_path):
    session = _session(tmp_path)
    result = session.run_turn(user_input="hello")

    assert not result.error
    assert [method for method, _ in session._client.calls] == [
        "initialize",
        "thread/start",
        "turn/start",
    ]
    thread_params = [p for m, p in session._client.calls if m == "thread/start"][0]
    assert thread_params == {"cwd": str(tmp_path)}
    assert _turn_start_params(session) == {
        "threadId": "thread-1",
        "input": [{"type": "text", "text": "hello"}],
    }


def test_optional_context_is_a_separate_bounded_text_item(tmp_path):
    session = _session(tmp_path)
    context = "[Background memory — use silently]\n用户以前喜欢夜跑。"
    session.run_turn(user_input="hello", context_text=context)

    params = _turn_start_params(session)
    assert params["threadId"] == "thread-1"
    assert params["input"] == [
        {"type": "text", "text": context},
        {"type": "text", "text": "hello"},
    ]
    # Thread start must not absorb private context.
    thread_params = [p for m, p in session._client.calls if m == "thread/start"][0]
    assert thread_params == {"cwd": str(tmp_path)}


def test_blank_context_keeps_single_item_request(tmp_path):
    session = _session(tmp_path)
    session.run_turn(user_input="hello", context_text="   ")
    assert _turn_start_params(session)["input"] == [
        {"type": "text", "text": "hello"}
    ]
