import json
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Thread

import pytest

from honeyos.routing import selective_loading as routing

TOOLS = ("companion_profile", "file", "web", "terminal", "memory", "cronjob")
SAFE = ("companion_profile", "file", "memory", "web")
AMBIGUOUS = "请帮我理清这两件事情之间的联系"


@pytest.fixture
def classifier_endpoint():
    requests = []
    outputs = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            requests.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps({"choices": [{"message": {"content": outputs.pop(0)}}]}).encode())

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        worker = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        worker.start()
        config = {"model_profiles": {"test": {
            "base_url": f"http://127.0.0.1:{server.server_port}/v1",
            "api_mode": "chat_completions",
            "model": "qwen-test",
        }}}
        try:
            yield config, requests, outputs
        finally:
            server.shutdown()
            worker.join()


def test_rules_and_structured_content_do_not_call_qwen(classifier_endpoint):
    config, requests, _ = classifier_endpoint
    assert routing.resolve_turn_toolsets("你好", TOOLS, config) == ("companion_profile",)
    assert routing.resolve_turn_toolsets("提醒我明天上午九点喝水", TOOLS, config) == (
        "companion_profile", "cronjob",
    )
    assert routing.resolve_turn_toolsets([{"text": "secret attachment"}], TOOLS, config) == SAFE
    assert not requests


def test_ambiguous_turn_sends_one_compact_request_and_intersects_config(classifier_endpoint):
    config, requests, outputs = classifier_endpoint
    outputs.append(json.dumps({
        "intent": "research", "skill_groups": ["research", "media"], "capabilities": ["web"],
        "confidence": 0.9,
    }))
    assert routing.resolve_turn_toolsets(AMBIGUOUS, TOOLS, config) == ("companion_profile", "web")
    assert len(requests) == 1
    assert requests[0]["model"] == "qwen-test"
    messages = requests[0]["messages"]
    assert [message["role"] for message in messages] == ["system", "user"]
    assert len(messages[0]["content"]) < 700
    assert messages[1]["content"] == AMBIGUOUS


@pytest.mark.parametrize("output", [
    "{}",
    "not json",
    json.dumps({"intent": "research", "skill_groups": ["research"], "capabilities": [], "confidence": 0.4}),
])
def test_bad_and_low_confidence_responses_fall_back(classifier_endpoint, output):
    config, _, outputs = classifier_endpoint
    outputs.append(output)
    assert routing.resolve_turn_toolsets(AMBIGUOUS, TOOLS, config) == SAFE


def test_deadline_and_busy_worker_do_not_queue(monkeypatch):
    entered = Event()
    release = Event()
    calls = []

    def slow(text, config):
        calls.append(text)
        entered.set()
        release.wait(2)
        raise OSError("simulated blocked HTTP")

    monkeypatch.setattr(routing, "_CLASSIFY_BUDGET_SECONDS", 0.1)
    monkeypatch.setattr(routing, "_classify", slow)
    try:
        assert routing.resolve_turn_toolsets(AMBIGUOUS, TOOLS, {}) == SAFE
        assert entered.is_set()
        assert routing.resolve_turn_toolsets(AMBIGUOUS, TOOLS, {}) == SAFE
        assert calls == [AMBIGUOUS]
    finally:
        release.set()
        assert routing._classifier_slot.acquire(timeout=2)
        routing._classifier_slot.release()


def test_offline_local_endpoint_uses_safe_fallback():
    with socket.socket() as reserved:
        reserved.bind(("127.0.0.1", 0))
        config = {"model_profiles": {"test": {
            "base_url": f"http://127.0.0.1:{reserved.getsockname()[1]}/v1",
            "api_mode": "chat_completions",
            "model": "qwen-offline",
        }}}
        assert routing.resolve_turn_toolsets(AMBIGUOUS, TOOLS, config) == SAFE
